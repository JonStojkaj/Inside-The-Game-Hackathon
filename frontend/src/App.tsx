import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AskButton, AskPanel } from './components/AskPanel'
import { useAskAvailable } from './lib/ask'
import { Commentator } from './components/Commentator'
import { ControlRoom } from './components/ControlRoom'
import { Onboarding } from './components/Onboarding'
import { ProfilePicker } from './components/ProfilePicker'
import { Screen } from './components/Screen'
import { Transport } from './components/Transport'
import { loadMatch, resolveSource } from './data/source'
import { unlockAudio } from './lib/audio'
import { MatchContext, type DoorsBreak, type MatchCtx } from './lib/context'
import { resetExplainer } from './lib/explainer'
import { indexMatch, timelineFrames } from './lib/match'
import { doorsForMoment, doorsOverlays, overlayList } from './lib/overlays'
import { createPlayback } from './lib/playback'
import { loadProfile, presets, profileFromQuery, saveProfile, t } from './lib/profile'
import type { Insight, MatchBundle, Moment, ViewerProfile } from './types'

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

let breakSeq = 0

function Player({ bundle }: { bundle: MatchBundle }) {
  const q = useMemo(() => new URLSearchParams(window.location.search), [])
  const base = useMemo(() => indexMatch(bundle), [bundle])
  // Ask Sliding Doors answers live next to the exported insights (never replacing a key moment's own insight)
  const [asked, setAsked] = useState<Record<string, { insight: Insight; question: string }>>({})
  const m = useMemo(() => ({ ...base, insight: (id: string | null | undefined) => base.insight(id) ?? (id ? asked[id]?.insight : undefined) }), [base, asked])
  const addAsked = useCallback((insight: Insight, question: string) => setAsked((a) => ({ ...a, [insight.id]: { insight, question } })), [])
  const pb = useMemo(() => {
    const p = createPlayback(timelineFrames(bundle), bundle.match.fps)
    if (q.has('f')) p.seek(Number(q.get('f'))) // before any child reads the clock (e.g. ?ask_open)
    return p
  }, [bundle, q])
  const [view, setView] = useState<View>(() => initialView(q))
  const demo = useMemo(() => presets(bundle.overlays, bundle.match.players), [bundle])
  const players = bundle.match.players
  // demo takes put the profile in the URL; everyone else answers the questions first (the last
  // answer is pre-selected, never auto-applied)
  const urlProfile = useMemo(() => profileFromQuery(players), [players])
  const skipOnboarding = Boolean(urlProfile) || initialView(q) !== 'viewer' || q.has('shot')
  const [profile, setProfile] = useState<ViewerProfile | null>(() => urlProfile ?? (skipOnboarding ? loadProfile(players) : null))
  const [onboarding, setOnboarding] = useState(() => q.has('onboarding') || !skipOnboarding)
  const lastProfile = useMemo(() => loadProfile(players), [players])
  const [menu, setMenu] = useState(false)
  const [split, setSplit] = useState<ViewerProfile[]>(demo)
  const [sound, setSound] = useState(true)
  const hasAudio = bundle.audio.length > 0
  const [askOpen, setAskOpen] = useState(q.has('ask_open'))
  const askOk = useAskAvailable()
  const me = profile ?? demo[0]
  const lang = profile?.language ?? 'en'
  const producer = view !== 'viewer'
  const primary = producer ? split[0] : me

  // ---------------------------------------------------------------- Sliding Doors breaks
  const [doorsBreak, setBreak] = useState<DoorsBreak | null>(null)
  const breakRef = useRef<DoorsBreak | null>(null)
  const lastShown = useRef<string | null>(null)
  const primaryList = useMemo(() => overlayList(m, primary).list, [m, primary])
  const primaryDoors = useMemo(() => doorsOverlays(m, primaryList), [m, primaryList])

  const openDoors = useCallback(
    (b: Omit<DoorsBreak, 'key'>) => {
      pb.pause()
      const next = { ...b, key: `brk-${++breakSeq}` }
      if (b.overlay) lastShown.current = b.overlay.id
      breakRef.current = next
      setBreak(next)
    },
    [pb],
  )
  const closeDoors = useCallback(
    (resume: boolean) => {
      const b = breakRef.current
      breakRef.current = null
      setBreak(null)
      if (resume) {
        if (b?.resumeFrame != null) pb.seek(b.resumeFrame)
        pb.play()
      }
    },
    [pb],
  )
  const openMoment = useCallback(
    (mo: Moment) => {
      const o = doorsForMoment(m, primaryList, mo.id)
      const ins = m.insightForMoment(mo.id)
      const resumeFrame = Math.max(0, mo.frame - 40) // then watch it happen for real
      if (o) {
        pb.seek(mo.frame)
        openDoors({ overlay: o, auto: true, resumeFrame })
      } else if (ins && ins.decision_frame != null) {
        pb.seek(mo.frame)
        openDoors({ insightId: ins.id, auto: true, resumeFrame })
      } else {
        closeDoors(false)
        pb.seek(resumeFrame)
        pb.play()
      }
    },
    [m, pb, primaryList, openDoors, closeDoors],
  )

  // the clock crossing the start of one of the primary viewer's Sliding Doors overlays pauses the
  // match for the break; playing again (Continue, space, play button) always ends a break
  useEffect(() => {
    let prev = pb.frame
    if (import.meta.env.DEV) (window as unknown as { __doors: unknown }).__doors = { list: primaryDoors, lastShown }
    return pb.subscribe(() => {
      const now = pb.frame
      if (pb.playing && breakRef.current) {
        breakRef.current = null
        setBreak(null)
      }
      // a break that was shown may come back once the viewer rewinds well before it
      const shown = lastShown.current ? primaryDoors.find((x) => x.id === lastShown.current) : undefined
      if (shown && (now / pb.fps) * 1000 < shown.start_ms - 20000) lastShown.current = null
      const step = now - prev
      if (pb.playing && step > 0 && step < pb.fps * 2 * Math.max(1, pb.speed)) {
        const t0 = (prev / pb.fps) * 1000
        const t1 = (now / pb.fps) * 1000
        const o = primaryDoors.find((x) => x.start_ms > t0 && x.start_ms <= t1 && x.id !== lastShown.current)
        if (o) {
          prev = now
          openDoors({ overlay: o, auto: true })
          return
        }
      }
      prev = now
    })
  }, [pb, primaryDoors, openDoors])

  const forcedInsight = doorsBreak?.insightId ?? null
  const setForcedInsight = useCallback((id: string | null) => (id ? openDoors({ insightId: id, auto: false }) : closeDoors(false)), [openDoors, closeDoors])

  const ctx = useMemo<MatchCtx>(
    () => ({ m, pb, doorsBreak, openDoors, closeDoors, openMoment, forcedInsight, setForcedInsight, addAsked, askedQuestion: (id) => (id ? asked[id]?.question : undefined) }),
    [m, pb, doorsBreak, openDoors, closeDoors, openMoment, forcedInsight, setForcedInsight, addAsked, asked],
  )

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

  // ?moment=<moment id>: a demo take opens that moment's Sliding Doors break
  useEffect(() => {
    const id = q.get('moment')
    const mo = id ? m.moment(id) : undefined
    if (mo && !onboarding) openMoment(mo)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // the first click / key (the onboarding answer) unlocks audio for the whole session
  useEffect(() => {
    const on = () => unlockAudio()
    window.addEventListener('pointerdown', on, { capture: true })
    window.addEventListener('keydown', on, { capture: true })
    return () => {
      window.removeEventListener('pointerdown', on, { capture: true })
      window.removeEventListener('keydown', on, { capture: true })
    }
  }, [])

  const who = me.mode === 'club_fan' && me.favourite_club ? m.club(me.favourite_club) : null
  const fav = me.mode === 'player_focus' ? m.player(me.favourite_players[0]) : undefined
  const ask = askOk ? () => setAskOpen(true) : undefined

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

          <span className="topbar-match">
            <i style={{ background: bundle.match.home.color }} />
            {bundle.match.home.name} <span>v</span> {bundle.match.away.name}
            <i style={{ background: bundle.match.away.color }} />
          </span>
          <div className="topbar-spacer" />
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
                title={t(lang, 'producer_title')}
                onClick={() => {
                  setMenu(false)
                  setView('split')
                }}
              >
                {t(lang, 'producer')}
              </button>
            )}
            <AskButton lang={lang} open={askOpen} onToggle={() => setAskOpen(!askOpen)} />
          </nav>
          {hasAudio && (
            <button
              className={`sound ${sound ? 'on' : ''}`}
              onClick={() => setSound(!sound)}
              title={t(lang, sound ? 'sound_on' : 'sound_off')}
              aria-label={t(lang, sound ? 'sound_on' : 'sound_off')}
              aria-pressed={sound}
            >
              <span aria-hidden>{sound ? '🔊' : '🔇'}</span>
              <small>{t(lang, sound ? 'sound_on' : 'sound_off')}</small>
            </button>
          )}
        </header>

        <main className="main" onClick={() => menu && setMenu(false)}>
          {view === 'viewer' && <Screen profile={me} primary onAsk={ask} holdBreak={askOpen} />}
          {view === 'split' && (
            <div className="split">
              {split.map((p, i) => (
                <div key={i} className="split-col">
                  <ProfilePicker compact profile={p} onChange={(np) => setSplit(split.map((x, k) => (k === i ? np : x)))} />
                  <Screen profile={p} label primary={i === 0} onAsk={i === 0 ? ask : undefined} holdBreak={askOpen} />
                </div>
              ))}
            </div>
          )}
          {view === 'control' && (
            <div className="control-layout">
              <Screen profile={split[0]} primary onAsk={ask} holdBreak={askOpen} />
              <ControlRoom />
            </div>
          )}
        </main>

        {askOpen && <AskPanel lang={producer ? split[0].language : lang} onClose={() => setAskOpen(false)} />}
        <Transport lang={lang} />
        {hasAudio && !onboarding && <Commentator profile={primary} audible={sound} />}
        {onboarding && (
          <Onboarding
            initial={profile ?? lastProfile}
            onDone={(p) => {
              choose(p)
              setOnboarding(false)
              setView('viewer')
              resetExplainer()
              // the answer was a click: audio is unlocked, so the match can start right away
              if (!q.has('shot')) pb.play()
            }}
            onClose={profile ? () => setOnboarding(false) : undefined}
          />
        )}
      </div>
    </MatchContext.Provider>
  )
}
