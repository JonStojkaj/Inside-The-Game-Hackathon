import { useEffect, useRef, useState } from 'react'
import { audioEl, caption, clipSrc, preloadClip, speaking } from '../lib/audio'
import { fallbackLines, fetchCommentary, type CommentaryLine } from '../lib/commentary'
import { useMatch } from '../lib/context'
import { oneSentence } from '../lib/story'
import type { ViewerProfile } from '../types'

interface Props {
  profile: ViewerProfile
  /** Sound on (user setting); captions run either way. */
  audible: boolean
}

/** A line more than this late (after a seek, a pause, a long previous line) is dropped. */
const LATE_MS = 3000
const PREFETCH = 3
const BREAK_CAPTION_MS = 9000

type Cur = { line: CommentaryLine; mode: 'live' | 'free'; endAt: number; audio: boolean }

/**
 * The commentator: a queue of lines played when the match clock crosses their start_ms, one at a
 * time (never overlapping), late ones dropped, the next three audio files prefetched. It pauses and
 * resumes with the match and speaks only at 1x. During a Sliding Doors break it explains the what-if
 * (the line that falls into the break, else the insight's claim as a caption) and may finish after
 * Continue. The caption shows on the stage, also when muted.
 */
export function Commentator({ profile, audible }: Props) {
  const { m, pb, doorsBreak } = useMatch()
  const [lines, setLines] = useState<CommentaryLine[]>([])
  const linesRef = useRef(lines)
  linesRef.current = lines
  const audibleRef = useRef(audible)
  const breakRef = useRef(doorsBreak)
  breakRef.current = doorsBreak
  const cur = useRef<Cur | null>(null)
  const done = useRef(new Set<string>())
  const ms = () => (pb.frame / pb.fps) * 1000

  // backend lines for exactly this viewer, else the recorded clips that fit best
  const { mode, language, favourite_club, favourite_players } = profile
  const fav = favourite_players[0] ?? ''
  useEffect(() => {
    let live = true
    const p: ViewerProfile = { mode, language, favourite_club, favourite_players: fav ? [fav] : [] }
    const fallback = fallbackLines(m.bundle, p)
    setLines(fallback)
    void fetchCommentary(m.bundle.match.match_id, p).then((api) => {
      if (live && api && api.length) setLines(api)
    })
    return () => {
      live = false
    }
  }, [m, mode, language, favourite_club, fav])

  const finish = () => {
    const el = audioEl()
    el.onended = null
    el.onerror = null
    el.pause()
    cur.current = null
    speaking.until = 0
    caption.set(null)
  }

  const start = (line: CommentaryLine, mode: 'live' | 'free') => {
    done.current.add(line.id)
    const el = audioEl()
    el.onended = null
    el.onerror = null
    const c: Cur = { line, mode, endAt: mode === 'live' ? ms() + line.duration_ms : performance.now() + line.duration_ms, audio: Boolean(line.audio) }
    cur.current = c
    caption.set({ id: line.id, text: line.text })
    if (line.audio) {
      el.onended = () => cur.current === c && finish()
      // missing or undecodable file: keep the caption for the line's duration
      el.onerror = () => {
        if (cur.current === c) c.audio = false
      }
      el.src = clipSrc(line.audio)
      el.muted = !audibleRef.current
      el.currentTime = 0
      el.play().catch(() => {
        if (cur.current === c) c.audio = false
      })
      speaking.until = audibleRef.current ? performance.now() + line.duration_ms : 0
    } else {
      el.pause()
      speaking.until = 0
    }
  }

  useEffect(() => {
    audibleRef.current = audible
    audioEl().muted = !audible
    if (!audible) speaking.until = 0
  }, [audible])

  // the match clock drives the queue
  useEffect(() => {
    let last = ms()
    const onTick = () => {
      const now = ms()
      const step = now - last
      last = now
      const all = linesRef.current
      // a seek: forget what lies ahead, drop what is already too late
      const maxStep = pb.playing ? 700 * Math.max(1, pb.speed) : 50
      if (step < -250 || step > maxStep) {
        if (cur.current?.mode === 'live') finish()
        for (const l of all) {
          if (l.start_ms > now) done.current.delete(l.id)
          else if (now - l.start_ms > LATE_MS) done.current.add(l.id)
        }
      }
      // prefetch the next few audio files
      let n = 0
      for (const l of all) {
        if (n >= PREFETCH) break
        if (l.start_ms > now - 500 && !done.current.has(l.id) && l.audio) {
          preloadClip(l.audio)
          n++
        }
      }
      const c = cur.current
      if (c?.mode === 'free') {
        if (!c.audio && performance.now() > c.endAt) finish()
        return
      }
      if (breakRef.current) return
      const el = audioEl()
      if (!pb.playing || pb.speed !== 1) {
        if (c) {
          if (pb.playing) finish() // fast-forward: the commentator stays quiet
          else if (!el.paused) el.pause()
        }
        return
      }
      if (c) {
        if (c.audio) {
          if (el.paused && !el.ended) void el.play().catch(() => (c.audio = false))
          return
        }
        if (now < c.endAt) return
        finish()
      }
      // next due line; the ones more than LATE_MS late are dropped
      for (const l of all) {
        if (done.current.has(l.id) || l.start_ms > now) continue
        if (now - l.start_ms > LATE_MS) {
          done.current.add(l.id)
          continue
        }
        start(l, 'live')
        break
      }
    }
    const unsub = pb.subscribe(onTick)
    onTick()
    return () => {
      unsub()
      finish()
    }
  }, [pb, lines]) // eslint-disable-line react-hooks/exhaustive-deps

  // a Sliding Doors break: the commentator explains the what-if during the pause
  const breakKey = doorsBreak?.key
  useEffect(() => {
    const br = breakRef.current
    if (!br) return
    const all = linesRef.current
    const p = br.overlay?.payload
    const ins = m.insight(br.insightId ?? (p?.insight_id as string | undefined)) ?? (p?.moment_id ? m.insightForMoment(String(p.moment_id)) : undefined)
    const t = br.overlay?.start_ms ?? ms()
    const lo = t - 1500
    const hi = br.overlay ? br.overlay.start_ms + br.overlay.duration_ms : t + 12000
    const inside = all.filter((l) => l.start_ms >= lo && l.start_ms <= hi)
    // the commentator's Sliding Doors verdict (sd_*) on THIS moment: the first one after it, never the
    // verdict on a later moment that happens to be near the break (a break can come well after its moment)
    const mo = ins ? m.moment(ins.moment_id) : undefined
    const moMs = mo ? (mo.frame / m.bundle.match.fps) * 1000 : null
    const verdict =
      moMs == null
        ? undefined
        : all
            .filter((l) => l.kind.startsWith('sd_') && l.start_ms >= moMs - 2000 && l.start_ms <= moMs + 20000)
            .sort((a, b) => Math.abs(a.start_ms - moMs) - Math.abs(b.start_ms - moMs))[0]
    const line =
      verdict ??
      (ins ? all.find((l) => l.id.endsWith(ins.id)) : undefined) ??
      inside.filter((l) => /doors|insight|what/i.test(l.kind)).sort((a, b) => b.priority - a.priority)[0] ??
      inside.sort((a, b) => b.priority - a.priority || Math.abs(a.start_ms - t) - Math.abs(b.start_ms - t))[0]
    if (line) {
      if (line.audio) preloadClip(line.audio)
      const c = cur.current
      if (c?.line.id === line.id) {
        c.mode = 'free'
        c.endAt = performance.now() + line.duration_ms
        const el = audioEl()
        if (c.audio && el.paused && !el.ended) void el.play().catch(() => (c.audio = false))
        return
      }
      start(line, 'free')
      return
    }
    if (cur.current?.mode === 'live') finish()
    if (ins?.claim) start({ id: `brk-${br.key}`, start_ms: t, duration_ms: BREAK_CAPTION_MS, text: oneSentence(ins.claim), kind: 'insight', priority: 0, audio: null }, 'free')
  }, [breakKey, m]) // eslint-disable-line react-hooks/exhaustive-deps

  return null
}
