import type { Lang, PlayerInfo, StatsSnapshot, Team } from '../types'
import type { MatchIndex } from './match'
import { rating, ratedActions, winProbability, xgSoFar } from './models'
import { fmtNum, fmtPct } from './profile'

/**
 * Every stat the analyst can search for, computed live at the current frame from the export
 * (events, stats snapshots, tracking positions). Numbers come from code only. Three scopes:
 *   team    home vs away
 *   player  one row per player (search "Holt" → all of his numbers), ranked among all 22
 *   match   one value for the whole game
 * Labels and search keywords exist in EN/DE/ES, and search matches across languages.
 */
export type Scope = 'team' | 'player' | 'match'
export type Group = 'attack' | 'passing' | 'defending' | 'physical' | 'control' | 'shape' | 'match'

export interface StatRow {
  /** Stable id: "team.xg", "player.xg.A20", "match.ball_speed". */
  id: string
  /** Stat id without the player ("player.xg"), for ranking and the player sheet. */
  stat: string
  scope: Scope
  group: Group
  label: string
  /** Search text (all languages + player name/number/club). */
  search: string
  home?: number
  away?: number
  value?: number
  /** Value as text (match-scope stats that are not numbers). */
  text?: string
  fmt: (v: number) => string
  player?: PlayerInfo
  /** Rank among all players (1 = best) and how many players have a value. */
  rank?: number
  of?: number
  /** Lower is better (ball losses): ranks ascending. */
  low?: boolean
}

type L3 = [en: string, de: string, es: string]
interface Def {
  label: L3
  keys?: string
  group: Group
  low?: boolean
}

const li = (lang: Lang) => (lang === 'en' ? 0 : lang === 'de' ? 1 : 2)

const TEAM: Record<string, Def> = {
  possession: { label: ['Possession', 'Ballbesitz', 'Posesión'], group: 'control', keys: 'ball share' },
  xg: { label: ['Expected goals (xG)', 'Erwartete Tore (xG)', 'Goles esperados (xG)'], group: 'attack', keys: 'chances quality' },
  goals: { label: ['Goals', 'Tore', 'Goles'], group: 'attack', keys: 'score' },
  shots: { label: ['Shots', 'Schüsse', 'Tiros'], group: 'attack', keys: 'attempts' },
  on_target: { label: ['Shots on target', 'Schüsse aufs Tor', 'Tiros a puerta'], group: 'attack', keys: 'accuracy' },
  shot_acc: { label: ['Shot accuracy', 'Schussgenauigkeit', 'Precisión de tiro'], group: 'attack', keys: 'on target %' },
  xg_shot: { label: ['xG per shot', 'xG pro Schuss', 'xG por tiro'], group: 'attack', keys: 'chance quality' },
  shot_speed: { label: ['Hardest shot', 'Härtester Schuss', 'Tiro más potente'], group: 'attack', keys: 'shot speed power kmh' },
  shot_dist: { label: ['Avg shot distance', 'Ø Schussdistanz', 'Distancia media de tiro'], group: 'attack', keys: 'range metres' },
  passes: { label: ['Passes', 'Pässe', 'Pases'], group: 'passing' },
  pass_acc: { label: ['Pass accuracy', 'Passquote', 'Precisión de pase'], group: 'passing', keys: 'completion completed %' },
  pass_len: { label: ['Avg pass length', 'Ø Passlänge', 'Longitud media de pase'], group: 'passing', keys: 'distance metres' },
  long_passes: { label: ['Long balls (30 m+)', 'Lange Bälle (30 m+)', 'Balones largos (30 m+)'], group: 'passing', keys: 'long pass diagonal' },
  key_passes: { label: ['Dangerous passes', 'Gefährliche Pässe', 'Pases peligrosos'], group: 'passing', keys: 'key progressive threat decisive' },
  pass_diff: { label: ['Avg pass difficulty', 'Ø Passschwierigkeit', 'Dificultad media de pase'], group: 'passing', keys: 'risk' },
  carries: { label: ['Dribbles / carries', 'Dribblings / Läufe mit Ball', 'Conducciones'], group: 'attack', keys: 'carry dribble run' },
  carry_m: { label: ['Metres carried', 'Meter mit Ball', 'Metros conducidos'], group: 'attack', keys: 'carry distance dribble' },
  tackles: { label: ['Tackles', 'Zweikämpfe gewonnen', 'Entradas'], group: 'defending', keys: 'duels won tackle' },
  interceptions: { label: ['Interceptions', 'Abgefangene Bälle', 'Intercepciones'], group: 'defending', keys: 'interception steal' },
  pressures: { label: ['Pressures', 'Pressing-Aktionen', 'Presiones'], group: 'defending', keys: 'press pressure' },
  ball_wins: { label: ['Ball wins', 'Ballgewinne', 'Recuperaciones'], group: 'defending', keys: 'recoveries turnovers won' },
  losses: { label: ['Ball losses', 'Ballverluste', 'Pérdidas'], group: 'defending', keys: 'turnovers lost giveaways', low: true },
  press_now: { label: ['Pressing intensity now', 'Pressing-Intensität jetzt', 'Intensidad de presión ahora'], group: 'defending', keys: 'press ppda' },
  set_pieces: { label: ['Set pieces', 'Standards', 'Balón parado'], group: 'attack', keys: 'corners free kicks' },
  work_rate: { label: ['Work rate (m/min)', 'Laufleistung (m/min)', 'Ritmo de carrera (m/min)'], group: 'physical', keys: 'distance running covered km' },
  sprints: { label: ['Sprints', 'Sprints', 'Sprints'], group: 'physical', keys: 'sprint fast runs' },
  top_speed: { label: ['Top speed', 'Höchstgeschwindigkeit', 'Velocidad máxima'], group: 'physical', keys: 'fastest kmh pace' },
  line_height: { label: ['Team height now', 'Höhe der Mannschaft jetzt', 'Altura del bloque ahora'], group: 'shape', keys: 'defensive line block high low' },
  width: { label: ['Team width now', 'Breite jetzt', 'Anchura ahora'], group: 'shape', keys: 'shape spread' },
  compact: { label: ['Team length now', 'Kompaktheit (Länge) jetzt', 'Longitud del bloque ahora'], group: 'shape', keys: 'compactness compact' },
  win_prob: { label: ['Win probability', 'Siegchance', 'Probabilidad de victoria'], group: 'match', keys: 'odds chance win' },
}

