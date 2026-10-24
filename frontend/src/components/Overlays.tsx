import { useMatch } from '../lib/context'
import { payloadPlayer } from '../lib/match'
import { fmtPct, t } from '../lib/profile'
import { usePresence } from '../lib/usePresence'
import { checkOverlay, overlayInsight } from '../lib/verify'
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
  return (
    <div className="ov-evidence">
      evidence · {o.evidence.slice(0, 2).join(' · ')}
      {o.evidence.length > 2 ? ` · +${o.evidence.length - 2}` : ''}
    </div>
  )
}

export function LowerThird({ overlay }: { overlay?: Overlay }) {
  const { m } = useMatch()
  const { shown, leaving } = usePresence(overlay)
  if (!shown) return null
  const colors = { home: m.bundle.match.home.color, away: m.bundle.match.away.color }
  const accent = teamColor(shown, '#ffc83d', colors)
  const player = m.player(payloadPlayer(shown))
  const cue = String(shown.payload.cue ?? shown.type)
  return (
    <div className={`lower-third ${shown.type} cue-${cue} ${leaving ? 'leave' : 'enter'}`} style={{ '--accent': accent } as React.CSSProperties}>
      <div className="lt-accent">{player ? player.number : shown.type === 'alert' ? '!' : '•'}</div>
      <div className="lt-text">
        <div className="lt-headline">{shown.headline}</div>
        {shown.body && <div className="lt-body">{shown.body}</div>}
        <Evidence o={shown} />
      </div>
    </div>
  )
}

const SHARE_METRICS = new Set(['possession', 'pass_accuracy', 'field_tilt'])

function fmtValue(lang: Lang, metric: string, v: number): string {
  if (SHARE_METRICS.has(metric)) return fmtPct(lang, v, 0)
  const s = Math.abs(v) >= 10 ? String(Math.round(v)) : v.toFixed(2)
  return lang === 'en' ? s : s.replace('.', ',')
}

/** Home vs away values of one metric as a split bar (metric_card / stat cues). */
function Versus({ metric, values, lang }: { metric: string; values: Record<Team, number>; lang: Lang }) {
  const { m } = useMatch()
  const { home, away } = m.bundle.match
  const sum = values.home + values.away
  const share = sum > 0 ? values.home / sum : 0.5
  return (
    <div className="sp-vs">
      <div className="sp-vs-nums">
        <span>
          <i style={{ background: home.color }} />
          {home.short} <b>{fmtValue(lang, metric, values.home)}</b>
        </span>
        <span>
          <b>{fmtValue(lang, metric, values.away)}</b> {away.short}
          <i style={{ background: away.color }} />
        </span>
      </div>
      <div className="sp-vs-bar">
        <i style={{ width: `${share * 100}%`, background: home.color }} />
        <i style={{ width: `${(1 - share) * 100}%`, background: away.color }} />
      </div>
    </div>
  )
}

/** Where the player has been: payload.heatmap[x][y] shares on a small pitch (home attacks right). */
export function Heatmap({ cells, color }: { cells: number[][]; color: string }) {
  const max = Math.max(...cells.flat(), 0.0001)
  const ny = cells[0]?.length ?? 0
  return (
    <div className="sp-heat" style={{ gridTemplateColumns: `repeat(${cells.length}, 1fr)` }}>
      {Array.from({ length: ny }, (_, row) =>
        cells.map((col, x) => {
          const v = col[ny - 1 - row] / max
          return <i key={`${x}-${row}`} style={{ background: color, opacity: 0.08 + 0.92 * v }} />
        }),
      )}
      <span className="sp-heat-half" />
    </div>
  )
}

