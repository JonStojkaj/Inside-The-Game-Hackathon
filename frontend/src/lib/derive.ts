import type { Hypothesis, Insight, Lang, MatchEvent, Moment, Overlay, StatsSnapshot, Team, ViewerProfile } from '../types'
import { comparison, minuteLabel, payloadPlayer, type MatchIndex } from './match'
import { fmtNum, fmtPct, surname, t, tf } from './profile'

/**
 * Client-side rules that turn the same analysis into four different viewer experiences.
 *
 *  - keepForMode(): which produced overlays a mode shows (selection, PLAN §8).
 *  - deriveOverlays(): when the production team has not produced the viewer's segment (another
 *    language, another club / player, casual DE/ES), the overlays are templated from insights,
 *    moments and events in the viewer's language. Every number comes from the data; templates
 *    contain words only, so verify.ts can audit the derived text like the produced one.
 *  - helpers the mode views use (goal context, decision record, alerts, heatmap).
 */

export const other = (team: Team): Team => (team === 'home' ? 'away' : 'home')
const scoreStr = (s: [number, number]) => `${s[0]}–${s[1]}`

// ---------------------------------------------------------------- moments and deciders

const isDoors = (o: Overlay) => o.type === 'sliding_doors' || o.type === 'insight'

export function overlayMoment(m: MatchIndex, o: Overlay): Moment | undefined {
  const p = o.payload
  if (p.moment_id) return m.moment(String(p.moment_id))
  return m.moment(m.insight(p.insight_id as string | undefined)?.moment_id)
}

/** The player whose decision a moment / Sliding Doors overlay is about (first of player_ids). */
export function deciderId(m: MatchIndex, o: Overlay): string | undefined {
  return payloadPlayer(o) ?? overlayMoment(m, o)?.player_ids[0]
}

/** Which produced overlays a viewer mode shows. */
export function keepForMode(m: MatchIndex, p: ViewerProfile, o: Overlay): boolean {
  const cue = String(o.payload.cue ?? o.type)
  const ids = (o.payload.player_ids as string[] | undefined) ?? []
  switch (p.mode) {
    case 'analyst':
      return true
    case 'club_fan': {
      const own = p.favourite_club
      // Sliding Doors only for our own players' decisions, always as the one-liner
      if (isDoors(o)) return m.player(deciderId(m, o))?.team === own
      if (o.slot === 'side_panel' || o.slot === 'scorebug') return false // few numbers; momentum is ours
      if (o.slot === 'ticker') return o.type === 'alert' && o.payload.team === own
      if (o.slot === 'lower_third') return cue !== 'goal' && cue !== 'shot' && o.payload.team === own // goals: our banners
      return true
    }
    case 'player_focus': {
      const pid = p.favourite_players[0]
      if (isDoors(o)) return deciderId(m, o) === pid // only HIS decisions
      if (o.type === 'player_tag') return payloadPlayer(o) === pid
      if (o.slot === 'side_panel' || o.slot === 'scorebug') return false // the live player card replaces them
      if (o.slot === 'ticker') return o.type === 'alert' && ids.includes(pid)
      if (o.slot === 'lower_third') return cue === 'goal' // his own actions come as alerts
      return true
    }
    case 'casual': {
      if (isDoors(o)) {
        const k = overlayMoment(m, o)?.kind
        return k === 'goal' || k === 'big_chance'
      }
      return o.type === 'recap'
    }
  }
}

/** Events worth a ticker line (default ticker). */
export function newsworthy(e: MatchEvent): boolean {
  if (e.type === 'pressure' || e.type === 'carry' || e.type === 'out_of_play') return false
  if (e.type === 'pass') return e.outcome === 'incomplete' || Number(e.meta.difficulty ?? 0) >= 55
  return true
}

/** Ticker selection per mode: everything / our team / the followed player / none (casual). */
export function tickerFilter(p: ViewerProfile): ((e: MatchEvent) => boolean) | null {
  if (p.mode === 'casual') return null
  if (p.mode === 'club_fan') return (e) => newsworthy(e) && (e.team === p.favourite_club || e.type === 'goal')
  if (p.mode === 'player_focus') {
    const pid = p.favourite_players[0]
    return (e) => (e.player_id === pid || e.target_id === pid || e.type === 'goal') && e.type !== 'pressure' && e.type !== 'out_of_play'
  }
  return newsworthy
}