const PLAYER: Record<string, Def> = {
  rating: { label: ['Rating', 'Note', 'Nota'], group: 'match', keys: 'score grade performance' },
  xg: TEAM.xg,
  goals: TEAM.goals,
  shots: TEAM.shots,
  on_target: TEAM.on_target,
  passes: TEAM.passes,
  pass_acc: TEAM.pass_acc,
  key_passes: TEAM.key_passes,
  long_passes: TEAM.long_passes,
  pass_diff: TEAM.pass_diff,
  carries: TEAM.carries,
  carry_m: TEAM.carry_m,
  touches: { label: ['Touches', 'Ballkontakte', 'Toques'], group: 'attack', keys: 'involvement on ball' },
  ball_time: { label: ['Time on the ball', 'Zeit am Ball', 'Tiempo con balón'], group: 'attack', keys: 'possession seconds' },
  tackles: TEAM.tackles,
  interceptions: TEAM.interceptions,
  pressures: TEAM.pressures,
  losses: TEAM.losses,
  work_rate: TEAM.work_rate,
  distance: { label: ['Distance covered', 'Laufdistanz', 'Distancia recorrida'], group: 'physical', keys: 'metres run km' },
  sprints: TEAM.sprints,
  top_speed: TEAM.top_speed,
  speed_now: { label: ['Speed now', 'Tempo jetzt', 'Velocidad ahora'], group: 'physical', keys: 'current pace' },
  avg_x: { label: ['Average position (upfield)', 'Ø Position (Höhe)', 'Posición media (altura)'], group: 'shape', keys: 'heat position where' },
}

const MATCH: Record<string, Def> = {
  ball_speed: { label: ['Ball speed now', 'Ballgeschwindigkeit jetzt', 'Velocidad del balón ahora'], group: 'match', keys: 'ball kmh' },
  pressure: { label: ['Pressure on the ball', 'Druck auf den Ball', 'Presión sobre el balón'], group: 'match', keys: 'press' },
  changes: { label: ['Possession changes / min', 'Ballbesitzwechsel / min', 'Cambios de posesión / min'], group: 'control', keys: 'turnovers chaos' },
  tempo: { label: ['Tempo (actions / min)', 'Tempo (Aktionen / min)', 'Ritmo (acciones / min)'], group: 'control', keys: 'rhythm speed of play' },
  chaos: { label: ['Chaos', 'Chaos', 'Caos'], group: 'control', keys: 'open game control' },
  control: { label: ['In control', 'Spielkontrolle', 'Control del partido'], group: 'control', keys: 'dominance momentum' },
}