export function SidePanel({ overlay, lang }: { overlay?: Overlay; lang: Lang }) {
  const { m } = useMatch()
  const { shown, leaving } = usePresence(overlay)
  if (!shown) return null
  const p = shown.payload
  const rows = (p.rows as Row[] | undefined) ?? []
  const insight = overlayInsight(m, shown)
  const audit = insight ? checkOverlay(m, shown) : undefined
  const player = m.player(payloadPlayer(shown))
  const { home, away } = m.bundle.match
  const values = p.values as Record<Team, number> | undefined
  const metric = String(p.metric ?? p.stat ?? '')
  const heat = p.heatmap as number[][] | undefined
  // with values drawn as a bar, the body's first line (the same numbers as text) is redundant
  const body = values ? shown.body.split('\n').slice(1).join(' ') : shown.body
  return (
    <div className={`side-panel ${shown.type} ${leaving ? 'leave' : 'enter'}`}>
      <div className="sp-head">
        {player && (
          <span className="sp-num" style={{ background: m.club(player.team).color }}>
            {player.number}
          </span>
        )}
        <span>{player && p.cue === 'player_card' ? player.name : shown.headline}</span>
        {p.my_metric === true && <span className="sp-mine">★</span>}
      </div>
      {values && <Versus metric={metric} values={values} lang={lang} />}
      {p.cue === 'player_card' ? (
        <div className="sp-player">
          <div className="sp-player-stats">
            <span>
              {t(lang, 'top_speed')} <b>{Number(p.top_speed_kmh ?? 0).toFixed(1)}</b>
            </span>
            <span>
              {t(lang, 'pass_acc')} <b>{p.pass_accuracy == null ? '–' : fmtPct(lang, Number(p.pass_accuracy), 0)}</b>
            </span>
          </div>
          {heat && heat.length > 0 && player && <Heatmap cells={heat} color={m.club(player.team).color} />}
        </div>
      ) : (
        body && <div className="sp-body">{body}</div>
      )}
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
      {insight && audit && (
        <div className={`sp-verified ${audit.ok ? '' : 'bad'}`}>
          <span className={`chip ${insight.confidence}`}>{t(lang, insight.confidence)}</span>
          <span>
            {audit.ok ? '✓' : '✗'} {audit.traced}/{audit.numbers} {t(lang, 'numbers_traced')} · {insight.hypotheses.length} {t(lang, 'tested')}
          </span>
        </div>
      )}
      <Evidence o={shown} />
    </div>
  )
}

/** Where the full-time recap comes from: the Recap agent (checked) or the data directly. */
function RecapSource({ source, lang }: { source: string; lang: string }) {
  const l = (lang === 'de' || lang === 'es' ? lang : 'en') as Lang
  return <div className={`fs-source ${source}`}>{t(l, source === 'agent' ? 'recap_by_agent' : 'recap_by_data')}</div>
}

export function Fullscreen({ overlay }: { overlay?: Overlay }) {
  const { m } = useMatch()
  const { shown, leaving } = usePresence(overlay, 500)
  if (!shown) return null
  const colors = { home: m.bundle.match.home.color, away: m.bundle.match.away.color }
  const accent = teamColor(shown, '#ffc83d', colors)
  const bullets = (shown.payload.bullets as string[] | undefined) ?? []
  const score = shown.payload.final_score as [number, number] | undefined
  const { home, away } = m.bundle.match
  return (
    <div className={`fullscreen ${shown.type} ${leaving ? 'leave' : 'enter'}`} style={{ '--accent': accent } as React.CSSProperties}>
      <div className="fs-sweep" />
      <div className="fs-card">
        {shown.type === 'recap' && score && (
          <div className="fs-score">
            <span style={{ '--c': home.color } as React.CSSProperties}>{home.short}</span>
            <b>
              {score[0]} – {score[1]}
            </b>
            <span style={{ '--c': away.color } as React.CSSProperties}>{away.short}</span>
          </div>
        )}
        <div className="fs-headline">{shown.headline}</div>
        {shown.body && <div className="fs-body">{shown.body}</div>}
        {shown.type === 'recap' && <RecapSource source={String(shown.payload.source ?? 'data')} lang={shown.lang} />}
        {bullets.length > 0 && (
          <ul className="fs-bullets">
            {bullets.map((b, i) => (
              <li key={i} style={{ animationDelay: `${700 + i * 150}ms` }}>
                {b}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
