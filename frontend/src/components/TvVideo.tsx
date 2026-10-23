import { useEffect, useRef } from 'react'
import { useMatch } from '../lib/context'

const DEBUG = new URLSearchParams(window.location.search).has('syncdebug')

/**
 * GRF render of the same match, slaved to the frame clock: the data is the master, never the
 * video. The render has exactly one video frame per data frame (10 fps), so a paused player shows
 * video frame N for data frame N (we seek to the middle of the frame to stay clear of rounding at
 * frame boundaries). While playing, small drift is absorbed with the playback rate, large drift
 * (seek, tab in background) with a hard seek.
 */
export function TvVideo({ hidden, onFail }: { hidden: boolean; onFail: () => void }) {
  const { m, pb } = useMatch()
  const ref = useRef<HTMLVideoElement>(null)
  const video = m.bundle.match.video

  useEffect(() => {
    const el = ref.current
    if (!el || !video) return
    const fps = video.fps || m.bundle.match.fps
    const sync = () => {
      if (el.readyState < 1) return // no metadata yet; loadedmetadata calls sync again
      const end = Number.isFinite(el.duration) ? el.duration - 0.5 / fps : Infinity
      const playing = pb.playing && pb.frame / fps < end
      const target = Math.min(end, playing ? pb.frame / fps : (Math.floor(pb.frame) + 0.5) / fps)
      const drift = target - el.currentTime
      if (!playing) {
        if (!el.paused) el.pause()
        if (Math.abs(drift) > 0.45 / fps) el.currentTime = target
        return
      }
      const rate = Math.min(Math.max(pb.speed, 0.0625), 16)
      if (Math.abs(drift) > 0.25 * Math.max(1, rate)) {
        el.currentTime = target
        el.playbackRate = rate
      } else {
        el.playbackRate = rate * (1 + Math.max(-0.1, Math.min(0.1, drift * 0.8)))
      }
      if (el.paused) void el.play().catch(() => undefined)
    }
    const dbg = DEBUG ? el.parentElement?.querySelector<HTMLElement>('.tv-sync') : null
    const tick = () => {
      if (dbg) dbg.textContent = `data frame ${Math.floor(pb.frame)} · video frame ${Math.floor(el.currentTime * fps)} · rate ${el.playbackRate.toFixed(2)}`
    }
    if (dbg) el.addEventListener('timeupdate', tick)
    const unsubDbg = dbg ? pb.subscribe(tick) : () => undefined
    // the picture is the stage: while it buffers or seeks, the data clock waits for it (never a
    // frozen picture with a running clock); a safety timer lets the clock go if the video hangs
    let safety = 0
    const hold = () => {
      if (!pb.playing) return
      pb.hold('video', true)
      window.clearTimeout(safety)
      safety = window.setTimeout(() => pb.hold('video', false), 2500)
    }
    const release = () => {
      window.clearTimeout(safety)
      pb.hold('video', false)
    }
    el.addEventListener('waiting', hold)
    el.addEventListener('seeking', hold)
    el.addEventListener('playing', release)
    el.addEventListener('seeked', release)
    el.addEventListener('canplay', release)
    el.addEventListener('loadedmetadata', sync)
    // also from the video side: if the frame clock stalls (background tab), the video must not run away
    el.addEventListener('timeupdate', sync)
    const unsub = pb.subscribe(sync)
    sync()
    return () => {
      el.removeEventListener('waiting', hold)
      el.removeEventListener('seeking', hold)
      el.removeEventListener('playing', release)
      el.removeEventListener('seeked', release)
      el.removeEventListener('canplay', release)
      release()
      el.removeEventListener('loadedmetadata', sync)
      el.removeEventListener('timeupdate', sync)
      el.removeEventListener('timeupdate', tick)
      unsub()
      unsubDbg()
    }
  }, [pb, video, m])

  if (!video) return null
  return (
    <>
      {DEBUG && <div className="tv-sync" />}
      <video
      ref={ref}
      className={`tv-video ${hidden ? 'hidden' : ''}`}
      src={`${m.bundle.baseUrl}/${video.file}`}
      muted
      playsInline
      preload="auto"
      onError={() => {
        console.warn(`TV view: cannot play ${video.file} (needs H.264/yuv420p mp4); falling back to the pitch`)
        onFail()
      }}
    />
    </>
  )
}
