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

function Spark({ values }: { values: number[] }) {
  if (values.length < 2) return null
  const lo = Math.min(...values)
  const hi = Math.max(...values, lo + 1)
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 100},${28 - ((v - lo) / (hi - lo)) * 26}`).join(' ')
  return (
    <svg className="hud-spark" viewBox="0 0 100 30" preserveAspectRatio="none">
      <polyline points={pts} />
    </svg>
  )
}

/** The analyst's always-on data HUD: control vs chaos, pressing, rhythm, last pass, last shot. */
export function AnalystHud({ lang }: { lang: Lang }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const s = statsAt(m.bundle, frame)
  if (!s) return null
  const { home, away } = m.bundle.match
  const stats = m.bundle.stats
  const i = stats.indexOf(s)
  const rhythm = stats.slice(Math.max(0, i - 60), i + 1).map((x) => x.rhythm.actions_per_min ?? 0)
  const chaos = s.control.chaos ?? 0
  const ct = s.control.control_team
  const pass = lastEvent(m.bundle.events, frame, (e) => e.type === 'pass')
  const shot = lastEvent(m.bundle.events, frame, (e) => e.type === 'shot')
  const trend = s.rhythm.trend ?? 'steady'
  const name = (id: string | null) => surname(m.player(id)?.name ?? '–')
  const diff = Number(pass?.meta.difficulty ?? 0)

  return (
    <div className="hud">
      <div className="hud-head">
        <span className="hud-dot" />
        {t(lang, 'hud')}
      </div>

      <div className="hud-row">
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
              <b style={{ color: m.club(ct).color }}>{m.club(ct).short}</b> {t(lang, 'in_control')} <b>{s.control.control_share == null ? '–' : fmtPct(lang, s.control.control_share, 0)}</b>
            </>
          ) : (
            '–'
          )}
          <span className="hud-sep">·</span>
          {t(lang, 'chaos')} <b>{fmtNum(lang, chaos, 2)}</b>
        </div>
      </div>

      <div className="hud-row">
        <div className="hud-label">{t(lang, 'pressing')}</div>
        {[home, away].map((c) => {
          const v = s.pressing[c.key] ?? 0
          return (
            <div key={c.key} className="hud-bar">
              <span>{c.short}</span>
              <div>
                <i style={{ width: `${Math.min(1, v) * 100}%`, background: c.color }} />
              </div>
              <b>{fmtNum(lang, v, 2)}</b>
            </div>
          )
        })}
      </div>

      <div className="hud-row hud-rhythm">
        <div>
          <div className="hud-label">{t(lang, 'rhythm')}</div>
          <div className="hud-big">
            {fmtNum(lang, s.rhythm.actions_per_min ?? 0)} <small>{t(lang, 'per_min')}</small>
          </div>
          <div className={`hud-trend ${trend}`}>
            {trend === 'rising' ? '▲' : trend === 'falling' ? '▼' : '■'} {t(lang, trend)}
          </div>
        </div>
        <Spark values={rhythm} />
      </div>

      {pass && (
        <div className="hud-row">
          <div className="hud-label">
            {t(lang, 'last_pass')} <span className={`hud-oc ${pass.outcome === 'complete' ? 'ok' : 'bad'}`}>{pass.outcome === 'complete' ? '✓' : '✗'}</span>
          </div>
          <div className="hud-line">
            {name(pass.player_id)} → {name(pass.target_id)}
          </div>
          <div className="hud-bar diff">
            <span>{t(lang, 'difficulty')}</span>
            <div>
              <i style={{ width: `${Math.min(100, diff)}%` }} />
            </div>
            <b>{Math.round(diff)}/100</b>
          </div>
        </div>
      )}

      {shot && (
        <div className="hud-row">
          <div className="hud-label">{t(lang, 'last_shot')}</div>
          <div className="hud-line">
            {name(shot.player_id)}
            {shot.meta.xg != null && (
              <>
                {' '}
                · xG <b>{fmtNum(lang, Number(shot.meta.xg), 2)}</b>
              </>
            )}
            {shot.meta.distance_m != null && <> · {fmtNum(lang, Number(shot.meta.distance_m))} m</>}
            {shot.outcome && <span className={`hud-oc ${shot.outcome === 'goal' ? 'ok' : ''}`}> · {shot.outcome === 'goal' ? t(lang, 'al_goal') : t(lang, shot.outcome)}</span>}
          </div>
        </div>
      )}

      <div className="hud-foot">
        {t(lang, 'pressure')} <b>{fmtNum(lang, s.pressure_on_ball, 2)}</b>
      </div>
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
