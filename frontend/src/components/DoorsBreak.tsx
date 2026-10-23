import { useEffect, useRef, useState } from 'react'
import { speaking } from '../lib/audio'
import { useMatch } from '../lib/context'
import { replayCount, wantExplainer } from '../lib/explainer'
import { comparison, minuteLabel, type Doors } from '../lib/match'
import { fmtPct, fmtPts, t, tf } from '../lib/profile'
import { checkClaim } from '../lib/verify'
import type { Lang, Overlay } from '../types'

const SHOT = new URLSearchParams(window.location.search).has('shot')
export const AUTO_MS = 8000
const MAX_MS = 20000

interface Props {
  doors: Doors
  overlay?: Overlay
  /** Ask Sliding Doors: the fan's question as the headline. */
  headline?: string
  /** Club fan / casual: the verdict and one sentence; analyst also gets the claim audit line. */
  simple?: boolean
  audit?: boolean
  lang: Lang
  /** Countdown to continue by itself (waits for a commentator clip that is still speaking). */
  auto: boolean
  /** Hold the countdown (Ask panel open). */
  hold?: boolean
  onContinue?: () => void
  onAsk?: () => void
}

/**
 * The Sliding Doors pause: the match is paused, the pitch behind shows the ghost futures, and this
 * compact card says one sentence and two numbers (what happened vs the best alternative), then
 * "Continue" (or the countdown) plays on and the card is gone.
 */
export function DoorsBreak({ doors, overlay, headline, simple, audit: showAudit, lang, auto, hold, onContinue, onAsk }: Props) {
  const { m } = useMatch()
  const cmp = comparison(doors.numbers, doors.metric)
  const hasAlt = cmp.alt != null
  const altBetter = hasAlt && cmp.alt! > cmp.actual
  const verdict = !hasAlt ? t(lang, 'no_better') : altBetter ? t(lang, 'better_existed') : t(lang, 'right_call')
  const claim = (overlay?.body || doors.claim).trim()
  const title = headline ?? (overlay?.headline && overlay.headline !== claim && !overlay.headline.startsWith(t(lang, 'replay')) ? overlay.headline : null)
  const altName = lang === 'en' && doors.alt_label ? doors.alt_label : t(lang, 'alternative')
  const audit = showAudit && doors.insight ? checkClaim(`${overlay?.headline ?? ''} ${claim}`, doors.insight, m, overlay?.evidence.length ? overlay.evidence : undefined) : undefined
  const [explain] = useState(() => wantExplainer(doors.key))
  const replays = replayCount(doors.insight).toLocaleString(lang === 'en' ? 'en-GB' : lang)

  // countdown: AUTO_MS, or until the commentator has finished the moment's clip (max 20 s)
  const [left, setLeft] = useState(AUTO_MS)
  const done = useRef(onContinue)
  done.current = onContinue
  const paused = Boolean(hold)
  const pausedRef = useRef(paused)
  pausedRef.current = paused
  useEffect(() => {
    if (!auto || SHOT) return
    let id = 0
    let last = performance.now()
    let elapsed = 0
    const t0 = last
    const step = () => {
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
    }
    id = window.setInterval(step, 100)
    return () => window.clearInterval(id)
  }, [auto])
  const secs = Math.ceil(left / 1000)

  return (
    <div className={`brk ${simple ? 'simple' : ''} ${altBetter ? 'worse' : 'ok'}`} role="dialog" aria-label={t(lang, 'replay')}>
      <div className="brk-top">
        <span className="brk-tag">
          <span className="sd-doors">
            <i />
            <i />
          </span>
          {t(lang, 'replay')} · {minuteLabel(m.bundle, doors.decision_frame)}
        </span>
        <span className={`brk-verdict ${altBetter ? 'worse' : 'ok'}`}>{verdict}</span>
      </div>
      {explain && <div className="brk-explain">{tf(lang, 'sd_explain', { n: replays })}</div>}
      {title && <div className="brk-title">{title}</div>}
      <div className="brk-claim">{claim}</div>
      <div className="brk-nums">
        <div className={`brk-num real ${altBetter ? '' : 'win'}`}>
          <span className="brk-lbl">
            <i className="lg-real" />
            {t(lang, 'what_happened')}
          </span>
          <b>{fmtPct(lang, cmp.actual)}</b>
        </div>
        {hasAlt ? (
          <div className={`brk-num alt ${altBetter ? 'win' : ''}`}>
            <span className="brk-lbl">
              <i className="lg-alt" />
              {altName}
            </span>
            <b>{fmtPct(lang, cmp.alt!)}</b>
            <em className={altBetter ? 'up' : 'down'}>{fmtPts(lang, cmp.alt! - cmp.actual)}</em>
          </div>
        ) : (
          <div className="brk-num alt none">
            <span className="brk-lbl">{t(lang, 'alternative')}</span>
            <b className="brk-none">{t(lang, 'no_better')}</b>
          </div>
        )}
        <div className="brk-metric">{t(lang, cmp.metric)}</div>
      </div>
      {audit && (
        <div className={`brk-audit ${audit.ok ? 'ok' : 'bad'}`} title={audit.untraced.length ? `not produced by the engine: ${audit.untraced.join(', ')}` : ''}>
          {audit.ok ? '✓' : '✗'} {audit.traced}/{audit.numbers} {t(lang, 'numbers_traced')} · {doors.tested} {t(lang, 'tested')}
        </div>
      )}
      <div className="brk-actions">
        {onContinue && (
          <button className="brk-go" onClick={onContinue} autoFocus>
            {auto && !SHOT && (
              <svg className="brk-ring" viewBox="0 0 36 36" aria-hidden>
                <circle cx="18" cy="18" r="15" />
                <circle cx="18" cy="18" r="15" className="fill" style={{ strokeDashoffset: `${94.25 * (1 - Math.min(1, left / AUTO_MS))}` }} />
              </svg>
            )}
            {t(lang, 'continue')} ▶
          </button>
        )}
        {onAsk && (
          <button className="brk-ask" onClick={onAsk}>
            <span className="ask-spark">?</span>
            {t(lang, 'ask_moment')}
          </button>
        )}
        {auto && !SHOT && <span className="brk-count">{paused ? '❚❚' : tf(lang, 'resume_in', { s: secs })}</span>}
      </div>
    </div>
  )
}
