import { useMatch } from '../lib/context'
import { LANGS, MODES, presets, t } from '../lib/profile'
import type { ViewerProfile } from '../types'

interface Props {
  profile: ViewerProfile
  onChange: (p: ViewerProfile) => void
}

/** Mode / club / player / language; the result is the overlay segment this viewer gets. */
export function ProfilePicker({ profile, onChange }: Props) {
  const { m } = useMatch()
  const { home, away, players } = m.bundle.match
  const set = (patch: Partial<ViewerProfile>) => onChange({ ...profile, ...patch })
  const lang = profile.language

  return (
    <div className="picker">
      <div className="seg-ctl">
        {MODES.map((mode) => (
          <button
            key={mode}
            className={profile.mode === mode ? 'on' : ''}
            onClick={() =>
              set({
                mode,
                favourite_club: mode === 'club_fan' ? (profile.favourite_club ?? 'home') : null,
                favourite_players: mode === 'player_focus' ? (profile.favourite_players.length ? profile.favourite_players : presets(m.bundle.overlays, players)[2].favourite_players) : [],
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
        <select aria-label={t(lang, 'player')} value={profile.favourite_players[0] ?? ''} onChange={(e) => set({ favourite_players: [e.target.value] })}>
          {[home, away].map((c) => (
            <optgroup key={c.key} label={c.name}>
              {players
                .filter((p) => p.team === c.key)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    #{p.number} {p.name} · {p.position}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      )}
      <div className="seg-ctl" aria-label={t(lang, 'language')}>
        {LANGS.map((l) => (
          <button key={l} className={profile.language === l ? 'on' : ''} onClick={() => set({ language: l })}>
            {l.toUpperCase()}
          </button>
        ))}
      </div>
    </div>
  )
}
