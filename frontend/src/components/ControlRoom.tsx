import { useEffect, useMemo, useRef, useState } from 'react'
import { useMatch } from '../lib/context'
import { clockLabel, comparison, type MatchIndex } from '../lib/match'
import { useFrame } from '../lib/playback'
import type { Hypothesis, Insight, Intervention } from '../types'

type Agent = 'detector' | 'analyst' | 'experimenter' | 'critic' | 'explain' | 'production'
interface Line {
  agent: Agent
  text: string
  tone?: 'ok' | 'bad' | 'dim'
}

const AGENT_LABEL: Record<Agent, string> = {
  detector: 'Moment detector',
  analyst: 'Analyst',
  experimenter: 'Experimenter',
  critic: 'Critic',
  explain: 'Explain team',
  production: 'Production',
}
const STEP_MS = 650
const METRIC = { p_goal: 'chance to score', p_keep: 'chance to keep the ball' }

const pct = (v: number | null | undefined) => (v == null ? '–' : `${Math.round(v * 100)} %`)

function describe(iv: Intervention | null): string {
  if (!iv) return 'no intervention'
  const p = iv.params
  if (iv.kind === 'move_player') return `move_player(${p.player_id}, dx=${p.dx ?? 0} m, dy=${p.dy ?? 0} m)`
  if (iv.kind === 'remove_player') return `remove_player(${p.player_id})`
  return `swap_action(${p.action}${p.target_id ? ` → ${p.target_id}` : ''})`
}

/** The explain + production teams' work for one insight, as the agent log the control room replays. */
function script(ins: Insight, m: MatchIndex): Line[] {
  const mo = m.moment(ins.moment_id)
  const lines: Line[] = []
  if (mo) {
    lines.push({ agent: 'detector', text: `${mo.kind.replace('_', ' ')} at ${clockLabel(m.bundle, mo.frame)} · ${mo.reason} · importance ${mo.score.toFixed(2)}` })
  }
  lines.push({ agent: 'analyst', text: `${ins.hypotheses.length} hypotheses from snapshot @ frame ${ins.decision_frame}`, tone: 'dim' })
  ins.hypotheses.forEach((h: Hypothesis, k) => {
    lines.push({ agent: 'analyst', text: `H${k + 1}: ${h.text}` })
    lines.push({
      agent: 'experimenter',
      text: `run_rollouts(${describe(h.intervention)}, n=500 × 5 seeds) → ${METRIC[h.metric ?? 'p_goal']} ${pct(h.baseline_p_goal)} → ${pct(h.counterfactual_p_goal)}${h.seed_spread != null ? ` (spread ±${Math.round(h.seed_spread * 100)} pts)` : ''}`,
    })
    lines.push({
      agent: 'critic',
      text: `${h.verdict.toUpperCase()} · ${h.critic_note}`,
      tone: h.verdict === 'accepted' ? 'ok' : h.verdict === 'rejected' ? 'bad' : 'dim',
    })
  })
  const cmp = comparison(ins.numbers, ins.metric)
  lines.push({
    agent: 'explain',
    text: `${ins.verified ? '✓ verified' : '✗ not verified'} · ${ins.confidence} · ${METRIC[cmp.metric]} ${pct(cmp.actual)}${cmp.alt != null ? ` vs ${pct(cmp.alt)}` : ' · no better alternative'} · "${ins.claim}"`,
    tone: ins.verified ? 'ok' : 'bad',
  })
  const produced = Object.entries(m.bundle.overlays)
    .flatMap(([seg, list]) => list.filter((o) => o.payload.insight_id === ins.id || o.evidence.includes(ins.id)).map((o) => ({ seg, o })))
  for (const { seg, o } of produced) {
    lines.push({ agent: 'production', text: `${seg} [${o.lang}] ${o.slot}/${o.type}: "${o.headline}"` })
  }
  return lines
}

/** Agent log: the selected insight's hypotheses tested, accepted and rejected, then produced per segment. */
export function ControlRoom() {
  const { m, pb, setForcedInsight } = useMatch()
  const frame = useFrame(pb)
  const insights = m.bundle.insights
  const [picked, setPicked] = useState<string | null>(null)

  // follow the match: the latest insight whose moment has happened, unless one was picked
  const live = [...insights].reverse().find((i) => (m.moment(i.moment_id)?.frame ?? Infinity) <= frame)
  const current = (picked ? m.insight(picked) : live) ?? insights[0]
  const lines = useMemo(() => (current ? script(current, m) : []), [current, m])

  const [shown, setShown] = useState(0)
  useEffect(() => {
    setShown(0)
    const id = setInterval(() => setShown((n) => (n >= lines.length ? n : n + 1)), STEP_MS)
    return () => clearInterval(id)
  }, [lines])

  const logRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
  }, [shown])

  const all = insights.flatMap((i) => i.hypotheses)
  const accepted = all.filter((h) => h.verdict === 'accepted').length
  const rejected = all.filter((h) => h.verdict === 'rejected').length
  // overlays that cite an insight which is missing or unverified (the pipeline should never produce one)
  const unverified = Object.values(m.bundle.overlays)
    .flat()
    .filter((o) => o.payload.insight_id != null && !m.insight(String(o.payload.insight_id))?.verified).length

  return (
    <div className="control-room">
      <div className="cr-head">
        <div className="cr-title">
          <span className="cr-dot" /> Control room
        </div>
        <div className="cr-tabs">
          {insights.map((i) => {
            const mo = m.moment(i.moment_id)
            return (
              <button
                key={i.id}
                className={current?.id === i.id ? 'on' : ''}
                onClick={() => setPicked(picked === i.id ? null : i.id)}
                onDoubleClick={() => {
                  if (i.decision_frame == null) return
                  pb.pause()
                  pb.seek(i.decision_frame)
                  setForcedInsight(i.id)
                }}
                title="click: show log · double-click: open Sliding Doors"
              >
                <span className={`k k-${mo?.kind}`} />
                {mo ? clockLabel(m.bundle, mo.frame) : i.id} {mo?.kind.replace('_', ' ')}
              </button>
            )
          })}
        </div>
      </div>
      <div className="cr-log" ref={logRef}>
        {!insights.length && <div className="cr-empty">Waiting for the explain team · no insights in this export yet</div>}
        {lines.slice(0, shown).map((l, k) => (
          <div key={`${current?.id}-${k}`} className={`cr-line a-${l.agent} ${l.tone ?? ''}`}>
            <span className="cr-agent">{AGENT_LABEL[l.agent]}</span>
            <span className="cr-text">{l.text}</span>
          </div>
        ))}
        {shown < lines.length && (
          <div className="cr-line typing">
            <span className="cr-agent">{AGENT_LABEL[lines[shown].agent]}</span>
            <span className="cr-dots">
              <i />
              <i />
              <i />
            </span>
          </div>
        )}
      </div>
      <div className="cr-foot">
        <div>
          <b>{all.length}</b> hypotheses
        </div>
        <div className="ok">
          <b>{accepted}</b> accepted
        </div>
        <div className="bad">
          <b>{rejected}</b> rejected
        </div>
        <div className={unverified ? 'bad' : 'zero'}>
          <b>{unverified}</b> unverified claims shown
        </div>
      </div>
    </div>
  )
}
