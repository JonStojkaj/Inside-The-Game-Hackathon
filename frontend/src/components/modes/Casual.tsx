import { useMemo } from 'react'
import { useMatch } from '../../lib/context'
import { chanceInfo, goalEvents, scoreAt, whyGoal } from '../../lib/derive'
import { minuteLabel } from '../../lib/match'
import { useFrame } from '../../lib/playback'
import { eventLabel, t } from '../../lib/profile'
import { usePresence } from '../../lib/usePresence'
import type { Lang } from '../../types'

const GOAL_FRAMES = 70
const CHANCE_FRAMES = 45

interface Card {
  id: string
  kind: 'goal' | 'chance'
  color: string
  title: string
  who: string
  why: string
  score?: [number, number]
}

/** Only goals and big chances, each as one short card with one line on why it mattered. */
export function CasualMoments({ lang }: { lang: Lang }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const goals = useMemo(() => goalEvents(m), [m])
  const chances = useMemo(() => m.bundle.moments.filter((mo) => mo.kind === 'big_chance'), [m])

  const g = goals.find((x) => frame >= x.frame && frame < x.frame + GOAL_FRAMES)
  const c = g ? undefined : chances.find((mo) => frame >= mo.frame && frame < mo.frame + CHANCE_FRAMES)
  // one stable object per moment, so usePresence does not see a "new" card every frame
  const card = useMemo(() => buildCard(), [g, c, lang]) // eslint-disable-line react-hooks/exhaustive-deps
  const { shown, leaving } = usePresence(card)

  function buildCard(): Card | undefined {
  if (g) {
    const club = m.club(g.team!)
    return {
      id: g.id,
      kind: 'goal',
      color: club.color,
      title: `${eventLabel(lang, 'goal')} · ${club.name}`,
      who: `${m.player(g.player_id)?.name ?? ''} · ${minuteLabel(m.bundle, g.frame)}`,
      why: whyGoal(m, g, lang),
      score: scoreAt(m, g.frame + 1),
    }
  }
    if (c) {
      const info = chanceInfo(m, c, lang)
      return {
        id: c.id,
        kind: 'chance',
        color: m.club(c.team).color,
        title: `${t(lang, 'big_chance')} · ${m.club(c.team).name}`,
        who: `${m.player(c.player_ids[0])?.name ?? ''} · ${minuteLabel(m.bundle, c.frame)}${info.outcome ? ` · ${info.outcome}` : ''}`,
        why: info.wouldMake,
      }
    }
    return undefined
  }
  if (!shown) return null
  return (
    <div className={`cz-card ${shown.kind} ${leaving ? 'leave' : 'enter'}`} style={{ '--accent': shown.color } as React.CSSProperties}>
      <div className="cz-title">
        <i />
        {shown.title}
      </div>
      <div className="cz-who">{shown.who}</div>
      <div className="cz-why">{shown.why}</div>
      {shown.score && (
        <div className="cz-score">
          {m.bundle.match.home.short} <b>{shown.score[0]}</b>–<b>{shown.score[1]}</b> {m.bundle.match.away.short}
        </div>
      )}
    </div>
  )
}