export const GROUPS: Group[] = ['match', 'attack', 'passing', 'defending', 'physical', 'shape', 'control']
export const GROUP_LABEL: Record<Group, L3> = {
  match: ['Match', 'Spiel', 'Partido'],
  attack: ['Attack', 'Angriff', 'Ataque'],
  passing: ['Passing', 'Passspiel', 'Pase'],
  defending: ['Defending', 'Defensive', 'Defensa'],
  physical: ['Physical', 'Athletik', 'Físico'],
  shape: ['Shape', 'Formation', 'Forma'],
  control: ['Control', 'Kontrolle', 'Control'],
}

// ------------------------------------------------------------------------------- tracking (once per match)

const SPRINT_KMH = 25
interface Track {
  /** cumulative metres per player per frame */
  dist: Float32Array[]
  /** cumulative sprints started per player per frame */
  sprints: Uint16Array[]
  /** smoothed speed km/h per player per frame */
  speed: Float32Array[]
  /** cumulative x (upfield, own attacking direction) per player per frame, for the average position */
  sumX: Float32Array[]
  /** cumulative frames on the ball / touches per player per frame */
  ballFrames: Uint16Array[]
  touches: Uint16Array[]
}

const tracks = new WeakMap<MatchIndex, Track>()

function track(m: MatchIndex): Track {
  const hit = tracks.get(m)
  if (hit) return hit
  const { players: pos, owner } = m.bundle.frames
  const fps = m.bundle.match.fps
  const n = pos.length
  const out: Track = { dist: [], sprints: [], speed: [], sumX: [], ballFrames: [], touches: [] }
  m.bundle.match.players.forEach((p, k) => {
    const dist = new Float32Array(n)
    const spr = new Uint16Array(n)
    const sp = new Float32Array(n)
    const sx = new Float32Array(n)
    const bf = new Uint16Array(n)
    const tc = new Uint16Array(n)
    let sprinting = false
    for (let f = 0; f < n; f++) {
      const a = pos[Math.max(0, f - 1)][k]
      const b = pos[f][k]
      const step = Math.hypot(b[0] - a[0], b[1] - a[1])
      dist[f] = (f ? dist[f - 1] : 0) + (step < 2 ? step : 0) // > 2 m in 0.1 s = teleport (restart), not running
      const back = pos[Math.max(0, f - 5)][k]
      const span = Math.min(f, 5) / fps
      sp[f] = span ? (Math.hypot(b[0] - back[0], b[1] - back[1]) / span) * 3.6 : 0
      if (sp[f] > 40) sp[f] = f ? sp[f - 1] : 0
      const start = !sprinting && sp[f] >= SPRINT_KMH
      sprinting = sp[f] >= SPRINT_KMH ? true : sp[f] < 21 ? false : sprinting
      spr[f] = (f ? spr[f - 1] : 0) + (start ? 1 : 0)
      sx[f] = (f ? sx[f - 1] : 0) + (p.team === 'home' ? b[0] : 105 - b[0])
      const on = owner[f] === k
      bf[f] = (f ? bf[f - 1] : 0) + (on ? 1 : 0)
      tc[f] = (f ? tc[f - 1] : 0) + (on && (f === 0 || owner[f - 1] !== k) ? 1 : 0)
    }
    out.dist.push(dist)
    out.sprints.push(spr)
    out.speed.push(sp)
    out.sumX.push(sx)
    out.ballFrames.push(bf)
    out.touches.push(tc)
  })
  tracks.set(m, out)
  return out
}

// ------------------------------------------------------------------------------- events so far

interface Agg {
  passes: number
  done: number
  passLen: number
  diff: number
  diffN: number
  long: number
  key: number
  shots: number
  onTarget: number
  shotDist: number
  goals: number
  carries: number
  carryM: number
  tackles: number
  interceptions: number
  pressures: number
  losses: number
  setPieces: number
  xg: number
  shotSpeed: number
}
const agg = (): Agg => ({
  passes: 0, done: 0, passLen: 0, diff: 0, diffN: 0, long: 0, key: 0, shots: 0, onTarget: 0, shotDist: 0, goals: 0,
  carries: 0, carryM: 0, tackles: 0, interceptions: 0, pressures: 0, losses: 0, setPieces: 0, xg: 0, shotSpeed: 0,
})

