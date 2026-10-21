import { useEffect, useRef } from 'react'
import { useMatch } from '../lib/context'

/** GRF render of the same match, slaved to the frame clock (the data is the master, never the video). */
export function TvVideo({ hidden }: { hidden: boolean }) {
  const { m, pb } = useMatch()
  const ref = useRef<HTMLVideoElement>(null)
  const video = m.bundle.match.video

  useEffect(() => {
    const el = ref.current
    if (!el || !video) return
    const sync = () => {
      const target = pb.frame / video.fps
      el.playbackRate = Math.min(pb.speed, 16)
      if (Math.abs(el.currentTime - target) > 0.3) el.currentTime = target
      if (pb.playing && el.paused) void el.play().catch(() => undefined)
      if (!pb.playing && !el.paused) el.pause()
    }
    sync()
    return pb.subscribe(sync)
  }, [pb, video])

  if (!video) return null
  return <video ref={ref} className={`tv-video ${hidden ? 'hidden' : ''}`} src={`${m.bundle.baseUrl}/${video.file}`} muted playsInline preload="auto" />
}
