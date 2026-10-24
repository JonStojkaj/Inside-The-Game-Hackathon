import { useEffect, useMemo, useState } from 'react'
import type { MatchIndex } from './match'
import type { Playback } from './playback'

/**
 * Big moments as a TV highlights package: playback only runs inside clips and cuts straight to the
 * next one. "highlights" = goals and the big chances, "extended" = every shot and every key moment
 * with more build-up, "full" = the whole match. Clips are frame ranges built from the data, merged
 * when they overlap or nearly touch.
 */
export type Cut = 'highlights' | 'extended' | 'full'
export const CUTS: Cut[] = ['highlights', 'extended', 'full']

export interface Clip {
  start: number
  end: number
  /** What the clip is about (the most important thing in it). */
  kind: 'goal' | 'chance' | 'moment'
  /** Frame of that thing, for the label's minute. */
  at: number
}

const RANK = { goal: 3, chance: 2, moment: 1 } as const

export function buildClips(m: MatchIndex, cut: Cut): Clip[] {
  if (cut === 'full') return []
  const fps = m.bundle.match.fps
  const s = (sec: number) => Math.round(sec * fps)
  const ext = cut === 'extended'
  const raw: Clip[] = []
  const ev = m.bundle.events
  for (const g of ev.filter((e) => e.type === 'goal')) {
    const shot = ev.find((e) => e.id === g.meta.shot_id) ?? g
    raw.push({ start: shot.frame - s(ext ? 12 : 8), end: g.frame + s(ext ? 6 : 4), kind: 'goal', at: g.frame })
  }
  for (const mo of m.bundle.moments) {
    if (mo.kind === 'goal') continue
    if (mo.kind === 'big_chance') raw.push({ start: mo.frame - s(ext ? 10 : 6), end: mo.frame + s(3), kind: 'chance', at: mo.frame })
    else if (ext) raw.push({ start: mo.frame - s(8), end: mo.frame + s(4), kind: 'moment', at: mo.frame })
  }
  if (ext) {
    for (const sh of ev.filter((e) => e.type === 'shot' && e.outcome !== 'goal'))
      raw.push({ start: sh.frame - s(8), end: sh.frame + s(3), kind: 'chance', at: sh.frame })
  }
  const last = m.bundle.frames.t_ms.length - 1
  const clips: Clip[] = []
  for (const c of raw
    .map((c) => ({ ...c, start: Math.max(0, c.start), end: Math.min(last, c.end) }))
    .sort((a, b) => a.start - b.start)) {
    const prev = clips[clips.length - 1]
    if (prev && c.start <= prev.end + s(2)) {
      prev.end = Math.max(prev.end, c.end)
      if (RANK[c.kind] > RANK[prev.kind]) Object.assign(prev, { kind: c.kind, at: c.at })
    } else clips.push({ ...c })
  }
  return clips
}

const KEY = 'sliding-doors.cut.v1'

/**
 * Drives the playback through the clips: outside a clip (or past its end) it jumps to the next
 * one; after the last one it stops. Returns the clip being shown and a counter that bumps on each cut.
 */
export function useCutPlayer(m: MatchIndex, pb: Playback, enabled: boolean) {
  const [cut, setCutState] = useState<Cut>(() => {
    try {
      const v = sessionStorage.getItem(KEY)
      if (v && (CUTS as string[]).includes(v)) return v as Cut
    } catch {
      // no storage
    }
    return 'highlights'
  })
  const setCut = (c: Cut) => {
    setCutState(c)
    try {
      sessionStorage.setItem(KEY, c)
    } catch {
      // no storage
    }
  }
  const active = enabled ? cut : 'full'
  const clips = useMemo(() => buildClips(m, active), [m, active])
  const [index, setIndex] = useState(-1)
  const [cuts, setCuts] = useState(0)

  useEffect(() => {
    if (!clips.length) {
      setIndex(-1)
      return
    }
    const check = () => {
      const f = pb.frame
      const i = clips.findIndex((c) => f >= c.start && f < c.end)
      if (i >= 0) {
        setIndex(i)
        return
      }
      if (!pb.playing) return
      const next = clips.findIndex((c) => c.start > f)
      if (next < 0) {
        // after the last clip: straight to the final whistle and the full-time recap (the clock runs on
        // past the last frame for it); from there, the next play starts the package again
        const last = m.bundle.frames.t_ms.length - 1
        if (f < last - 1) {
          pb.seek(last)
          setIndex(-1)
          setCuts((n) => n + 1)
        } else if (f >= pb.nFrames - 1) {
          pb.pause()
          pb.seek(clips[0].start)
        }
        return
      }
      pb.seek(clips[next].start)
      setIndex(next)
      setCuts((n) => n + 1)
    }
    check()
    return pb.subscribe(check)
  }, [clips, pb, m])

  return { cut, setCut, clips, clip: index >= 0 ? clips[index] : undefined, index, cuts }
}