function aggregate(m: MatchIndex, frame: number): { team: Record<Team, Agg>; player: Map<string, Agg> } {
  const team = { home: agg(), away: agg() }
  const player = new Map<string, Agg>()
  const of = (id: string | null) => {
    if (!id) return null
    let a = player.get(id)
    if (!a) player.set(id, (a = agg()))
    return a
  }
  for (const e of m.bundle.events) {
    if (e.frame > frame) break
    const t = e.team ? team[e.team] : null
    const targets = [t, of(e.player_id)].filter((x): x is Agg => x != null)
    const meta = e.meta
    for (const a of targets) {
      if (e.type === 'pass') {
        a.passes++
        const d = Number(meta.distance_m ?? 0)
        a.passLen += d
        if (d >= 30) a.long++
        if (meta.difficulty != null) {
          a.diff += Number(meta.difficulty)
          a.diffN++
        }
        if (e.outcome === 'complete') {
          a.done++
          if (Number(meta.threat_gain ?? 0) >= 0.05) a.key++
        } else a.losses++
      } else if (e.type === 'shot') {
        a.shots++
        if (e.outcome === 'saved' || e.outcome === 'goal') a.onTarget++
        if (e.outcome === 'goal') a.goals++
        a.xg += Number(meta.xg ?? 0)
        a.shotDist += Number(meta.distance_m ?? 0)
        a.shotSpeed = Math.max(a.shotSpeed, Number(meta.shot_speed_kmh ?? 0))
      } else if (e.type === 'carry') {
        a.carries++
        a.carryM += Number(meta.distance_m ?? 0)
      } else if (e.type === 'tackle') a.tackles++
      else if (e.type === 'interception') a.interceptions++
      else if (e.type === 'pressure') a.pressures++
      else if (e.type === 'set_piece') a.setPieces++
    }
    // the player who lost it to a tackle / interception
    if ((e.type === 'tackle' || e.type === 'interception') && e.target_id) {
      const victim = of(e.target_id)
      if (victim) victim.losses++
      const vt = m.player(e.target_id)?.team
      if (vt && e.type === 'tackle') team[vt].losses++
    }
  }
  return { team, player }
}

// ------------------------------------------------------------------------------- the catalog

function norm(s: string): string {
  return s
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
}

const keysOf = (d: Def) => norm([...d.label, d.keys ?? ''].join(' '))

