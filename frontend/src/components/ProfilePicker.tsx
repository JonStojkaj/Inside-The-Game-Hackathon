import { useMatch } from '../lib/context'
import { LANGS, resolveSegment, segmentId, t } from '../lib/profile'
import type { ProfileMode, ViewerProfile } from '../types'

const MODES: ProfileMode[] = ['analyst', 'club_fan', 'player_focus']

interface Props {
  profile: ViewerProfile
  onChange: (p: ViewerProfile) => void
  compact?: boolean
}

/** Mode / club / player / language; the result is the overlay segment this viewer gets. */
export function ProfilePicker({ profile, onChange, compact }: Props) {
  const { m } = useMatch()
  const { home, away, players } = m.bundle.match
  const seg = resolveSegment(m.bundle.overlays, profile)
  const set = (patch: Partial<ViewerProfile>) => onChange({ ...profile, ...patch })
  const lang = compact ? profile.language : 'en'

  return (
    <div className={`picker ${compact ? 'compact' : ''}`}>
      <div className="seg-ctl">
        {MODES.map((mode) => (
          <button
            key={mode}
            className={profile.mode === mode ? 'on' : ''}
            onClick={() =>
              set({
                mode,
                favourite_club: mode === 'club_fan' ? (profile.favourite_club ?? 'home') : null,
                favourite_players: mode === 'player_focus' ? (profile.favourite_players.length ? profile.favourite_players : ['H10']) : [],
              })
            }
          >
            {t(lang, mode)}
          </button>
        ))}
      </div>
      {profile.mode === 'club_fan' && (
        <div className="seg-ctl">
          {[home, away].map((c) => (
            <button
              key={c.key}
              className={profile.favourite_club === c.key ? 'on' : ''}
              style={{ '--club': c.color } as React.CSSProperties}
              onClick={() => set({ favourite_club: c.key })}
            >
              <i className="club-dot" />
              {c.short}
            </button>
          ))}
        </div>
      )}
      {profile.mode === 'player_focus' && (
        <select value={profile.favourite_players[0] ?? ''} onChange={(e) => set({ favourite_players: [e.target.value] })}>
          {[home, away].map((c) => (
            <optgroup key={c.key} label={c.name}>
              {players
                .filter((p) => p.team === c.key)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    #{p.number} {p.name}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      )}
      <div className="seg-ctl">
        {LANGS.map((l) => (
          <button key={l} className={profile.language === l ? 'on' : ''} onClick={() => set({ language: l })}>
            {l.toUpperCase()}
          </button>
        ))}
      </div>
      {!compact && (
        <div className={`seg-id ${seg.exact ? 'ok' : 'fallback'}`} title="overlay segment (production runs once per segment)">
          segment <code>{segmentId(profile)}</code>
          {!seg.exact && (seg.id !== segmentId(profile) ? <> → <code>{seg.id}</code></> : <span className="seg-none"> · no overlays yet</span>)}
        </div>
      )}
    </div>
  )
}
