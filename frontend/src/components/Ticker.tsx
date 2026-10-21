import { useMemo } from 'react'
import { useMatch } from '../lib/context'
import { newsworthy } from '../lib/derive'
import { minuteLabel } from '../lib/match'
import { useFrame } from '../lib/playback'
import { eventLabel, t } from '../lib/profile'
import { usePresence } from '../lib/usePresence'
import type { Lang, MatchEvent, Overlay } from '../types'

const SHOWN = 4

/** Bottom ticker: latest notable events; a ticker-slot overlay (alert) takes over the strip. */
export function Ticker({ lang, overlay, filter }: { lang: Lang; overlay?: Overlay; filter?: (e: MatchEvent) => boolean }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const feed = useMemo(() => m.bundle.events.filter(filter ?? newsworthy), [m, filter])
  const { shown, leaving } = usePresence(overlay)

  let hi = 0
  while (hi < feed.length && feed[hi].frame <= frame) hi++
  const items = feed.slice(Math.max(0, hi - SHOWN), hi).reverse()

  return (
    <div className="ticker">
      <div className="tk-label">{lang === 'de' ? 'TICKER' : lang === 'es' ? 'MINUTO' : 'TICKER'}</div>
      <div className="tk-items">
        {items.map((e) => {
          const p = m.player(e.player_id)
          const target = m.player(e.target_id)
          const club = e.team ? m.club(e.team) : null
          const name = p ? p.name.split(' ').slice(-1)[0] : club?.short ?? ''
          return (
            <div key={e.id} className={`tk-item tk-${e.type}`}>
              <span className="tk-min">{minuteLabel(m.bundle, e.frame)}</span>
              <i className="tk-bar" style={{ background: club?.color ?? '#888' }} />
              <span className="tk-type">{eventLabel(lang, e.type)}</span>
              <span className="tk-name">
                {name}
                {e.type === 'pass' && target ? ` → ${target.name.split(' ').slice(-1)[0]}` : ''}
                {e.type === 'shot' && e.outcome ? ` · ${e.outcome === 'goal' ? eventLabel(lang, 'goal') : t(lang, e.outcome)}` : ''}
              </span>
            </div>
          )
        })}
      </div>
      {shown && (
        <div className={`tk-alert ${leaving ? 'leave' : 'enter'}`}>
          <b>{shown.headline}</b>
          <span>{shown.body}</span>
        </div>
      )}
    </div>
  )
}
