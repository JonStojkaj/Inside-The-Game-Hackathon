import { useMatch } from '../../lib/context'
import { interventionLabel } from '../../lib/derive'
import { fmtPct, fmtPts, t } from '../../lib/profile'
import { outcome } from '../../lib/verify'
import type { Insight, Lang } from '../../types'

/** Every hypothesis the explain team tested for this moment, with its rollout numbers. */
export function Hypotheses({ ins, lang }: { ins: Insight; lang: Lang }) {
  const { m } = useMatch()
  return (
    <div className="hyp">
      <div className="hyp-head">
        {t(lang, 'hypotheses')} <b>{ins.hypotheses.length}</b>
      </div>
      {ins.hypotheses.map((h, i) => {
        const oc = outcome(h)
        const has = h.baseline_p_goal != null && h.counterfactual_p_goal != null
        const d = has ? h.counterfactual_p_goal! - h.baseline_p_goal! : 0
        return (
          <div key={i} className={`hyp-row ${oc}`} style={{ animationDelay: `${900 + i * 140}ms` }}>
            <span className={`hyp-chip ${oc}`}>{t(lang, oc === 'rejected' ? 'rejected_one' : oc)}</span>
            <span className="hyp-label">{interventionLabel(m, lang, h)}</span>
            {has && (
              <span className="hyp-nums">
                {fmtPct(lang, h.baseline_p_goal!)} → <b>{fmtPct(lang, h.counterfactual_p_goal!)}</b> <em className={d >= 0 ? 'up' : 'down'}>{fmtPts(lang, d)}</em>
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
