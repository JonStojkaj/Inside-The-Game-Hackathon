import { useMemo } from 'react'
import { useMatch } from '../../lib/context'
import { activeAlert, decisionRecord, decisionsSoFar, heatmap, playerAlerts } from '../../lib/derive'
import { statsAt } from '../../lib/match'
import { useFrame } from '../../lib/playback'
import { fmtNum, fmtPct, t, tf } from '../../lib/profile'
import { usePresence } from '../../lib/usePresence'
import type { Insight, Lang } from '../../types'
import { Heatmap } from '../Overlays'

/** Live player card: speed, top speed, pass accuracy, pass difficulty, decisions, heatmap. */
export function PlayerCard({ pid, lang }: { pid: string; lang: Lang }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const p = m.player(pid)
  const s = statsAt(m.bundle, frame)
  // the heatmap only changes visibly every second or so
  const bucket = Math.floor(frame / 10) * 10
  const cells = useMemo(() => heatmap(m, pid, bucket), [m, pid, bucket])
  if (!p) return null
  const ps = s?.players[pid]
  const club = m.club(p.team)
  const passes = m.bundle.events.filter((e) => e.type === 'pass' && e.player_id === pid && e.frame <= frame && e.meta.difficulty != null)
  const avgDiff = passes.length ? passes.reduce((a, e) => a + Number(e.meta.difficulty), 0) / passes.length : null
  const rec = decisionsSoFar(m, pid, frame)
  const speed = ps?.speed_kmh ?? 0
  const top = ps?.top_speed_kmh ?? 0
  return (
    <div className="pc" style={{ '--pc': club.color } as React.CSSProperties}>
      <div className="pc-head">
        <div className="pc-num">{p.number}</div>
        <div>
          <div className="pc-name">{p.name}</div>
          <div className="pc-meta">
            {p.position} · {club.name}
          </div>
        </div>
      </div>
      <div className="pc-speed">
        <div className="pc-speed-num">
          {Math.round(speed)}
          <small>km/h</small>
        </div>
        <div className="pc-speed-bar">
          <i style={{ width: `${top > 0 ? Math.min(1, speed / top) * 100 : 0}%` }} />
        </div>
        <div className="pc-speed-label">{t(lang, 'speed')}</div>
      </div>
      <div className="pc-stats">
        <div>
          <b>{fmtNum(lang, top)}</b>
          <span>{t(lang, 'top_speed')} km/h</span>
        </div>
        <div>
          <b>{ps && ps.passes > 0 ? fmtPct(lang, ps.passes_completed / ps.passes, 0) : '–'}</b>
          <span>{t(lang, 'pass_acc')}</span>
        </div>
        <div>
          <b>{avgDiff == null ? '–' : Math.round(avgDiff)}</b>
          <span>{t(lang, 'avg_difficulty')}</span>
        </div>
        <div>
          <b>{rec.total ? `${rec.right}/${rec.total}` : '–'}</b>
          <span>
            {t(lang, 'decisions')} ✓
          </span>
        </div>
      </div>
      <div className="pc-heat">
        <span>{t(lang, 'heatmap')}</span>
        <Heatmap cells={cells} color={club.color} />
      </div>
    </div>
  )
}

/** Alert strip when the followed player does something notable. */
export function PlayerAlert({ pid, lang }: { pid: string; lang: Lang }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const alerts = useMemo(() => playerAlerts(m, pid, lang), [m, pid, lang])
  const { shown, leaving } = usePresence(activeAlert(alerts, frame))
  const p = m.player(pid)
  if (!shown || !p) return null
  return (
    <div className={`lower-third alert pf-alert ${leaving ? 'leave' : 'enter'}`} style={{ '--accent': m.club(p.team).color } as React.CSSProperties}>
      <div className="lt-accent">{p.number}</div>
      <div className="lt-text">
        <div className="lt-headline">
          {shown.headline} · {p.name}
        </div>
        {shown.body && <div className="lt-body">{shown.body}</div>}
        <div className="ov-evidence">evidence · {shown.evidence.join(' · ')}</div>
      </div>
    </div>
  )
}

/** "Best of N options": the real decision ranked against the alternatives the engine played out. */
export function DecisionRecordView({ ins, lang }: { ins: Insight; lang: Lang }) {
  const { m } = useMatch()
  const rec = decisionRecord(m, ins, lang)
  const max = Math.max(...rec.options.map((o) => o.p), 0.0001)
  const best = rec.rank === 1
  return (
    <div className="dr">
      <div className="dr-head">
        <span>{t(lang, 'decision_record')}</span>
        <b className={best ? 'ok' : 'warn'}>{best ? tf(lang, 'best_of', { n: rec.n }) : tf(lang, 'rank_of', { r: rec.rank, n: rec.n })}</b>
      </div>
      {rec.options.map((o, i) => (
        <div key={i} className={`dr-row ${o.chosen ? 'chosen' : ''} ${o.status === 'accepted' ? '' : 'noise'}`} style={{ animationDelay: `${700 + i * 160}ms` }}>
          <span className="dr-label">
            {o.chosen && '★ '}
            {o.label}
            {o.chosen && <em>{t(lang, 'his_choice')}</em>}
            {o.status !== 'accepted' && <em>{t(lang, 'noise')}</em>}
          </span>
          <span className="dr-bar">
            <i style={{ width: `${(o.p / max) * 100}%` }} />
          </span>
          <b>{fmtPct(lang, o.p)}</b>
        </div>
      ))}
    </div>
  )
}
