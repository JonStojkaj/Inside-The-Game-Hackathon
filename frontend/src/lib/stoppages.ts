import type { Playback } from './playback'
import type { MatchEvent } from '../types'

/**
 * GRF has no stoppages: a goal or a shot wide jumps straight to the restart (goal kick, throw-in,
 * kick-off) in one 100 ms frame. So every strike plays in slow motion (~1.2 s of play), so does the
 * last moment before the restart cut that follows a shot, and the second before the kick-off after a
 * goal. The viewer sees the finish before the picture cuts.
 */
const BEFORE = 4 // data frames before the shot
const AFTER = 8 // frames after the shot in slow motion
const CUT_LEAD = 6 // frames before a restart cut in slow motion
const RESTART_WITHIN = 40 // a restart this soon after the shot ends the play
const SLOW = 0.35
const SLOWEST = 0.15 // the last 0.4 s before a cut

interface FrameData {
  ball: number[][]
  mode: string[]
}

/** A slow-motion window [from, to) in data frames; `cut` = the picture jumps at `to`. */
export interface SlowWindow {
  from: number
  to: number
  cut: boolean
}

/** Frames where GRF jumps to a restart: the mode leaves open play or the ball teleports. */
export function restartFrames(f: FrameData): number[] {
  const out: number[] = []
  for (let i = 1; i < f.ball.length; i++) {
    const [x0, y0] = f.ball[i - 1]
    const [x1, y1] = f.ball[i]
    if ((f.mode[i - 1] === 'normal' && f.mode[i] !== 'normal') || Math.hypot(x1 - x0, y1 - y0) > 8) out.push(i)
  }
  return out
}

export function slowWindows(f: FrameData, events: MatchEvent[]): SlowWindow[] {
  const restarts = restartFrames(f)
  const out: SlowWindow[] = []
  for (const e of events) {
    if (e.type === 'shot') {
      // the strike, then (when the ball goes dead) the last moment before the cut
      const r = restarts.find((x) => x > e.frame && x - e.frame <= RESTART_WITHIN)
      if (r != null && r <= e.frame + AFTER) out.push({ from: e.frame - BEFORE, to: r, cut: true })
      else {
        out.push({ from: e.frame - BEFORE, to: e.frame + AFTER, cut: false })
        if (r != null) out.push({ from: Math.max(e.frame + AFTER, r - CUT_LEAD), to: r, cut: true })
      }
    } else if (e.type === 'goal') {
      // the cut to the kick-off: the ball in the net, then the restart
      const r = restarts.find((x) => x >= e.frame - 2 && x - e.frame <= 15)
      if (r != null) out.push({ from: r - CUT_LEAD * 2, to: r, cut: true })
    }
  }
  return out.sort((a, b) => a.from - b.from)
}

/** Slow-motion factor for a frame: 1 normally, slower inside a window, slowest right before a cut. */
export function slowmoAt(windows: SlowWindow[], frame: number): number {
  for (const w of windows) {
    if (frame >= w.from && frame < w.to) return w.cut && w.to - frame <= 4 ? SLOWEST : SLOW
  }
  return 1
}

/** Keeps pb.slowmo in step with the clock; returns the unsubscribe. */
export function driveSlowmo(pb: Playback, windows: SlowWindow[]): () => void {
  return pb.subscribe(() => {
    const s = pb.playing ? slowmoAt(windows, pb.frame) : 1
    if (s !== pb.slowmo) pb.setSlowmo(s)
  })
}
