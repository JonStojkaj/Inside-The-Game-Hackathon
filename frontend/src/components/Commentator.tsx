import { useEffect, useMemo, useRef } from 'react'
import { audioEl, breakClip, caption, clipSrc, preloadClip, speaking } from '../lib/audio'
import { useMatch } from '../lib/context'
import { segmentId } from '../lib/profile'
import type { AudioClip, ViewerProfile } from '../types'

interface Props {
  /** The viewer whose segment speaks (producer view: the first column). */
  profile: ViewerProfile
  /** Sound on (user setting); captions run either way. */
  audible: boolean
}

/** A clip may still start this long after its start_ms (after a seek, a pause, a slow frame). */
const LATE_MS = 1500
const PRELOAD_MS = 25000

/**
 * Commentator clips of audio.json for one segment. A clip plays when the clock reaches its
 * start_ms (or within LATE_MS after, e.g. after a seek), pauses and resumes with the match, and a
 * Sliding Doors break plays the moment's clip during the pause (and lets it finish after Continue).
 * The caption is shown on the primary screen, so muted viewers still get the words.
 */
export function Commentator({ profile, audible }: Props) {
  const { m, pb, doorsBreak } = useMatch()
  const seg = segmentId(profile)
  const clips = useMemo(
    () => m.bundle.audio.filter((c) => c.segment_id === seg || c.segment_id === '*').sort((a, b) => a.start_ms - b.start_ms),
    [m, seg],
  )
  const audibleRef = useRef(audible)
  const breakRef = useRef(doorsBreak)
  breakRef.current = doorsBreak
  // 'live' follows the clock; 'free' (a break's clip) plays to its end regardless of the clock
  const cur = useRef<{ clip: AudioClip; mode: 'live' | 'free' } | null>(null)
  const played = useRef(new Set<string>())
  const url = (c: AudioClip) => `${m.bundle.baseUrl}/${c.file}`

  const stop = () => {
    const el = audioEl()
    el.pause()
    cur.current = null
    speaking.until = 0
    caption.set(null)
  }

  const start = (c: AudioClip, offsetMs: number, mode: 'live' | 'free') => {
    const el = audioEl()
    el.onended = () => {
      if (cur.current?.clip === c) stop()
    }
    el.src = clipSrc(url(c))
    el.muted = !audibleRef.current
    const off = Math.max(0, offsetMs) / 1000
    if (off > 0.2) el.addEventListener('loadedmetadata', () => (el.currentTime = off), { once: true })
    el.play().catch(() => {
      // blocked or missing file: the caption still runs for the clip's duration
    })
    cur.current = { clip: c, mode }
    played.current.add(c.id)
    speaking.until = audibleRef.current ? performance.now() + c.duration_ms - offsetMs : 0
    caption.set(c)
    // caption fallback when the file never plays (no 'ended' event)
    window.setTimeout(() => {
      if (cur.current?.clip === c && audioEl().paused && (mode === 'free' || pb.playing)) stop()
    }, c.duration_ms - offsetMs + 1500)
  }

  useEffect(() => {
    audibleRef.current = audible
    audioEl().muted = !audible
    if (!audible) speaking.until = 0
  }, [audible])

  // the clock drives live clips
  useEffect(() => {
    if (!clips.length) return
    const ms = () => (pb.frame / pb.fps) * 1000
    const onTick = () => {
      const now = ms()
      // clips ahead of the clock may play again (rewind)
      for (const c of clips) if (c.start_ms > now + 200) played.current.delete(c.id)
      for (const c of clips) if (c.start_ms > now && c.start_ms < now + PRELOAD_MS) preloadClip(url(c))
      if (breakRef.current || cur.current?.mode === 'free') return
      const el = audioEl()
      if (!pb.playing || pb.speed !== 1) {
        if (cur.current) {
          if (pb.playing) stop()
          else if (!el.paused) el.pause()
        }
        return
      }
      if (cur.current) {
        const off = now - cur.current.clip.start_ms
        if (off < -300 || off > cur.current.clip.duration_ms + 300) stop()
        else {
          if (el.paused) {
            if (Math.abs(el.currentTime * 1000 - off) > 500) el.currentTime = off / 1000
            void el.play().catch(() => undefined)
          }
          return
        }
      }
      const c = clips.find((x) => !played.current.has(x.id) && x.start_ms <= now && now - x.start_ms < LATE_MS)
      if (c) start(c, now - c.start_ms, 'live')
    }
    const unsub = pb.subscribe(onTick)
    onTick()
    return () => {
      unsub()
      stop()
    }
  }, [m, pb, clips]) // eslint-disable-line react-hooks/exhaustive-deps

  // a Sliding Doors break plays the moment's clip during the pause
  const breakKey = doorsBreak?.key
  useEffect(() => {
    const br = breakRef.current
    if (!br || !clips.length) return
    const c = breakClip(m, clips, br.insightId, br.overlay)
    if (!c) {
      if (cur.current?.mode === 'live') stop()
      return
    }
    preloadClip(url(c))
    if (cur.current?.clip.id === c.id) {
      cur.current.mode = 'free'
      const el = audioEl()
      if (el.paused) void el.play().catch(() => undefined)
      return
    }
    start(c, 0, 'free')
  }, [breakKey, m, clips]) // eslint-disable-line react-hooks/exhaustive-deps

  return null
}
