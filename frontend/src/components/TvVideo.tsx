import { useEffect, useRef } from 'react'
import { useMatch } from '../lib/context'

const DEBUG = new URLSearchParams(window.location.search).has('syncdebug')

/**
 * GRF render of the same match (30 fps, same duration as the 10 fps data). While it plays, the
 * picture is the master clock: it runs untouched at its native rate and the data clock reads its
 * position (pb.follow), so the picture never gets nudged, re-rated or re-seeked mid-play (that is
 * what made it stutter). Buffering simply stops both. Seeks from the UI (pb.seeks) jump the
 * picture; paused, it shows the middle of the current data frame.
 */
export function TvVideo({ hidden, onFail }: { hidden: boolean; onFail: () => void }) {
  const { m, pb } = useMatch()
  const ref = useRef<HTMLVideoElement>(null)
  const video = m.bundle.match.video

  useEffect(() => {
    const el = ref.current
    if (!el || !video || hidden) return
    const fps = video.fps || m.bundle.match.fps
    const source = () => el.currentTime * fps
    let seeks = pb.seeks
    const sync = () => {
      if (el.readyState < 1) return // no metadata yet; loadedmetadata calls sync again
      const end = Number.isFinite(el.duration) ? el.duration - 0.5 / fps : Infinity
      const playing = pb.playing && pb.frame / fps < end
      if (!playing) {
        pb.follow(null)
        if (!el.paused) el.pause()
        const target = Math.min(end, (Math.floor(pb.frame) + 0.5) / fps)
        if (Math.abs(target - el.currentTime) > 0.45 / fps) el.currentTime = target
        seeks = pb.seeks
        return
      }
      const rate = Math.min(Math.max(pb.speed, 0.0625), 16)
      if (el.playbackRate !== rate) el.playbackRate = rate
      if (seeks !== pb.seeks || (el.paused && Math.abs(pb.frame / fps - el.currentTime) > 0.2)) {
        seeks = pb.seeks
        el.currentTime = pb.frame / fps
      }
      if (el.paused) void el.play().catch(() => pb.follow(null))
      pb.follow(source)
    }
    const dbg = DEBUG ? el.parentElement?.querySelector<HTMLElement>('.tv-sync') : null
    const tick = () => {
      if (dbg) dbg.textContent = `data frame ${pb.frame.toFixed(1)} · video ${(el.currentTime * fps).toFixed(1)} · rate ${el.playbackRate.toFixed(2)}`
    }
    const unsubDbg = dbg ? pb.subscribe(tick) : () => undefined
    const ended = () => pb.follow(null)
    el.addEventListener('loadedmetadata', sync)
    el.addEventListener('ended', ended)
    const unsub = pb.subscribe(sync)
    sync()
    return () => {
      pb.follow(null)
      el.pause()
      el.removeEventListener('loadedmetadata', sync)
      el.removeEventListener('ended', ended)
      unsub()
      unsubDbg()
    }
  }, [pb, video, m, hidden])

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
