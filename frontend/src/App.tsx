import { useEffect, useMemo, useState } from 'react'
import { ControlRoom } from './components/ControlRoom'
import { ProfilePicker } from './components/ProfilePicker'
import { Screen } from './components/Screen'
import { Transport } from './components/Transport'
import { loadMatch, resolveSource } from './data/source'
import { MatchContext, type MatchCtx } from './lib/context'
import { indexMatch, timelineFrames } from './lib/match'
import { createPlayback } from './lib/playback'
import { presets } from './lib/profile'
import type { MatchBundle, ViewerProfile } from './types'

type View = 'broadcast' | 'split' | 'control'
const VIEWS: { id: View; label: string }[] = [
  { id: 'broadcast', label: 'Broadcast' },
  { id: 'split', label: '3-up' },
  { id: 'control', label: 'Control room' },
]

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

function Player({ bundle }: { bundle: MatchBundle }) {
  const q = new URLSearchParams(window.location.search)
  const m = useMemo(() => indexMatch(bundle), [bundle])
  const pb = useMemo(() => createPlayback(timelineFrames(bundle), bundle.match.fps), [bundle])
  const [forcedInsight, setForcedInsight] = useState<string | null>(null)
  const [view, setView] = useState<View>((q.get('view') as View) || 'broadcast')
  const [tv, setTv] = useState(q.has('tv'))
  const initial = useMemo(() => presets(bundle.overlays, bundle.match.players), [bundle])
  const [profile, setProfile] = useState<ViewerProfile>(initial[0])
  const [split, setSplit] = useState<ViewerProfile[]>(initial)
  const ctx = useMemo<MatchCtx>(() => ({ m, pb, forcedInsight, setForcedInsight }), [m, pb, forcedInsight])
  const hasVideo = Boolean(bundle.match.video)

  // ?f=<frame>&speed=5&play: start a demo take at a given moment
  useEffect(() => {
    const p = new URLSearchParams(window.location.search)
    if (p.has('f')) pb.seek(Number(p.get('f')))
    if (p.has('speed')) pb.setSpeed(Number(p.get('speed')))
    if (p.has('play')) pb.play()
    if (import.meta.env.DEV) (window as unknown as { __pb: typeof pb }).__pb = pb
    return () => pb.pause()
  }, [pb])

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
          <nav className="views">
            {VIEWS.map((v) => (
              <button key={v.id} className={view === v.id ? 'on' : ''} onClick={() => setView(v.id)}>
                {v.label}
              </button>
            ))}
            <button
              className={`tv ${tv ? 'on' : ''}`}
              disabled={!hasVideo}
              title={hasVideo ? 'TV picture with overlays' : 'no video in this export'}
              onClick={() => setTv(!tv)}
            >
              TV
            </button>
          </nav>
          {view !== 'split' && <ProfilePicker profile={profile} onChange={setProfile} />}
        </header>

        <main className="main">
          {view === 'broadcast' && <Screen profile={profile} tv={tv} />}
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
              <Screen profile={profile} tv={tv} />
              <ControlRoom />
            </div>
          )}
        </main>

        <Transport />
      </div>
    </MatchContext.Provider>
  )
}
