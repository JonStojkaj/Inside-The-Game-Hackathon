import { useMemo, type ReactNode } from 'react'
import { useMatch } from '../../lib/context'
import { minuteLabel } from '../../lib/match'
import { useFrame } from '../../lib/playback'
import { eventLabel, surname, t } from '../../lib/profile'
import type { Lang, MatchEvent } from '../../types'

/** One glanceable sidebar block: small caps title, optional note under the title, content. */
export function Block({ title, note, accent, children, className = '' }: { title: ReactNode; note?: ReactNode; accent?: string; children: ReactNode; className?: string }) {
  return (
    <section className={`blk ${className}`} style={accent ? ({ '--accent': accent } as React.CSSProperties) : undefined}>
      <header className="blk-h">
        <span>{title}</span>
        {note && <small>{note}</small>}
      </header>
      {children}
    </section>
  )
}

/** The last 3-4 important events, each with its team colour (replaces the full-width ticker). */
export function Latest({ lang, filter, n = 4, us }: { lang: Lang; filter: (e: MatchEvent) => boolean; n?: number; us?: string }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const feed = useMemo(() => m.bundle.events.filter(filter), [m, filter])
  let hi = 0
  while (hi < feed.length && feed[hi].frame <= frame) hi++
  const items = feed.slice(Math.max(0, hi - n), hi).reverse()
  return (
    <Block title={t(lang, 'blk_latest')}>
      <ul className="lt-list">
        {items.length === 0 && <li className="lt-empty">–</li>}
        {items.map((e) => {
          const p = m.player(e.player_id)
          const target = m.player(e.target_id)
          const club = e.team ? m.club(e.team) : null
          const goal = e.type === 'goal' || (e.type === 'shot' && e.outcome === 'goal')
          return (
            <li key={e.id} className={`${goal ? 'goal' : ''} ${us && e.team && e.team !== us ? 'them' : ''}`}>
              <span className="lt-min">{minuteLabel(m.bundle, e.frame)}</span>
              <i className="lt-bar" style={{ background: club?.color ?? '#888' }} />
              <span className="lt-what">
                <b>{eventLabel(lang, e.type)}</b> {p ? surname(p.name) : (club?.short ?? '')}
                {e.type === 'pass' && target ? ` → ${surname(target.name)}` : ''}
                {e.type === 'shot' && e.outcome && e.outcome !== 'goal' ? ` · ${t(lang, e.outcome)}` : ''}
              </span>
            </li>
          )
        })}
      </ul>
    </Block>
  )
}
