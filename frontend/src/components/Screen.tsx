import { useMemo, useState } from 'react'
import { useMatch } from '../lib/context'
import { deriveOverlays, keepForMode, tickerFilter } from '../lib/derive'
import { activeOverlays, doorsFromInsight, doorsFromOverlay, isDoorsOverlay, payloadPlayer } from '../lib/match'
import { useFrame } from '../lib/playback'
import { resolveSegment, t } from '../lib/profile'
import type { ViewerProfile } from '../types'
import { AnalystHud, Hypotheses } from './modes/Analyst'
import { CasualMoments } from './modes/Casual'
import { FanBanner, FanMomentum } from './modes/Fan'
import { DecisionRecordView, PlayerAlert, PlayerCard } from './modes/Player'
import { Fullscreen, LowerThird, SidePanel } from './Overlays'
import { Pitch, type PitchTag } from './Pitch'
import { Radar } from './Radar'
import { Scorebug } from './Scorebug'
import { SlidingDoorsCard } from './SlidingDoors'
import { Ticker } from './Ticker'
import { TvVideo } from './TvVideo'

interface Props {
  profile: ViewerProfile
  tv?: boolean
  label?: boolean
}

/**
 * One viewer's broadcast. The same match clock, moments and insights, but each mode selects,
 * words and lays out them differently (PLAN §8): analyst HUD, club-fan banners in club colours,
 * a player cam with live card, or the casual big-moments view.
 */
export function Screen({ profile, tv, label }: Props) {
  const { m, pb, forcedInsight, setForcedInsight, askedQuestion } = useMatch()
  const frame = useFrame(pb)
  const { overlays, match } = m.bundle
  const { mode, language: lang } = profile
  const seg = resolveSegment(overlays, profile)
  // produced segment when the production team made exactly this one, else derived client-side in
  // the viewer's language (never another language's text)
  const list = useMemo(() => {
    const base = seg.exact ? (overlays[seg.id] ?? []) : deriveOverlays(m, profile)
    return [...(overlays['*'] ?? []), ...base].filter((o) => keepForMode(m, profile, o))
  }, [m, overlays, seg.id, seg.exact, profile])
  const ticker = useMemo(() => tickerFilter(profile), [profile])
  const tMs = (frame / match.fps) * 1000
  const active = activeOverlays(list, tMs)

  const sdOverlay = isDoorsOverlay(active.pitch) ? active.pitch : undefined
  const sd = forcedInsight ? doorsFromInsight(m.insight(forcedInsight)) : sdOverlay ? doorsFromOverlay(m, sdOverlay) : undefined
  const sdSince = useMemo(() => (sd ? performance.now() : 0), [sd])
  const oneLine = mode === 'club_fan' || mode === 'casual'

  const pid = mode === 'player_focus' ? profile.favourite_players[0] : undefined
  const club = mode === 'club_fan' && profile.favourite_club ? m.club(profile.favourite_club) : undefined

  const tagOverlay = active.pitch?.type === 'player_tag' ? active.pitch : undefined
  const tagSince = useMemo(() => (tagOverlay ? performance.now() : 0), [tagOverlay?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const tags: PitchTag[] = tagOverlay
    ? [{ playerId: String(payloadPlayer(tagOverlay)), label: tagOverlay.headline.toUpperCase(), since: tagSince }]
    : []

  const fullscreen = active.fullscreen
  const [videoFailed, setVideoFailed] = useState(false)
  const hasVideo = Boolean(tv && match.video && !videoFailed)
  const showTv = hasVideo && !sd

  return (
    <div
      className={`screen mode-${mode} ${showTv ? 'on-tv' : ''} ${sd ? 'in-doors' : ''}`}
      style={club ? ({ '--club': club.color } as React.CSSProperties) : undefined}
    >
      <div className="stage">
        {hasVideo && (
          <div className={`tv-box ${showTv ? '' : 'hidden'}`}>
            <TvVideo hidden={false} onFail={() => setVideoFailed(true)} />
            {/* our graphics sit exactly on the engine's own HUD (scoreboard top-left, minimap bottom-centre) */}
            <div className="tv-cover tv-cover-score">
              <span className="brand-mark">
                <i />
                <i />
              </span>
              {match.home.short} – {match.away.short}
            </div>
            <Radar focusPlayer={pid ?? null} />
          </div>
        )}
        <div className={`pitch-wrap ${showTv ? 'hidden' : ''}`}>
          <Pitch
            frozenFrame={sd?.decision_frame ?? null}
            ghosts={sd ? { insight: sd, since: sdSince } : null}
            tags={tags}
            focusPlayer={pid ?? null}
            follow={mode === 'player_focus'}
            showPressure={mode === 'analyst'}
          />
        </div>
        {club && <div className="club-frame" />}
        {sd && <div key={`vignette-${sd.key}`} className="sd-vignette" />}

        <Scorebug lang={lang} overlay={sd ? undefined : active.scorebug} />
        <div className="feed">
          {!sd && mode === 'analyst' && (
            <div className="hud-col">
              <AnalystHud lang={lang} />
              <SidePanel overlay={active.side_panel} lang={lang} />
            </div>
          )}
          {!sd && club && <FanMomentum team={club.key} lang={lang} />}
          {!sd && pid && <PlayerCard pid={pid} lang={lang} />}
          {!sd && !fullscreen && pid && <PlayerAlert pid={pid} lang={lang} />}
          {!sd && !fullscreen && mode !== 'casual' && <LowerThird overlay={active.lower_third} />}
        </div>
        {!sd && !fullscreen && club && <FanBanner team={club.key} lang={lang} />}
        {!sd && !fullscreen && mode === 'casual' && <CasualMoments lang={lang} />}
        {sd && (
          <SlidingDoorsCard
            key={sd.key}
            doors={sd}
            overlay={forcedInsight ? undefined : sdOverlay}
            headline={askedQuestion(forcedInsight)}
            simple={!forcedInsight && oneLine}
            lang={lang}
            onClose={forcedInsight ? () => setForcedInsight(null) : undefined}
            side={mode === 'player_focus' && sd.insight ? <DecisionRecordView ins={sd.insight} lang={lang} /> : undefined}
            aside={mode === 'analyst' && sd.insight ? <Hypotheses ins={sd.insight} lang={lang} /> : undefined}
          />
        )}
        {ticker && <Ticker lang={lang} overlay={active.ticker} filter={ticker} />}
        <Fullscreen overlay={fullscreen} />

        {label && (
          <div className="screen-label" title={seg.exact ? `overlay segment ${seg.id}` : t(lang, 'derived')}>
            <b>{t(lang, mode)}</b>
            {club && <span style={{ boxShadow: `inset 0.25em 0 0 ${club.color}` }}>{club.short}</span>}
            {pid && <span>#{m.player(pid)?.number}</span>}
            <span className="lang">{lang.toUpperCase()}</span>
          </div>
        )}
      </div>
    </div>
  )
}
