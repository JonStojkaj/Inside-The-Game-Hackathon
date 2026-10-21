import { useEffect, useMemo, useRef, useState } from 'react'
import { useMatch } from '../lib/context'
import { clockLabel, comparison, type MatchIndex } from '../lib/match'
import { useFrame } from '../lib/playback'
import { checkClaim, checkOverlay, expectedDirection, measuredDirection, outcome } from '../lib/verify'
import type { Hypothesis, Insight, Intervention, Metric } from '../types'

type Agent = 'detector' | 'analyst' | 'experimenter' | 'critic' | 'explain' | 'producer' | 'narrator'
interface Line {
  agent: Agent
  text: string
  tone?: 'ok' | 'bad' | 'warn' | 'dim'
  tag?: string
  seg?: string
}

const AGENT_LABEL: Record<Agent, string> = {
  detector: 'Moment detector',
  analyst: 'Analyst',
  experimenter: 'Experimenter',
  critic: 'Critic',
  explain: 'Explain team',
  producer: 'Producer',
  narrator: 'Narrator',
}
const STEP_MS = 520
const METRIC: Record<Metric, string> = { p_goal: 'chance to score', p_keep: 'chance to keep the ball' }
const ARROW = { up: '↑', down: '↓' }

const pct = (v: number | null | undefined) => (v == null ? '–' : `${(v * 100).toFixed(1)}%`)

function describe(iv: Intervention | null): string {
  if (!iv) return 'baseline'
  const p = iv.params
  if (iv.kind === 'move_player') return `move_player(${p.player_id}, dx=${p.dx ?? 0} m, dy=${p.dy ?? 0} m)`
  if (iv.kind === 'remove_player') return `remove_player(${p.player_id})`
  return `swap_action(${p.action}${p.target_id ? ` → ${p.target_id}` : ''})`
}

function critic(h: Hypothesis): Line {
  const o = outcome(h)
  const exp = expectedDirection(h)
  const got = measuredDirection(h)
  if (o === 'refuted') {
    return {
      agent: 'critic',
      tag: 'refuted',
      tone: 'warn',
      text: `effect is real and stable, but the Analyst predicted ${ARROW[exp!]} and the rollouts say ${ARROW[got!]} · ${h.critic_note}`,
    }
  }
  if (o === 'confirmed') return { agent: 'critic', tag: 'accepted', tone: 'ok', text: h.critic_note }
  return { agent: 'critic', tag: o, tone: o === 'rejected' ? 'bad' : 'dim', text: h.critic_note }
}

