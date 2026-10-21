import { useEffect, useState } from 'react'
import { useMatch } from '../lib/context'
import { clockLabel, comparison, type Doors } from '../lib/match'
import { fmtPct, fmtPts, t } from '../lib/profile'
import { checkClaim } from '../lib/verify'
import type { Lang, Overlay } from '../types'

const SHOT = new URLSearchParams(window.location.search).has('shot')

function useCountUp(target: number, ms: number, delay: number): number {
  const [v, setV] = useState(SHOT ? target : 0)
  useEffect(() => {
    if (SHOT) return
    let raf = 0
    const t0 = performance.now() + delay
    const step = (now: number) => {
      const k = Math.min(1, Math.max(0, (now - t0) / ms))
      setV(target * (1 - Math.pow(1 - k, 3)))
      if (k < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, ms, delay])
  return v
}

interface Props {
  doors: Doors
  overlay?: Overlay
  simple?: boolean
  lang: Lang
  onClose?: () => void
}

/** DOM layer of the Sliding Doors moment; the ghost futures themselves are drawn by <Pitch>. */
export function SlidingDoorsCard({ doors, overlay, simple, lang, onClose }: Props) {
  const { m } = useMatch()
  const cmp = comparison(doors.numbers, doors.metric)
  const actual = useCountUp(cmp.actual, 1100, 600)
  const alt = useCountUp(cmp.alt ?? 0, 1100, 1900)
  const hasAlt = cmp.alt != null
  const altBetter = hasAlt && cmp.alt! > cmp.actual
  const scale = Math.max(cmp.actual, cmp.alt ?? 0, 0.0001)
  const futures = doors.ghost_paths.length + doors.alt_ghost_paths.length
  const metric = t(lang, cmp.metric)
  const headline = overlay?.headline ?? t(lang, 'replay')
  const claim = overlay?.body || doors.claim
  const audit = doors.insight ? checkClaim(`${overlay?.headline ?? ''} ${claim}`, doors.insight, m, overlay?.evidence.length ? overlay.evidence : undefined) : undefined
  const altName = lang === 'en' && doors.alt_label ? doors.alt_label : t(lang, 'alternative')
  const verdict = !hasAlt ? t(lang, 'no_better') : altBetter ? t(lang, 'better_existed') : t(lang, 'right_call')

  return (
    <div className={`sd-layer ${simple ? 'simple' : ''}`}>
      <div className="sd-badge">
        <div className="sd-title">
          <span className="sd-doors">
            <i />
            <i />
          </span>
          {t(lang, 'replay')}
        </div>
        <div className="sd-sub">
          {t(lang, 'simulated')} · {clockLabel(m.bundle, doors.decision_frame)} · <b>{futures}</b> {t(lang, 'futures')}
        </div>
        {onClose && (
          <button className="sd-close" onClick={onClose} aria-label="close">
            ×
          </button>
        )}
      </div>

      <div className="sd-legend">
        <span className="lg real">
          <i />
          {t(lang, 'what_happened')}
        </span>
        {doors.alt_ghost_paths.length > 0 && (
          <span className="lg alt">
            <i />
            {altName}
          </span>
        )}
      </div>

      <div className="sd-card">
        <div className="sd-text">
          <div className="sd-kicker">
            <span className={`sd-verdict ${altBetter ? 'worse' : 'ok'}`}>{verdict}</span>
            {!simple && hasAlt && <span className={`chip ${doors.confidence}`}>{t(lang, doors.confidence)}</span>}
          </div>
          <div className="sd-headline">{headline}</div>
          <div className="sd-claim">{claim}</div>
          {!simple && audit && (
            <div className={`sd-meta ${audit.ok ? 'ok' : 'bad'}`} title={audit.untraced.length ? `not produced by the engine: ${audit.untraced.join(', ')}` : ''}>
              {audit.ok ? '✓' : '✗'} {audit.traced}/{audit.numbers} {t(lang, 'numbers_traced')} · {audit.evidenceOk}/{audit.evidence} {t(lang, 'evidence')} ·{' '}
              {doors.tested} {t(lang, 'tested')}, {doors.rejected} {t(lang, 'rejected')}
            </div>
          )}
        </div>
        <div className="sd-probs">
          <div className={`sd-prob real ${altBetter ? '' : 'win'}`}>
            <div className="sd-plabel">{t(lang, 'what_happened')}</div>
            <div className="sd-pct">{fmtPct(lang, actual)}</div>
            <div className="sd-metric">{metric}</div>
            <div className="sd-pbar">
              <i style={{ width: `${(actual / scale) * 100}%` }} />
            </div>
          </div>
          {hasAlt ? (
            <div className={`sd-prob alt ${altBetter ? 'win' : ''}`}>
              <div className="sd-plabel">{t(lang, 'alternative')}</div>
              <div className="sd-pct">{fmtPct(lang, alt)}</div>
              <div className="sd-metric">
                {metric} <b className={altBetter ? 'up' : 'down'}>{fmtPts(lang, cmp.alt! - cmp.actual)}</b>
              </div>
              <div className="sd-pbar">
                <i style={{ width: `${(alt / scale) * 100}%` }} />
              </div>
            </div>
          ) : (
            <div className="sd-prob alt none">
              <div className="sd-plabel">{t(lang, 'alternative')}</div>
              <div className="sd-none">{t(lang, 'no_better')}</div>
              <div className="sd-metric">
                {doors.tested} {t(lang, 'tested')}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