// ---------------------------------------------------------------- goals and big chances

export const goalEvents = (m: MatchIndex): MatchEvent[] => m.bundle.events.filter((e) => e.type === 'goal' && e.team)

export function scoreAt(m: MatchIndex, frame: number): [number, number] {
  const s = m.bundle.frames.score
  return s[Math.max(0, Math.min(Math.floor(frame), s.length - 1))] ?? [0, 0]
}

function goalScore(m: MatchIndex, g: MatchEvent): [number, number] {
  const s = g.meta.score
  return Array.isArray(s) ? [Number(s[0]), Number(s[1])] : scoreAt(m, g.frame + 1)
}

/** One line on why a goal mattered, from the score before and after it. */
export function whyGoal(m: MatchIndex, g: MatchEvent, lang: Lang): string {
  const team = g.team!
  const after = goalScore(m, g)
  const i = team === 'home' ? 0 : 1
  const mine = after[i]
  const theirs = after[1 - i]
  const club = m.club(team).name
  if (mine + theirs === 1) return tf(lang, 'why_open', { club })
  if (mine === theirs) return t(lang, 'why_level')
  if (mine < theirs) return tf(lang, 'why_back', { club })
  return mine - theirs === 1 ? tf(lang, 'why_lead', { club }) : tf(lang, 'why_extend', { club })
}

export interface ChanceInfo {
  moment: Moment
  shot?: MatchEvent
  outcome: string // localised
  wouldMake: string // "Would have made it 1–1"
}

/** A big chance (missed shot) and what it would have meant. */
export function chanceInfo(m: MatchIndex, mo: Moment, lang: Lang): ChanceInfo {
  const shot = mo.event_ids.map((id) => m.event(id)).find((e) => e?.type === 'shot')
  const s = scoreAt(m, mo.frame)
  const ifScored: [number, number] = mo.team === 'home' ? [s[0] + 1, s[1]] : [s[0], s[1] + 1]
  const oc = shot?.outcome ?? ''
  return {
    moment: mo,
    shot,
    outcome: ['off_target', 'blocked', 'saved'].includes(oc) ? t(lang, oc) : '',
    wouldMake: tf(lang, 'would_make', { score: scoreStr(ifScored) }),
  }
}

// ---------------------------------------------------------------- Sliding Doors text + timing

/**
 * When a moment's Sliding Doors airs: the production scheduler's earliest slot for it in any
 * segment (the stoppage it found), else 4 s after the moment.
 */
function doorsSchedule(m: MatchIndex): Map<string, { start: number; dur: number }> {
  const out = new Map<string, { start: number; dur: number }>()
  for (const o of Object.values(m.bundle.overlays).flat()) {
    if (!isDoors(o) || !o.payload.moment_id) continue
    const id = String(o.payload.moment_id)
    const cur = out.get(id)
    if (!cur || o.start_ms < cur.start) out.set(id, { start: o.start_ms, dur: o.duration_ms })
  }
  for (const mo of m.bundle.moments) if (!out.has(mo.id)) out.set(mo.id, { start: mo.t_ms + 4000, dur: 5200 })
  return out
}

/** The insight's verdict as one localised sentence; numbers straight from insight.numbers. */
export function doorsSentence(ins: Insight, lang: Lang): string {
  const c = comparison(ins.numbers, ins.metric)
  const metric = t(lang, c.metric)
  const a = fmtPct(lang, c.actual)
  if (c.alt == null) return tf(lang, 'sd_none', { metric, a })
  const b = fmtPct(lang, c.alt)
  return tf(lang, c.alt <= c.actual ? 'sd_right' : 'sd_better', { metric, a, b })
}

// ---------------------------------------------------------------- derived segment

const ov = (o: Omit<Overlay, 'lang' | 'evidence'> & { evidence?: string[] }, lang: Lang): Overlay => ({ evidence: [], lang, ...o })

