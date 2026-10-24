import type { ReactNode } from 'react'
import { CATS, type Cat } from '../../lib/analystCats'
import { useMatch } from '../../lib/context'
import { frameAt, statsAt, type MatchIndex } from '../../lib/match'
import { useFrame } from '../../lib/playback'
import { fmtNum, fmtPct, surname, t } from '../../lib/profile'
import type { Lang, MatchEvent, StatsSnapshot, Team } from '../../types'

/**
 * The analyst's dashboard: two data columns (left and right of the stage) with the categories the
 * viewer picks. Only rates, shares, maxima and the xG flow: never totals that depend on how long
 * the (5-minute GRF) match has run.
 */
export function CatPicker({ lang, cats, onToggle }: { lang: Lang; cats: Cat[]; onToggle: (c: Cat) => void }) {
  return (
    <div className="cat-pick" role="group" aria-label={t(lang, 'cat_pick')}>
      {CATS.map((c) => (
        <button key={c} className={cats.includes(c) ? 'on' : ''} aria-pressed={cats.includes(c)} onClick={() => onToggle(c)}>
          {t(lang, `cat_${c}`)}
        </button>
      ))}
    </div>
  )
}

function lastEvent(events: MatchEvent[], frame: number, pick: (e: MatchEvent) => boolean): MatchEvent | undefined {
  for (let i = events.length - 1; i >= 0; i--) if (events[i].frame <= frame && pick(events[i])) return events[i]
  return undefined
}

function xgSoFar(events: MatchEvent[], frame: number): Record<Team, number> {
  const out = { home: 0, away: 0 }
  for (const e of events) {
    if (e.frame > frame) break
    if (e.type === 'shot' && e.team && e.meta.xg != null) out[e.team] += Number(e.meta.xg)
  }
  return out
}

/** Big home vs away numbers with a split bar under them. */
function Versus({ m, a, b, fmt, label }: { m: MatchIndex; a: number; b: number; fmt: (v: number) => string; label: string }) {
  const { home, away } = m.bundle.match
  const sum = a + b
  return (
    <div className="vs">
      <div className="vs-nums">
        <b style={{ color: home.color }}>{fmt(a)}</b>
        <span>{label}</span>
        <b style={{ color: away.color }}>{fmt(b)}</b>
      </div>
      <div className="vs-bar">
        <i style={{ width: `${sum ? (a / sum) * 100 : 50}%`, background: home.color }} />
        <i style={{ width: `${sum ? (b / sum) * 100 : 50}%`, background: away.color }} />
      </div>
    </div>
  )
}

function Row({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div className="an-row" title={hint}>
      <span>{label}</span>
      <b>{children}</b>
    </div>
  )
}

function teamPair(m: MatchIndex, a: string, b: string) {
  const { home, away } = m.bundle.match
  return (
    <>
      <em style={{ color: home.color }}>{a}</em> · <em style={{ color: away.color }}>{b}</em>
    </>
  )
}

