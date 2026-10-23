import { useEffect, useRef, useState } from 'react'
import { ask, askAvailable, askBase, AskFailure, askMenu, type AskMoment, type AskResult, type AskStep, type AskSuggestion } from '../lib/ask'
import { useMatch } from '../lib/context'
import { fmtPct, surname, t, tf } from '../lib/profile'
import { checkClaim } from '../lib/verify'
import type { Lang } from '../types'
import './ask.css'

// one feature check per page load; null = no backend (static demo): the button is hidden
let available: Promise<boolean | null> | null = null
function useAskAvailable(): boolean | null | undefined {
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

export function AskButton({ lang, open, onToggle }: { lang: Lang; open: boolean; onToggle: () => void }) {
  const ok = useAskAvailable()
  if (ok == null) return null
  return (
    <button className={`ask-btn ${open ? 'on' : ''}`} onClick={onToggle} aria-expanded={open}>
      <span className="ask-spark">?</span>
      {t(lang, 'ask_button')}
    </button>
  )
}

/** The fan's question in the viewer's language, from a menu item (names from the match, never invented). */
function phrase(lang: Lang, s: AskSuggestion): string {
  return tf(lang, `ask_q_${s.kind}`, {
    player: surname(s.player),
    target: surname(s.target ?? ''),
    defender: surname(s.defender ?? ''),
  })
}

const pctText = (lang: Lang, v?: string) => (v ? fmtPct(lang, parseFloat(v) / 100) : '')

function stepText(lang: Lang, s: AskStep): string {
  const n = (1500).toLocaleString(lang === 'en' ? 'en-GB' : lang)
  const experiment = s.experiment ? `if ${s.experiment}` : ''
  return tf(lang, `ask_s_${s.code}`, {
    n,
    value: pctText(lang, s.value),
    experiment: experiment.charAt(0).toUpperCase() + experiment.slice(1),
    accepted: s.accepted ?? 0,
    rejected: s.rejected ?? 0,
  })
}

type Phase = { kind: 'idle' } | { kind: 'running'; question: string } | { kind: 'done'; result: AskResult; askedId: string | null } | { kind: 'error'; code: string; retry?: number }

/**
 * Ask Sliding Doors: pause, ask "what if ...?", watch the agents work (streamed steps), get a verified answer.
 * The answer opens as a Sliding Doors replay on every screen (ghost futures + claim, audited by verify.ts).
 */
export function AskPanel({ lang, onClose }: { lang: Lang; onClose: () => void }) {
  const { m, pb, addAsked, setForcedInsight } = useMatch()
  const matchId = m.bundle.match.match_id
  const base = askBase()
  const ok = useAskAvailable()
  const [frame] = useState(() => Math.floor(pb.frame))
  const [moment, setMoment] = useState<AskMoment | null>(null)
  const [suggestions, setSuggestions] = useState<AskSuggestion[]>([])
  const [question, setQuestion] = useState('')
  const [steps, setSteps] = useState<AskStep[]>([])
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [elapsed, setElapsed] = useState(0)
  const abort = useRef<AbortController | null>(null)

  useEffect(() => {
    pb.pause()
    return () => abort.current?.abort()
  }, [pb])

  useEffect(() => {
    if (ok !== true) return
    let live = true
    askMenu(base, matchId, frame)
      .then((r) => {
        if (!live) return
        setMoment(r.moment)
        setSuggestions(r.suggestions)
      })
      .catch((e: unknown) => live && setPhase({ kind: 'error', code: e instanceof AskFailure ? e.code : 'failed' }))
    return () => {
      live = false
    }
  }, [ok, base, matchId, frame])

  useEffect(() => {
    if (phase.kind !== 'running') return
    const t0 = performance.now()
    const id = window.setInterval(() => setElapsed((performance.now() - t0) / 1000), 200)
    return () => window.clearInterval(id)
  }, [phase.kind])

  const send = async (q: string) => {
    const text = q.trim()
    if (text.length < 3 || phase.kind === 'running') return
    setQuestion(text)
    setSteps([])
    setElapsed(0)
    setPhase({ kind: 'running', question: text })
    abort.current?.abort()
    const ctrl = new AbortController()
    abort.current = ctrl
    try {
      const result = await ask(base, matchId, { frame, question: text, lang, moment_id: moment?.id }, (s) => setSteps((xs) => [...xs, s]), ctrl.signal)
      let askedId: string | null = null
      if (result.answered && result.insight) {
        askedId = `${result.insight.id}-ask-${Date.now()}`
        addAsked({ ...result.insight, id: askedId, claim: result.claim }, text)
        setForcedInsight(askedId)
      }
      setPhase({ kind: 'done', result, askedId })
    } catch (e: unknown) {
      if (ctrl.signal.aborted) return
      setPhase(e instanceof AskFailure ? { kind: 'error', code: e.code, retry: e.retryAfter } : { kind: 'error', code: 'failed' })
    }
  }

  const log = steps.filter((s) => s.code !== 'done')
  const disabled = ok === false
  const running = phase.kind === 'running'
  const result = phase.kind === 'done' ? phase.result : null
  const asked = phase.kind === 'done' && phase.askedId ? m.insight(phase.askedId) : undefined
  const audit = asked ? checkClaim(asked.claim, asked, m) : undefined
  const chips = (list: AskSuggestion[]) => (
    <div className="ask-chips">
      {list.map((s) => (
        <button key={s.experiment_id} className="ask-chip" disabled={running} onClick={() => void send(phrase(lang, s))}>
          {phrase(lang, s)}
        </button>
      ))}
    </div>
  )

  return (
    <aside className="ask-panel" role="dialog" aria-label={t(lang, 'ask_title')}>
      <header className="ask-head">
        <div>
          <div className="ask-title">
            <span className="ask-spark">?</span>
            {t(lang, 'ask_title')}
          </div>
          <div className="ask-sub">{t(lang, 'ask_sub')}</div>
        </div>
        <button className="ask-x" onClick={onClose} aria-label={t(lang, 'ask_close')}>
          ×
        </button>
      </header>

      {disabled && <div className="ask-msg">{t(lang, 'ask_err_disabled')}</div>}
      {!disabled && moment && (
        <div className="ask-about">
          {/* the backend's decision label is English; other languages name the kind of moment */}
          {tf(lang, 'ask_about', {
            label: lang === 'en' ? moment.label : t(lang, moment.key_moment ? `k_${moment.kind}` : 'ask_scene'),
            minute: moment.minute + 1,
          })}
        </div>
      )}

      {!disabled && (
        <form
          className="ask-form"
          onSubmit={(e) => {
            e.preventDefault()
            void send(question)
          }}
        >
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={t(lang, 'ask_placeholder')}
            maxLength={200}
            disabled={running || phase.kind === 'error' && phase.code === 'no_moment'}
            autoFocus
          />
          <button type="submit" disabled={running || question.trim().length < 3}>
            {t(lang, 'ask_send')}
          </button>
        </form>
      )}

      {!disabled && phase.kind === 'idle' && suggestions.length > 0 && (
        <>
          <div className="ask-try">{t(lang, 'ask_try')}</div>
          {chips(suggestions)}
        </>
      )}

      {running && (
        <ol className="ask-steps">
          {log.map((s, i) => (
            <li key={i} className={i === log.length - 1 ? 'now' : 'ok'}>
              <span className="ask-dot" />
              {stepText(lang, s)}
            </li>
          ))}
          <li className="ask-clock">{elapsed.toFixed(1)} s</li>
        </ol>
      )}
      {!running && log.length > 0 && (
        // the answer is on screen as a replay: keep the agents' work one click away so the panel stays small
        <details className="ask-log">
          <summary>{tf(lang, 'ask_log', { n: log.length })}</summary>
          <ol className="ask-steps">
            {log.map((s, i) => (
              <li key={i} className="ok">
                <span className="ask-dot" />
                {stepText(lang, s)}
              </li>
            ))}
          </ol>
        </details>
      )}

      {result && result.answered && (
        <div className="ask-answer">
          <div className="ask-label">{t(lang, 'ask_answer')}</div>
          <p className="ask-claim">{result.claim}</p>
          <div className="ask-meta">
            {audit && (
              <span className={audit.ok ? 'ok' : 'bad'}>
                {audit.ok ? '✓' : '✗'} {audit.traced}/{audit.numbers} {t(lang, 'numbers_traced')}
              </span>
            )}
            <span>
              {result.cached
                ? t(lang, 'ask_meta_cached')
                : tf(lang, 'ask_meta', {
                    n: ((result.numbers.n_rollouts ?? 500) * (result.numbers.n_seeds ?? 3) * (1 + result.hypotheses.length)).toLocaleString(lang === 'en' ? 'en-GB' : lang),
                    s: (result.timings.total_ms / 1000).toFixed(1),
                  })}
            </span>
          </div>
          <div className="ask-actions">
            {phase.kind === 'done' && phase.askedId && (
              <button className="ask-watch" onClick={() => setForcedInsight(phase.askedId)}>
                ▶ {t(lang, 'ask_watch')}
              </button>
            )}
            <button className="ask-again" onClick={() => setPhase({ kind: 'idle' })}>
              {t(lang, 'ask_again')}
            </button>
          </div>
        </div>
      )}

      {result && !result.answered && (
        <div className="ask-answer none">
          <p className="ask-claim">{t(lang, 'ask_unanswerable')}</p>
          {chips(result.suggestions ?? suggestions)}
        </div>
      )}

      {phase.kind === 'error' && <div className="ask-msg bad">{tf(lang, `ask_err_${phase.code in ERRORS ? phase.code : 'failed'}`, { s: phase.retry ?? 10 })}</div>}
    </aside>
  )
}

const ERRORS = { disabled: 1, busy: 1, rate_limited: 1, timeout: 1, no_moment: 1, unavailable: 1, failed: 1 }
