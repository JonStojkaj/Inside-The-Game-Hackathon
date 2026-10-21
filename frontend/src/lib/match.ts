import type { Insight, MatchBundle, MatchEvent, Metric, Moment, Overlay, OverlaySlot, PlayerInfo, StatsSnapshot, Team, XY } from '../types'

export const PITCH_L = 105
export const PITCH_W = 68

/** Lookups derived once from a bundle. */
export interface MatchIndex {
  bundle: MatchBundle
  playerIdx: Map<string, number>
  player: (id: string | null | undefined) => PlayerInfo | undefined
  insight: (id: string | null | undefined) => Insight | undefined
  moment: (id: string | null | undefined) => Moment | undefined
  insightForMoment: (id: string) => Insight | undefined
  event: (id: string) => MatchEvent | undefined
  club: (team: Team) => MatchBundle['match']['home']
}

export function indexMatch(bundle: MatchBundle): MatchIndex {
  const playerIdx = new Map(bundle.match.players.map((p, i) => [p.id, i]))
  const insights = new Map(bundle.insights.map((i) => [i.id, i]))
  const byMoment = new Map(bundle.insights.map((i) => [i.moment_id, i]))
  const moments = new Map(bundle.moments.map((m) => [m.id, m]))
  const events = new Map(bundle.events.map((e) => [e.id, e]))
  return {
    bundle,
    playerIdx,
    player: (id) => (id == null ? undefined : bundle.match.players[playerIdx.get(id) ?? -1]),
    insight: (id) => (id == null ? undefined : insights.get(id)),
    moment: (id) => (id == null ? undefined : moments.get(id)),
    insightForMoment: (id) => byMoment.get(id),
    event: (id) => events.get(id),
    club: (team) => (team === 'home' ? bundle.match.home : bundle.match.away),
  }
}

