import { useMatch } from '../lib/context'
import { t } from '../lib/profile'
import { usePresence } from '../lib/usePresence'
import type { Lang, Overlay, Team } from '../types'

interface Row {
  label: string
  home?: string
  away?: string
  value?: string
}

function teamColor(o: Overlay, fallback: string, colors: Record<Team, string>): string {
  const team = o.payload.team as Team | undefined
  return team ? colors[team] : fallback
}

function Evidence({ o }: { o: Overlay }) {
  if (!o.evidence.length) return null
  return <div className="ov-evidence">evidence · {o.evidence.slice(0, 3).join(' · ')}</div>
}

export function LowerThird({ overlay }: { overlay?: Overlay }) {
  const { m } = useMatch()
  const { shown, leaving } = usePresence(overlay)
  if (!shown) return null
  const colors = { home: m.bundle.match.home.color, away: m.bundle.match.away.color }
  const accent = teamColor(shown, '#ffc83d', colors)
  const player = m.player(shown.payload.player_id as string | undefined)
  return (
    <div className={`lower-third ${shown.type} ${leaving ? 'leave' : 'enter'}`} style={{ '--accent': accent } as React.CSSProperties}>
      <div className="lt-accent">{player ? player.number : shown.type === 'alert' ? '!' : '•'}</div>
      <div className="lt-text">
        <div className="lt-headline">{shown.headline}</div>
        {shown.body && <div className="lt-body">{shown.body}</div>}
      </div>
      <Evidence o={shown} />
    </div>
  )
}

export function SidePanel({ overlay, lang }: { overlay?: Overlay; lang: Lang }) {
  const { m } = useMatch()
  const { shown, leaving } = usePresence(overlay)
  if (!shown) return null
  const rows = (shown.payload.rows as Row[] | undefined) ?? []
  const insight = m.insight(shown.payload.insight_id as string | undefined)
  const player = m.player(shown.payload.player_id as string | undefined)
  const { home, away } = m.bundle.match
  return (
    <div className={`side-panel ${shown.type} ${leaving ? 'leave' : 'enter'}`}>
      <div className="sp-head">
        {player && <span className="sp-num" style={{ background: m.club(player.team).color }}>{player.number}</span>}
        <span>{shown.headline}</span>
      </div>
      {shown.body && <div className="sp-body">{shown.body}</div>}
      {rows.length > 0 && (
        <div className="sp-rows">
          {rows.some((r) => r.home !== undefined) && (
            <div className="sp-row sp-row-head">
              <span style={{ color: home.color }}>{home.short}</span>
              <span />
              <span style={{ color: away.color }}>{away.short}</span>
            </div>
          )}
          {rows.map((r, i) =>
            r.value !== undefined ? (
              <div key={i} className="sp-row sp-row-single" style={{ animationDelay: `${120 + i * 90}ms` }}>
                <span className="sp-label">{r.label}</span>
                <span className="sp-val">{r.value}</span>
              </div>
            ) : (
              <div key={i} className="sp-row" style={{ animationDelay: `${120 + i * 90}ms` }}>
                <span className="sp-val">{r.home}</span>
                <span className="sp-label">{r.label}</span>
                <span className="sp-val">{r.away}</span>
              </div>
            ),
          )}
        </div>
      )}
      {insight && (
        <div className="sp-verified">
          <span className={`chip ${insight.confidence}`}>{t(lang, insight.confidence)}</span>
          <span>
            ✓ {t(lang, 'verified')} · {insight.hypotheses.length} {t(lang, 'tested')}
          </span>
        </div>
      )}
      <Evidence o={shown} />
    </div>
  )
}

export function Fullscreen({ overlay }: { overlay?: Overlay }) {
  const { m } = useMatch()
  const { shown, leaving } = usePresence(overlay, 500)
  if (!shown) return null
  const colors = { home: m.bundle.match.home.color, away: m.bundle.match.away.color }
  const accent = teamColor(shown, '#ffc83d', colors)
  const bullets = (shown.payload.bullets as string[] | undefined) ?? []
  return (
    <div className={`fullscreen ${shown.type} ${leaving ? 'leave' : 'enter'}`} style={{ '--accent': accent } as React.CSSProperties}>
      <div className="fs-sweep" />
      <div className="fs-card">
        <div className="fs-headline">{shown.headline}</div>
        {shown.body && <div className="fs-body">{shown.body}</div>}
        {bullets.length > 0 && (
          <ul className="fs-bullets">
            {bullets.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
