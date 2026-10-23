import type { Insight, MatchEvent, Moment, PlayerInfo, Team } from '../types'
import { other, scoreAt } from './derive'
import { comparison, statsAt, type MatchIndex } from './match'

/**
 * Small, documented models behind the viewer widgets. Every input is computed from the export
 * (events, frames, stats, insights); nothing comes from an LLM.
 */

// ---------------------------------------------------------------- broadcast minute

export function broadcastMinute(m: MatchIndex, frame: number): number {
  const { fps, clock_scale } = m.bundle.match
  return Math.min(90, (frame / fps) * clock_scale / 60)
}

/** Cumulative xG per team from the shot events up to `frame`. */
export function xgSoFar(events: MatchEvent[], frame: number): Record<Team, number> {
  const out = { home: 0, away: 0 }
  for (const e of events) {
    if (e.frame > frame) break
    if (e.type === 'shot' && e.team && e.meta.xg != null) out[e.team] += Number(e.meta.xg)
  }
  return out
}

// ---------------------------------------------------------------- win probability (model estimate)

/**
 * Win / draw / loss for `team` (model estimate). Goals in the remaining minutes are Poisson for each
 * side, with a rate that blends a prior (1.35 goals per 90 per team, home x1.08 / away x0.92) with
 * the xG rate observed so far (weight grows with the minute, max 60 %). Result = current goal
 * difference + Poisson(us) - Poisson(them).
 */
export function winProbability(m: MatchIndex, team: Team, frame: number): { win: number; draw: number; loss: number } {
  const minute = broadcastMinute(m, frame)
  const rem = Math.max(0, 90 - minute)
  const xg = xgSoFar(m.bundle.events, frame)
  const score = scoreAt(m, frame)
  const lambda = (t: Team) => {
    const prior = (1.35 / 90) * (t === 'home' ? 1.08 : 0.92)
    const observed = xg[t] / Math.max(minute, 15)
    const w = Math.min(0.6, minute / 90)
    return ((1 - w) * prior + w * observed) * rem
  }
  const us = lambda(team)
  const them = lambda(other(team))
  const diff = team === 'home' ? score[0] - score[1] : score[1] - score[0]
  const pois = (l: number) => {
    const p: number[] = []
    let v = Math.exp(-l)
    for (let k = 0; k <= 10; k++) {
      p.push(v)
      v = (v * l) / (k + 1)
    }
    return p
  }
  const pu = pois(us)
  const pt = pois(them)
  let win = 0
  let draw = 0
  for (let a = 0; a <= 10; a++)
    for (let b = 0; b <= 10; b++) {
      const d = diff + a - b
      if (d > 0) win += pu[a] * pt[b]
      else if (d === 0) draw += pu[a] * pt[b]
    }
  const tot = Math.max(1e-9, pu.reduce((x, y) => x + y, 0) * pt.reduce((x, y) => x + y, 0))
  win /= tot
  draw /= tot
  return { win, draw, loss: Math.max(0, 1 - win - draw) }
}

/** Win probability every 2 s of match time (for the little line). */
export function winSeries(m: MatchIndex, team: Team): { frame: number; win: number }[] {
  const n = m.bundle.frames.t_ms.length
  const out: { frame: number; win: number }[] = []
  for (let f = 0; f < n; f += 20) out.push({ frame: f, win: winProbability(m, team, f).win })
  return out
}

// ---------------------------------------------------------------- fan mood

/**
 * Mood meter 0..1 for a fan of `team`: score difference (±0.22 per goal, capped), our share of
 * control (±0.15) and the last 30 s of play (our shots +0.08, theirs -0.08; a goal within the last
 * 60 s ±0.25).
 */
export function fanMood(m: MatchIndex, team: Team, frame: number): number {
  const score = scoreAt(m, frame)
  const diff = team === 'home' ? score[0] - score[1] : score[1] - score[0]
  const s = statsAt(m.bundle, frame)
  const ct = s?.control.control_team
  const share = s && ct && s.control.control_share != null ? (ct === team ? s.control.control_share : 1 - s.control.control_share) : 0.5
  let v = 0.5 + Math.max(-0.4, Math.min(0.4, diff * 0.22)) + (share - 0.5) * 0.3
  const fps = m.bundle.match.fps
  for (const e of m.bundle.events) {
    if (e.frame > frame) break
    if (e.type === 'shot' && frame - e.frame < 30 * fps) v += e.team === team ? 0.08 : -0.08
    if (e.type === 'goal' && frame - e.frame < 60 * fps) v += e.team === team ? 0.25 : -0.25
  }
  return Math.max(0, Math.min(1, v))
}

// ---------------------------------------------------------------- player rating

export type RatingPart = 'passing' | 'shooting' | 'defending' | 'pressing'

export interface RatedAction {
  event: MatchEvent
  part: RatingPart
  value: number
}

