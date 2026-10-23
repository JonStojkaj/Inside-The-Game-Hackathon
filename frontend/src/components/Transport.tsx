import { useEffect } from 'react'
import { useMatch } from '../lib/context'
import { clockLabel } from '../lib/match'
import { useFrame, usePlaybackState } from '../lib/playback'
import { t } from '../lib/profile'
import type { Lang } from '../types'
import { MatchStory } from './MatchStory'

const SPEEDS = [1, 5, 10]

interface Props {
  lang: Lang
  /** First-run hint above the play button ("Press play ..."); dismissed by play or "Got it". */
  hint?: boolean
  onHintDone?: () => void
}

/** Play/pause, the match-story strip (scrubber + key moments) and speed. */
export function Transport({ lang, hint, onHintDone }: Props) {
  const { m, pb, setForcedInsight } = useMatch()
  const frame = useFrame(pb)
  const { playing, speed } = usePlaybackState(pb)

  useEffect(() => {
    if (hint && playing) onHintDone?.()
  }, [hint, playing, onHintDone])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return
      if (e.code === 'Space') {
        e.preventDefault()
        pb.toggle()
      } else if (e.code === 'ArrowRight') pb.seek(pb.frame + 50)
      else if (e.code === 'ArrowLeft') pb.seek(pb.frame - 50)
      else if (e.key === '1') pb.setSpeed(1)
      else if (e.key === '5') pb.setSpeed(5)
      else if (e.key === '0') pb.setSpeed(10)
      else if (e.code === 'Escape') setForcedInsight(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [pb, setForcedInsight])

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