export interface FrameView {
  ball: [number, number, number]
  players: XY[]
  owner: number
  score: [number, number]
  mode: string
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t

/** Interpolated state at a fractional frame. Restarts (mode change) are not interpolated. */
export function frameAt(bundle: MatchBundle, f: number): FrameView {
  const fr = bundle.frames
  const n = fr.t_ms.length
  const i = Math.max(0, Math.min(Math.floor(f), n - 1))
  const j = Math.min(i + 1, n - 1)
  let t = f - i
  const jump = Math.abs(fr.ball[j][0] - fr.ball[i][0]) > 8 // teleports at restarts
  if (fr.mode[i] !== fr.mode[j] || jump) t = 0
  const b0 = fr.ball[i]
  const b1 = fr.ball[j]
  return {
    ball: [lerp(b0[0], b1[0], t), lerp(b0[1], b1[1], t), lerp(b0[2], b1[2], t)],
    players: fr.players[i].map((p, k) => [lerp(p[0], fr.players[j][k][0], t), lerp(p[1], fr.players[j][k][1], t)] as XY),
    owner: fr.owner[i],
    score: fr.score[i],
    mode: fr.mode[i],
  }
}

/** Broadcast clock "mm:ss" for a frame. */
export function clockLabel(bundle: MatchBundle, frame: number): string {
  const f = Math.min(frame, bundle.frames.t_ms.length - 1)
  const s = Math.max(0, Math.floor((f / bundle.match.fps) * bundle.match.clock_scale))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

/** Minute mark like 23' for tickers. */
export function minuteLabel(bundle: MatchBundle, frame: number): string {
  const f = Math.min(frame, bundle.frames.t_ms.length - 1)
  return `${Math.min(90, Math.floor(((f / bundle.match.fps) * bundle.match.clock_scale) / 60) + 1)}'`
}

export function statsAt(bundle: MatchBundle, frame: number): StatsSnapshot | undefined {
  const t = (frame / bundle.match.fps) * 1000
  const s = bundle.stats
  if (!s.length) return undefined
  let lo = 0
  let hi = s.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (s[mid].t_ms <= t) lo = mid
    else hi = mid - 1
  }
  return s[lo]
}

/** Overlays visible at match time t_ms, one per slot: the highest priority wins collisions. */
export function activeOverlays(list: Overlay[], tMs: number): Partial<Record<OverlaySlot, Overlay>> {
  const out: Partial<Record<OverlaySlot, Overlay>> = {}
  for (const o of list) {
    if (tMs < o.start_ms || tMs >= o.start_ms + o.duration_ms) continue
    const cur = out[o.slot]
    if (!cur || o.priority > cur.priority || (o.priority === cur.priority && o.start_ms > cur.start_ms)) out[o.slot] = o
  }
  return out
}

/** The probability a Sliding Doors comparison is about; higher is better for both metrics. */
export function comparison(numbers: Record<string, number>, metric?: Metric): { metric: Metric; actual: number; alt: number | null } {
  const m: Metric =
    metric ?? (numbers.best_alt_p_keep != null && numbers.best_alt_p_goal == null ? 'p_keep' : 'p_goal')
  return { metric: m, actual: numbers[`actual_${m}`] ?? 0, alt: numbers[`best_alt_${m}`] ?? null }
}

/** Everything a Sliding Doors moment needs, from an insight or from a self-contained overlay payload. */
export interface Doors {
  key: string
  decision_frame: number
  ghost_paths: XY[][]
  alt_ghost_paths: XY[][]
  alt_label: string
  numbers: Record<string, number>
  metric?: Metric
  confidence: 'clear' | 'slight'
  claim: string
  tested: number // alternatives tested (hypotheses)
  rejected: number
}

const doorsCache = new WeakMap<object, Doors>()

function cached(src: object, make: () => Doors | undefined): Doors | undefined {
  const hit = doorsCache.get(src)
  if (hit) return hit
  const d = make()
  if (d) doorsCache.set(src, d)
  return d
}

export function doorsFromInsight(ins: Insight | undefined): Doors | undefined {
  if (!ins || ins.decision_frame == null) return undefined
  return cached(ins, () => ({
    key: ins.id,
    decision_frame: ins.decision_frame!,
    ghost_paths: ins.ghost_paths,
    alt_ghost_paths: ins.alt_ghost_paths,
    alt_label: ins.alt_label,
    numbers: ins.numbers,
    metric: ins.metric,
    confidence: ins.confidence,
    claim: ins.claim,
    tested: ins.hypotheses.length,
    rejected: ins.hypotheses.filter((h) => h.verdict === 'rejected').length,
  }))
}

/**
 * A sliding_doors overlay either points at an insight (payload.insight_id / moment_id) or carries
 * its own ghost paths and numbers. The payload wins so text and numbers on screen always agree.
 */
export function doorsFromOverlay(m: MatchIndex, o: Overlay): Doors | undefined {
  const p = o.payload
  const ins = m.insight(p.insight_id as string | undefined) ?? (p.moment_id ? m.insightForMoment(String(p.moment_id)) : undefined)
  if (!Array.isArray(p.ghost_paths) || p.decision_frame == null) return doorsFromInsight(ins)
  return cached(o, () => {
    const hyps = (p.hypotheses as { verdict?: string }[] | undefined) ?? ins?.hypotheses ?? []
    return {
      key: o.id,
      decision_frame: Number(p.decision_frame),
      ghost_paths: p.ghost_paths as XY[][],
      alt_ghost_paths: (p.alt_ghost_paths as XY[][] | undefined) ?? [],
      alt_label: String(p.alt_label ?? ins?.alt_label ?? ''),
      numbers: (p.numbers as Record<string, number> | undefined) ?? ins?.numbers ?? {},
      metric: (p.metric as Metric | undefined) ?? ins?.metric,
      confidence: (p.confidence as 'clear' | 'slight' | undefined) ?? ins?.confidence ?? 'clear',
      claim: o.body || ins?.claim || '',
      tested: hyps.length,
      rejected: hyps.filter((h) => h.verdict === 'rejected').length,
    }
  })
}

/** payload.player_id or the first of payload.player_ids. */
export function payloadPlayer(o: Overlay | undefined): string | undefined {
  if (!o) return undefined
  const ids = o.payload.player_ids
  return (o.payload.player_id as string | undefined) ?? (Array.isArray(ids) && ids.length ? String(ids[0]) : undefined)
}

/** Last match time anything is on screen (the full-time recap starts after the last frame). */
export function timelineFrames(bundle: MatchBundle): number {
  const end = Object.values(bundle.overlays)
    .flat()
    .reduce((mx, o) => Math.max(mx, o.start_ms + o.duration_ms), 0)
  return Math.max(bundle.frames.t_ms.length, Math.ceil((end / 1000) * bundle.match.fps) + 1)
}