/** The explain + production teams' work for one insight, as the agent log the control room replays. */
function script(ins: Insight, m: MatchIndex): Line[] {
  const mo = m.moment(ins.moment_id)
  const lines: Line[] = []
  if (mo) {
    lines.push({ agent: 'detector', text: `${mo.kind.replace('_', ' ')} at ${clockLabel(m.bundle, mo.frame)} · ${mo.reason} · importance ${mo.score.toFixed(2)}` })
  }
  lines.push({ agent: 'analyst', tone: 'dim', text: `snapshot @ frame ${ins.decision_frame} → ${ins.hypotheses.length} hypotheses` })
  ins.hypotheses.forEach((h, k) => {
    const exp = expectedDirection(h)
    lines.push({ agent: 'analyst', tag: `H${k + 1}${exp ? ` ${ARROW[exp]}` : ''}`, text: h.text })
    lines.push({
      agent: 'experimenter',
      text: `run_rollouts(${describe(h.intervention)}) → ${METRIC[h.metric ?? ins.metric ?? 'p_goal']} ${pct(h.baseline_p_goal)} → ${pct(h.counterfactual_p_goal)}${h.seed_spread != null ? ` · seed spread ±${(h.seed_spread * 100).toFixed(1)} pts` : ''}`,
    })
    lines.push(critic(h))
  })
  const cmp = comparison(ins.numbers, ins.metric)
  const audit = checkClaim(ins.claim, ins, m)
  lines.push({
    agent: 'explain',
    tag: audit.ok ? 'verified' : 'blocked',
    tone: audit.ok ? 'ok' : 'bad',
    text: `${METRIC[cmp.metric]} ${pct(cmp.actual)}${cmp.alt != null ? ` vs best alternative ${pct(cmp.alt)}` : ' · no better alternative'} · ${audit.traced}/${audit.numbers} numbers traced, ${audit.evidenceOk}/${audit.evidence} evidence ids · "${ins.claim}"${audit.untraced.length ? ` · untraced: ${audit.untraced.join(', ')}` : ''}`,
  })

  // production team: per segment, the producer's call and what the narrator put on screen
  const steps = (m.bundle.production?.steps ?? []).filter((s) => s.moment_id === ins.moment_id && s.agent !== 'narrator')
  const produced = Object.entries(m.bundle.overlays).flatMap(([seg, list]) =>
    list.filter((o) => o.payload.insight_id === ins.id || o.payload.moment_id === ins.moment_id).map((o) => ({ seg, o })),
  )
  const segs = [...new Set([...steps.map((s) => s.segment_id), ...produced.map((p) => p.seg)])]
  for (const seg of segs) {
    const step = steps.find((s) => s.segment_id === seg)
    const shown = produced.find((p) => p.seg === seg)
    if (step && step.decision !== 'show' && !shown) {
      lines.push({ agent: 'producer', seg, tone: 'dim', text: `${step.agent}: ${step.decision}` })
      continue
    }
    if (step) lines.push({ agent: 'producer', seg, text: `show · priority ${step.detail.priority ?? '–'}${step.detail.angle ? ` · angle "${step.detail.angle}"` : ''}` })
    if (shown) {
      const a = checkOverlay(m, shown.o)
      lines.push({
        agent: 'narrator',
        seg,
        tone: a && !a.ok ? 'bad' : undefined,
        tag: a ? (a.ok ? `✓ ${a.traced}/${a.numbers}` : '✗ untraced') : undefined,
        text: `${shown.o.slot}/${shown.o.type} @ ${clockLabel(m.bundle, (shown.o.start_ms / 1000) * m.bundle.match.fps)}: "${shown.o.headline}" ${shown.o.body}`,
      })
    } else if (step?.decision === 'show') {
      lines.push({ agent: 'producer', seg, tone: 'dim', text: 'scheduler: no dead-ball window, dropped' })
    }
  }
  return lines
}

/** Agent log: the selected insight's hypotheses tested, accepted and rejected, then produced per segment. */
export function ControlRoom() {
  const { m, pb, setForcedInsight } = useMatch()
  const frame = useFrame(pb)
  const insights = m.bundle.insights
  const [picked, setPicked] = useState<string | null>(() => new URLSearchParams(window.location.search).get('cr'))

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

  const totals = useMemo(() => {
    const all = insights.flatMap((i) => i.hypotheses)
    const by = (o: string) => all.filter((h) => outcome(h) === o).length
    // every on-screen text that cites an insight, re-checked against the rollout numbers
    const cited = Object.values(m.bundle.overlays)
      .flat()
      .map((o) => checkOverlay(m, o))
      .filter((a) => a !== undefined)
    return {
      hypotheses: all.length,
      confirmed: by('confirmed'),
      refuted: by('refuted'),
      rejected: by('rejected'),
      claims: cited.length,
      unverified: cited.filter((a) => !a.ok).length,
    }
  }, [insights, m])

  return (
    <div className="control-room">
      <div className="cr-head">
        <div className="cr-title">
          <span className="cr-dot" /> Control room
          <span className="cr-sub">explain team → production team, replayed from the agent log</span>
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
            <span className="cr-agent">
              {AGENT_LABEL[l.agent]}
              {l.seg && <small>{l.seg}</small>}
            </span>
            <span className="cr-text">
              {l.tag && <span className={`cr-tag t-${l.tag.replace(/[^a-z]/g, '') || 'n'}`}>{l.tag}</span>}
              {l.text}
            </span>
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
          <b>{totals.hypotheses}</b> hypotheses
        </div>
        <div className="ok">
          <b>{totals.confirmed}</b> confirmed
        </div>
        <div className="warn" title="accepted by the critic (stable effect), but the effect goes the other way than the Analyst predicted">
          <b>{totals.refuted}</b> refuted
        </div>
        <div className="bad">
          <b>{totals.rejected}</b> rejected
        </div>
        <div className={totals.unverified ? 'bad' : 'zero'} title={`${totals.claims} on-screen texts cite an insight; each number re-checked against the rollouts`}>
          <b>{totals.unverified}</b> unverified claims shown
        </div>
      </div>
    </div>
  )
}
