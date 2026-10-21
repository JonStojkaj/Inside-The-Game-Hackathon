import { useEffect, useRef } from 'react'
import { useMatch } from '../lib/context'
import { clockLabel } from '../lib/match'
import { useFrame, usePlaybackState } from '../lib/playback'
import type { MomentKind } from '../types'

const SPEEDS = [1, 5, 10]
const KIND_LABEL: Record<MomentKind, string> = {
  goal: 'Goal',
  big_chance: 'Big chance',
  decisive_pass: 'Decisive pass',
  dangerous_turnover: 'Dangerous turnover',
}

/** Play/pause, scrubber with key-moment markers, speed, and a Sliding Doors launcher. */
export function Transport() {
  const { m, pb, forcedInsight, setForcedInsight } = useMatch()
  const frame = useFrame(pb)
  const { playing, speed } = usePlaybackState(pb)
  const barRef = useRef<HTMLDivElement>(null)
  const n = pb.nFrames - 1

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

  const seekFromPointer = (clientX: number) => {
    const r = barRef.current!.getBoundingClientRect()
    pb.seek(((clientX - r.left) / r.width) * n)
  }

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
      <div
        className="tp-bar"
        ref={barRef}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId)
          seekFromPointer(e.clientX)
        }}
        onPointerMove={(e) => {
          if (e.buttons & 1) seekFromPointer(e.clientX)
        }}
      >
        <div className="tp-track" />
        <div className="tp-fill" style={{ width: `${(frame / n) * 100}%` }} />
        {m.bundle.moments.map((mo) => {
          const ins = m.insightForMoment(mo.id)
          return (
            <button
              key={mo.id}
              className={`tp-marker k-${mo.kind} ${ins ? 'has-insight' : ''}`}
              style={{ left: `${(mo.frame / n) * 100}%` }}
              title={`${KIND_LABEL[mo.kind]} · ${clockLabel(m.bundle, mo.frame)} · ${mo.reason}`}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => {
                pb.seek(Math.max(0, mo.frame - 40))
                pb.play()
              }}
            />
          )
        })}
        <div className="tp-head" style={{ left: `${(frame / n) * 100}%` }} />
      </div>
      <div className="tp-speeds">
        {SPEEDS.map((s) => (
          <button key={s} className={s === speed ? 'on' : ''} onClick={() => pb.setSpeed(s)}>
            {s}×
          </button>
        ))}
      </div>
      <div className="tp-sd">
        {m.bundle.insights
          .filter((i) => i.decision_frame != null)
          .map((i, k) => (
            <button
              key={i.id}
              className={forcedInsight === i.id ? 'on' : ''}
              title={i.claim}
              onClick={() => {
                if (forcedInsight === i.id) return setForcedInsight(null)
                pb.pause()
                pb.seek(i.decision_frame!)
                setForcedInsight(i.id)
              }}
            >
              SD{k + 1}
            </button>
          ))}
      </div>
    </div>
  )
}