/** All stats at `frame`. Cheap enough to run on every integer frame (~350 rows). */
export function statCatalog(m: MatchIndex, frame: number, s: StatsSnapshot | undefined, lang: Lang): StatRow[] {
  const L = li(lang)
  const tr = track(m)
  const fps = m.bundle.match.fps
  const f = Math.max(0, Math.min(frame, m.bundle.frames.players.length - 1))
  const mins = Math.max(f / fps / 60, 1 / 6)
  const { team: ta, player: pa } = aggregate(m, f)
  const xg = xgSoFar(m.bundle.events, f)
  const n0 = (v: number) => fmtNum(lang, v, 0)
  const n1 = (v: number) => fmtNum(lang, v, 1)
  const n2 = (v: number) => fmtNum(lang, v, 2)
  const pct = (v: number) => fmtPct(lang, v, 0)
  const kmh = (v: number) => `${fmtNum(lang, v, 1)} km/h`
  const m0 = (v: number) => `${fmtNum(lang, v, 0)} m`
  const sec = (v: number) => `${fmtNum(lang, v, 0)} s`
  const players = m.bundle.match.players
  const rows: StatRow[] = []
  const club = (t: Team) => m.club(t)
  const teamSearch = `${norm(club('home').name)} ${norm(club('away').name)} ${norm(club('home').short)} ${norm(club('away').short)} team`

  // team shape at this frame (outfield players)
  const shape = (t: Team) => {
    const xs: number[] = []
    const ys: number[] = []
    players.forEach((p, k) => {
      if (p.team !== t || p.position === 'GK') return
      const [x, y] = m.bundle.frames.players[f][k]
      xs.push(t === 'home' ? x : 105 - x)
      ys.push(y)
    })
    const avg = xs.reduce((a, b) => a + b, 0) / (xs.length || 1)
    return { height: avg, width: Math.max(...ys) - Math.min(...ys), length: Math.max(...xs) - Math.min(...xs) }
  }
  const teamPhys = (t: Team) => {
    let d = 0
    let sp = 0
    let top = 0
    let n = 0
    players.forEach((p, k) => {
      if (p.team !== t) return
      d += tr.dist[k][f]
      sp += tr.sprints[k][f]
      top = Math.max(top, s?.players[p.id]?.top_speed_kmh ?? 0)
      n++
    })
    return { work: d / (n || 1) / mins, sprints: sp, top }
  }
  const sh = { home: shape('home'), away: shape('away') }
  const ph = { home: teamPhys('home'), away: teamPhys('away') }
  const win = { home: winProbability(m, 'home', f).win, away: winProbability(m, 'away', f).win }

  const tv: Record<string, [number, number, (v: number) => string] | null> = {
    possession: s ? [s.teams.home.possession, s.teams.away.possession, pct] : null,
    xg: [xg.home, xg.away, n2],
    goals: [ta.home.goals, ta.away.goals, n0],
    shots: [ta.home.shots, ta.away.shots, n0],
    on_target: [ta.home.onTarget, ta.away.onTarget, n0],
    shot_acc: ta.home.shots + ta.away.shots ? [ta.home.shots ? ta.home.onTarget / ta.home.shots : 0, ta.away.shots ? ta.away.onTarget / ta.away.shots : 0, pct] : null,
    xg_shot: ta.home.shots + ta.away.shots ? [ta.home.shots ? xg.home / ta.home.shots : 0, ta.away.shots ? xg.away / ta.away.shots : 0, n2] : null,
    shot_speed: ta.home.shots + ta.away.shots ? [ta.home.shotSpeed, ta.away.shotSpeed, kmh] : null,
    shot_dist: ta.home.shots + ta.away.shots ? [ta.home.shots ? ta.home.shotDist / ta.home.shots : 0, ta.away.shots ? ta.away.shotDist / ta.away.shots : 0, m0] : null,
    passes: [ta.home.passes, ta.away.passes, n0],
    pass_acc: [ta.home.passes ? ta.home.done / ta.home.passes : 0, ta.away.passes ? ta.away.done / ta.away.passes : 0, pct],
    pass_len: [ta.home.passes ? ta.home.passLen / ta.home.passes : 0, ta.away.passes ? ta.away.passLen / ta.away.passes : 0, m0],
    long_passes: [ta.home.long, ta.away.long, n0],
    key_passes: [ta.home.key, ta.away.key, n0],
    pass_diff: [ta.home.diffN ? ta.home.diff / ta.home.diffN : 0, ta.away.diffN ? ta.away.diff / ta.away.diffN : 0, n0],
    carries: [ta.home.carries, ta.away.carries, n0],
    carry_m: [ta.home.carryM, ta.away.carryM, m0],
    tackles: [ta.home.tackles, ta.away.tackles, n0],
    interceptions: [ta.home.interceptions, ta.away.interceptions, n0],
    pressures: [ta.home.pressures, ta.away.pressures, n0],
    ball_wins: [ta.home.tackles + ta.home.interceptions, ta.away.tackles + ta.away.interceptions, n0],
    losses: [ta.home.losses, ta.away.losses, n0],
    press_now: s ? [s.pressing.home ?? 0, s.pressing.away ?? 0, n2] : null,
    set_pieces: [ta.home.setPieces, ta.away.setPieces, n0],
    work_rate: [ph.home.work, ph.away.work, n0],
    sprints: [ph.home.sprints, ph.away.sprints, n0],
    top_speed: [ph.home.top, ph.away.top, kmh],
    line_height: [sh.home.height, sh.away.height, m0],
    width: [sh.home.width, sh.away.width, m0],
    compact: [sh.home.length, sh.away.length, m0],
    win_prob: [win.home, win.away, pct],
  }
  for (const [k, d] of Object.entries(TEAM)) {
    const v = tv[k]
    if (!v) continue
    rows.push({ id: `team.${k}`, stat: `team.${k}`, scope: 'team', group: d.group, label: d.label[L], search: `${keysOf(d)} ${teamSearch}`, home: v[0], away: v[1], fmt: v[2], low: d.low })
  }

  // players
  const perPlayer: Record<string, (p: PlayerInfo, k: number, a: Agg) => [number, (v: number) => string] | null> = {
    rating: (p) => [rating(ratedActions(m, p.id, f)), n1],
    xg: (_p, _k, a) => [a.xg, n2],
    goals: (_p, _k, a) => [a.goals, n0],
    shots: (_p, _k, a) => [a.shots, n0],
    on_target: (_p, _k, a) => [a.onTarget, n0],
    passes: (_p, _k, a) => [a.passes, n0],
    pass_acc: (_p, _k, a) => (a.passes >= 3 ? [a.done / a.passes, pct] : null),
    key_passes: (_p, _k, a) => [a.key, n0],
    long_passes: (_p, _k, a) => [a.long, n0],
    pass_diff: (_p, _k, a) => (a.diffN ? [a.diff / a.diffN, n0] : null),
    carries: (_p, _k, a) => [a.carries, n0],
    carry_m: (_p, _k, a) => [a.carryM, m0],
    touches: (_p, k) => [tr.touches[k][f], n0],
    ball_time: (_p, k) => [tr.ballFrames[k][f] / fps, sec],
    tackles: (_p, _k, a) => [a.tackles, n0],
    interceptions: (_p, _k, a) => [a.interceptions, n0],
    pressures: (_p, _k, a) => [a.pressures, n0],
    losses: (_p, _k, a) => [a.losses, n0],
    work_rate: (_p, k) => [tr.dist[k][f] / mins, n0],
    distance: (_p, k) => [tr.dist[k][f], m0],
    sprints: (_p, k) => [tr.sprints[k][f], n0],
    top_speed: (p) => [s?.players[p.id]?.top_speed_kmh ?? 0, kmh],
    speed_now: (_p, k) => [tr.speed[k][f], kmh],
    avg_x: (_p, k) => [tr.sumX[k][f] / (f + 1), m0],
  }
  for (const [k, d] of Object.entries(PLAYER)) {
    const fn = perPlayer[k]
    const vals: StatRow[] = []
    players.forEach((p, i) => {
      const v = fn(p, i, pa.get(p.id) ?? agg())
      if (!v) return
      vals.push({
        id: `player.${k}.${p.id}`, stat: `player.${k}`, scope: 'player', group: d.group, label: d.label[L],
        search: `${keysOf(d)} ${norm(p.name)} #${p.number} ${norm(p.position)} ${norm(club(p.team).name)} ${norm(club(p.team).short)} player spieler jugador`,
        value: v[0], fmt: v[1], player: p, low: d.low,
      })
    })
    const sorted = [...vals].sort((a, b) => (d.low ? a.value! - b.value! : b.value! - a.value!))
    for (const r of vals) {
      r.rank = sorted.findIndex((x) => x.value === r.value) + 1
      r.of = vals.length
    }
    rows.push(...vals)
  }

  // match
  if (s) {
    const ctl = s.control.control_team
    const mv: Record<string, [number | undefined, string | undefined, (v: number) => string]> = {
      ball_speed: [s.ball_speed_kmh, undefined, kmh],
      pressure: [s.pressure_on_ball, undefined, n1],
      changes: [s.control.possession_changes_per_min ?? 0, undefined, n1],
      tempo: [s.rhythm.actions_per_min ?? 0, undefined, n0],
      chaos: [s.control.chaos ?? 0, undefined, pct],
      control: [undefined, ctl ? club(ctl).short : '–', n0],
    }
    for (const [k, d] of Object.entries(MATCH)) {
      const [value, text, fmt] = mv[k]
      rows.push({ id: `match.${k}`, stat: `match.${k}`, scope: 'match', group: d.group, label: d.label[L], search: keysOf(d), value, text, fmt })
    }
  }
  return rows
}

/** Rows matching every word of the query (any language, player names, numbers like "#20"), best first. */
export function searchStats(rows: StatRow[], query: string, limit = 40): StatRow[] {
  const words = norm(query).split(/\s+/).filter(Boolean)
  if (!words.length) return []
  const scored: [number, StatRow][] = []
  for (const r of rows) {
    const label = norm(r.label)
    const name = r.player ? norm(r.player.name) : ''
    let score = 0
    let ok = true
    for (const w of words) {
      if (!r.search.includes(w)) {
        ok = false
        break
      }
      score += label.startsWith(w) ? 4 : label.includes(w) ? 3 : name.split(' ').some((x) => x.startsWith(w)) ? 3 : 1
    }
    if (!ok) continue
    if (r.scope === 'team') score += 0.5 // the team comparison first, then the players
    if (r.rank) score += 0.3 / r.rank // best players first
    scored.push([score, r])
  }
  return scored.sort((a, b) => b[0] - a[0]).slice(0, limit).map(([, r]) => r)
}

export const groupLabel = (g: Group, lang: Lang) => GROUP_LABEL[g][li(lang)]
