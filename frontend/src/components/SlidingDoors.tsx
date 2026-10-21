import { useEffect, useState } from 'react'
import { useMatch } from '../lib/context'
import { clockLabel, comparison } from '../lib/match'
import { t } from '../lib/profile'
import type { Insight, Lang, Overlay } from '../types'

function useCountUp(target: number, ms: number, delay: number): number {
  const [v, setV] = useState(0)
  useEffect(() => {
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
  insight: Insight
  overlay?: Overlay
  lang: Lang
  onClose?: () => void
}

/** DOM layer of the Sliding Doors moment; the ghost futures themselves are drawn by <Pitch>. */
export function SlidingDoorsCard({ insight, overlay, lang, onClose }: Props) {
  const { m } = useMatch()
  const cmp = comparison(insight)
  const actual = useCountUp(cmp.actual * 100, 1200, 700)
  const alt = useCountUp(cmp.alt * 100, 1200, 2100)
  const altBetter = cmp.key === 'goal_chance' ? cmp.alt > cmp.actual : cmp.alt < cmp.actual
  const rejected = insight.hypotheses.filter((h) => h.verdict === 'rejected').length
  const futures = insight.ghost_paths.length + insight.alt_ghost_paths.length
  const simple = Boolean(overlay?.payload.simple)

  return (
    <div className="sd-layer">
      <div className="sd-badge">
        <div className="sd-title">
          <span className="sd-doors">
            <i />
            <i />
          </span>
          {t(lang, 'replay')}
        </div>
        <div className="sd-sub">
          {t(lang, 'simulated')} · {insight.decision_frame != null ? clockLabel(m.bundle, insight.decision_frame) : ''} · {futures}{' '}
          {t(lang, 'futures')}
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
        <span className="lg alt">
          <i />
          {insight.alt_label || t(lang, 'alternative')}
        </span>
      </div>

      <div className="sd-card">
        <div className="sd-text">
          <div className="sd-headline">{overlay?.headline ?? t(lang, 'replay')}</div>
          <div className="sd-claim">{overlay?.body ?? insight.claim}</div>
          {!simple && (
            <div className="sd-meta">
              <span className={`chip ${insight.confidence}`}>{t(lang, insight.confidence)}</span>
              <span>
                ✓ {t(lang, 'verified')} · {insight.hypotheses.length} {t(lang, 'tested')}, {rejected} {t(lang, 'rejected')}
              </span>
            </div>
          )}
        </div>
        <div className="sd-probs">
          <div className={`sd-prob real ${altBetter ? '' : 'win'}`}>
            <div className="sd-pct">{Math.round(actual)}%</div>
            <div className="sd-plabel">
              {t(lang, 'what_happened')}
              <br />
              <small>{t(lang, cmp.key)}</small>
            </div>
            <div className="sd-pbar">
              <i style={{ width: `${Math.min(100, actual * 2)}%` }} />
            </div>
          </div>
          <div className={`sd-prob alt ${altBetter ? 'win' : ''}`}>
            <div className="sd-pct">{Math.round(alt)}%</div>
            <div className="sd-plabel">
              {t(lang, 'alternative')}
              <br />
              <small>{t(lang, cmp.key)}</small>
            </div>
            <div className="sd-pbar">
              <i style={{ width: `${Math.min(100, alt * 2)}%` }} />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
