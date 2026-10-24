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
  /** Hold the clock without pausing (e.g. while the TV picture buffers), so data and video never drift apart. */
  hold(reason: string, on: boolean): void
  readonly held: boolean
  /**
   * Master clock while playing: the visible TV picture hands in its own position (in data frames), so
   * the picture plays untouched at its native rate and everything else follows it. null = wall clock.
   */
  follow(source: (() => number) | null): void
  /** Bumped on every seek, so a followed source knows to jump too. */
  readonly seeks: number
}

export function createPlayback(nFrames: number, fps: number): Playback {
  const listeners = new Set<() => void>()
  let raf = 0
  let timer = 0
  let last = 0
  const holds = new Set<string>()
  let source: (() => number) | null = null
  let seeks = 0
  const emit = () => listeners.forEach((fn) => fn())

  const tick = (now: number) => {
    // real time up to 0.5 s per tick: a throttled rAF (busy page, hidden pane) must not slow the
    // clock down against the video; longer gaps (background tab) are not caught up
    const dt = Math.min(now - last, 500)
    last = now
    if (source) {
      const f = source()
      if (Number.isFinite(f)) pb.frame = Math.min(Math.max(0, f), nFrames - 1)
    } else if (!holds.size) pb.frame = Math.min(pb.frame + (dt / 1000) * fps * pb.speed, nFrames - 1)
    if (pb.frame >= nFrames - 1) pb.playing = false
    emit()
    cancelAnimationFrame(raf)
    if (pb.playing) raf = requestAnimationFrame(tick)
    else window.clearInterval(timer)
  }
  // fallback when rAF stalls (page not rendered, e.g. a hidden pane or a covered window): the TV
  // picture keeps playing, so the clock must too
  const watchdog = () => {
    if (pb.playing && performance.now() - last > 200) tick(performance.now())
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
      seeks++
      emit()
    },
    play() {
      if (pb.playing) return
      if (pb.frame >= nFrames - 1) pb.frame = 0
      pb.playing = true
      last = performance.now()
      raf = requestAnimationFrame(tick)
      window.clearInterval(timer)
      timer = window.setInterval(watchdog, 100)
      emit()
    },
    pause() {
      pb.playing = false
      cancelAnimationFrame(raf)
      window.clearInterval(timer)
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
    hold(reason, on) {
      if (on) holds.add(reason)
      else holds.delete(reason)
    },
    get held() {
      return holds.size > 0
    },
    follow(fn) {
      source = fn
    },
    get seeks() {
      return seeks
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
