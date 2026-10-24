import type { Lang, MatchEvent, Moment, Team } from '../types'
import type { MatchIndex } from './match'
import { fmtNum, fmtPct, surname, tf } from './profile'

/**
 * Why a key moment matters, beyond "it happened" (same analysis as the commentator, backend
 * app/commentary/narrative.py): the move behind a goal, what a ball loss led to, how big a chance
 * was against the rest of the game, how much a pass raised the scoring chance. Numbers from the data.
 */
const other = (t: Team): Team => (t === 'home' ? 'away' : 'home')

/** Walk back from the shot through the same team's chain until the ball was won or play restarted. */
export function buildUp(m: MatchIndex, shot: MatchEvent): { passes: number; seconds: number; start: 'regain' | 'set_piece' | 'open'; starter?: string } {
  const ev = m.bundle.events
  const i = ev.findIndex((e) => e.id === shot.id)
  let passes = 0
  let first = shot
  let start: 'regain' | 'set_piece' | 'open' = 'open'
  let starter: string | undefined
  for (let k = i - 1; k >= 0; k--) {
    const e = ev[k]
    if (shot.t_ms - e.t_ms > 30_000) break
    if (e.type === 'pressure' || e.t_ms >= shot.t_ms || (e.type === 'set_piece' && !e.team)) continue
    if (e.team !== shot.team || e.type === 'shot' || e.type === 'goal' || e.type === 'out_of_play' || (e.type === 'pass' && e.outcome !== 'complete')) break
    if (e.type === 'tackle' || e.type === 'interception') {
      start = 'regain'
      starter = e.player_id ?? undefined
      first = e
      break
    }
    if (e.type === 'set_piece' || e.type === 'kickoff') {
      start = e.type === 'set_piece' ? 'set_piece' : 'open'
      first = e
      break
    }
    if (e.type === 'pass') passes++
    first = e
    starter = e.player_id ?? undefined
  }
  return { passes, seconds: (shot.t_ms - first.t_ms) / 1000, start, starter }
}

function name(m: MatchIndex, id?: string | null): string {
  const p = m.player(id)
  return p ? surname(p.name) : ''
}

export function momentContext(m: MatchIndex, mo: Moment, lang: Lang): string {
  const ev = mo.event_ids.map((id) => m.event(id)).filter((e): e is MatchEvent => Boolean(e))
  const shot = ev.find((e) => e.type === 'shot') ?? (mo.kind === 'goal' ? m.bundle.events.find((e) => e.type === 'shot' && e.outcome === 'goal' && Math.abs(e.frame - mo.frame) < 30) : undefined)
  const s = (v: number) => fmtNum(lang, Math.max(1, v), 0)
  if (mo.kind === 'goal' && shot) {
    const b = buildUp(m, shot)
    if (b.start === 'regain' && b.starter) return tf(lang, 'why_move_regain', { who: name(m, b.starter), s: s(b.seconds) })
    if (b.start === 'set_piece') return tf(lang, 'why_move_set', {})
    if (b.passes >= 2) return tf(lang, 'why_move_pass', { n: b.passes, s: s(b.seconds) })
    return ''
  }
  if (mo.kind === 'big_chance' && shot && shot.team) {
    const xg = Number(shot.meta.xg ?? 0)
    const before = m.bundle.events.filter((e) => e.type === 'shot' && e.team === shot.team && e.frame < shot.frame)
    const best = before.every((e) => Number(e.meta.xg ?? 0) < xg)
    const d = fmtNum(lang, Number(shot.meta.distance_m ?? 0), 0)
    return tf(lang, best ? 'why_chance_best' : 'why_chance', { xg: fmtNum(lang, xg, 2), d })
  }
  if (mo.kind === 'dangerous_turnover') {
    const won = ev.find((e) => (e.type === 'tackle' || e.type === 'interception') && e.team)
    if (!won || !won.team) return ''
    const x = won.start_xy ? won.start_xy[0] : 52.5
    const d = fmtNum(lang, other(won.team) === 'home' ? x : 105 - x, 0)
    const next = m.bundle.events.find((e) => e.type === 'shot' && e.team === won.team && e.t_ms >= won.t_ms && e.t_ms - won.t_ms <= 15_000)
    return next ? tf(lang, 'why_turnover_shot', { d, s: s((next.t_ms - won.t_ms) / 1000) }) : tf(lang, 'why_turnover', { d })
  }
  if (mo.kind === 'decisive_pass') {
    const pass = ev.find((e) => e.type === 'pass')
    const gain = Number(pass?.meta.threat_gain ?? 0)
    if (pass && gain > 0) return tf(lang, 'why_pass', { who: name(m, pass.player_id), to: name(m, pass.target_id), p: fmtPct(lang, gain, 0) })
  }
  return ''
}

/** "headline · context" without empty parts. */
export const joinWhy = (...parts: string[]) => parts.filter(Boolean).join(' · ')
