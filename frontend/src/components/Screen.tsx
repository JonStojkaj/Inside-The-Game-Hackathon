import { useMemo, useState, useSyncExternalStore } from 'react'
import { caption } from '../lib/audio'
import { useMatch } from '../lib/context'
import { overlayMoment } from '../lib/derive'
import { activeOverlays, comparison, doorsFromInsight, doorsFromOverlay, payloadPlayer, type Doors } from '../lib/match'
import { doorsOverlays, useOverlayList } from '../lib/overlays'
import { useFrame } from '../lib/playback'
import { t } from '../lib/profile'
import { isCarry, representative } from '../lib/story'
import type { Overlay, ViewerProfile } from '../types'
import { DoorsBreak } from './DoorsBreak'
import { CasualMoments } from './modes/Casual'
import { FanBanner } from './modes/Fan'
import { PlayerAlert } from './modes/Player'
import { Fullscreen, LowerThird } from './Overlays'
import { Pitch, type PitchTag } from './Pitch'
import { Radar } from './Radar'
import { Scorebug } from './Scorebug'
import { FanSide } from './side/FanSide'
import { useAnalystCats } from '../lib/analystCats'
import { AnalystColumn, CatPicker } from './side/AnalystBoard'
import { AnalystSide, CasualSide } from './side/OtherSides'
import { PlayerSide } from './side/PlayerSide'
import { TvVideo } from './TvVideo'

interface Props {
  profile: ViewerProfile
  /** The viewer the commentator speaks for (shows the caption). */
  primary?: boolean
  /** Ask Sliding Doors is available: the break card offers it. */
  onAsk?: () => void
  /** Hold the break countdown (Ask panel open). */
  holdBreak?: boolean
}

/**
 * One viewer's broadcast: the TV picture is the stage (our scorebug and radar sit on the engine's
 * own HUD), a slim sidebar carries the few mode-specific blocks, and at a key moment the match
 * pauses for Sliding Doors (pitch with the ghost futures + one compact card), then plays on.
 * Without a video the 2D tactical pitch is the stage.
 */