/** Overlays for a segment the production team did not produce, in the viewer's language. */
export function deriveOverlays(m: MatchIndex, p: ViewerProfile): Overlay[] {
  const lang = p.language
  const { bundle } = m
  const out: Overlay[] = []
  const seg = `derived-${p.mode}`

  for (const g of goalEvents(m)) {
    const scorer = m.player(g.player_id)
    out.push(
      ov(
        {
          id: `${seg}-goal-${g.id}`,
          segment_id: seg,
          start_ms: g.t_ms,
          duration_ms: 6000,
          slot: 'lower_third',
          type: 'event_card',
          priority: 60,
          headline: tf(lang, 'goal_card', { club: m.club(g.team!).name }),
          body: tf(lang, 'goal_card_sub', { name: scorer?.name ?? '', min: minuteLabel(bundle, g.frame), score: scoreStr(goalScore(m, g)) }),
          payload: { cue: 'goal', team: g.team, player_ids: g.player_id ? [g.player_id] : [] },
          evidence: [g.id],
        },
        lang,
      ),
    )
  }

  const when = doorsSchedule(m)
  for (const ins of bundle.insights) {
    const mo = m.moment(ins.moment_id)
    const slot = mo && when.get(mo.id)
    if (!mo || !slot || ins.decision_frame == null) continue
    const min = minuteLabel(bundle, mo.frame)
    const dec = m.player(mo.player_ids[0])
    const oneLine = p.mode === 'club_fan' || p.mode === 'casual'
    const headline =
      p.mode === 'club_fan'
        ? tf(lang, 'fan_sd_head', { min })
        : p.mode === 'player_focus' && dec
          ? tf(lang, 'pf_sd_head', { name: surname(dec.name), min })
          : tf(lang, 'sd_head', { min })
    out.push(
      ov(
        {
          id: `${seg}-doors-${ins.id}`,
          segment_id: seg,
          start_ms: slot.start,
          duration_ms: slot.dur,
          slot: 'pitch',
          type: oneLine ? 'insight' : 'sliding_doors',
          priority: 80,
          headline,
          body: doorsSentence(ins, lang),
          payload: { moment_id: mo.id, insight_id: ins.id, team: mo.team, player_ids: mo.player_ids, metric: ins.metric, view: oneLine ? 'one_line' : 'full' },
          evidence: ins.evidence,
        },
        lang,
      ),
    )
  }

  const recap = Object.values(bundle.overlays)
    .flat()
    .find((o) => o.type === 'recap')
  const last = bundle.stats[bundle.stats.length - 1]
  const final = bundle.match.final_score
  out.push(
    ov(
      {
        id: `${seg}-recap`,
        segment_id: seg,
        start_ms: recap?.start_ms ?? bundle.frames.t_ms[bundle.frames.t_ms.length - 1],
        duration_ms: recap?.duration_ms ?? 30000,
        slot: 'fullscreen',
        type: 'recap',
        priority: 100,
        headline: recapHeadline(m, p, final),
        body: `${t(lang, 'goals')}: ${goalEvents(m)
          .map((g) => `${surname(m.player(g.player_id)?.name ?? '')} ${minuteLabel(bundle, g.frame)}`)
          .join(', ')}`,
        payload: { final_score: final, bullets: recapBullets(m, p, last) },
        evidence: last ? [`stats:final@${last.t_ms}`] : [],
      },
      lang,
    ),
  )
  return out
}

function recapHeadline(m: MatchIndex, p: ViewerProfile, final: [number, number]): string {
  const lang = p.language
  const { home, away } = m.bundle.match
  if (p.mode === 'club_fan' && p.favourite_club) {
    const i = p.favourite_club === 'home' ? 0 : 1
    const key = final[i] > final[1 - i] ? 'ft_won' : final[i] < final[1 - i] ? 'ft_lost' : 'ft_draw'
    return tf(lang, key, { score: scoreStr(final) })
  }
  if (p.mode === 'player_focus') return tf(lang, 'ft_player', { name: m.player(p.favourite_players[0])?.name ?? '' })
  return `${t(lang, 'ft')}: ${home.short} ${scoreStr(final)} ${away.short}`
}

