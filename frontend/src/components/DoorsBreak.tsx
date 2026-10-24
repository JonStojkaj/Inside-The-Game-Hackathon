import { useEffect, useRef, useState } from 'react'
import { speaking } from '../lib/audio'
import { useMatch } from '../lib/context'
import { comparison, minuteLabel, type Doors } from '../lib/match'
import { fmtPct, fmtPts, t, tf } from '../lib/profile'
import { altName, bestHypothesis, oneSentence, scenarioCount, usePhase } from '../lib/story'
import { checkClaim } from '../lib/verify'
import type { Lang, Overlay } from '../types'

const SHOT = new URLSearchParams(window.location.search).has('shot')
export const AUTO_MS = 8000
const MAX_MS = 16000

interface Props {
  doors: Doors
  overlay?: Overlay
  /** performance.now() when the break opened: the pitch story runs on the same clock. */
  since: number
  /** Ask Sliding Doors: the fan's question as the headline. */
  headline?: string
  /** Analyst: a tiny "numbers traced" chip. */
  audit?: boolean
  lang: Lang
  /** Countdown to continue by itself once the verdict is shown (waits for the commentator). */
  auto: boolean
  /** Hold the countdown (Ask panel open). */
  hold?: boolean
  onContinue?: () => void
  onAsk?: () => void
}

/**
 * The Sliding Doors pause, told as a short story over the 2D pitch: one big "Simulating N
 * scenarios…" line, then "What happened" (the real action replays), "What could have happened"
 * (one alternative plays out), then the verdict: two big numbers and one sentence.
 */
