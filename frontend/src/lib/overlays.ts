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
  const base = seg.exact ? (overlays[seg.id] ?? []) : deriveOverlays(m, profile)
  return { list: [...(overlays['*'] ?? []), ...base].filter((o) => keepForMode(m, profile, o)), segment: seg.id, exact: seg.exact }
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
