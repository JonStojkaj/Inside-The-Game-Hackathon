import { useMemo, useRef, useState } from 'react'
import { useMatch } from '../lib/context'
import { chanceInfo, doorsSentence, goalEvents, whyGoal } from '../lib/derive'
import { minuteLabel, type MatchIndex } from '../lib/match'
import { useFrame } from '../lib/playback'
import { t } from '../lib/profile'
import type { Lang, Moment, MomentKind } from '../types'

const KIND_ICON: Record<MomentKind, string> = {
  goal: '⚽',
  big_chance: '◎',
  decisive_pass: '➚',
  dangerous_turnover: '⇄',
}

const W = 1000
const H = 40
const SMOOTH = 9 // snapshots (~1 per match second) in the rolling mean

/** Home share of control per stats snapshot (0.5 = balanced) and chaos (0..1), smoothed. */
function storySeries(m: MatchIndex): { x: number; home: number; chaos: number }[] {
  const { stats, match } = m.bundle
  const n = Math.max(1, match.n_frames - 1)
  const raw = stats.map((s) => {
    const ct = s.control.control_team
    const sh = s.control.control_share
    const home = ct && sh != null ? (ct === 'home' ? sh : 1 - sh) : 0.5
    return { x: ((s.t_ms / 1000) * match.fps) / n, home, chaos: s.control.chaos ?? 0 }
  })
  return raw.map((p, i) => {
    const w = raw.slice(Math.max(0, i - SMOOTH + 1), i + 1)
    return { x: p.x, home: w.reduce((a, q) => a + q.home, 0) / w.length, chaos: w.reduce((a, q) => a + q.chaos, 0) / w.length }
  })
}

/** One line on why a moment mattered, in the viewer's language; numbers only from the data. */
function whyItMattered(m: MatchIndex, mo: Moment, lang: Lang): string {
  if (mo.kind === 'goal') {
    const g = goalEvents(m).find((e) => Math.abs(e.frame - mo.frame) < 30)
    if (g) return whyGoal(m, g, lang)
  }
  if (mo.kind === 'big_chance') return chanceInfo(m, mo, lang).wouldMake
  const ins = m.insightForMoment(mo.id)
  return ins ? doorsSentence(ins, lang) : mo.reason
}

/**
 * The match at a glance: who controls the game (home above the line, away below), how chaotic it
 * is (gold band) and every key moment as a clickable marker that opens its Sliding Doors replay.
 * Doubles as the scrubber; shared by every view, the producer view included.
 */