function recapBullets(m: MatchIndex, p: ViewerProfile, s: StatsSnapshot | undefined): string[] {
  const lang = p.language
  if (!s || p.mode === 'casual') return []
  const { home, away } = m.bundle.match
  const pos = `${t(lang, 'possession')}: ${home.short} ${fmtPct(lang, s.teams.home.possession, 0)} · ${away.short} ${fmtPct(lang, s.teams.away.possession, 0)}`
  if (p.mode === 'club_fan') return [pos]
  if (p.mode === 'player_focus') {
    const pid = p.favourite_players[0]
    const ps = s.players[pid]
    if (!ps) return [pos]
    const rec = decisionsSoFar(m, pid, Infinity)
    const out = [`${t(lang, 'top_speed')}: ${fmtNum(lang, ps.top_speed_kmh)} km/h`]
    if (ps.passes > 0) out.push(`${t(lang, 'pass_acc')}: ${fmtPct(lang, ps.passes_completed / ps.passes, 0)}`)
    if (rec.total) out.push(`${t(lang, 'decisions')}: ${rec.right}/${rec.total} ${t(lang, 'right_calls')}`)
    return out
  }
  const acc = (x: StatsSnapshot['teams']['home']) => (x.pass_accuracy == null ? '–' : fmtPct(lang, x.pass_accuracy, 0))
  const out = [pos, `${t(lang, 'pass_acc')}: ${home.short} ${acc(s.teams.home)} · ${away.short} ${acc(s.teams.away)}`]
  const ct = s.control.control_team
  if (ct && s.control.control_share != null) out.push(`${m.club(ct).short} ${t(lang, 'in_control')} ${fmtPct(lang, s.control.control_share, 0)}`)
  return out
}

// ---------------------------------------------------------------- player focus

export interface DecisionOption {
  label: string
  p: number
  chosen: boolean
  status: 'accepted' | 'rejected' | 'pending'
}

export interface DecisionRecord {
  options: DecisionOption[] // best first
  rank: number // of the real decision among the options the critic accepted
  n: number
}

function actionLabel(m: MatchIndex, lang: Lang, action: string, target?: string): string {
  if (action === 'shoot' || action === 'shot') return t(lang, 'opt_shoot')
  if (action === 'carry') return t(lang, 'opt_carry')
  if (action === 'pass') return tf(lang, 'opt_pass', { name: surname(m.player(target)?.name ?? '?') })
  return t(lang, 'opt_actual')
}

/** A tested alternative in words: "Shoot", "Pass to Pike", "Ondo positioned differently". */
export function interventionLabel(m: MatchIndex, lang: Lang, h: Hypothesis): string {
  const iv = h.intervention
  if (!iv) return h.text
  const prm = iv.params
  if (iv.kind === 'swap_action') return actionLabel(m, lang, String(prm.action ?? ''), prm.target_id as string | undefined)
  const who = surname(m.player(prm.player_id as string | undefined)?.name ?? '?')
  return iv.kind === 'move_player' ? tf(lang, 'teammate_moved', { name: who }) : `− ${who}`
}

/**
 * The player's own options at a decision, from the experimenter's swap_action rollouts:
 * the real action vs each alternative action. Rejected rollouts (noise) are listed but not ranked.
 */
export function decisionRecord(m: MatchIndex, ins: Insight, lang: Lang): DecisionRecord {
  const c = comparison(ins.numbers, ins.metric)
  const mo = m.moment(ins.moment_id)
  const dec = mo?.player_ids[0]
  const ev = mo?.event_ids.map((id) => m.event(id)).find((e) => e && e.player_id === dec)
  const actual = ev ? actionLabel(m, lang, ev.type, ev.target_id ?? undefined) : t(lang, 'opt_actual')
  const options: DecisionOption[] = [{ label: actual, p: c.actual, chosen: true, status: 'accepted' }]
  for (const h of ins.hypotheses) {
    if (h.intervention?.kind !== 'swap_action' || h.counterfactual_p_goal == null) continue
    const prm = h.intervention.params
    options.push({ label: actionLabel(m, lang, String(prm.action ?? ''), prm.target_id as string | undefined), p: h.counterfactual_p_goal, chosen: false, status: h.verdict })
  }
  options.sort((a, b) => b.p - a.p)
  const ranked = options.filter((o) => o.status === 'accepted')
  return { options, rank: 1 + ranked.filter((o) => !o.chosen && o.p > c.actual).length, n: ranked.length }
}

/** How many of the player's analysed decisions up to `frame` were the right call. */
export function decisionsSoFar(m: MatchIndex, pid: string, frame: number): { right: number; total: number } {
  let right = 0
  let total = 0
  for (const ins of m.bundle.insights) {
    const mo = m.moment(ins.moment_id)
    if (!mo || mo.player_ids[0] !== pid || mo.frame > frame) continue
    const c = comparison(ins.numbers, ins.metric)
    total++
    if (c.alt == null || c.alt <= c.actual) right++
  }
  return { right, total }
}

