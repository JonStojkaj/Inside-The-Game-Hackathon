import { useEffect, useMemo, useRef, useState } from 'react'
import { useMatch } from '../lib/context'
import { segmentId, t } from '../lib/profile'
import type { AudioClip, Lang, ViewerProfile } from '../types'

interface Props {
  /** The viewer whose segment speaks (producer view: the first column). */
  profile: ViewerProfile
  /** Sound on (user setting) and unlocked by a first user gesture; otherwise clips run muted. */
  audible: boolean
  lang: Lang
}

/**
 * Plays the commentator clips of audio.json for one segment when the match clock crosses a
 * clip's start_ms, only while playing at 1x. Seeking, pausing or another speed stops the clip.
 * The spoken text is shown as a caption, so muted viewers still get it.
 */
export function Commentator({ profile, audible, lang }: Props) {
  const { m, pb } = useMatch()
  const seg = segmentId(profile)
  const clips = useMemo(
    () => m.bundle.audio.filter((c) => c.segment_id === seg || c.segment_id === '*').sort((a, b) => a.start_ms - b.start_ms),
    [m, seg],
  )
  const [caption, setCaption] = useState<AudioClip | null>(null)
  const audio = useRef<HTMLAudioElement | null>(null)
  const audibleRef = useRef(audible)

  useEffect(() => {
    audibleRef.current = audible
    if (audio.current) audio.current.muted = !audible
  }, [audible])

  useEffect(() => {
    if (!clips.length) return
    const base = m.bundle.baseUrl
    const ms = () => (pb.frame / pb.fps) * 1000
    let prev = ms()
    let wall = performance.now()
    let timer = 0

    const stop = () => {
      window.clearTimeout(timer)
      if (audio.current) {
        audio.current.pause()
        audio.current = null
      }
      setCaption(null)
    }

    const start = (c: AudioClip) => {
      stop()
      const a = new Audio(`${base}/${c.file}`)
      a.muted = !audibleRef.current
      a.onended = () => {
        if (audio.current === a) stop()
      }
      a.play().catch(() => {
        // autoplay blocked or file missing: the caption still runs for the clip's duration
      })
      audio.current = a
      setCaption(c)
      timer = window.setTimeout(() => {
        if (audio.current === a || !audio.current) stop()
      }, c.duration_ms + 1500)
    }

    const unsub = pb.subscribe(() => {
      const now = ms()
      const nowWall = performance.now()
      const expected = nowWall - wall
      wall = nowWall
      const step = now - prev
      // a seek is a jump the 1x clock could not have made in the elapsed wall time
      const jumped = step < 0 || step > expected + 400
      if (!pb.playing || pb.speed !== 1 || jumped) {
        if (audio.current || jumped) stop()
        prev = now
        return
      }
      const c = clips.find((x) => x.start_ms > prev && x.start_ms <= now)
      prev = now
      if (c) start(c)
    })
    return () => {
      unsub()
      stop()
    }
  }, [m, pb, clips])

  if (!caption) return null
  return (
    <div className="commentary" key={caption.id} role="status" aria-live="polite">
      <span className="commentary-tag">🎙 {t(lang, 'commentator')}</span>
      <span className="commentary-text">{caption.text}</span>
    </div>
  )
}