function Card({ cat, s, frame, lang }: { cat: Cat; s: StatsSnapshot; frame: number; lang: Lang }) {
  const { m } = useMatch()
  const ev = m.bundle.events
  const name = (id: string | null | undefined) => surname(m.player(id)?.name ?? '–')
  const pct = (v: number) => fmtPct(lang, v, 0)
  let body: ReactNode = null
  if (cat === 'control') {
    const ct = s.control.control_team
    const chaos = s.control.chaos ?? 0
    body = (
      <>
        <Versus m={m} a={s.teams.home.possession} b={s.teams.away.possession} fmt={pct} label={t(lang, 'k_possession')} />
        <div className="an-gauge" title={t(lang, 'hud_control_hint')}>
          <div className="ps-gauge">
            <i style={{ left: `${chaos * 100}%` }} />
          </div>
          <span>{ct ? <b style={{ color: m.club(ct).color }}>{`${m.club(ct).short} ${t(lang, 'in_control_short')}`}</b> : t(lang, 'open_game')}</span>
        </div>
        <Row label={t(lang, 'k_tempo')}>{fmtNum(lang, s.rhythm.actions_per_min ?? 0)}</Row>
      </>
    )
  } else if (cat === 'pressing') {
    body = (
      <>
        <Versus m={m} a={s.pressing.home ?? 0} b={s.pressing.away ?? 0} fmt={(v) => fmtNum(lang, v, 2)} label={t(lang, 'k_press_now')} />
        <Row label={t(lang, 'k_pressure')} hint={t(lang, 'hud_pressing_hint')}>
          {fmtNum(lang, s.pressure_on_ball, 1)}
        </Row>
        <Row label={t(lang, 'k_changes')}>{fmtNum(lang, s.control.possession_changes_per_min ?? 0)}</Row>
      </>
    )
  } else if (cat === 'passing') {
    const pass = lastEvent(ev, frame, (e) => e.type === 'pass')
    const diff = Number(pass?.meta.difficulty ?? 0)
    body = (
      <>
        <Versus m={m} a={s.teams.home.pass_accuracy ?? 0} b={s.teams.away.pass_accuracy ?? 0} fmt={pct} label={t(lang, 'k_pass_acc')} />
        <Row label={t(lang, 'k_pass_len')}>{teamPair(m, `${fmtNum(lang, s.teams.home.avg_pass_distance_m ?? 0, 0)} m`, `${fmtNum(lang, s.teams.away.avg_pass_distance_m ?? 0, 0)} m`)}</Row>
        {pass && (
          <Row label={t(lang, 'k_last_pass')} hint={`${name(pass.player_id)} → ${name(pass.target_id)}`}>
            <span className={pass.outcome === 'complete' ? 'ok' : 'bad'}>{pass.outcome === 'complete' ? '✓' : '✗'}</span> {Math.round(diff)}/100
          </Row>
        )}
      </>
    )
  } else if (cat === 'shooting') {
    const xg = xgSoFar(ev, frame)
    const shot = lastEvent(ev, frame, (e) => e.type === 'shot')
    body = (
      <>
        <Versus m={m} a={xg.home} b={xg.away} fmt={(v) => fmtNum(lang, v, 2)} label={t(lang, 'k_xg')} />
        <Row label={t(lang, 'k_shot_speed')}>{teamPair(m, `${Math.round(s.teams.home.max_shot_speed_kmh)}`, `${Math.round(s.teams.away.max_shot_speed_kmh)} km/h`)}</Row>
        {shot && <Row label={`${t(lang, 'last_shot')} · ${name(shot.player_id)}`}>xG {fmtNum(lang, Number(shot.meta.xg ?? 0), 2)}</Row>}
      </>
    )
  } else if (cat === 'physical') {
    const avg = (team: Team) => {
      const ps = Object.values(s.players).filter((p) => p.team === team && p.position !== 'GK')
      return ps.length ? ps.reduce((a, p) => a + p.speed_kmh, 0) / ps.length : 0
    }
    const fastest = Object.values(s.players).sort((a, b) => b.top_speed_kmh - a.top_speed_kmh)[0]
    body = (
      <>
        <div className="an-hero">
          <b>{Math.round(s.ball_speed_kmh)}</b>
          <span>km/h · {t(lang, 'k_ball_speed')}</span>
        </div>
        <Row label={t(lang, 'k_top_speed')}>{fastest ? `${surname(fastest.name)} ${fmtNum(lang, fastest.top_speed_kmh)} km/h` : '–'}</Row>
        <Row label={t(lang, 'k_avg_speed')}>{teamPair(m, fmtNum(lang, avg('home')), fmtNum(lang, avg('away')))}</Row>
      </>
    )
  } else {
    const fv = frameAt(m.bundle, frame)
    const carrier = fv.owner >= 0 ? m.bundle.match.players[fv.owner] : undefined
    const ps = carrier ? s.players[carrier.id] : undefined
    const top = Object.values(s.players)
      .sort((a, b) => b.top_speed_kmh - a.top_speed_kmh)
      .slice(0, 3)
    body = (
      <>
        <div className="an-hero">
          <b style={{ color: carrier ? m.club(carrier.team).color : undefined }}>{carrier ? `#${carrier.number}` : '–'}</b>
          <span>{carrier ? `${surname(carrier.name)} · ${t(lang, 'k_on_ball')}` : t(lang, 'k_ball_carrier')}</span>
        </div>
        {ps && <Row label={t(lang, 'k_top_speed')}>{fmtNum(lang, ps.top_speed_kmh)} km/h</Row>}
        <div className="an-list">
          {top.map((p) => (
            <span key={p.id}>
              <i style={{ background: m.club(p.team as Team).color }} />
              {surname(p.name)} <b>{fmtNum(lang, p.top_speed_kmh)}</b>
            </span>
          ))}
        </div>
      </>
    )
  }
  return (
    <section className={`blk an-card an-${cat}`}>
      <header className="blk-h">
        <span>{t(lang, `cat_${cat}`)}</span>
      </header>
      {body}
    </section>
  )
}

/** One column of the analyst dashboard: the picked categories at even (left) or odd (right) positions. */
export function AnalystColumn({ lang, cats, side }: { lang: Lang; cats: Cat[]; side: 0 | 1 }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const s = statsAt(m.bundle, frame)
  if (!s) return null
  return (
    <>
      {cats
        .filter((_, i) => i % 2 === side)
        .map((c) => (
          <Card key={c} cat={c} s={s} frame={frame} lang={lang} />
        ))}
    </>
  )
}
