import { useMatch } from '../../lib/context'
import { interventionLabel } from '../../lib/derive'
import { statsAt } from '../../lib/match'
import { useFrame } from '../../lib/playback'
import { fmtNum, fmtPct, fmtPts, surname, t } from '../../lib/profile'
import { outcome } from '../../lib/verify'
import type { Insight, Lang, MatchEvent } from '../../types'

function lastEvent(events: MatchEvent[], frame: number, pick: (e: MatchEvent) => boolean): MatchEvent | undefined {
  for (let i = events.length - 1; i >= 0; i--) if (events[i].frame <= frame && pick(events[i])) return events[i]
  return undefined
}

/** Cumulative xG per team from the shot events up to `frame`. */
function xgSoFar(events: MatchEvent[], frame: number): Record<'home' | 'away', number> {
  const out = { home: 0, away: 0 }
  for (const e of events) {
    if (e.frame > frame) break
    if (e.type === 'shot' && e.team && e.meta.xg != null) out[e.team] += Number(e.meta.xg)
  }
  return out
}

/**
 * The analyst's always-on data HUD, one glanceable number per row and one plain-language line
 * under each: control vs chaos (hero), pressing, xG flow, last pass difficulty.
 */
export function AnalystHud({ lang }: { lang: Lang }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const s = statsAt(m.bundle, frame)
  if (!s) return null
  const { home, away } = m.bundle.match
  const chaos = s.control.chaos ?? 0
  const ct = s.control.control_team
  const pass = lastEvent(m.bundle.events, frame, (e) => e.type === 'pass')
  const trend = s.rhythm.trend ?? 'steady'
  const name = (id: string | null) => surname(m.player(id)?.name ?? '–')
  const diff = Number(pass?.meta.difficulty ?? 0)
  const xg = xgSoFar(m.bundle.events, frame)
  const xgTotal = xg.home + xg.away
  const pressMax = Math.max(1, s.pressing.home ?? 0, s.pressing.away ?? 0)

  return (
    <div className="hud">
      <div className="hud-head">
        <span className="hud-dot" />
        {t(lang, 'hud')}
      </div>

      <div className="hud-row hud-hero" title={t(lang, 'hud_control_hint')}>
        <div className="hud-gauge-labels">
          <span>{t(lang, 'control')}</span>
          <span>{t(lang, 'chaos')}</span>
        </div>
        <div className="ps-gauge">
          <i style={{ left: `${chaos * 100}%` }} />
        </div>
        <div className="hud-sub">
          {ct ? (
            <>
              <b style={{ color: m.club(ct).color }}>{m.club(ct).short}</b> {t(lang, 'in_control')}
            </>
          ) : (
            t(lang, 'chaos')
          )}
          <span className="hud-sep">·</span>
          {t(lang, 'hud_tempo')} <b>{fmtNum(lang, s.rhythm.actions_per_min ?? 0)}</b>/min{' '}
          <span className={`hud-trend ${trend}`}>{trend === 'rising' ? '▲' : trend === 'falling' ? '▼' : '■'}</span>
        </div>
        <div className="hud-hint">{t(lang, 'hud_control_hint')}</div>
      </div>

      <div className="hud-row" title={t(lang, 'hud_pressing_hint')}>
        <div className="hud-label">{t(lang, 'pressing')}</div>
        {[home, away].map((c) => {
          const v = s.pressing[c.key] ?? 0
          return (
            <div key={c.key} className="hud-bar">
              <span>{c.short}</span>
              <div>
                <i style={{ width: `${(v / pressMax) * 100}%`, background: c.color }} />
              </div>
              <b>{fmtNum(lang, v, 1)}</b>
            </div>
          )
        })}
        <div className="hud-hint">{t(lang, 'hud_pressing_hint')}</div>
      </div>

      <div className="hud-row" title={t(lang, 'hud_xg_hint')}>
        <div className="hud-label">{t(lang, 'hud_xg')}</div>
        <div className="hud-split">
          <b style={{ color: home.color }}>{fmtNum(lang, xg.home, 2)}</b>
          <div>
            <i style={{ width: `${xgTotal ? (xg.home / xgTotal) * 100 : 50}%`, background: home.color }} />
            <i style={{ width: `${xgTotal ? (xg.away / xgTotal) * 100 : 50}%`, background: away.color }} />
          </div>
          <b style={{ color: away.color }}>{fmtNum(lang, xg.away, 2)}</b>
        </div>
        <div className="hud-hint">{t(lang, 'hud_xg_hint')}</div>
      </div>

      {pass && (
        <div className="hud-row" title={t(lang, 'hud_pass_hint')}>
          <div className="hud-label">
            {t(lang, 'last_pass')} <span className={`hud-oc ${pass.outcome === 'complete' ? 'ok' : 'bad'}`}>{pass.outcome === 'complete' ? '✓' : '✗'}</span>
            <span className="hud-line-inline">
              {name(pass.player_id)} → {name(pass.target_id)}
            </span>
          </div>
          <div className="hud-bar diff">
            <span>{t(lang, 'difficulty')}</span>
            <div>
              <i style={{ width: `${Math.min(100, diff)}%` }} />
            </div>
            <b>{Math.round(diff)}/100</b>
          </div>
          <div className="hud-hint">{t(lang, 'hud_pass_hint')}</div>
        </div>
      )}
    </div>
  )
}

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
