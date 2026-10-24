import { useMemo } from 'react'
import { useMatch } from '../../lib/context'
import { chanceInfo, goalEvents, whyGoal } from '../../lib/derive'
import { clockLabel, minuteLabel } from '../../lib/match'
import { useFrame } from '../../lib/playback'
import { t } from '../../lib/profile'
import type { Insight, Lang } from '../../types'
import { Hypotheses } from '../modes/Analyst'
import type { Cat } from '../../lib/analystCats'
import { AnalystColumn } from './AnalystBoard'
import { Block } from './Block'

/** Analyst right column: every hypothesis during a break, then the odd-numbered picked categories. */
export function AnalystSide({ lang, cats, breakInsight }: { lang: Lang; cats: Cat[]; breakInsight?: Insight }) {
  return (
    <>
      {breakInsight && (
        <Block title={t(lang, 'hypotheses')} className="blk-break">
          <Hypotheses ins={breakInsight} lang={lang} />
        </Block>
      )}
      <AnalystColumn lang={lang} cats={cats} side={1} />
    </>
  )
}

/** Casual sidebar: the score, big, and the big moments so far with one line each (click = watch it). */
export function CasualSide({ lang }: { lang: Lang }) {
  const { m, pb, openMoment } = useMatch()
  const frame = useFrame(pb)
  const { home, away } = m.bundle.match
  const score = m.bundle.frames.score[Math.min(frame, m.bundle.frames.score.length - 1)] ?? [0, 0]
  const goals = useMemo(() => goalEvents(m), [m])
  const items = useMemo(() => {
    const out: { id: string; frame: number; goal: boolean; team: 'home' | 'away'; who: string; why: string; moment?: (typeof m.bundle.moments)[number] }[] = []
    for (const g of goals) {
      const mo = m.bundle.moments.find((x) => x.kind === 'goal' && Math.abs(x.frame - g.frame) < 30)
      out.push({ id: g.id, frame: g.frame, goal: true, team: g.team!, who: m.player(g.player_id)?.name ?? '', why: whyGoal(m, g, lang), moment: mo })
    }
    for (const mo of m.bundle.moments.filter((x) => x.kind === 'big_chance')) {
      out.push({ id: mo.id, frame: mo.frame, goal: false, team: mo.team, who: m.player(mo.player_ids[0])?.name ?? '', why: chanceInfo(m, mo, lang).wouldMake, moment: mo })
    }
    return out.sort((a, b) => a.frame - b.frame)
  }, [m, goals, lang])
  const past = items.filter((x) => x.frame <= frame).reverse()
  return (
    <>
      <Block title={t(lang, 'live')} className="cz-score-blk">
        <div className="cz-big">
          <span className="cz-team">
            <i style={{ background: home.color }} />
            {home.name}
          </span>
          <span className="cz-nums">
            {score[0]}
            <small>–</small>
            {score[1]}
          </span>
          <span className="cz-team right">
            {away.name}
            <i style={{ background: away.color }} />
          </span>
        </div>
        <div className="cz-clock">{clockLabel(m.bundle, frame)}</div>
      </Block>
      <Block title={t(lang, 'blk_moments')} className="cz-moments">
        {past.length === 0 && <div className="blk-empty">{t(lang, 'none_yet')}</div>}
        <ul>
          {past.map((x) => (
            <li key={x.id} className={x.goal ? 'goal' : 'chance'} style={{ '--team': m.club(x.team).color } as React.CSSProperties}>
              <button
                title={x.why}
                onClick={() => {
                  if (x.moment) openMoment(x.moment)
                  else {
                    pb.seek(Math.max(0, x.frame - 40))
                    pb.play()
                  }
                }}
              >
                <span className="czm-head">
                  <b>{x.goal ? '⚽' : '◎'}</b> {minuteLabel(m.bundle, x.frame)} · {x.goal ? t(lang, 'k_goal') : t(lang, 'big_chance')} · {x.who}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Block>
    </>
  )
}
