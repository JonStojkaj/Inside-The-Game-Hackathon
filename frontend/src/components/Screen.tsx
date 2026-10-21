import { useMemo } from 'react'
import { useMatch } from '../lib/context'
import { activeOverlays, doorsFromInsight, doorsFromOverlay, payloadPlayer } from '../lib/match'
import { useFrame } from '../lib/playback'
import { resolveSegment, t } from '../lib/profile'
import type { ViewerProfile } from '../types'
import { Fullscreen, LowerThird, SidePanel } from './Overlays'
import { Persistent } from './Persistent'
import { Pitch, type PitchTag } from './Pitch'
import { Scorebug } from './Scorebug'
import { SlidingDoorsCard } from './SlidingDoors'
import { Ticker } from './Ticker'
import { TvVideo } from './TvVideo'

interface Props {
  profile: ViewerProfile
  tv?: boolean
  label?: boolean
}

/** One viewer's broadcast: a 16:9 stage with the pitch (or TV picture) and the segment's overlays. */
export function Screen({ profile, tv, label }: Props) {
  const { m, pb, forcedInsight, setForcedInsight } = useMatch()
  const frame = useFrame(pb)
  const { overlays, match } = m.bundle
  const seg = resolveSegment(overlays, profile)
  const list = useMemo(() => [...(overlays['*'] ?? []), ...(overlays[seg.id] ?? [])], [overlays, seg.id])
  const tMs = (frame / match.fps) * 1000
  const active = activeOverlays(list, tMs)

  const sdOverlay = active.pitch?.type === 'sliding_doors' ? active.pitch : undefined
  const sd = forcedInsight ? doorsFromInsight(m.insight(forcedInsight)) : sdOverlay ? doorsFromOverlay(m, sdOverlay) : undefined
  const sdSince = useMemo(() => (sd ? performance.now() : 0), [sd])

  const tagOverlay = active.pitch?.type === 'player_tag' ? active.pitch : undefined
  const tagSince = useMemo(() => (tagOverlay ? performance.now() : 0), [tagOverlay?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const tags: PitchTag[] = tagOverlay
    ? [{ playerId: String(payloadPlayer(tagOverlay)), label: tagOverlay.headline.toUpperCase(), since: tagSince }]
    : []

  const fullscreen = active.fullscreen
  const showTv = Boolean(tv && match.video && !sd)

  return (
    <div className={`screen mode-${profile.mode}`}>
      <div className="stage">
        {tv && match.video && <TvVideo hidden={!showTv} />}
        <div className={`pitch-wrap ${showTv ? 'hidden' : ''}`}>
          <Pitch
            frozenFrame={sd?.decision_frame ?? null}
            ghosts={sd ? { insight: sd, since: sdSince } : null}
            tags={tags}
            focusPlayer={profile.mode === 'player_focus' ? profile.favourite_players[0] : null}
            showPressure={profile.mode === 'analyst'}
          />
        </div>
        {showTv && <div className="tv-mask" />}
        {sd && <div key={sd.key} className="sd-vignette" />}

        <Scorebug lang={profile.language} overlay={active.scorebug} />
        {!sd && <Persistent profile={profile} />}
        {!sd && <SidePanel overlay={active.side_panel} lang={profile.language} />}
        {!sd && !fullscreen && <LowerThird overlay={active.lower_third} />}
        {sd && (
          <SlidingDoorsCard
            key={sd.key}
            doors={sd}
            overlay={forcedInsight ? undefined : sdOverlay}
            lang={profile.language}
            onClose={forcedInsight ? () => setForcedInsight(null) : undefined}
          />
        )}
        <Ticker lang={profile.language} overlay={active.ticker} />
        <Fullscreen overlay={fullscreen} />

        {label && (
          <div className="screen-label">
            <b>{t(profile.language, profile.mode)}</b>
            {profile.mode === 'club_fan' && profile.favourite_club && <span>{m.club(profile.favourite_club).short}</span>}
            {profile.mode === 'player_focus' && profile.favourite_players[0] && (
              <span>#{m.player(profile.favourite_players[0])?.number}</span>
            )}
            <span className="lang">{profile.language.toUpperCase()}</span>
          </div>
        )}
      </div>
    </div>
  )
}
