import { useMemo } from 'react'
import type { Overlay, ViewerProfile } from '../types'
import { deriveOverlays, keepForMode, overlayMoment } from './derive'
import { doorsFromOverlay, isDoorsOverlay, type MatchIndex } from './match'
import { resolveSegment } from './profile'

/**
 * The overlays one viewer sees: the produced segment when the production team made exactly this
 * one, else derived client-side in the viewer's language (never another language's text).
 */
export function overlayList(m: MatchIndex, profile: ViewerProfile): { list: Overlay[]; segment: string; exact: boolean } {
  const { overlays } = m.bundle
  const seg = resolveSegment(overlays, profile)
  const base = seg.exact ? checkedRecaps(m, profile, overlays[seg.id] ?? []) : deriveOverlays(m, profile)
  return { list: [...(overlays['*'] ?? []), ...base].filter((o) => keepForMode(m, profile, o)), segment: seg.id, exact: seg.exact }
}

/**
 * Every player name in an agent-written text must be a player of this match, first name and surname
 * as in the roster ("Sergio Strand" for Emil Strand fails). Conservative: any doubt fails.
 */
export function namesMatchRoster(m: MatchIndex, text: string): boolean {
  for (const p of m.bundle.match.players) {
    const [first, ...rest] = p.name.split(' ')
    const last = rest.join(' ') || first
    const re = new RegExp(`(\\p{Lu}[\\p{L}'’-]+)\\s+${last.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'gu')
    for (const hit of text.matchAll(re)) if (hit[1] !== first) return false
  }
  return true
}

/**
 * The full-time recap written by the Recap agent stays only if its names check out against the roster;
 * otherwise the viewer gets the recap computed from the data. Either way the card says which it is.
 */
function checkedRecaps(m: MatchIndex, profile: ViewerProfile, list: Overlay[]): Overlay[] {
  return list.map((o) => {
    if (o.type !== 'recap') return o
    const byAgent = o.payload.narration === 'llm'
    if (!byAgent || namesMatchRoster(m, `${o.headline} ${o.body}`)) return { ...o, payload: { ...o.payload, source: byAgent ? 'agent' : 'data' } }
    const derived = deriveOverlays(m, profile).find((d) => d.type === 'recap')
    return derived ? { ...derived, start_ms: o.start_ms, payload: { ...derived.payload, source: 'data', agent_rejected: true } } : o
  })
}

export function useOverlayList(m: MatchIndex, profile: ViewerProfile) {
  return useMemo(() => overlayList(m, profile), [m, profile])
}

/** The viewer's Sliding Doors overlays that can actually be replayed (ghost paths + decision frame), by start. */
export function doorsOverlays(m: MatchIndex, list: Overlay[]): Overlay[] {
  return list.filter((o) => isDoorsOverlay(o) && doorsFromOverlay(m, o)).sort((a, b) => a.start_ms - b.start_ms)
}

/** The viewer's Sliding Doors overlay about a given moment, if the production made one. */
export function doorsForMoment(m: MatchIndex, list: Overlay[], momentId: string): Overlay | undefined {
  return doorsOverlays(m, list).find((o) => overlayMoment(m, o)?.id === momentId)
}
