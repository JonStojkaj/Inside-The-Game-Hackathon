import type { Insight } from '../types'

const SHOT = new URLSearchParams(window.location.search).has('shot')

// ---- first-time explainer: shown on the first Sliding Doors moment a viewer sees
const EXPLAINED = 'sliding-doors.sd-explained.v1'
let explainedKey: string | null = null

export function wantExplainer(key: string): boolean {
  if (SHOT) return true
  if (explainedKey) return explainedKey === key
  try {
    if (localStorage.getItem(EXPLAINED) === '1') return false
    localStorage.setItem(EXPLAINED, '1')
  } catch {
    // no storage: once per page load
  }
  explainedKey = key
  return true
}

/** Show the explainer again (after onboarding: a new viewer). */
export function resetExplainer(): void {
  explainedKey = null
  try {
    localStorage.removeItem(EXPLAINED)
  } catch {
    // ignore
  }
}

const DEFAULT_ROLLOUTS = 500 // futures per seed (backend N_ROLLOUTS) when the export does not say

/** Total simulated futures behind an insight: rollouts per seed x seeds (from the rollout evidence ids). */
export function replayCount(ins: Insight | undefined): number {
  const per = ins?.numbers.n_rollouts ?? DEFAULT_ROLLOUTS
  const seeds = new Set((ins?.evidence ?? []).filter((e) => e.startsWith('rollout:')).map((e) => e.split(':').pop()))
  return per * (ins?.numbers.n_seeds ?? (seeds.size || 3))
}
