import { useMatch } from '../lib/context'
import { statsAt } from '../lib/match'
import { useFrame } from '../lib/playback'
import { t } from '../lib/profile'
import type { Lang, ViewerProfile } from '../types'

const pct = (v: number | null | undefined) => (v == null ? '–' : `${Math.round(v * 100)}%`)

/** Always-on element per mode (PLAN §8 "persistent elements"), top-right of the screen. */
export function Persistent({ profile }: { profile: ViewerProfile }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const s = statsAt(m.bundle, frame)
  if (!s) return null
  const lang: Lang = profile.language
  const { home, away } = m.bundle.match

  if (profile.mode === 'analyst') {
    const chaos = s.control.chaos ?? 0
    const ct = s.control.control_team
    return (
      <div className="persistent analyst">
        <div className="ps-row">
          <span className="ps-label">{t(lang, 'control')}</span>
          <div className="ps-gauge">
            <i style={{ left: `${chaos * 100}%` }} />
          </div>
          <span className="ps-label">{t(lang, 'chaos')}</span>
        </div>
        <div className="ps-facts">
          <span>
            {ct ? (
              <>
                <b style={{ color: m.club(ct).color }}>{m.club(ct).short}</b> {t(lang, 'in_control')} {pct(s.control.control_share)}
              </>
            ) : (
              '–'
            )}
          </span>
          <span>
            {t(lang, 'pressure')} <b>{s.pressure_on_ball.toFixed(1)}</b>
          </span>
        </div>
      </div>
    )
  }

  if (profile.mode === 'club_fan' && profile.favourite_club) {
    const team = profile.favourite_club
    const club = m.club(team)
    const share = s.teams[team].possession
    return (
      <div className="persistent fan">
        <div className="ps-row">
          <span className="ps-label" style={{ color: club.color }}>
            {club.short}
          </span>
          <div className="ps-bar">
            <i style={{ width: `${share * 100}%`, background: club.color }} />
          </div>
          <span className="ps-big">{pct(share)}</span>
        </div>
        <div className="ps-facts">
          <span>{t(lang, 'possession')}</span>
          <span>
            {s.teams[team].xg != null ? (
              <>
                {t(lang, 'xg')} <b>{s.teams[team].xg!.toFixed(2)}</b>
              </>
            ) : (
              <>
                {t(lang, 'shots')} <b>{s.teams[team].shots_on_target}/{s.teams[team].shots}</b>
              </>
            )}
          </span>
        </div>
      </div>
    )
  }

  const pid = profile.favourite_players[0]
  const ps = pid ? s.players[pid] : undefined
  if (profile.mode === 'player_focus' && ps) {
    const club = ps.team === 'home' ? home : away
    return (
      <div className="persistent player">
        <div className="pp-num" style={{ background: club.color }}>
          {ps.number}
        </div>
        <div className="pp-main">
          <div className="pp-name">{ps.name}</div>
          <div className="pp-stats">
            <span>
              <b>{Math.round(ps.speed_kmh)}</b> km/h
            </span>
            <span>
              {t(lang, 'top_speed')} <b>{ps.top_speed_kmh.toFixed(1)}</b>
            </span>
            <span>
              {t(lang, 'passes')} <b>{ps.passes_completed}/{ps.passes}</b>
            </span>
          </div>
        </div>
      </div>
    )
  }
  return null
}
