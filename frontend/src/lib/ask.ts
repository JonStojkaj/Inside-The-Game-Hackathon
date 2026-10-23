import { useEffect, useState } from 'react'
import type { Hypothesis, Insight, Lang } from '../types'

/**
 * Client for Ask Sliding Doors (backend/app/api/ask.py): a fan's "What if ...?" answered live by the
 * explain team. The API streams NDJSON: {type: "step"} lines while the agents work, then {type: "result"}
 * or {type: "error"}. Errors before any work starts come back as plain JSON with a status code.
 *
 * Where the API lives: ?ask=<origin> (e.g. http://localhost:8000), else the data source's API origin in api
 * mode, else the page's own origin (the deployed container; in `npm run dev` Vite proxies /api to :8000).
 */
export function askBase(search = window.location.search): string {
  const q = new URLSearchParams(search)
  if (q.has('ask')) return (q.get('ask') ?? '').replace(/\/$/, '')
  if (q.has('api')) return (q.get('api') ?? '').replace(/\/$/, '')
  return (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')
}

export type SuggestionKind = 'shoot' | 'pass' | 'tight' | 'carry'

export interface AskSuggestion {
  experiment_id: string
  kind: SuggestionKind
  player: string
  target?: string
  defender?: string
  meters?: number
  question: string // English, from the backend
}

export interface AskMoment {
  id: string
  kind: string
  frame: number
  decision_frame: number
  minute: number
  team: string
  label: string
  key_moment: boolean
}

export interface AskStep {
  code: string
  text: string
  t_ms: number
  value?: string
  experiment?: string
  accepted?: number
  rejected?: number
  items?: string[]
}

export interface AskResult {
  answered: boolean
  cached: boolean
  question: string
  moment: AskMoment
  claim: string
  claim_en: string
  claim_lang: Lang
  metric: string
  numbers: Record<string, number>
  confidence: 'clear' | 'slight'
  hypotheses: Hypothesis[]
  insight: Insight | null
  reason?: string
  suggestions?: AskSuggestion[]
  runtime: string
  timings: { total_ms: number }
}

export class AskFailure extends Error {
  code: string
  retryAfter?: number
  constructor(code: string, message: string, retryAfter?: number) {
    super(message)
    this.code = code
    this.retryAfter = retryAfter
  }
}

const url = (base: string, matchId: string, q = '') => `${base}/api/matches/${encodeURIComponent(matchId)}/ask${q}`

/** null = no backend reachable (static demo without API): the feature is hidden. */
export async function askAvailable(base: string): Promise<boolean | null> {
  try {
    const res = await fetch(`${base}/api/features`)
    if (!res.ok) return null
    const data = (await res.json()) as { ask?: boolean }
    return Boolean(data.ask)
  } catch {
    return null
  }
}

async function failure(res: Response): Promise<AskFailure> {
  try {
    const data = (await res.json()) as { error?: string; message?: string; retry_after_s?: number }
    return new AskFailure(data.error ?? `http_${res.status}`, data.message ?? res.statusText, data.retry_after_s)
  } catch {
    return new AskFailure(`http_${res.status}`, res.statusText)
  }
}

export async function askMenu(base: string, matchId: string, frame: number): Promise<{ moment: AskMoment; suggestions: AskSuggestion[] }> {
  const res = await fetch(url(base, matchId, `?frame=${Math.floor(frame)}`))
  if (!res.ok) throw await failure(res)
  const data = (await res.json()) as { enabled: boolean; moment?: AskMoment; suggestions?: AskSuggestion[]; error?: string; message?: string }
  if (!data.enabled) throw new AskFailure('disabled', 'disabled')
  if (data.error || !data.moment) throw new AskFailure(data.error ?? 'failed', data.message ?? '')
  return { moment: data.moment, suggestions: data.suggestions ?? [] }
}

export async function ask(
  base: string,
  matchId: string,
  body: { frame: number; question: string; lang: Lang; moment_id?: string },
  onStep: (s: AskStep) => void,
  signal?: AbortSignal,
): Promise<AskResult> {
  const res = await fetch(url(base, matchId), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...body, frame: Math.floor(body.frame) }),
    signal,
  })
  if (!res.ok) throw await failure(res)
  if (!res.body) throw new AskFailure('failed', 'no response body')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    buf += decoder.decode(value, { stream: !done })
    let nl: number
    while ((nl = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, nl).trim()
      buf = buf.slice(nl + 1)
      if (!line) continue
      const msg = JSON.parse(line) as { type: string } & Record<string, unknown>
      if (msg.type === 'step') onStep(msg as unknown as AskStep)
      else if (msg.type === 'result') return msg as unknown as AskResult
      else if (msg.type === 'error') throw new AskFailure(String(msg.error ?? 'failed'), String(msg.message ?? ''))
    }
    if (done) throw new AskFailure('failed', 'stream ended without an answer')
  }
}

// one feature check per page load; null = no backend (static demo): the button is hidden
let available: Promise<boolean | null> | null = null
/** Ask feature check (undefined while checking, null = no backend). */
export function useAskAvailable(): boolean | null | undefined {
  const [ok, setOk] = useState<boolean | null | undefined>(undefined)
  useEffect(() => {
    let live = true
    available ??= askAvailable(askBase())
    void available.then((v) => live && setOk(v))
    return () => {
      live = false
    }
  }, [])
  return ok
}

