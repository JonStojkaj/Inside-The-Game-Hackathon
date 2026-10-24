import { useMemo } from 'react'
import { useMatch } from '../../lib/context'
import { leagueClub, useLeague } from '../../lib/league'
import { minuteLabel } from '../../lib/match'
import { bestAction, decisions, directOpponent, passProfile, rating, ratedActions, ratingParts, type RatedAction, type RatingPart } from '../../lib/models'
import { useFrame } from '../../lib/playback'
import { eventLabel, fmtNum, fmtPct, surname, t, tf } from '../../lib/profile'
import type { Insight, Lang } from '../../types'
import { DecisionRecordView } from '../modes/Player'
import { Block } from './Block'

const PARTS: RatingPart[] = ['passing', 'shooting', 'defending', 'pressing']

/** Player focus sidebar: live rating vs his season average, his duel, and his decisions rated by Sliding Doors. */
export function PlayerSide({ pid, lang, breakInsight }: { pid: string; lang: Lang; breakInsight?: Insight }) {
  const { m } = useMatch()
  const mine = breakInsight && m.moment(breakInsight.moment_id)?.player_ids[0] === pid
  return (
    <>
      {mine && (
        <Block title={t(lang, 'decision_record')} className="blk-break">
          <DecisionRecordView ins={breakInsight} lang={lang} />
        </Block>
      )}
      <RatingBlock pid={pid} lang={lang} />
      <DuelBlock pid={pid} lang={lang} />
      <DecisionsBlock pid={pid} lang={lang} />
    </>
  )
}

function actionText(m: ReturnType<typeof useMatch>['m'], a: RatedAction, lang: Lang): string {
  const e = a.event
  const target = m.player(e.target_id)
  const bits = [eventLabel(lang, e.type)]
  if (e.type === 'pass' && target) bits.push(`→ ${surname(target.name)}`)
  if (e.type === 'pass' && e.meta.difficulty != null) bits.push(`· ${t(lang, 'difficulty')} ${Math.round(Number(e.meta.difficulty))}`)
  if (e.type === 'shot' && e.meta.xg != null) bits.push(`· xG ${fmtNum(lang, Number(e.meta.xg), 2)}`)
  return bits.join(' ')
}

function RatingBlock({ pid, lang }: { pid: string; lang: Lang }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const league = useLeague()
  const p = m.player(pid)!
  const club = m.club(p.team)
  const acts = useMemo(() => ratedActions(m, pid, frame), [m, pid, frame])
  const r = rating(acts)
  const parts = ratingParts(acts)
  const best = bestAction(acts)
  const avg = league && leagueClub(league, club) ? (league.season_ratings[p.name] ?? league.default_rating) : null
  return (
    <Block title={t(lang, 'blk_rating')} accent={club.color} className="rating-blk">
      <div className="rt-head" title={`${t(lang, 'rating_hint')}\n${PARTS.map((k) => `${t(lang, `part_${k}`)} ${parts[k] >= 0 ? '+' : '−'}${fmtNum(lang, Math.abs(parts[k]), 1)}`).join(' · ')}`}>
        <div className="rt-num" style={{ '--r': (r - 1) / 9 } as React.CSSProperties}>
          {fmtNum(lang, r, 1)}
        </div>
        <div className="rt-who">
          <b>
            #{p.number} {p.name}
          </b>
          {avg != null && (
            <span className={`rt-avg ${r >= avg ? 'up' : 'down'}`}>
              {r >= avg ? '▲' : '▼'} {tf(lang, 'season_avg', { r: fmtNum(lang, avg, 1) })}
            </span>
          )}
        </div>
      </div>
      {best && best.value > 0 && (
        <button
          className="rt-best"
          onClick={() => {
            pb.seek(Math.max(0, best.event.frame - 30))
            pb.play()
          }}
        >
          <span className="rt-best-l">{t(lang, 'best_action')}</span>
          <span className="rt-best-t">
            {minuteLabel(m.bundle, best.event.frame)} · {actionText(m, best, lang)}
          </span>
          <span className="rt-best-go">{t(lang, 'watch')}</span>
        </button>
      )}
    </Block>
  )
}

function DuelBlock({ pid, lang }: { pid: string; lang: Lang }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const p = m.player(pid)!
  const o = directOpponent(m, p)
  const bucket = Math.floor(frame / 5) * 5
  const stats = useMemo(() => {
    if (!o) return null
    const one = (id: string) => ({ r: rating(ratedActions(m, id, bucket)), ...passProfile(m, id, bucket) })
    return { a: one(p.id), b: one(o.id) }
  }, [m, p.id, o, bucket])
  if (!o || !stats) return null
  const ca = m.club(p.team).color
  const cb = m.club(o.team).color
  const rows: { k: string; a: number | null; b: number | null; fmt: (v: number) => string; max: number }[] = [
    { k: 'duel_rating', a: stats.a.r, b: stats.b.r, fmt: (v) => fmtNum(lang, v, 1), max: 10 },
    { k: 'duel_acc', a: stats.a.acc, b: stats.b.acc, fmt: (v) => fmtPct(lang, v, 0), max: 1 },
  ]
  return (
    <Block title={t(lang, 'blk_duel')} className="duel-blk">
      <div className="duel-names">
        <span style={{ color: ca }}>
          #{p.number} {surname(p.name)}
        </span>
        <small>{t(lang, 'vs')}</small>
        <span style={{ color: cb }}>
          #{o.number} {surname(o.name)}
        </span>
      </div>
      {rows.map((r) => {
        const a = r.a ?? 0
        const b = r.b ?? 0
        const lead = r.a != null && r.b != null ? (a > b ? 'a' : b > a ? 'b' : '') : ''
        return (
          <div key={r.k} className="duel-row">
            <b className={lead === 'a' ? 'lead' : ''}>{r.a == null ? '–' : r.fmt(a)}</b>
            <div className="duel-bars">
              <span>{t(lang, r.k)}</span>
              <div>
                <i style={{ width: `${(a / r.max) * 50}%`, background: ca }} />
                <i style={{ width: `${(b / r.max) * 50}%`, background: cb }} />
              </div>
            </div>
            <b className={lead === 'b' ? 'lead' : ''}>{r.b == null ? '–' : r.fmt(b)}</b>
          </div>
        )
      })}
    </Block>
  )
}

function DecisionsBlock({ pid, lang }: { pid: string; lang: Lang }) {
  const { m, pb, openMoment } = useMatch()
  const frame = useFrame(pb)
  const list = decisions(m, pid, frame)
  const right = list.filter((d) => d.right).length
  return (
    <Block title={t(lang, 'blk_decisions')} note={list.length ? `${right}/${list.length} ✓` : undefined} className="dec-blk">
      {list.length === 0 && <div className="blk-empty">{t(lang, 'dec_none')}</div>}
      <ul className="dec-list">
        {list.map((d) => (
          <li key={d.ins.id}>
            <button onClick={() => openMoment(d.mo)}>
              <span className="dec-min">{minuteLabel(m.bundle, d.mo.frame)}</span>
              <span className="dec-kind">{t(lang, `k_${d.mo.kind}`)}</span>
              <span className={`dec-v ${d.right ? 'ok' : 'warn'}`}>{d.right ? `✓ ${t(lang, 'dec_right')}` : `✗ ${t(lang, 'dec_better')}`}</span>
            </button>
          </li>
        ))}
      </ul>
    </Block>
  )
}
