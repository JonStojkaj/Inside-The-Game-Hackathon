import { useMemo, useState } from 'react'
import { useMatch } from '../../lib/context'
import { statsAt, type MatchIndex } from '../../lib/match'
import { useFrame } from '../../lib/playback'
import { surname, t } from '../../lib/profile'
import { groupLabel, searchStats, statCatalog, type StatRow } from '../../lib/statCatalog'
import type { Lang } from '../../types'

/**
 * The analyst's board: one big panel. A search box over every live stat (team vs team, each of
 * the 22 players, the match), a standard panel underneath, and stats the viewer pins (★) from the
 * search into that panel. Everything updates with the match clock.
 */
const STANDARD = ['team.possession', 'team.xg', 'team.shots', 'team.on_target', 'team.pass_acc', 'team.key_passes', 'team.ball_wins', 'team.press_now', 'team.work_rate', 'team.line_height', 'team.win_prob']
const LIVE = ['match.control', 'match.tempo', 'match.changes', 'match.ball_speed']
const PIN_KEY = 'sliding-doors.analyst-pins.v1'

function usePins(): [string[], (id: string) => void] {
  const [pins, setPins] = useState<string[]>(() => {
    try {
      const v = JSON.parse(localStorage.getItem(PIN_KEY) ?? '[]') as unknown
      return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
    } catch {
      return []
    }
  })
  const toggle = (id: string) => {
    const next = pins.includes(id) ? pins.filter((x) => x !== id) : [...pins, id]
    setPins(next)
    try {
      localStorage.setItem(PIN_KEY, JSON.stringify(next))
    } catch {
      // no storage
    }
  }
  return [pins, toggle]
}

function Pin({ id, pins, onPin, lang }: { id: string; pins: string[]; onPin: (id: string) => void; lang: Lang }) {
  const on = pins.includes(id)
  return (
    <button className={`stb-pin ${on ? 'on' : ''}`} aria-pressed={on} title={t(lang, on ? 'sb_unpin' : 'sb_pin')} onClick={() => onPin(id)}>
      {on ? '★' : '☆'}
    </button>
  )
}

/** Team stat: home value · label · away value, split bar underneath. */
function TeamRow({ m, r, pin }: { m: MatchIndex; r: StatRow; pin?: React.ReactNode }) {
  const { home, away } = m.bundle.match
  const a = r.home ?? 0
  const b = r.away ?? 0
  const sum = Math.abs(a) + Math.abs(b)
  const lead = a === b ? 0 : (a > b) !== Boolean(r.low) ? -1 : 1
  return (
    <div className="stb-team">
      <div className="stb-team-n">
        <b className={lead < 0 ? 'lead' : ''} style={{ color: home.color }}>
          {r.fmt(a)}
        </b>
        <span>{r.label}</span>
        <b className={lead > 0 ? 'lead' : ''} style={{ color: away.color }}>
          {r.fmt(b)}
        </b>
        {pin}
      </div>
      <div className="stb-bar">
        <i style={{ width: `${sum ? (Math.abs(a) / sum) * 100 : 50}%`, background: home.color }} />
        <i style={{ width: `${sum ? (Math.abs(b) / sum) * 100 : 50}%`, background: away.color }} />
      </div>
    </div>
  )
}

function PlayerRow({ m, r, pin, withName = true }: { m: MatchIndex; r: StatRow; pin?: React.ReactNode; withName?: boolean }) {
  const p = r.player!
  return (
    <div className="stb-row">
      <i className="stb-dot" style={{ background: m.club(p.team).color }} />
      <span className="stb-l">
        {withName && (
          <em>
            #{p.number} {surname(p.name)}
          </em>
        )}
        {r.label}
      </span>
      <b>{r.fmt(r.value ?? 0)}</b>
      {r.rank != null && (r.value ?? 0) !== 0 && <small className={r.rank <= 3 ? 'top' : ''}>{`${r.rank}/${r.of}`}</small>}
      {pin}
    </div>
  )
}

function MatchRow({ r, pin }: { r: StatRow; pin?: React.ReactNode }) {
  return (
    <div className="stb-row">
      <span className="stb-l">{r.label}</span>
      <b>{r.text ?? r.fmt(r.value ?? 0)}</b>
      {pin}
    </div>
  )
}

function AnyRow({ m, r, pins, onPin, lang, withName }: { m: MatchIndex; r: StatRow; pins: string[]; onPin: (id: string) => void; lang: Lang; withName?: boolean }) {
  const pin = <Pin id={r.id} pins={pins} onPin={onPin} lang={lang} />
  if (r.scope === 'team') return <TeamRow m={m} r={r} pin={pin} />
  if (r.scope === 'player') return <PlayerRow m={m} r={r} pin={pin} withName={withName} />
  return <MatchRow r={r} pin={pin} />
}

