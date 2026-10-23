import { useMemo } from 'react'
import { useMatch } from '../../lib/context'
import { chanceInfo, goalEvents, other, scoreAt } from '../../lib/derive'
import { minuteLabel, statsAt } from '../../lib/match'
import { useFrame } from '../../lib/playback'
import { t, tf } from '../../lib/profile'
import type { Lang, Team } from '../../types'

const GOAL_FRAMES = 60
const CHANCE_FRAMES = 40

/** The fan's persistent element: our club, the score from our side and a partisan momentum bar. */
export function FanMomentum({ team, lang }: { team: Team; lang: Lang }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const s = statsAt(m.bundle, frame)
  const club = m.club(team)
  const opp = m.club(other(team))
  // our share of control (completed passes); falls back to possession
  const ct = s?.control.control_team
  const share = s ? (ct && s.control.control_share != null ? (ct === team ? s.control.control_share : 1 - s.control.control_share) : s.teams[team].possession) : 0.5
  const chaos = s?.control.chaos ?? 0
  const mood = chaos > 0.6 ? t(lang, 'fan_chaos') : share >= 0.5 ? t(lang, 'fan_on_top') : tf(lang, 'fan_pushed', { club: opp.short })
  return (
    <div className="fan-card">
      <div className="fan-club">
        <span className="fan-crest">{club.short}</span>
        <span className="fan-name">{club.name}</span>
      </div>
      <div className="fan-mood">{mood}</div>
      <div className="fan-bar" title={t(lang, 'fan_momentum')}>
        <span>{t(lang, 'fan_us')}</span>
        <div>
          <i style={{ width: `${share * 100}%` }} />
          <i style={{ width: `${(1 - share) * 100}%`, background: opp.color }} />
        </div>
        <span>{opp.short}</span>
      </div>
      <div className="fan-hint">{t(lang, 'fan_momentum')}</div>
    </div>
  )
}

/** Big emotional banners for our goals and chances; their goals shown soberly. */
export function FanBanner({ team, lang }: { team: Team; lang: Lang }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const goals = useMemo(() => goalEvents(m), [m])
  const chances = useMemo(() => m.bundle.moments.filter((mo) => mo.kind === 'big_chance' && mo.team === team), [m, team])
  const goal = goals.find((g) => frame >= g.frame && frame < g.frame + GOAL_FRAMES)
  const score = goal ? scoreAt(m, goal.frame + 1) : null

  if (goal && goal.team === team) {
    const scorer = m.player(goal.player_id)
    return (
      <div key={goal.id} className="fan-goal">
        <div className="fan-goal-sweep" />
        <div className="fan-goal-card">
          <div className="fan-goal-word">{t(lang, 'fan_goal')}</div>
          <div className="fan-goal-sub">
            {tf(lang, 'fan_goal_sub', { name: scorer?.name ?? '' })} · {minuteLabel(m.bundle, goal.frame)}
          </div>
          {score && (
            <div className="fan-goal-score">
              {score[0]} – {score[1]}
            </div>
          )}
        </div>
      </div>
    )
  }
  if (goal) {
    const scorer = m.player(goal.player_id)
    return (
      <div key={goal.id} className="fan-against">
        <span className="fan-against-chip" style={{ background: m.club(goal.team!).color }} />
        {tf(lang, 'fan_against', { club: m.club(goal.team!).name })} · {scorer?.name} {minuteLabel(m.bundle, goal.frame)}
        {score && (
          <b>
            {score[0]}–{score[1]}
          </b>
        )}
      </div>
    )
  }
  const chance = chances.find((mo) => frame >= mo.frame && frame < mo.frame + CHANCE_FRAMES)
  if (chance) {
    const info = chanceInfo(m, chance, lang)
    return (
      <div key={chance.id} className="fan-close">
        <div className="fan-close-word">{t(lang, 'fan_close')}</div>
        <div className="fan-close-sub">
          {m.player(chance.player_ids[0])?.name}
          {info.outcome && ` · ${info.outcome}`}
        </div>
      </div>
    )
  }
  return null
}
