import { useEffect, useMemo, useState } from 'react'
import { ControlRoom } from './components/ControlRoom'
import { Onboarding } from './components/Onboarding'
import { ProfilePicker } from './components/ProfilePicker'
import { Screen } from './components/Screen'
import { Transport } from './components/Transport'
import { loadMatch, resolveSource } from './data/source'
import { MatchContext, type MatchCtx } from './lib/context'
import { indexMatch, timelineFrames } from './lib/match'
import { createPlayback } from './lib/playback'
import { loadProfile, presets, profileFromQuery, saveProfile, t } from './lib/profile'
import type { MatchBundle, ViewerProfile } from './types'

/** viewer = the single-viewer product (default); split / control = the producer view. */
type View = 'viewer' | 'split' | 'control'

export default function App() {
  const [bundle, setBundle] = useState<MatchBundle | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const src = resolveSource()
    loadMatch(src)
      .then(setBundle)
      .catch((e: unknown) => setError(`${src.kind} ${src.base}: ${e instanceof Error ? e.message : String(e)}`))
  }, [])

  if (error) return <div className="splash error">Could not load match data · {error}</div>
  if (!bundle) return <div className="splash">Loading match…</div>
  return <Player bundle={bundle} />
}

function initialView(q: URLSearchParams): View {
  const v = q.get('view')
  return v === 'split' || v === 'control' ? v : 'viewer'
}

function Player({ bundle }: { bundle: MatchBundle }) {
  const q = useMemo(() => new URLSearchParams(window.location.search), [])
  const m = useMemo(() => indexMatch(bundle), [bundle])
  const pb = useMemo(() => createPlayback(timelineFrames(bundle), bundle.match.fps), [bundle])
  const [forcedInsight, setForcedInsight] = useState<string | null>(null)
  const [view, setView] = useState<View>(() => initialView(q))
  const [tv, setTv] = useState(q.has('tv'))
  const demo = useMemo(() => presets(bundle.overlays, bundle.match.players), [bundle])
  const players = bundle.match.players
  // URL profile (demo takes) > saved profile > onboarding
  const [profile, setProfile] = useState<ViewerProfile | null>(() => profileFromQuery(players) ?? (q.has('onboarding') ? null : loadProfile(players)))
  const [onboarding, setOnboarding] = useState(() => q.has('onboarding') || (!profile && initialView(q) === 'viewer' && !q.has('shot')))
  const [menu, setMenu] = useState(false)
  const [split, setSplit] = useState<ViewerProfile[]>(demo)
  const ctx = useMemo<MatchCtx>(() => ({ m, pb, forcedInsight, setForcedInsight }), [m, pb, forcedInsight])
  const hasVideo = Boolean(bundle.match.video)
  const me = profile ?? demo[0]
  const lang = profile?.language ?? 'en'

  const choose = (p: ViewerProfile) => {
    setProfile(p)
    saveProfile(p)
  }

  // ?f=<frame>&speed=5&play: start a demo take at a given moment
  useEffect(() => {
    const p = new URLSearchParams(window.location.search)
    if (p.has('f')) pb.seek(Number(p.get('f')))
    if (p.has('speed')) pb.setSpeed(Number(p.get('speed')))
    if (p.has('play')) pb.play()
    if (import.meta.env.DEV) (window as unknown as { __pb: typeof pb }).__pb = pb
    return () => pb.pause()
  }, [pb])

  const who = me.mode === 'club_fan' && me.favourite_club ? m.club(me.favourite_club) : null
  const fav = me.mode === 'player_focus' ? m.player(me.favourite_players[0]) : undefined
  const producer = view !== 'viewer'

  return (
    <MatchContext.Provider value={ctx}>
      <div className={`app view-${view} ${q.has('shot') ? 'shot' : ''}`}>
        <header className="topbar">
          <div className="brand">
            <span className="brand-mark">
              <i />
              <i />
            </span>
            <span className="brand-name">Sliding Doors</span>
            <span className="brand-match">
              {bundle.match.home.name} v {bundle.match.away.name}
            </span>
          </div>

          {!producer && (
            <div className="me">
              <button className={`me-chip ${menu ? 'open' : ''}`} onClick={() => setMenu(!menu)} aria-expanded={menu}>
                <span className="me-label">{t(lang, 'watching_as')}</span>
                <b className={`me-mode m-${me.mode}`}>{t(lang, me.mode)}</b>
                {who && (
                  <span className="me-extra">
                    <i className="club-dot" style={{ '--club': who.color } as React.CSSProperties} />
                    {who.short}
                  </span>
                )}
                {fav && (
                  <span className="me-extra">
                    #{fav.number} {fav.name.split(' ').slice(-1)[0]}
                  </span>
                )}
                <span className="me-lang">{lang.toUpperCase()}</span>
                <span className="me-caret">▾</span>
              </button>
              {menu && (
                <div className="me-menu">
                  <ProfilePicker profile={me} onChange={choose} />
                  <button
                    className="me-restart"
                    onClick={() => {
                      setMenu(false)
                      setOnboarding(true)
                    }}
                  >
                    ↺ {t(lang, 'start_over')}
                  </button>
                </div>
              )}
            </div>
          )}

          <nav className="views">
            {producer ? (
              <>
                <button onClick={() => setView('viewer')}>← {t(lang, 'back_to_mine')}</button>
                <button className={view === 'split' ? 'on' : ''} onClick={() => setView('split')}>
                  {t(lang, 'three_viewers')}
                </button>
                <button className={view === 'control' ? 'on' : ''} onClick={() => setView('control')}>
                  {t(lang, 'control_room')}
                </button>
              </>
            ) : (
              <button
                className="producer"
                onClick={() => {
                  setMenu(false)
                  setView('split')
                }}
              >
                <b>{t(lang, 'producer')}</b> · {t(lang, 'producer_sub')}
              </button>
            )}
            <button className={`tv ${tv ? 'on' : ''}`} disabled={!hasVideo} title={hasVideo ? 'TV picture with overlays' : 'no video in this export'} onClick={() => setTv(!tv)}>
              TV
            </button>
          </nav>
        </header>

        <main className="main" onClick={() => menu && setMenu(false)}>
          {view === 'viewer' && <Screen profile={me} tv={tv} />}
          {view === 'split' && (
            <div className="split">
              {split.map((p, i) => (
                <div key={i} className="split-col">
                  <ProfilePicker compact profile={p} onChange={(np) => setSplit(split.map((x, k) => (k === i ? np : x)))} />
                  <Screen profile={p} tv={tv} label />
                </div>
              ))}
            </div>
          )}
          {view === 'control' && (
            <div className="control-layout">
              <Screen profile={split[0]} tv={tv} />
              <ControlRoom />
            </div>
          )}
        </main>

        <Transport />
        {onboarding && (
          <Onboarding
            initial={profile}
            onDone={(p) => {
              choose(p)
              setOnboarding(false)
              setView('viewer')
            }}
            onClose={profile ? () => setOnboarding(false) : undefined}
          />
        )}
      </div>
    </MatchContext.Provider>
  )
}