export function StatBoard({ lang }: { lang: Lang }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const [q, setQ] = useState('')
  const [pins, togglePin] = usePins()
  const s = statsAt(m.bundle, frame)
  const rows = useMemo(() => statCatalog(m, frame, s, lang), [m, frame, s, lang])
  const byId = useMemo(() => new Map(rows.map((r) => [r.id, r])), [rows])
  const hits = useMemo(() => searchStats(rows, q), [rows, q])
  const top = rows.filter((r) => r.stat === 'player.rating').sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99)).slice(0, 3)
  const examples = [t(lang, 'sb_ex_xg'), t(lang, 'sb_ex_speed'), top[0] ? surname(top[0].player!.name) : '', t(lang, 'sb_ex_press')].filter(Boolean)
  const onePlayer = hits.length > 1 && hits.every((r) => r.player && r.player.id === hits[0].player?.id) ? hits[0].player : undefined

  return (
    <section className="blk stb">
      <div className="stb-search">
        <span aria-hidden>⌕</span>
        <input
          type="search"
          value={q}
          placeholder={t(lang, 'sb_placeholder')}
          aria-label={t(lang, 'sb_placeholder')}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Escape' && setQ('')}
        />
        {q && (
          <button className="stb-clear" onClick={() => setQ('')} aria-label="clear">
            ×
          </button>
        )}
      </div>

      {q ? (
        <div className="stb-results">
          {onePlayer && (
            <div className="stb-player-h" style={{ borderColor: m.club(onePlayer.team).color }}>
              <b>#{onePlayer.number}</b> {onePlayer.name} <span>{m.club(onePlayer.team).short} · {onePlayer.position}</span>
            </div>
          )}
          {hits.length === 0 && <p className="stb-empty">{t(lang, 'sb_none')}</p>}
          {hits.map((r) => (
            <AnyRow key={r.id} m={m} r={r} pins={pins} onPin={togglePin} lang={lang} withName={!onePlayer} />
          ))}
        </div>
      ) : (
        <>
          <div className="stb-examples">
            {examples.map((x) => (
              <button key={x} onClick={() => setQ(x)}>
                {x}
              </button>
            ))}
          </div>
          {pins.length > 0 && (
            <div className="stb-sec">
              <h4>★ {t(lang, 'sb_pinned')}</h4>
              {pins.map((id) => byId.get(id)).filter((r): r is StatRow => Boolean(r)).map((r) => (
                <AnyRow key={r.id} m={m} r={r} pins={pins} onPin={togglePin} lang={lang} />
              ))}
            </div>
          )}
          <div className="stb-sec">
            <h4>{groupLabel('match', lang)}</h4>
            {STANDARD.map((id) => byId.get(id)).filter((r): r is StatRow => Boolean(r)).map((r) => (
              <TeamRow key={r.id} m={m} r={r} pin={<Pin id={r.id} pins={pins} onPin={togglePin} lang={lang} />} />
            ))}
          </div>
          <div className="stb-sec stb-live">
            {LIVE.map((id) => byId.get(id)).filter((r): r is StatRow => Boolean(r)).map((r) => (
              <div key={r.id} className="stb-chip">
                <b>{r.text ?? r.fmt(r.value ?? 0)}</b>
                <span>{r.label}</span>
              </div>
            ))}
          </div>
          {top.length > 0 && (
            <div className="stb-sec">
              <h4>{t(lang, 'sb_top')}</h4>
              {top.map((r) => (
                <button key={r.id} className="stb-top" onClick={() => setQ(surname(r.player!.name))}>
                  <PlayerRow m={m} r={r} />
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  )
}

/** Every stat of one player with his rank among all 22 (player focus). */
export function PlayerSheet({ pid, lang }: { pid: string; lang: Lang }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const s = statsAt(m.bundle, frame)
  const rows = useMemo(() => statCatalog(m, frame, s, lang).filter((r) => r.player?.id === pid && r.stat !== 'player.rating'), [m, frame, s, lang, pid])
  const groups = [...new Set(rows.map((r) => r.group))]
  return (
    <section className="blk stb stb-sheet">
      <header className="blk-h">
        <span>{t(lang, 'sb_all_stats')}</span>
        <small>{t(lang, 'sb_rank_note')}</small>
      </header>
      {groups.map((g) => (
        <div key={g} className="stb-sec">
          <h4>{groupLabel(g, lang)}</h4>
          {rows
            .filter((r) => r.group === g)
            .map((r) => (
              <PlayerRow key={r.id} m={m} r={r} withName={false} />
            ))}
        </div>
      ))}
    </section>
  )
}
