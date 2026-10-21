import { useSyncExternalStore } from 'react'

/**
 * Shared match clock for every screen on the page (the 3-up split view runs one timeline).
 * `frame` is fractional so the pitch can interpolate between 10 Hz frames; React components
 * subscribe to the integer frame only, the canvas reads `frame` in its own rAF loop.
 */
export interface Playback {
  readonly nFrames: number
  readonly fps: number
  frame: number
  playing: boolean
  speed: number
  subscribe(fn: () => void): () => void
  seek(frame: number): void
  play(): void
  pause(): void
  toggle(): void
  setSpeed(speed: number): void
}

export function createPlayback(nFrames: number, fps: number): Playback {
  const listeners = new Set<() => void>()
  let raf = 0
  let last = 0
  const emit = () => listeners.forEach((fn) => fn())

  const tick = (now: number) => {
    const dt = Math.min(now - last, 100)
    last = now
    pb.frame = Math.min(pb.frame + (dt / 1000) * fps * pb.speed, nFrames - 1)
    if (pb.frame >= nFrames - 1) pb.playing = false
    emit()
    if (pb.playing) raf = requestAnimationFrame(tick)
  }

  const pb: Playback = {
    nFrames,
    fps,
    frame: 0,
    playing: false,
    speed: 1,
    subscribe(fn) {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    seek(frame) {
      pb.frame = Math.max(0, Math.min(frame, nFrames - 1))
      emit()
    },
    play() {
      if (pb.playing) return
      if (pb.frame >= nFrames - 1) pb.frame = 0
      pb.playing = true
      last = performance.now()
      raf = requestAnimationFrame(tick)
      emit()
    },
    pause() {
      pb.playing = false
      cancelAnimationFrame(raf)
      emit()
    },
    toggle() {
      if (pb.playing) pb.pause()
      else pb.play()
    },
    setSpeed(speed) {
      pb.speed = speed
      emit()
    },
  }
  return pb
}

/** Integer frame: re-renders at most 10x per match second. */
export function useFrame(pb: Playback): number {
  return useSyncExternalStore(pb.subscribe, () => Math.floor(pb.frame))
}

export function usePlaybackState(pb: Playback): { playing: boolean; speed: number } {
  const playing = useSyncExternalStore(pb.subscribe, () => pb.playing)
  const speed = useSyncExternalStore(pb.subscribe, () => pb.speed)
  return { playing, speed }
}
