import { useEffect } from 'react'
import { CUTS, useCutPlayer } from '../lib/highlights'
import { useMatch } from '../lib/context'
import { clockLabel, minuteLabel } from '../lib/match'
import { useFrame, usePlaybackState } from '../lib/playback'
import { t } from '../lib/profile'
import type { Lang, ProfileMode } from '../types'
import { MatchStory } from './MatchStory'

const SPEEDS = [1, 5, 10]

interface Props {
  lang: Lang
  /** First-run hint above the play button ("Press play ..."); dismissed by play or "Got it". */
  hint?: boolean
  onHintDone?: () => void
  /** Big moments (casual) plays as a cut highlights package. */
  mode?: ProfileMode
}

/** Play/pause, the match-story strip (scrubber + key moments) and speed. */
export function Transport({ lang, hint, onHintDone, mode }: Props) {
  const { m, pb, closeDoors } = useMatch()
  const frame = useFrame(pb)
  const { playing, speed } = usePlaybackState(pb)
  const hl = useCutPlayer(m, pb, mode === 'casual')

  useEffect(() => {
    if (hint && playing) onHintDone?.()
  }, [hint, playing, onHintDone])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement || e.target instanceof HTMLTextAreaElement) return
      if (e.code === 'Space') {
        e.preventDefault()
        pb.toggle()
      } else if (e.code === 'ArrowRight') pb.seek(pb.frame + 50)
      else if (e.code === 'ArrowLeft') pb.seek(pb.frame - 50)
      else if (e.key === '1') pb.setSpeed(1)
      else if (e.key === '5') pb.setSpeed(5)
      else if (e.key === '0') pb.setSpeed(10)
      else if (e.code === 'Escape') closeDoors(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [pb, closeDoors])

  return (
    <div className="transport">
      <button className="tp-play" onClick={() => pb.toggle()} aria-label={playing ? 'pause' : 'play'}>
        {playing ? (
          <svg viewBox="0 0 24 24">
            <rect x="6" y="5" width="4" height="14" rx="1" />
            <rect x="14" y="5" width="4" height="14" rx="1" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24">
            <path d="M7 5l12 7-12 7z" />
          </svg>
        )}
      </button>
      <div className="tp-clock">{clockLabel(m.bundle, frame)}</div>
      <MatchStory lang={lang} />
      {mode === 'casual' && (
        <div className="tp-cuts" role="group">
          {CUTS.map((c) => (
            <button key={c} className={c === hl.cut ? 'on' : ''} aria-pressed={c === hl.cut} onClick={() => hl.setCut(c)}>
              {t(lang, `cut_${c}`)}
            </button>
          ))}
        </div>
      )}
      {hl.clip && (
        <div key={hl.cuts} className={`cut-label cut-${hl.clip.kind}`} role="status">
          <b>{t(lang, `cut_${hl.clip.kind}`)}</b> {minuteLabel(m.bundle, hl.clip.at)}
          <span>
            {hl.index + 1}/{hl.clips.length}
          </span>
        </div>
      )}
      {hl.cuts > 0 && <div key={`flash-${hl.cuts}`} className="cut-flash" aria-hidden />}
      <div className="tp-speeds">
        {SPEEDS.map((s) => (
          <button key={s} className={s === speed ? 'on' : ''} onClick={() => pb.setSpeed(s)}>
            {s}×
          </button>
        ))}
      </div>
      {hint && (
        <div className="tp-hint" role="status">
          <span>▶</span> {t(lang, 'hint_play')}
          <button onClick={onHintDone}>{t(lang, 'hint_ok')}</button>
        </div>
      )}
    </div>
  )
}
