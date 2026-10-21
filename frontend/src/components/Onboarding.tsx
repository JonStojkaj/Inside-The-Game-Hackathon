import { useState } from 'react'
import { useMatch } from '../lib/context'
import { LANGS, MODES, t } from '../lib/profile'
import type { Lang, ProfileMode, Team, ViewerProfile } from '../types'
import { Pitch } from './Pitch'

const ICONS: Record<ProfileMode, React.ReactNode> = {
  analyst: (
    <svg viewBox="0 0 48 48">
      <path d="M8 40V26M18 40V14M28 40V22M38 40V8" />
      <path d="M6 42h36" />
    </svg>
  ),
  club_fan: (
    <svg viewBox="0 0 48 48">
      <path d="M24 5l15 6v11c0 10-6.5 17-15 21C15.5 39 9 32 9 22V11z" />
      <path d="M24 5v38M9 20h30" />
    </svg>
  ),
  player_focus: (
    <svg viewBox="0 0 48 48">
      <circle cx="24" cy="24" r="15" />
      <circle cx="24" cy="24" r="6" />
      <path d="M24 3v8M24 37v8M3 24h8M37 24h8" />
    </svg>
  ),
  casual: (
    <svg viewBox="0 0 48 48">
      <path d="M27 4L11 27h11l-3 17 18-25H25z" />
    </svg>
  ),
}

interface Props {
  initial?: ViewerProfile | null
  onDone: (p: ViewerProfile) => void
  onClose?: () => void
}

/** First-visit welcome: who are you, then club or player, plus language. */
export function Onboarding({ initial, onDone, onClose }: Props) {
  const { m } = useMatch()
  const { home, away, players } = m.bundle.match
  const [lang, setLang] = useState<Lang>(initial?.language ?? 'en')
  const [step, setStep] = useState<'who' | 'club' | 'player'>('who')
  const done = (mode: ProfileMode, club: Team | null = null, player: string | null = null) =>
    onDone({ mode, language: lang, favourite_club: club, favourite_players: player ? [player] : [] })

  const pick = (mode: ProfileMode) => {
    if (mode === 'club_fan') setStep('club')
    else if (mode === 'player_focus') setStep('player')
    else done(mode)
  }

  return (
    <div className="ob">
      <div className="ob-bg">
        <Pitch />
      </div>
      <div className="ob-shade" />
      <header className="ob-top">
        <div className="brand">
          <span className="brand-mark">
            <i />
            <i />
          </span>
          <span className="brand-name">Sliding Doors</span>
        </div>
        <div className="ob-match">
          <i style={{ background: home.color }} />
          {home.name} <span>v</span> {away.name}
          <i style={{ background: away.color }} />
        </div>
        <div className="seg-ctl ob-lang" role="group" aria-label={t(lang, 'language')}>
          {LANGS.map((l) => (
            <button key={l} className={lang === l ? 'on' : ''} onClick={() => setLang(l)}>
              {l.toUpperCase()}
            </button>
          ))}
        </div>
        {onClose && (
          <button className="ob-close" onClick={onClose} aria-label="close">
            ×
          </button>
        )}
      </header>

      <main className="ob-main" key={step}>
        <div className="ob-kicker">
          <span className="dot" />
          {t(lang, 'ob_kicker')}
        </div>
        {step === 'who' && (
          <>
            <h1 className="ob-title">{t(lang, 'ob_title')}</h1>
            <p className="ob-sub">{t(lang, 'ob_sub')}</p>
            <div className="ob-cards">
              {MODES.map((mode, i) => (
                <button key={mode} className={`ob-card m-${mode}`} style={{ animationDelay: `${60 + i * 50}ms` }} onClick={() => pick(mode)}>
                  <span className="ob-icon">{ICONS[mode]}</span>
                  <span className="ob-card-t">{t(lang, `ob_${mode}_t`)}</span>
                  <span className="ob-card-d">{t(lang, `ob_${mode}_d`)}</span>
                  <span className="ob-card-mode">{t(lang, mode)} →</span>
                </button>
              ))}
            </div>
          </>
        )}

        {step === 'club' && (
          <>
            <h1 className="ob-title">{t(lang, 'ob_pick_club')}</h1>
            <div className="ob-clubs">
              {[home, away].map((c, i) => (
                <button key={c.key} className="ob-club" style={{ '--c': c.color, animationDelay: `${50 + i * 60}ms` } as React.CSSProperties} onClick={() => done('club_fan', c.key)}>
                  <span className="ob-crest">{c.short}</span>
                  <span className="ob-club-name">{c.name}</span>
                </button>
              ))}
            </div>
          </>
        )}

        {step === 'player' && (
          <>
            <h1 className="ob-title">{t(lang, 'ob_pick_player')}</h1>
            <div className="ob-squads">
              {[home, away].map((c) => (
                <div key={c.key} className="ob-squad">
                  <div className="ob-squad-name" style={{ color: c.color }}>
                    {c.name}
                  </div>
                  <div className="ob-players">
                    {players
                      .filter((p) => p.team === c.key)
                      .map((p) => (
                        <button key={p.id} className="ob-player" style={{ '--c': c.color } as React.CSSProperties} onClick={() => done('player_focus', null, p.id)}>
                          <span className="ob-pnum">{p.number}</span>
                          <span className="ob-pname">{p.name}</span>
                          <span className="ob-ppos">{p.position}</span>
                        </button>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {step !== 'who' && (
          <button className="ob-back" onClick={() => setStep('who')}>
            ← {t(lang, 'ob_back')}
          </button>
        )}
      </main>
      <footer className="ob-note">{t(lang, 'ob_note')}</footer>
    </div>
  )
}
