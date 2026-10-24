import { useMemo } from 'react'
import { useMatch } from '../../lib/context'
import { other, scoreAt } from '../../lib/derive'
import { inLeague, liveTable, ordinal, stakes, useLeague } from '../../lib/league'
import { fanMood, winProbability, winSeries } from '../../lib/models'
import { useFrame } from '../../lib/playback'
import { fmtPct, t, tf } from '../../lib/profile'
import type { Lang, MatchEvent, Team } from '../../types'
import { Block, Latest } from './Block'
import { important } from './important'

/** Club fan sidebar: mood + win chance, the live league table with what's at stake, our latest events. */
export function FanSide({ team, lang }: { team: Team; lang: Lang }) {
  const filter = useMemo(() => (e: MatchEvent) => important(e) && (e.team === team || e.type === 'goal'), [team])
  return (
    <>
      <MoodBlock team={team} lang={lang} />
      <TableBlock team={team} lang={lang} />
      <Latest lang={lang} filter={filter} n={3} us={team} />
    </>
  )
}

function MoodBlock({ team, lang }: { team: Team; lang: Lang }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const club = m.club(team)
  const opp = m.club(other(team))
  const score = scoreAt(m, frame)
  const [us, them] = team === 'home' ? score : [score[1], score[0]]
  const mood = fanMood(m, team, frame)
  const moodKey = `mood_${Math.min(4, Math.floor(mood * 5))}`
  const series = useMemo(() => winSeries(m, team), [m, team])
  const wp = winProbability(m, team, frame)
  const line = us > them ? 'we_lead' : us === them ? 'we_level' : 'we_behind'

  // win-probability line up to now (x = match time, y = 0..100 %)
  const n = Math.max(1, m.bundle.frames.t_ms.length - 1)
  const pts = series.filter((p) => p.frame <= frame)
  const path = pts.map((p, i) => `${i ? 'L' : 'M'}${((p.frame / n) * 100).toFixed(1)},${(30 - p.win * 30).toFixed(1)}`).join(' ')

  const wdl = tf(lang, 'wdl', { w: fmtPct(lang, wp.win, 0), d: fmtPct(lang, wp.draw, 0), l: fmtPct(lang, wp.loss, 0) })
  return (
    <Block title={t(lang, 'blk_winprob')} accent={club.color} className="fan-mood-blk">
      <div className="hero" title={`${wdl} · ${opp.short} — ${t(lang, 'model_est')}`}>
        <b>{fmtPct(lang, wp.win, 0)}</b>
        <span>
          {t(lang, moodKey)} · {tf(lang, line, { s: `${us}–${them}` })}
        </span>
      </div>
      <svg className="wp-line" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden>
        <line x1="0" x2="100" y1="15" y2="15" className="wp-mid" />
        <path d={path} style={{ stroke: club.color }} />
      </svg>
    </Block>
  )
}

function TableBlock({ team, lang }: { team: Team; lang: Lang }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const league = useLeague()
  const score = scoreAt(m, frame)
  const { match } = m.bundle
  const rows = useMemo(() => (inLeague(league, match) ? liveTable(league, match, score) : null), [league, match, score[0], score[1]]) // eslint-disable-line react-hooks/exhaustive-deps
  const st = useMemo(() => (inLeague(league, match) ? stakes(league, match, team, score) : null), [league, match, team, score[0], score[1]]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!rows || !st || !league) return null
  const me = rows.find((r) => r.short === m.club(team).short)!
  const rivals = new Set(me.rivals)
  // a window of 5 rows around us
  const start = Math.max(0, Math.min(rows.length - 5, me.pos - 3))
  const shown = rows.slice(start, start + 5)
  const move = me.before - me.pos
  return (
    <Block title={t(lang, 'blk_table')} className="tbl-blk">
      <div className="stake" title={tf(lang, 'stake_line', { w: ordinal(st.win, lang), d: ordinal(st.draw, lang), l: ordinal(st.loss, lang) })}>
        <div className="stake-now">
          {tf(lang, 'now_live', { p: ordinal(me.pos, lang) })}
          {move !== 0 && <em className={move > 0 ? 'up' : 'down'}>{move > 0 ? `▲ ${tf(lang, 'move_up', { n: move })}` : `▼ ${tf(lang, 'move_down', { n: -move })}`}</em>}
        </div>
      </div>
      <table className="tbl">
        <thead>
          <tr>
            <th>#</th>
            <th />
            <th>{t(lang, 'col_gd')}</th>
            <th>{t(lang, 'col_pts')}</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => {
            const d = r.before - r.pos
            return (
              <tr key={r.short} className={`${r.short === me.short ? 'me' : ''} ${rivals.has(r.short) ? 'rival' : ''} ${r.live ? 'live' : ''}`}>
                <td className="tbl-pos">
                  {r.pos}
                  {d !== 0 && <i className={d > 0 ? 'up' : 'down'}>{d > 0 ? '▲' : '▼'}</i>}
                </td>
                <td className="tbl-name">
                  <i style={{ background: r.color }} />
                  {r.name}
                  {rivals.has(r.short) && <small>{t(lang, 'rival')}</small>}
                </td>
                <td>{r.gd > 0 ? `+${r.gd}` : r.gd}</td>
                <td className="tbl-pts">{r.pts}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </Block>
  )
}