export interface Alert {
  id: string
  frame: number
  headline: string
  body: string
  evidence: string[]
}

const ALERT_FRAMES = 40
/** Sprint alerts use the backend's threshold when the export carries one. */
function sprintThreshold(m: MatchIndex): number {
  for (const o of Object.values(m.bundle.overlays).flat()) if (typeof o.payload.threshold_kmh === 'number') return o.payload.threshold_kmh
  return 27.5
}

/** Notable actions of one player (goal, shot, ball won, key / hard pass, sprint), oldest first. */
export function playerAlerts(m: MatchIndex, pid: string, lang: Lang): Alert[] {
  const { bundle } = m
  const keyEvents = new Set(bundle.moments.flatMap((mo) => mo.event_ids))
  const out: Alert[] = []
  for (const e of bundle.events) {
    if (e.player_id !== pid) continue
    const target = m.player(e.target_id)
    const base = { id: e.id, frame: e.frame, evidence: [e.id] }
    if (e.type === 'goal') out.push({ ...base, headline: t(lang, 'al_goal'), body: `${minuteLabel(bundle, e.frame)} · ${scoreStr(goalScore(m, e))}` })
    else if (e.type === 'shot' && e.outcome !== 'goal')
      out.push({ ...base, headline: t(lang, 'al_shot'), body: [e.meta.xg != null ? `xG ${fmtNum(lang, Number(e.meta.xg), 2)}` : '', e.meta.distance_m != null ? `${fmtNum(lang, Number(e.meta.distance_m))} m` : '', e.outcome && ['off_target', 'blocked', 'saved'].includes(e.outcome) ? t(lang, e.outcome) : ''].filter(Boolean).join(' · ') })
    else if (e.type === 'interception') out.push({ ...base, headline: t(lang, 'al_interception'), body: target ? tf(lang, 'al_from', { name: target.name }) : '' })
    else if (e.type === 'tackle' && e.outcome === 'won') out.push({ ...base, headline: t(lang, 'al_tackle'), body: target ? tf(lang, 'al_from', { name: target.name }) : '' })
    else if (e.type === 'pass' && e.outcome === 'complete') {
      const diff = Number(e.meta.difficulty ?? 0)
      const body = `${t(lang, 'to')} ${target?.name ?? ''} · ${t(lang, 'difficulty')} ${Math.round(diff)}/100`
      if (keyEvents.has(e.id)) out.push({ ...base, headline: t(lang, 'al_key_pass'), body })
      else if (diff >= 55) out.push({ ...base, headline: t(lang, 'al_hard_pass'), body })
    }
  }
  const thr = sprintThreshold(m)
  let was = false
  for (const s of bundle.stats) {
    const v = s.players[pid]?.speed_kmh ?? 0
    const f = Math.round((s.t_ms / 1000) * bundle.match.fps)
    if (v >= thr && !was) out.push({ id: `sprint-${pid}-${s.t_ms}`, frame: f, headline: t(lang, 'al_sprint'), body: `${fmtNum(lang, v)} km/h`, evidence: [`stats:speed@${s.t_ms}`] })
    was = v >= thr
  }
  return out.sort((a, b) => a.frame - b.frame)
}

/** The alert on screen at `frame`, if any (the most recent one within its 4 s window). */
export function activeAlert(alerts: Alert[], frame: number): Alert | undefined {
  let hit: Alert | undefined
  for (const a of alerts) {
    if (a.frame > frame) break
    if (frame < a.frame + ALERT_FRAMES) hit = a
  }
  return hit
}

/** Where a player has been up to `frame`: share of samples per cell, cells[x][y] (y up). */
export function heatmap(m: MatchIndex, pid: string, frame: number, nx = 12, ny = 8): number[][] {
  const idx = m.playerIdx.get(pid)
  const cells = Array.from({ length: nx }, () => new Array<number>(ny).fill(0))
  if (idx == null) return cells
  const pl = m.bundle.frames.players
  const end = Math.min(Math.floor(frame), pl.length - 1)
  let n = 0
  for (let f = 0; f <= end; f += 5) {
    const [x, y] = pl[f][idx]
    cells[Math.min(nx - 1, Math.max(0, Math.floor((x / 105) * nx)))][Math.min(ny - 1, Math.max(0, Math.floor((y / 68) * ny)))]++
    n++
  }
  return n ? cells.map((c) => c.map((v) => v / n)) : cells
}