const PRESS_WIN_FRAMES = 30

/**
 * Value of each of a player's actions for the live rating:
 *  - completed pass: +0.05 + 0.10 x difficulty/100; failed pass: -0.12
 *  - shot: +0.15 + 2 x xG; goal: +1.2
 *  - tackle won / interception: +0.30
 *  - pressure won (his team wins the ball within 3 s): +0.15
 */
export function ratedActions(m: MatchIndex, pid: string, frame: number): RatedAction[] {
  const ev = m.bundle.events
  const team = m.player(pid)?.team
  const out: RatedAction[] = []
  for (let i = 0; i < ev.length; i++) {
    const e = ev[i]
    if (e.frame > frame) break
    if (e.player_id !== pid) continue
    if (e.type === 'pass') out.push({ event: e, part: 'passing', value: e.outcome === 'complete' ? 0.05 + (0.1 * Number(e.meta.difficulty ?? 0)) / 100 : -0.12 })
    else if (e.type === 'shot') out.push({ event: e, part: 'shooting', value: 0.15 + 2 * Number(e.meta.xg ?? 0) })
    else if (e.type === 'goal') out.push({ event: e, part: 'shooting', value: 1.2 })
    else if (e.type === 'interception' || (e.type === 'tackle' && e.outcome === 'won')) out.push({ event: e, part: 'defending', value: 0.3 })
    else if (e.type === 'pressure') {
      const won = ev.slice(i + 1).find((x) => x.frame - e.frame <= PRESS_WIN_FRAMES && x.frame <= frame && x.team === team && (x.type === 'interception' || x.type === 'tackle'))
      if (won) out.push({ event: e, part: 'pressing', value: 0.15 })
    }
  }
  return out
}

/** Live rating 1..10: 6.0 + 3.5 x tanh(sum of action values / 3), so it saturates instead of growing with match length. */
export function rating(actions: RatedAction[]): number {
  const s = actions.reduce((a, x) => a + x.value, 0)
  return Math.max(1, Math.min(10, 6 + 3.5 * Math.tanh(s / 3)))
}

export function ratingParts(actions: RatedAction[]): Record<RatingPart, number> {
  const out: Record<RatingPart, number> = { passing: 0, shooting: 0, defending: 0, pressing: 0 }
  for (const a of actions) out[a.part] += a.value
  return out
}

/** His best action so far (a goal also credits the shot before it). */
export function bestAction(actions: RatedAction[]): RatedAction | undefined {
  return actions.reduce<RatedAction | undefined>((b, a) => (!b || a.value > b.value ? a : b), undefined)
}

/** Pass accuracy and average pass difficulty so far (rates, not totals). */
export function passProfile(m: MatchIndex, pid: string, frame: number): { acc: number | null; diff: number | null } {
  const passes = m.bundle.events.filter((e) => e.type === 'pass' && e.player_id === pid && e.frame <= frame)
  if (!passes.length) return { acc: null, diff: null }
  const done = passes.filter((e) => e.outcome === 'complete').length
  const withD = passes.filter((e) => e.meta.difficulty != null)
  return { acc: done / passes.length, diff: withD.length ? withD.reduce((a, e) => a + Number(e.meta.difficulty), 0) / withD.length : null }
}

const MIRROR: Record<string, string[]> = {
  GK: ['CF'],
  CF: ['CB'],
  CB: ['CF'],
  LB: ['RM', 'RW'],
  RB: ['LM', 'LW'],
  LM: ['RB'],
  RM: ['LB'],
  CM: ['CM', 'DM', 'AM'],
  DM: ['AM', 'CM'],
  AM: ['DM', 'CM'],
}

/** His direct opponent: the mirrored position on the other team (same shirt number breaks ties). */
export function directOpponent(m: MatchIndex, p: PlayerInfo): PlayerInfo | undefined {
  const opp = m.bundle.match.players.filter((x) => x.team !== p.team)
  for (const pos of MIRROR[p.position] ?? []) {
    const c = opp.filter((x) => x.position === pos)
    if (c.length) return c.find((x) => x.number === p.number) ?? c[0]
  }
  return opp.find((x) => x.position !== 'GK')
}

/** The player's decisions the explain team replayed, up to `frame`, with the verdict. */
export function decisions(m: MatchIndex, pid: string, frame: number): { ins: Insight; mo: Moment; right: boolean }[] {
  const out: { ins: Insight; mo: Moment; right: boolean }[] = []
  for (const ins of m.bundle.insights) {
    const mo = m.moment(ins.moment_id)
    if (!mo || mo.player_ids[0] !== pid || mo.frame > frame || ins.decision_frame == null) continue
    const c = comparison(ins.numbers, ins.metric)
    out.push({ ins, mo, right: c.alt == null || c.alt <= c.actual })
  }
  return out.sort((a, b) => a.mo.frame - b.mo.frame)
}