export function DoorsBreak({ doors, overlay, since, headline, audit: showAudit, lang, auto, hold, onContinue, onAsk }: Props) {
  const { m } = useMatch()
  const cmp = comparison(doors.numbers, doors.metric)
  const hasAlt = cmp.alt != null
  const altBetter = hasAlt && cmp.alt! > cmp.actual
  const { phase, progress } = usePhase(since, hasAlt && doors.alt_ghost_paths.length > 0)
  const hyp = bestHypothesis(doors, cmp.metric, cmp.alt)
  const alt = altName(m, doors, lang, hyp)
  const n = scenarioCount(doors).toLocaleString(lang === 'en' ? 'en-GB' : lang)
  const why = oneSentence(overlay?.body || doors.claim)
  const audit = showAudit && doors.insight ? checkClaim(`${overlay?.headline ?? ''} ${overlay?.body || doors.claim}`, doors.insight, m, overlay?.evidence.length ? overlay.evidence : undefined) : undefined
  const minute = minuteLabel(m.bundle, doors.decision_frame)

  // countdown once the verdict is up: AUTO_MS, or until the commentator has finished (max 16 s)
  const [left, setLeft] = useState(AUTO_MS)
  const done = useRef(onContinue)
  done.current = onContinue
  const pausedRef = useRef(Boolean(hold))
  pausedRef.current = Boolean(hold)
  const result = phase === 'result'
  useEffect(() => {
    if (!auto || SHOT || !result) return
    let last = performance.now()
    let elapsed = 0
    const t0 = last
    const id = window.setInterval(() => {
      const now = performance.now()
      if (!pausedRef.current) elapsed += now - last
      last = now
      const until = Math.min(t0 + MAX_MS, Math.max(t0 + AUTO_MS, speaking.until + 400))
      const remaining = until - t0 - elapsed
      setLeft(Math.max(0, remaining))
      if (remaining <= 0) {
        window.clearInterval(id)
        done.current?.()
      }
    }, 100)
    return () => window.clearInterval(id)
  }, [auto, result])

  const actions = (
    <div className="brk-actions">
      {onContinue && (
        <button className="brk-go" onClick={onContinue} autoFocus={result}>
          {auto && !SHOT && result && (
            <svg className="brk-ring" viewBox="0 0 36 36" aria-hidden>
              <circle cx="18" cy="18" r="15" />
              <circle cx="18" cy="18" r="15" className="fill" style={{ strokeDashoffset: `${94.25 * (1 - Math.min(1, left / AUTO_MS))}` }} />
            </svg>
          )}
          {t(lang, 'continue')} ▶
        </button>
      )}
      {onAsk && result && (
        <button className="brk-ask" onClick={onAsk} title={t(lang, 'ask_moment')}>
          <span className="ask-spark">?</span>
          {t(lang, 'ask_moment')}
        </button>
      )}
    </div>
  )

  if (phase === 'loading') {
    const step = progress < 0.4 ? 'sim_actual' : progress < 0.8 ? 'sim_alts' : 'sim_check'
    return (
      <div className="sim" role="status" aria-live="polite">
        <span className="sim-tag">
          <span className="sd-doors">
            <i />
            <i />
          </span>
          {t(lang, 'replay')} · {minute}
        </span>
        {headline && <div className="sim-q">“{headline}”</div>}
        <div className="sim-line">{tf(lang, 'simulating', { n })}</div>
        <div className="sim-bar">
          <i style={{ transform: `scaleX(${Math.max(0.04, progress)})` }} />
        </div>
        <div className="sim-step">{t(lang, step)}</div>
      </div>
    )
  }

  if (phase === 'actual' || phase === 'alt') {
    const isAlt = phase === 'alt'
    return (
      <>
        <div className={`story-pill ${isAlt ? 'alt' : 'real'}`} key={phase} role="status" aria-live="polite">
          <span className="story-step">{isAlt ? 2 : 1}</span>
          <span className="story-what">{t(lang, isAlt ? 'story_alt' : 'story_actual')}</span>
          {isAlt && <span className="story-alt">{alt}</span>}
          {!isAlt && <span className="story-num">{fmtPct(lang, cmp.actual)}</span>}
          {isAlt && cmp.alt != null && <span className="story-num">{fmtPct(lang, cmp.alt)}</span>}
        </div>
        <div className="story-skip">{actions}</div>
      </>
    )
  }

  return (
    <div className={`brk ${altBetter ? 'worse' : 'ok'}`} role="dialog" aria-label={t(lang, 'replay')}>
      <div className="brk-top">
        <span className="brk-tag">
          <span className="sd-doors">
            <i />
            <i />
          </span>
          {t(lang, 'replay')} · {minute}
        </span>
        {audit && (
          <span className={`brk-audit ${audit.ok ? 'ok' : 'bad'}`} title={`${audit.traced}/${audit.numbers} ${t(lang, 'numbers_traced')} · ${doors.tested} ${t(lang, 'tested')}`}>
            {audit.ok ? '✓' : '✗'} {t(lang, 'verified')}
          </span>
        )}
      </div>
      {headline && <div className="brk-title">“{headline}”</div>}
      <div className="brk-flow">
        <div className="brk-n real">
          <b>{fmtPct(lang, cmp.actual)}</b>
          <span>
            <i className="lg-real" />
            {t(lang, 'story_actual')}
          </span>
        </div>
        {hasAlt ? (
          <>
            <div className={`brk-arrow ${altBetter ? 'up' : 'down'}`}>
              →<em>{fmtPts(lang, cmp.alt! - cmp.actual)}</em>
            </div>
            <div className={`brk-n alt ${altBetter ? 'win' : ''}`}>
              <b>{fmtPct(lang, cmp.alt!)}</b>
              <span>
                <i className="lg-alt" />
                {alt}
              </span>
            </div>
          </>
        ) : (
          <div className="brk-n none">
            <b>✓</b>
            <span>{t(lang, 'no_better_short')}</span>
          </div>
        )}
      </div>
      <div className="brk-metric">{t(lang, cmp.metric)}</div>
      <div className="brk-why" title={overlay?.body || doors.claim}>
        {why}
      </div>
      {actions}
    </div>
  )
}
