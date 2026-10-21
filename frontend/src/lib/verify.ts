import type { Hypothesis, Insight, Overlay } from '../types'
import type { MatchIndex } from './match'

/**
 * Client-side audit of a claim shown on screen. `Insight.verified` is set by the backend, so the
 * player re-checks what it can on its own instead of trusting the flag:
 *  - every probability ("12.5%", "12,5 %") and point delta ("8.3 points", "−8,3 Punkte") written
 *    in the text must be one the rollout engine produced for this moment (insight numbers,
 *    hypothesis baseline / counterfactual, or a difference of two of them), up to display rounding;
 *  - every evidence id must resolve: an event id from events.json, a rollout id of this moment,
 *    or a stats / frame reference.
 * Numbers in metres, km/h, minutes and xG are not probabilities and are not checked here.
 */
export interface ClaimCheck {
  ok: boolean
  numbers: number // probabilities / deltas found in the text
  traced: number // of those, produced by the engine
  untraced: string[] // the ones that are not (shown in the control room)
  evidence: number
  evidenceOk: number
}

const PCT = /([−-]?\d+(?:[.,]\d+)?)\s?%/g
const POINTS = /([+−-]?\d+(?:[.,]\d+)?)\s?(?:percentage points|points|pts|Prozentpunkte|Punkte|puntos porcentuales|puntos|pp)\b/gi
const num = (s: string) => Math.abs(Number(s.replace('−', '-').replace(',', '.')))

/** Every probability (in percent) the engine produced for this insight. */
export function engineValues(ins: Insight): number[] {
  const vals = new Set<number>()
  const add = (v: number | null | undefined) => {
    if (v != null && Number.isFinite(v)) vals.add(Math.abs(v) * 100)
  }
  Object.values(ins.numbers).forEach(add)
  ins.hypotheses.forEach((h: Hypothesis) => {
    add(h.baseline_p_goal)
    add(h.counterfactual_p_goal)
    if (h.baseline_p_goal != null && h.counterfactual_p_goal != null) add(h.counterfactual_p_goal - h.baseline_p_goal)
  })
  const base = [...vals]
  for (const a of base) for (const b of base) if (a > b) vals.add(a - b)
  return [...vals]
}

function traced(v: number, engine: number[]): boolean {
  // text rounds to 1 decimal (or to an integer); allow that plus float noise
  return engine.some((e) => Math.abs(e - v) <= 0.051 || (Number.isInteger(v) && Math.abs(e - v) <= 0.5))
}

export function checkText(text: string, ins: Insight): Pick<ClaimCheck, 'numbers' | 'traced' | 'untraced'> {
  const engine = engineValues(ins)
  const found = [...text.matchAll(PCT), ...text.matchAll(POINTS)].map((mt) => mt[1])
  const untraced = found.filter((s) => !traced(num(s), engine))
  return { numbers: found.length, traced: found.length - untraced.length, untraced }
}

function evidenceOk(id: string, ins: Insight, m: MatchIndex): boolean {
  if (m.event(id)) return true
  if (id === ins.id || id === ins.moment_id) return true
  if (id.startsWith('rollout:')) return id.split(':')[1] === ins.moment_id
  return /^(stats|frame):/.test(id)
}

export function checkClaim(text: string, ins: Insight, m: MatchIndex, evidence: string[] = ins.evidence): ClaimCheck {
  const t = checkText(text, ins)
  const evOk = evidence.filter((id) => evidenceOk(id, ins, m)).length
  return {
    ...t,
    evidence: evidence.length,
    evidenceOk: evOk,
    ok: t.untraced.length === 0 && evidence.length > 0 && evOk === evidence.length,
  }
}

/** The insight an overlay cites (payload.insight_id, then payload.moment_id). */
export function overlayInsight(m: MatchIndex, o: Overlay): Insight | undefined {
  const p = o.payload
  return m.insight(p.insight_id as string | undefined) ?? (p.moment_id ? m.insightForMoment(String(p.moment_id)) : undefined)
}

/** Check an overlay's on-screen text (headline + body) against the insight it cites. */
export function checkOverlay(m: MatchIndex, o: Overlay): ClaimCheck | undefined {
  const ins = overlayInsight(m, o)
  if (!ins) return undefined
  return checkClaim(`${o.headline} ${o.body}`, ins, m, o.evidence.length ? o.evidence : ins.evidence)
}

export type Direction = 'up' | 'down'

/**
 * What the Analyst predicted: `expected_direction` when the backend sends it, otherwise read from
 * the hypothesis text (EN; the explain team writes hypotheses in English).
 */
export function expectedDirection(h: Hypothesis): Direction | null {
  if (h.expected_direction) return h.expected_direction
  const s = h.text.toLowerCase()
  const up = /(would have |would )?(increased?|raised?|higher|improved?|better|more likely)/.test(s)
  const down = /(would have |would )?(lowered?|reduced?|decreased?|lower|worse|less likely|smaller|dropped?)/.test(s)
  if (up === down) return null
  return up ? 'up' : 'down'
}

/** Measured direction of the counterfactual vs the baseline. */
export function measuredDirection(h: Hypothesis): Direction | null {
  if (h.baseline_p_goal == null || h.counterfactual_p_goal == null || h.baseline_p_goal === h.counterfactual_p_goal) return null
  return h.counterfactual_p_goal > h.baseline_p_goal ? 'up' : 'down'
}

/**
 * Accepted means "the effect is real and stable", not "the Analyst was right". An accepted
 * hypothesis whose measured effect points the other way is shown as refuted.
 */
export function outcome(h: Hypothesis): 'confirmed' | 'refuted' | 'rejected' | 'pending' {
  if (h.verdict !== 'accepted') return h.verdict
  const exp = expectedDirection(h)
  const got = measuredDirection(h)
  return exp && got && exp !== got ? 'refuted' : 'confirmed'
}
