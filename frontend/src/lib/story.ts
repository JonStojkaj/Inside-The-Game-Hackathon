import { useEffect, useState } from 'react'
import type { Hypothesis, Lang, XY } from '../types'
import type { Doors, MatchIndex } from './match'
import { surname, t, tf } from './profile'

/**
 * The Sliding Doors story, told in four timed phases on the 2D pitch and in the card:
 *   loading  "Simulating N scenarios…" while the ghost futures fan in
 *   actual   the real action replays from the decision frame (ball path in white)
 *   alt      the same moment again, the ball (and the carrier, for a dribble) moves along ONE
 *            representative alternative future (gold)
 *   result   both paths stay, the card shows "6.5 % → 10.1 %" and one short sentence
 * Pitch and card read the same clock (`since` = performance.now() when the break opened).
 */
export type Phase = 'loading' | 'actual' | 'alt' | 'result'

export const LOAD_MS = 2600
export const ACTUAL_MS = 3400
export const ALT_MS = 3400
/** Real play replayed in the "what happened" phase. */
export const ACTUAL_S = 4

const Q = new URLSearchParams(window.location.search)
const SHOT = Q.has('shot')
/** ?sdphase=loading|actual|alt|result pins a phase for screenshots. */
const PINNED = Q.get('sdphase') as Phase | null

export function storyLength(hasAlt: boolean): number {
  return LOAD_MS + ACTUAL_MS + (hasAlt ? ALT_MS : 0)
}

/** Elapsed story time; pinned phases sit in the middle of that phase (end of it for the paths). */
export function storyElapsed(since: number, hasAlt: boolean, now = performance.now()): number {
  if (PINNED === 'loading') return LOAD_MS * 0.6
  if (PINNED === 'actual') return LOAD_MS + ACTUAL_MS * 0.75
  if (PINNED === 'alt') return LOAD_MS + ACTUAL_MS + ALT_MS * 0.8
  if (PINNED === 'result' || (SHOT && !PINNED)) return storyLength(hasAlt) + 1
  return now - since
}

export function phaseAt(el: number, hasAlt: boolean): Phase {
  if (el < LOAD_MS) return 'loading'
  if (el < LOAD_MS + ACTUAL_MS) return 'actual'
  if (hasAlt && el < LOAD_MS + ACTUAL_MS + ALT_MS) return 'alt'
  return 'result'
}

/** The current phase, re-rendered at each boundary. */
export function usePhase(since: number, hasAlt: boolean): { phase: Phase; progress: number } {
  const [, tick] = useState(0)
  const el = storyElapsed(since, hasAlt)
  const phase = phaseAt(el, hasAlt)
  useEffect(() => {
    if (phase === 'result') return
    const id = window.setInterval(() => tick((n) => n + 1), 100)
    return () => window.clearInterval(id)
  }, [phase])
  return { phase, progress: Math.min(1, el / LOAD_MS) }
}

const restartCache = new WeakMap<XY[], XY[]>()
/**
 * A rollout keeps running after a goal or the ball going out, and the restart teleports the ball
 * (e.g. 25 m -> goal line -> centre spot). Use each future only up to that teleport.
 */
export function untilRestart(path: XY[]): XY[] {
  const hit = restartCache.get(path)
  if (hit) return hit
  let n = path.length
  for (let k = 1; k < path.length; k++) {
    const d = Math.hypot(path[k][0] - path[k - 1][0], path[k][1] - path[k - 1][1])
    // > 22 m in one sample: a restart (the first steps may be the shot or pass itself)
    if (d > 22 && k > 1) {
      n = k
      break
    }
  }
  const out = path.slice(0, n)
  restartCache.set(path, out)
  return out
}

const repCache = new WeakMap<XY[][], XY[] | null>()
/** The alternative future whose end point is closest to the median end point of all of them. */
export function representative(paths: XY[][]): XY[] | null {
  if (repCache.has(paths)) return repCache.get(paths)!
  const cut = paths.map(untilRestart).filter((p) => p.length >= 2)
  let best: XY[] | null = null
  if (cut.length) {
    const med = (v: number[]) => v.sort((a, b) => a - b)[Math.floor(v.length / 2)]
    const ends = cut.map((p) => p[p.length - 1])
    const mx = med(ends.map((e) => e[0]))
    const my = med(ends.map((e) => e[1]))
    let bd = Infinity
    for (const p of cut) {
      const e = p[p.length - 1]
      const d = Math.hypot(e[0] - mx, e[1] - my)
      if (d < bd) {
        bd = d
        best = p
      }
    }
  }
  repCache.set(paths, best)
  return best
}

/** A dribble: the ball moves in small steps, so the carrier runs with it. */
export function isCarry(path: XY[]): boolean {
  const steps: number[] = []
  for (let k = 1; k < Math.min(path.length, 7); k++) steps.push(Math.hypot(path[k][0] - path[k - 1][0], path[k][1] - path[k - 1][1]))
  steps.sort((a, b) => a - b)
  return steps.length > 0 && steps[Math.floor(steps.length / 2)] < 3.5
}

/** The hypothesis behind the best alternative (counterfactual = best_alt value). */
export function bestHypothesis(d: Doors, metric: string, alt: number | null): Hypothesis | undefined {
  if (alt == null || !d.insight) return undefined
  return d.insight.hypotheses.find((h) => h.counterfactual_p_goal != null && Math.abs(h.counterfactual_p_goal - alt) < 0.0015 && (h.metric ?? metric) === metric)
}

/** Short, localised name of the alternative ("Dribble forward", "Pass to Brann"). */
export function altName(m: MatchIndex, d: Doors, lang: Lang, h: Hypothesis | undefined): string {
  const iv = h?.intervention
  const params = (iv?.params ?? {}) as Record<string, unknown>
  const then = (params.then_action ?? {}) as Record<string, unknown>
  const action = String(params.action ?? then.action ?? '')
  const name = (id: unknown) => surname(m.player(String(id ?? ''))?.name ?? '')
  if (iv?.kind === 'move_player' && params.player_id) return tf(lang, 'alt_move', { name: name(params.player_id) })
  if (action === 'carry') return t(lang, 'alt_carry')
  if (action === 'shoot') return t(lang, 'alt_shoot')
  if (action === 'pass' && params.target_id) return tf(lang, 'alt_pass', { name: name(params.target_id) })
  if (lang === 'en' && d.alt_label) return d.alt_label
  return t(lang, 'alt_generic')
}

/** Futures simulated behind a moment: rollouts per seed x seeds x (the real action + each alternative). */
export function scenarioCount(d: Doors): number {
  const ins = d.insight
  const per = ins?.numbers.n_rollouts ?? 500
  const seeds = new Set((ins?.evidence ?? []).filter((e) => e.startsWith('rollout:')).map((e) => e.split(':').pop()))
  const n = ins?.numbers.n_seeds ?? (seeds.size || 3)
  return per * n * (Math.max(1, d.tested) + 1)
}

/** One sentence: the first sentence / clause of a claim. */
export function oneSentence(text: string): string {
  const s = text.trim()
  const cut = s.search(/[;:](\s|$)|\.\s+(?=[A-ZÁÉÍÓÚÄÖÜ¿¡])/)
  const out = cut > 30 ? s.slice(0, cut) : s
  return out.replace(/[\s,]+$/, '').replace(/([^.!?])$/, '$1.')
}