export function MatchStory({ lang }: { lang: Lang }) {
  const { m, pb, forcedInsight, doorsBreak, openMoment } = useMatch()
  const frame = useFrame(pb)
  const ref = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<string | null>(null)
  const n = pb.nFrames - 1
  const { home, away } = m.bundle.match
  const series = useMemo(() => storySeries(m), [m])
  const goals = useMemo(() => goalEvents(m), [m])

  const area = useMemo(() => {
    if (series.length < 2) return null
    const pts = series.map((p) => `${(p.x * W).toFixed(1)},${(H - p.home * H).toFixed(1)}`)
    const first = (series[0].x * W).toFixed(1)
    const last = (series[series.length - 1].x * W).toFixed(1)
    return `M${first},${H / 2} L${pts.join(' L')} L${last},${H / 2} Z`
  }, [series])

  // chaos as a gold area growing up from the bottom edge (full height = chaos 1)
  const chaos = useMemo(() => {
    if (series.length < 2) return null
    const pts = series.map((p) => `${(p.x * W).toFixed(1)},${(10 - Math.min(1, p.chaos) * 10).toFixed(2)}`)
    return `M${(series[0].x * W).toFixed(1)},10 L${pts.join(' L')} L${(series[series.length - 1].x * W).toFixed(1)},10 Z`
  }, [series])

  const seek = (clientX: number) => {
    const r = ref.current!.getBoundingClientRect()
    pb.seek(((clientX - r.left) / r.width) * n)
  }

  const open = (mo: Moment) => openMoment(mo)

  const pos = (f: number) => `${(Math.min(f, n) / n) * 100}%`
  const head = pos(frame)

  return (
    <div className="ms" title={t(lang, 'story_hint')}>
      <div className="ms-legend">
        <span style={{ color: home.color }}>▲ {home.short}</span>
        <span className="ms-legend-mid">{t(lang, 'story_control')}</span>
        <span style={{ color: away.color }}>▼ {away.short}</span>
        <span className="ms-legend-chaos">{t(lang, 'story_chaos')}</span>
      </div>
      <div className="ms-body">
        <div className="ms-lane">
          {m.bundle.moments.map((mo) => {
            const ins = m.insightForMoment(mo.id)
            const on = (ins != null && forcedInsight === ins.id) || (doorsBreak?.overlay != null && doorsBreak.overlay.payload.moment_id === mo.id)
            return (
              <button
                key={mo.id}
                className={`ms-mk k-${mo.kind} ${on ? 'on' : ''} ${frame >= mo.frame ? 'past' : ''}`}
                style={{ left: pos(mo.frame), '--team': m.club(mo.team).color } as React.CSSProperties}
                onClick={() => open(mo)}
                onPointerEnter={() => setHover(mo.id)}
                onPointerLeave={() => setHover((h) => (h === mo.id ? null : h))}
                onFocus={() => setHover(mo.id)}
                onBlur={() => setHover(null)}
                aria-label={`${t(lang, `k_${mo.kind}`)} ${minuteLabel(m.bundle, mo.frame)}`}
              >
                <i>{KIND_ICON[mo.kind]}</i>
                <span>{minuteLabel(m.bundle, mo.frame)}</span>
                {hover === mo.id && (
                  <div className={`ms-tip ${mo.frame / n > 0.75 ? 'right' : mo.frame / n < 0.2 ? 'left' : ''}`}>
                    <div className="ms-tip-head">
                      {KIND_ICON[mo.kind]} {minuteLabel(m.bundle, mo.frame)} · {t(lang, `k_${mo.kind}`)} · <b style={{ color: m.club(mo.team).color }}>{m.club(mo.team).short}</b>
                    </div>
                    <div className="ms-tip-why">{whyItMattered(m, mo, lang)}</div>
                    <div className="ms-tip-cta">{t(lang, ins ? 'story_click' : 'story_jump')}</div>
                  </div>
                )}
              </button>
            )
          })}
        </div>
        <div
          className="ms-chart"
          ref={ref}
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId)
            seek(e.clientX)
          }}
          onPointerMove={(e) => {
            if (e.buttons & 1) seek(e.clientX)
          }}
        >
          <svg className="ms-momentum" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
            <defs>
              <clipPath id="ms-top">
                <rect x="0" y="0" width={W} height={H / 2} />
              </clipPath>
              <clipPath id="ms-bot">
                <rect x="0" y={H / 2} width={W} height={H / 2} />
              </clipPath>
            </defs>
            {area && (
              <>
                <path d={area} fill={home.color} clipPath="url(#ms-top)" opacity="0.85" />
                <path d={area} fill={away.color} clipPath="url(#ms-bot)" opacity="0.85" />
              </>
            )}
            <line x1="0" x2={W} y1={H / 2} y2={H / 2} className="ms-mid" />
            {goals.map((g) => (
              <line key={g.id} x1={(g.frame / n) * W} x2={(g.frame / n) * W} y1="0" y2={H} className="ms-goal" />
            ))}
          </svg>
          {chaos && (
            <svg className="ms-chaos" viewBox={`0 0 ${W} 10`} preserveAspectRatio="none">
              <path d={chaos} />
            </svg>
          )}
          <div className="ms-future" style={{ left: head }} />
          <div className="ms-head" style={{ left: head }} />
        </div>
      </div>
    </div>
  )
}
