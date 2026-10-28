import type { Playback } from './playback'

/**
 * GRF has no stoppages: a shot off the post or a goal jumps straight to the restart (goal kick,
 * kick-off) in one 100 ms frame. So the player slows the last moment before such a restart down,
 * the viewer sees the ball reach the line (or the post) before the picture cuts.
 */
const LEAD = 15 // data frames (1.5 s) before the restart that play in slow motion
const SLOW = 0.3
const SLOWEST = 0.15 // the last 0.4 s

interface FrameData {
  ball: number[][]
  mode: string[]
}

/** First frame of every restart that follows play near a goal (goals, shots wide or off the post). */
export function restartFrames(f: FrameData): number[] {
  const out: number[] = []
  for (let i = 1; i < f.ball.length; i++) {
    const [x0, y0] = f.ball[i - 1]
    const [x1, y1] = f.ball[i]
    const modeChange = f.mode[i - 1] === 'normal' && f.mode[i] !== 'normal'
    const jump = Math.hypot(x1 - x0, y1 - y0) > 8
    const nearGoal = (x0 < 17 || x0 > 88) && y0 > 12 && y0 < 56
    if ((modeChange || jump) && nearGoal && (!out.length || i - out[out.length - 1] > 30)) out.push(i)
  }
  return out
}

/** Slow-motion factor for a frame: 1 normally, slower right before a restart. */
export function slowmoAt(restarts: number[], frame: number): number {
  for (const r of restarts) {
    const d = r - frame
    if (d > 0 && d <= LEAD) return d <= 4 ? SLOWEST : SLOW
  }
  return 1
}

/** Keeps pb.slowmo in step with the clock; returns the unsubscribe. */
export function driveSlowmo(pb: Playback, restarts: number[]): () => void {
  return pb.subscribe(() => {
    const s = pb.playing ? slowmoAt(restarts, pb.frame) : 1
    if (s !== pb.slowmo) pb.setSlowmo(s)
  })
}