export function Screen({ profile, primary, onAsk, holdBreak }: Props) {
  const { m, pb, doorsBreak, closeDoors, askedQuestion } = useMatch()
  const frame = useFrame(pb)
  const { match } = m.bundle
  const { mode, language: lang } = profile
  const { list } = useOverlayList(m, profile)
  const tMs = (frame / match.fps) * 1000
  const active = activeOverlays(list, tMs)

  // Sliding Doors only during a break (the clock is paused), never as a frozen view while playing
  const mine = useMemo(() => doorsOverlays(m, list), [m, list])
  const br = doorsBreak
  const asked = br?.insightId ? askedQuestion(br.insightId) : undefined
  let sdOverlay: Overlay | undefined
  let sd: Doors | undefined
  if (br) {
    if (br.overlay && list.includes(br.overlay)) sdOverlay = br.overlay
    else {
      const mo = br.overlay ? overlayMoment(m, br.overlay) : br.insightId ? m.moment(m.insight(br.insightId)?.moment_id) : undefined
      if (!asked) sdOverlay = mine.find((o) => mo && overlayMoment(m, o)?.id === mo.id)
    }
    sd = sdOverlay ? doorsFromOverlay(m, sdOverlay) : br.insightId ? doorsFromInsight(m.insight(br.insightId)) : br.overlay ? doorsFromOverlay(m, br.overlay) : undefined
  }
  const sdSince = useMemo(() => (sd ? performance.now() : 0), [sd])
  // the one alternative future the story plays out (only when the engine found a best alternative)
  const sdAlt = useMemo(() => (sd && comparison(sd.numbers, sd.metric).alt != null ? representative(sd.alt_ghost_paths) : null), [sd])

  const pid = mode === 'player_focus' ? profile.favourite_players[0] : undefined
  const club = mode === 'club_fan' && profile.favourite_club ? m.club(profile.favourite_club) : undefined

  const tagOverlay = active.pitch?.type === 'player_tag' ? active.pitch : undefined
  const tagSince = useMemo(() => (tagOverlay ? performance.now() : 0), [tagOverlay?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const tags: PitchTag[] = tagOverlay ? [{ playerId: String(payloadPlayer(tagOverlay)), label: tagOverlay.headline.toUpperCase(), since: tagSince }] : []

  const fullscreen = active.fullscreen
  const [videoFailed, setVideoFailed] = useState(false)
  const hasVideo = Boolean(match.video && !videoFailed)
  const [view, setView] = useStageView(mode)
  const [cats, toggleCat] = useAnalystCats()
  const showVideo = hasVideo && !sd && view === 'video'
  const quiet = Boolean(sd || fullscreen)
  const breakInsight = sd?.insight

  return (
    <div
      className={`screen mode-${mode} ${showVideo ? 'on-tv' : ''} ${sd ? 'in-doors' : ''}`}
      style={club ? ({ '--club': club.color } as React.CSSProperties) : undefined}
    >
      {mode === 'analyst' && (
        <aside className="side side-left" aria-label={t(lang, 'cat_pick')}>
          <CatPicker lang={lang} cats={cats} onToggle={toggleCat} />
          <AnalystColumn lang={lang} cats={cats} side={0} />
        </aside>
      )}
      <div className="stage-col">
        <div className="stage">
          {hasVideo && view === 'video' && (
            <div className={`tv-box ${showVideo ? '' : 'hidden'}`} aria-hidden={!showVideo}>
              <TvVideo hidden={!showVideo} onFail={() => setVideoFailed(true)} />
              <Radar focusPlayer={pid ?? null} />
            </div>
          )}
          {!showVideo && (
            <div className="pitch-wrap">
              <Pitch
                frozenFrame={sd?.decision_frame ?? null}
                ghosts={sd ? { insight: sd, since: sdSince, alt: sdAlt, carry: sdAlt ? isCarry(sdAlt) : false } : null}
                tags={tags}
                focusPlayer={pid ?? null}
                follow={mode === 'player_focus' && !sd}
                showPressure={mode === 'analyst'}
              />
            </div>
          )}
          {club && <div className="club-frame" />}

          <Scorebug lang={lang} overlay={quiet || mode === 'casual' ? undefined : active.scorebug} />
          {!quiet && pid && <PlayerAlert pid={pid} lang={lang} />}
          {!quiet && !pid && mode !== 'casual' && <LowerThird overlay={active.lower_third ?? (active.ticker?.type === 'alert' ? active.ticker : undefined)} />}
          {!quiet && club && <FanBanner team={club.key} lang={lang} />}
          {!quiet && mode === 'casual' && <CasualMoments lang={lang} />}
          {sd && (
            <DoorsBreak
              key={`${br?.key}-${sd.key}`}
              doors={sd}
              overlay={sdOverlay}
              since={sdSince}
              headline={asked}
              audit={mode === 'analyst'}
              lang={lang}
              auto={Boolean(br?.auto)}
              hold={holdBreak}
              onContinue={() => closeDoors(true)}
              onAsk={onAsk}
            />
          )}
          {!sd && (
            <div className="view-switch" role="radiogroup" aria-label="Video / 2D">
              <button role="radio" aria-checked={showVideo} className={showVideo ? 'on' : ''} disabled={!hasVideo} onClick={() => setView('video')}>
                ▶ {t(lang, 'view_video')}
              </button>
              <button role="radio" aria-checked={!showVideo} className={!showVideo ? 'on' : ''} onClick={() => setView('2d')}>
                ▦ {t(lang, 'view_2d')}
              </button>
            </div>
          )}
          <Fullscreen overlay={fullscreen} />
          {primary && <Caption lang={lang} />}

        </div>
      </div>
      <aside className={`side side-${mode}`} aria-label={t(lang, mode)}>
        {mode === 'club_fan' && club && <FanSide team={club.key} lang={lang} />}
        {mode === 'player_focus' && pid && <PlayerSide pid={pid} lang={lang} breakInsight={breakInsight} />}
        {mode === 'analyst' && <AnalystSide lang={lang} cats={cats} breakInsight={breakInsight} />}
        {mode === 'casual' && <CasualSide lang={lang} />}
      </aside>
    </div>
  )
}

/** The commentator's words while a clip plays (also when muted). */
function Caption({ lang }: { lang: ViewerProfile['language'] }) {
  const c = useSyncExternalStore(caption.subscribe, caption.get)
  if (!c) return null
  return (
    <div className="commentary" key={c.id} role="status" aria-live="polite">
      <span className="commentary-tag">🎙 {t(lang, 'commentator')}</span>
      <span className="commentary-text">{c.text}</span>
    </div>
  )
}

type StageView = 'video' | '2d'
const VIEW_KEY = 'sliding-doors.stage-view.v1'

/**
 * Video or 2D pitch, chosen per mode and remembered for the session. The analyst starts on 2D
 * (all 22 players, the pressure halo and the shape read better than the broadcast camera, which
 * only ever shows a third of the pitch); everyone else starts on the TV picture.
 */
function useStageView(mode: ViewerProfile['mode']): [StageView, (v: StageView) => void] {
  const read = (): StageView => {
    try {
      const v = sessionStorage.getItem(`${VIEW_KEY}.${mode}`)
      if (v === 'video' || v === '2d') return v
    } catch {
      // no storage
    }
    return mode === 'analyst' ? '2d' : 'video'
  }
  const [state, setState] = useState<{ mode: string; view: StageView }>(() => ({ mode, view: read() }))
  const view = state.mode === mode ? state.view : read()
  const set = (v: StageView) => {
    setState({ mode, view: v })
    try {
      sessionStorage.setItem(`${VIEW_KEY}.${mode}`, v)
    } catch {
      // no storage
    }
  }
  return [view, set]
}
