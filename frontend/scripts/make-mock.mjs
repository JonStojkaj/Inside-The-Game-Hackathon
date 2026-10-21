// Generates a small, deterministic mock export in public/mock/demo/ (same format as data/export/<id>/).
// A hand-scripted 90 s passage (900 frames at 10 Hz, clock_scale 18 => 0'-27'):
// kickoff, away big chance (saved), home goal, dangerous home turnover + away miss.
// Run: node scripts/make-mock.mjs
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'mock', 'demo')
const MATCH_ID = 'demo'
const FPS = 10
const N = 900
const CLOCK_SCALE = 18
const L = 105
const W = 68

let seed = 34
const rnd = () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296)
const gauss = () => Math.sqrt(-2 * Math.log(rnd() + 1e-9)) * Math.cos(2 * Math.PI * rnd())
const r1 = (v) => Math.round(v * 10) / 10
const r3 = (v) => Math.round(v * 1000) / 1000
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1])

// --- roster -----------------------------------------------------------------------------
const HOME = { key: 'home', name: 'FC Northbridge', short: 'NOR', color: '#d6262e' }
const AWAY = { key: 'away', name: 'Harbour City', short: 'HCY', color: '#1f5fbf' }
// [number, position, name, base x, base y] for the home side attacking +x; away is mirrored
const SHAPE = [
  [1, 'GK', 5, 34], [2, 'RB', 30, 10], [4, 'CB', 26, 26], [5, 'CB', 26, 42], [3, 'LB', 30, 58],
  [6, 'DM', 40, 34], [7, 'RM', 54, 12], [8, 'CM', 50, 27], [11, 'LM', 54, 56], [10, 'AM', 63, 40], [9, 'CF', 72, 31],
]
const HOME_NAMES = ['Tomas Vell', 'Idris Calloway', 'Kofi Asante-Rhys', 'Lukas Hagen', 'Mateo Brann', 'Ruben Saldo',
  'Noah Fairley', 'Emil Strand', 'Jonah Pike', 'Leo Marchetti', 'Sami Okoro']
const AWAY_NAMES = ['Arne Dahl', 'Marcus Quill', 'Dario Kesh', 'Oscar Lindqvist', 'Yusuf Benali', 'Felix Ondo',
  'Callum Reyes', 'Theo Varga', 'Bastian Holt', 'Kai Nakamura', 'Ilan Moreau']
const players = []
for (const [team, names] of [['home', HOME_NAMES], ['away', AWAY_NAMES]]) {
  SHAPE.forEach(([number, position, x, y], i) => {
    const base = team === 'home' ? [x, y] : [L - x, W - y]
    players.push({ id: `${team === 'home' ? 'H' : 'A'}${number}`, team, name: names[i], number, position, base })
  })
}
const idx = Object.fromEntries(players.map((p, i) => [p.id, i]))
const P = (id) => players[idx[id]]
const attackDir = (team) => (team === 'home' ? 1 : -1)
const goalOf = (team) => (team === 'home' ? [L, W / 2] : [0, W / 2]) // goal a team attacks

// --- script ---------------------------------------------------------------------------------
// pass(from, to, {intercept: id}) | hold(id, frames) | shot(id, outcome) | tackle(byId) | dead(frames, mode, kickoffTeam?)
const S = []
const pass = (from, to, opt = {}) => S.push({ k: 'pass', from, to, ...opt })
const hold = (id, frames, opt = {}) => S.push({ k: 'hold', id, frames, ...opt })
const shot = (id, outcome, opt = {}) => S.push({ k: 'shot', id, outcome, ...opt })
const tackle = (by) => S.push({ k: 'tackle', by })
const dead = (frames, mode, kickoff) => S.push({ k: 'dead', frames, mode, kickoff })

dead(12, 'kickoff', 'home')
hold('H9', 4); pass('H9', 'H8'); hold('H8', 10); pass('H8', 'H6'); hold('H6', 8); pass('H6', 'H4'); hold('H4', 12)
pass('H4', 'H2'); hold('H2', 14, { run: 6 }); pass('H2', 'H7'); hold('H7', 16, { run: 7 }); pass('H7', 'H10', { intercept: 'A3' })
hold('A3', 8); pass('A3', 'A6'); hold('A6', 10); pass('A6', 'A8'); hold('A8', 12, { run: 5 }); pass('A8', 'A7'); hold('A7', 16, { run: 9 })
pass('A7', 'A10'); hold('A10', 8, { run: 4 }); pass('A10', 'A9'); hold('A9', 6, { run: 3 }); shot('A9', 'saved', { key: 'away_chance' })
hold('H1', 22); dead(14, 'goal_kick'); pass('H1', 'H4'); hold('H4', 10); pass('H4', 'H6'); hold('H6', 8); pass('H6', 'H11'); hold('H11', 18, { run: 8 })
pass('H11', 'H8'); hold('H8', 8); tackle('A8'); hold('A8', 8); pass('A8', 'A5'); hold('A5', 12); pass('A5', 'A2'); hold('A2', 12, { run: 6 })
pass('A2', 'A7'); hold('A7', 8); pass('A7', 'A8', { intercept: 'H6' })
hold('H6', 10); pass('H6', 'H8'); hold('H8', 10); pass('H8', 'H7'); hold('H7', 18, { run: 10 }); pass('H7', 'H8'); hold('H8', 6)
pass('H8', 'H10', { key: 'through_ball', lead: 9 }); hold('H10', 7, { run: 5, key: 'h10_decision' }); pass('H10', 'H9', { key: 'square' }); hold('H9', 2)
shot('H9', 'goal', { key: 'goal' })
dead(60, 'kickoff', 'away')
hold('A9', 4); pass('A9', 'A8'); hold('A8', 10); pass('A8', 'A6'); hold('A6', 10); pass('A6', 'A4'); hold('A4', 14); pass('A4', 'A2'); hold('A2', 12, { run: 5 })
pass('A2', 'A7', { intercept: 'H3' }); hold('H3', 10); pass('H3', 'H5'); hold('H5', 12); pass('H5', 'H4'); hold('H4', 8, { key: 'h4_decision' })
pass('H4', 'H6', { intercept: 'A9', key: 'turnover' }); hold('A9', 8, { run: 5 }); pass('A9', 'A10'); hold('A10', 4); shot('A10', 'off_target', { key: 'away_miss' })
dead(30, 'goal_kick'); hold('H1', 10); pass('H1', 'H5'); hold('H5', 12); pass('H5', 'H6'); hold('H6', 10); pass('H6', 'H8'); hold('H8', 12, { run: 5 })
pass('H8', 'H10'); hold('H10', 14, { run: 6 }); pass('H10', 'H11'); hold('H11', 20, { run: 9 }); pass('H11', 'H8'); hold('H8', 12); pass('H8', 'H2'); hold('H2', 30, { run: 8 })

// --- simulation ----------------------------------------------------------------------------
const pos = players.map((p) => [...p.base])
const frames = { t_ms: [], ball: [], players: [], owner: [], score: [], mode: [] }
const events = []
const keys = {} // script key -> {frame, ...}
let score = [0, 0]
let owner = idx.H9
let ball = [L / 2, W / 2, 0]
let f = 0
let evN = 0
const ev = (type, extra) => events.push({ id: `e${String(++evN).padStart(4, '0')}`, match_id: MATCH_ID, t_ms: f * 100, frame: f,
  type, team: null, player_id: null, target_id: null, start_xy: null, end_xy: null, outcome: null, meta: {}, ...extra })

function targets(activeTeam, ballXY, special) {
  // formation block shifted towards the ball; attacking side pushes up
  const shiftX = (ballXY[0] - L / 2) * 0.45
  return players.map((p, i) => {
    if (special[i]) return special[i]
    const push = p.team === activeTeam ? 6 * attackDir(p.team) : -3 * attackDir(p.team)
    const gk = p.position === 'GK'
    const x = p.base[0] + (gk ? shiftX * 0.15 : shiftX + push)
    const y = p.base[1] + (ballXY[1] - p.base[1]) * (gk ? 0.3 : 0.22)
    return [Math.min(Math.max(x, 1), L - 1), Math.min(Math.max(y, 1), W - 1)]
  })
}

function step(activeTeam, special, maxSpeed = 0.75) {
  const tg = targets(activeTeam, ball, special)
  pos.forEach((p, i) => {
    const wob = [Math.sin((f + i * 7) / 9) * 0.06, Math.cos((f + i * 5) / 11) * 0.06]
    const dx = tg[i][0] - p[0]
    const dy = tg[i][1] - p[1]
    const d = Math.hypot(dx, dy)
    const s = Math.min(1, maxSpeed / (d || 1))
    p[0] += dx * s * (d > 0.4 ? 1 : 0.4) + wob[0]
    p[1] += dy * s * (d > 0.4 ? 1 : 0.4) + wob[1]
  })
}

function nearestOpp(team, xy) {
  let best = -1
  let bd = 1e9
  players.forEach((p, i) => {
    if (p.team !== team && dist(pos[i], xy) < bd) { bd = dist(pos[i], xy); best = i }
  })
  return { i: best, d: bd }
}

function record(mode) {
  frames.t_ms.push(f * 100)
  frames.ball.push([r1(ball[0]), r1(ball[1]), r1(ball[2])])
  frames.players.push(pos.map((p) => [r1(p[0]), r1(p[1])]))
  frames.owner.push(owner)
  frames.score.push([...score])
  frames.mode.push(mode)
  f++
}

const footOf = (i) => [pos[i][0] + 0.6 * attackDir(players[i].team), pos[i][1] - 0.3, 0]

for (const a of S) {
  if (f >= N) break
  if (a.k === 'dead') {
    if (a.kickoff) {
      // reset to kickoff shape, then hold still
      players.forEach((p, i) => {
        const back = p.team === a.kickoff ? 0 : 0
        pos[i] = [p.base[0] - attackDir(p.team) * (p.position === 'GK' ? 0 : 14 + back), p.base[1]]
      })
      const cf = idx[a.kickoff === 'home' ? 'H9' : 'A9']
      pos[cf] = [L / 2 - attackDir(players[cf].team) * 0.5, W / 2]
      owner = cf
      ball = [L / 2, W / 2, 0]
      ev('kickoff', { team: a.kickoff, player_id: players[cf].id, start_xy: [L / 2, W / 2] })
    } else {
      ev('set_piece', { team: players[owner].team, player_id: players[owner].id, outcome: a.mode, start_xy: [r1(ball[0]), r1(ball[1])] })
    }
    for (let k = 0; k < a.frames && f < N; k++) record(a.mode)
    continue
  }
  if (a.k === 'hold') {
    owner = idx[a.id]
    const p = players[owner]
    const start = [...pos[owner]]
    if (a.key) keys[a.key] = { frame: f, xy: [...start] }
    const run = a.run ?? 1.5
    const startF = f
    for (let k = 0; k < a.frames && f < N; k++) {
      const t = (k + 1) / a.frames
      const tgt = [start[0] + attackDir(p.team) * run * t, start[1] + (W / 2 - start[1]) * 0.08 * t]
      step(p.team, { [owner]: tgt }, 0.85)
      ball = footOf(owner)
      record('normal')
    }
    if (run >= 5) ev('carry', { team: p.team, player_id: p.id, start_xy: [r1(start[0]), r1(start[1])], end_xy: [r1(pos[owner][0]), r1(pos[owner][1])], meta: { distance_m: r1(dist(start, pos[owner])), frames: f - startF } })
    // light pressure events when an opponent is close
    const opp = nearestOpp(p.team, pos[owner])
    if (opp.d < 3.5) ev('pressure', { team: players[opp.i].team, player_id: players[opp.i].id, target_id: p.id, start_xy: [r1(pos[opp.i][0]), r1(pos[opp.i][1])], meta: { pressure_index: r3(1 - opp.d / 5) } })
    continue
  }
  if (a.k === 'tackle') {
    const by = idx[a.by]
    const victim = owner
    ev('tackle', { team: players[by].team, player_id: players[by].id, target_id: players[victim].id, start_xy: [r1(ball[0]), r1(ball[1])], outcome: 'won' })
    for (let k = 0; k < 4 && f < N; k++) {
      step(players[by].team, { [by]: [ball[0], ball[1]] }, 0.9)
      ball = [ball[0] + (pos[by][0] - ball[0]) * 0.5, ball[1] + (pos[by][1] - ball[1]) * 0.5, 0]
      record('normal')
    }
    owner = by
    continue
  }
  if (a.k === 'pass') {
    const from = idx[a.from]
    const team = players[from].team
    const recv = idx[a.intercept ?? a.to]
    const intended = idx[a.to]
    const start = [ball[0], ball[1]]
    const lead = a.lead ?? 2.5
    const endGuess = [pos[intended][0] + attackDir(team) * lead, pos[intended][1]]
    const d = dist(start, endGuess)
    const n = Math.max(5, Math.round(d / 1.9))
    const lofted = d > 30
    if (a.key) keys[a.key] = { frame: f, xy: start, from: a.from, to: a.to }
    const startF = f
    owner = -1
    const meta = { distance_m: r1(d), difficulty: Math.round(Math.min(95, 20 + d * 1.4 + (a.key === 'through_ball' ? 25 : 0) + rnd() * 10)) }
    const evStart = { frame: f, t: f * 100 }
    for (let k = 0; k < n && f < N; k++) {
      const t = (k + 1) / n
      const special = { [intended]: endGuess }
      if (a.intercept) special[recv] = [start[0] + (endGuess[0] - start[0]) * 0.75, start[1] + (endGuess[1] - start[1]) * 0.75]
      step(team, special, 0.8)
      const end = a.intercept ? pos[recv] : pos[intended]
      ball = [start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t, lofted ? 6 * t * (1 - t) * 4 * Math.min(1, d / 45) : 0]
      record('normal')
    }
    owner = recv
    const endXY = [r1(ball[0]), r1(ball[1])]
    events.push({ id: `e${String(++evN).padStart(4, '0')}`, match_id: MATCH_ID, t_ms: evStart.t, frame: evStart.frame, type: 'pass', team,
      player_id: a.from, target_id: a.to, start_xy: [r1(start[0]), r1(start[1])], end_xy: endXY, outcome: a.intercept ? 'incomplete' : 'complete',
      meta: { ...meta, frames: f - startF } })
    if (a.intercept) ev('interception', { team: players[recv].team, player_id: a.intercept, target_id: a.to, start_xy: endXY })
    if (a.key) keys[a.key].event = events.find((e) => e.frame === evStart.frame && e.type === 'pass')?.id
    continue
  }
  if (a.k === 'shot') {
    const from = idx[a.id]
    const team = players[from].team
    const goal = goalOf(team)
    const start = [ball[0], ball[1]]
    const gk = idx[team === 'home' ? 'A1' : 'H1']
    const end = a.outcome === 'goal' ? [goal[0] + attackDir(team) * 1.2, goal[1] + 2.2, 1.4]
      : a.outcome === 'saved' ? [goal[0] - attackDir(team) * 1.5, goal[1] - 1.5, 0.8]
        : [goal[0] + attackDir(team) * 2, goal[1] + 7, 2.2]
    const d = dist(start, goal)
    const n = Math.max(4, Math.round(d / 2.6))
    const speed = r1(d / (n / FPS) * 3.6)
    const xg = r3(Math.max(0.03, Math.min(0.6, 0.9 * Math.exp(-d / 9))))
    keys[a.key] = { frame: f, xy: start, player: a.id, d }
    const shotId = `e${String(evN + 1).padStart(4, '0')}`
    ev('shot', { team, player_id: a.id, start_xy: [r1(start[0]), r1(start[1])], end_xy: [r1(end[0]), r1(end[1])], outcome: a.outcome,
      meta: { distance_m: r1(d), xg, shot_speed_kmh: speed, on_target: a.outcome !== 'off_target' } })
    keys[a.key].event = shotId
    owner = -1
    for (let k = 0; k < n && f < N; k++) {
      const t = (k + 1) / n
      const special = {}
      if (a.outcome === 'saved') special[gk] = [end[0], end[1]]
      else special[gk] = [goal[0] - attackDir(team) * 1.5, goal[1] + (end[1] - goal[1]) * 0.4]
      step(team, special, 0.9)
      ball = [start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t, end[2] * Math.sin(t * Math.PI * 0.6)]
      record('normal')
    }
    if (a.outcome === 'goal') {
      score = team === 'home' ? [score[0] + 1, score[1]] : [score[0], score[1] + 1]
      ev('goal', { team, player_id: a.id, start_xy: [r1(start[0]), r1(start[1])], outcome: 'goal', meta: { score: [...score], assist_id: 'H10' } })
      keys[a.key].goalEvent = `e${String(evN).padStart(4, '0')}`
      ball = [end[0], end[1], 0.2]
    } else if (a.outcome === 'saved') {
      owner = gk
    } else {
      ev('out_of_play', { team, start_xy: [r1(end[0]), r1(end[1])], outcome: 'goal_kick' })
      owner = gk
      ball = [goalOf(team)[0] - attackDir(team) * 5.5, goalOf(team)[1] - 3, 0]
      pos[gk] = [ball[0] - attackDir(players[gk].team) * -0.8, ball[1]]
    }
    continue
  }
}
while (f < N) { step(players[Math.max(owner, 0)].team, owner >= 0 ? { [owner]: pos[owner] } : {}); if (owner >= 0) ball = footOf(owner); record('normal') }
events.sort((a, b) => a.frame - b.frame || a.id.localeCompare(b.id))

// --- stats every 10 frames ------------------------------------------------------------------
const stats = []
const possFrames = { home: 0, away: 0 }
const topSpeed = new Array(22).fill(0)
for (let fr = 0; fr < N; fr++) {
  const o = frames.owner[fr]
  if (o >= 0) possFrames[players[o].team]++
  if (fr > 0) players.forEach((_, i) => {
    const v = dist(frames.players[fr][i], frames.players[fr - 1][i]) * FPS * 3.6
    if (frames.mode[fr] === 'normal' && frames.mode[fr - 1] === 'normal') topSpeed[i] = Math.max(topSpeed[i], v)
  })
  if (fr % 10 !== 0) continue
  const tMs = fr * 100
  const seen = events.filter((e) => e.frame <= fr)
  const team = (t) => {
    const passes = seen.filter((e) => e.type === 'pass' && e.team === t)
    const comp = passes.filter((e) => e.outcome === 'complete').length
    const shots = seen.filter((e) => e.type === 'shot' && e.team === t)
    const total = possFrames.home + possFrames.away
    return {
      team: t,
      possession: total ? r3(possFrames[t] / total) : 0.5,
      passes: passes.length,
      passes_completed: comp,
      pass_accuracy: passes.length ? r3(comp / passes.length) : null,
      avg_pass_distance_m: passes.length ? r1(passes.reduce((s, e) => s + e.meta.distance_m, 0) / passes.length) : null,
      shots: shots.length,
      shots_on_target: shots.filter((e) => e.meta.on_target).length,
      goals: seen.filter((e) => e.type === 'goal' && e.team === t).length,
      max_shot_speed_kmh: Math.max(0, ...shots.map((e) => e.meta.shot_speed_kmh)),
      tackles: seen.filter((e) => e.type === 'tackle' && e.team === t).length,
      interceptions: seen.filter((e) => e.type === 'interception' && e.team === t).length,
      pressures: seen.filter((e) => e.type === 'pressure' && e.team === t).length,
      xg: r3(shots.reduce((s, e) => s + e.meta.xg, 0)),
    }
  }
  const pl = {}
  players.forEach((p, i) => {
    const prev = frames.players[Math.max(0, fr - 3)][i]
    const sp = frames.mode[fr] === 'normal' ? dist(frames.players[fr][i], prev) / 0.3 * 3.6 : 0
    const mine = seen.filter((e) => e.player_id === p.id)
    const passes = mine.filter((e) => e.type === 'pass')
    pl[p.id] = { id: p.id, name: p.name, team: p.team, number: p.number, position: p.position, speed_kmh: r1(sp), top_speed_kmh: r1(topSpeed[i]),
      passes: passes.length, passes_completed: passes.filter((e) => e.outcome === 'complete').length,
      shots: mine.filter((e) => e.type === 'shot').length, goals: mine.filter((e) => e.type === 'goal').length,
      tackles: mine.filter((e) => e.type === 'tackle').length, interceptions: mine.filter((e) => e.type === 'interception').length,
      pressures: mine.filter((e) => e.type === 'pressure').length }
  })
  // pressure on the ball carrier
  let pressure = 0
  if (o >= 0) {
    players.forEach((p, i) => {
      if (p.team !== players[o].team) pressure += Math.max(0, 1 - dist(frames.players[fr][i], frames.players[fr][o]) / 5)
    })
  }
  const win = seen.filter((e) => e.frame > fr - 300)
  const prevWin = seen.filter((e) => e.frame > fr - 600 && e.frame <= fr - 300)
  const minutes = Math.max((Math.min(fr, 300) / FPS) * CLOCK_SCALE / 60, 1)
  const changes = win.filter((e) => e.type === 'interception' || e.type === 'tackle').length
  const wp = win.filter((e) => e.type === 'pass')
  const compl = wp.length ? wp.filter((e) => e.outcome === 'complete').length / wp.length : 0.5
  const chaos = Math.min(1, 0.6 * Math.min(changes / minutes / 0.6, 1) * 0.6 + 0.25 * (1 - compl) + 0.12 + 0.1 * Math.sin(fr / 90))
  const compBy = { home: wp.filter((e) => e.team === 'home' && e.outcome === 'complete').length, away: wp.filter((e) => e.team === 'away' && e.outcome === 'complete').length }
  const ctot = compBy.home + compBy.away
  const leader = ctot ? (compBy.home >= compBy.away ? 'home' : 'away') : null
  const actions = (arr) => arr.filter((e) => ['pass', 'shot', 'tackle', 'interception', 'carry'].includes(e.type)).length
  const apm = r1(actions(win) / minutes)
  const before = actions(prevWin) / minutes
  const change = before ? (apm - before) / before : 0
  const press = (t) => r3(win.filter((e) => e.type === 'pressure' && e.team === t).reduce((s, e) => s + e.meta.pressure_index, 0) / Math.max(1, win.filter((e) => e.type === 'pressure' && e.team === t).length) || 0)
  stats.push({
    match_id: MATCH_ID, t_ms: tMs, clock_s: (tMs / 1000) * CLOCK_SCALE, score: frames.score[fr],
    teams: { home: team('home'), away: team('away') }, players: pl,
    ball_speed_kmh: r1(fr > 0 ? dist(frames.ball[fr], frames.ball[fr - 1]) * FPS * 3.6 : 0),
    pressure_on_ball: r3(pressure), pressing: { home: press('home'), away: press('away') },
    control: { chaos: r3(chaos), control_team: leader, control_share: leader ? r3(compBy[leader] / ctot) : null, possession_changes_per_min: r1(changes / minutes) },
    rhythm: { actions_per_min: apm, change: r3(change), trend: change > 0.2 ? 'rising' : change < -0.2 ? 'falling' : 'steady' },
  })
}

// --- moments + insights -----------------------------------------------------------------------
const clock = (frame) => frame * 0.1 * CLOCK_SCALE
const kAway = keys.away_chance
const kGoal = keys.goal
const kThrough = keys.through_ball
const kTurn = keys.turnover
const kMiss = keys.away_miss
const moments = [
  { id: 'm1', match_id: MATCH_ID, frame: kAway.frame, t_ms: kAway.frame * 100, clock_s: clock(kAway.frame), kind: 'big_chance', score: 0.71, team: 'away',
    player_ids: ['A9', 'A10'], event_ids: [kAway.event], reason: `shot from ${Math.round(kAway.d)} m, saved by H1` },
  { id: 'm2', match_id: MATCH_ID, frame: kThrough.frame, t_ms: kThrough.frame * 100, clock_s: clock(kThrough.frame), kind: 'decisive_pass', score: 0.64, team: 'home',
    player_ids: ['H8', 'H10'], event_ids: [kThrough.event], reason: 'through ball breaks two lines, threat +0.18' },
  { id: 'm3', match_id: MATCH_ID, frame: kGoal.frame, t_ms: kGoal.frame * 100, clock_s: clock(kGoal.frame), kind: 'goal', score: 0.97, team: 'home',
    player_ids: ['H9', 'H10'], event_ids: [kGoal.event, kGoal.goalEvent], reason: 'goal H9, assist H10 (1-0)' },
  { id: 'm4', match_id: MATCH_ID, frame: kTurn.frame, t_ms: kTurn.frame * 100, clock_s: clock(kTurn.frame), kind: 'dangerous_turnover', score: 0.68, team: 'home',
    player_ids: ['H4', 'A9'], event_ids: [kTurn.event, kMiss.event], reason: `H4 pass intercepted ${Math.round(frames.ball[kTurn.frame][0])} m from own goal` },
]

function fan(from, target, n, spread, len, hitShare, endSpread = 8) {
  // n ghost ball paths: wobbling curves from `from` towards `target`; some fall short (turnovers)
  const paths = []
  for (let k = 0; k < n; k++) {
    const hit = rnd() < hitShare
    const tgt = hit ? [target[0] + gauss() * 1.5, target[1] + gauss() * 2.5]
      : [from[0] + (target[0] - from[0]) * (0.35 + rnd() * 0.5) + gauss() * endSpread * 0.4, from[1] + (target[1] - from[1]) * (0.4 + rnd() * 0.4) + gauss() * endSpread]
    const bend = gauss() * spread
    const pts = []
    for (let s = 0; s <= len; s++) {
      const t = s / len
      const nx = -(tgt[1] - from[1])
      const ny = tgt[0] - from[0]
      const nl = Math.hypot(nx, ny) || 1
      const b = Math.sin(t * Math.PI) * bend
      pts.push([r1(from[0] + (tgt[0] - from[0]) * t + (nx / nl) * b + gauss() * 0.25), r1(Math.min(W, Math.max(0, from[1] + (tgt[1] - from[1]) * t + (ny / nl) * b + gauss() * 0.25)))])
    }
    paths.push(pts)
  }
  return paths
}

const hyp = (text, intervention, b, c, spread, verdict, note) => ({ text, intervention, baseline_p_goal: b, counterfactual_p_goal: c, seed_spread: spread, verdict, critic_note: note })
const bAway = frames.ball[kAway.frame]
const a10 = frames.players[kAway.frame][idx.A10]
const bH10 = frames.ball[keys.h10_decision.frame + 6]
const bTurn = frames.ball[keys.h4_decision.frame]
const insights = [
  {
    id: 'i1', moment_id: 'm1',
    claim: 'Moreau shot from 22 m (9 % goal chance). Laying it off to Nakamura in space would have made a goal clearly more likely: 24 %.',
    evidence: [kAway.event, 'rollout:m1:base', 'rollout:m1:alt2'],
    numbers: { actual_p_goal: 0.09, actual_p_turnover: 0.41, best_alt_p_goal: 0.24, delta_p_goal: 0.15 },
    verified: true, confidence: 'clear', metric: 'p_goal', decision_frame: kAway.frame,
    hypotheses: [
      hyp('A9 should have passed to A10, who was unmarked at the edge of the box', { kind: 'swap_action', params: { action: 'pass', target_id: 'A10' } }, 0.09, 0.24, 0.02, 'accepted', 'Effect +15 pts, stable across 5 seeds (spread 2 pts).'),
      hyp('A9 should have carried the ball 5 m further before shooting', { kind: 'swap_action', params: { action: 'carry' } }, 0.09, 0.11, 0.04, 'rejected', 'Effect +2 pts is inside the seed spread (4 pts). Not shown.'),
      hyp('H5 was 4 m too deep and left the shooting lane open', { kind: 'move_player', params: { player_id: 'H5', dx: 4, dy: 0 } }, 0.09, 0.05, 0.02, 'accepted', 'Defensive view: moving H5 up halves the chance. Kept for the analyst segment.'),
    ],
    ghost_paths: fan([bAway[0], bAway[1]], [0, 34], 30, 4, 14, 0.12, 10),
    alt_ghost_paths: fan([a10[0], a10[1]], [0, 34], 30, 3, 14, 0.3, 7),
    alt_label: 'Lay-off to Nakamura (#10)',
  },
  {
    id: 'i2', moment_id: 'm3',
    claim: 'Marchetti squared it instead of shooting himself: the pass to Okoro made the goal about 3x more likely (34 % vs 11 %).',
    evidence: [kThrough.event, kGoal.event, 'rollout:m3:base', 'rollout:m3:alt1'],
    numbers: { actual_p_goal: 0.34, actual_p_turnover: 0.22, best_alt_p_goal: 0.11, delta_p_goal: -0.23 },
    verified: true, confidence: 'clear', metric: 'p_goal', decision_frame: keys.h10_decision.frame + 6,
    hypotheses: [
      hyp('H10 shooting from 18 m would have been the better option', { kind: 'swap_action', params: { action: 'shoot' } }, 0.34, 0.11, 0.03, 'rejected', 'Counterfactual is worse by 23 pts: the real decision was the right one.'),
      hyp("Strand's through ball broke two lines and created the chance", { kind: 'remove_player', params: { player_id: 'A6' } }, 0.34, 0.37, 0.05, 'rejected', 'Removing A6 changes little (+3 pts, spread 5): A6 was not the key defender.'),
      hyp('Without the square pass the goal chance falls to a third', { kind: 'swap_action', params: { action: 'carry' } }, 0.34, 0.12, 0.02, 'accepted', 'Stable across 5 seeds. Claim allowed: "about 3x more likely".'),
    ],
    ghost_paths: fan([bH10[0], bH10[1]], [105, 34], 30, 3, 12, 0.36, 6),
    alt_ghost_paths: fan([bH10[0], bH10[1]], [105, 34], 30, 2, 12, 0.11, 9),
    alt_label: 'Marchetti shoots from 18 m',
  },
  {
    id: 'i3', moment_id: 'm4',
    claim: 'Asante-Rhys forced the pass into midfield under pressure; switching it to Hagen would have kept the ball (turnover risk 12 % instead of 47 %).',
    evidence: [kTurn.event, kMiss.event, 'rollout:m4:base', 'rollout:m4:alt1'],
    numbers: { actual_p_goal: 0.0, actual_p_keep: 0.53, best_alt_p_keep: 0.88, delta_p_keep: 0.35 },
    verified: true, confidence: 'slight', metric: 'p_keep', decision_frame: keys.h4_decision.frame,
    hypotheses: [
      hyp('H4 should have switched play to H5', { kind: 'swap_action', params: { action: 'pass', target_id: 'H5' } }, 0.14, 0.03, 0.04, 'accepted', 'Goal-against chance drops 11 pts; spread 4 pts, so "slightly" not "clearly".'),
      hyp('H6 dropping 5 m deeper would have opened a safe lane', { kind: 'move_player', params: { player_id: 'H6', dx: -5, dy: 0 } }, 0.14, 0.12, 0.05, 'rejected', 'Effect inside the seed spread. Not shown.'),
    ],
    ghost_paths: fan([bTurn[0], bTurn[1]], [0, 34], 30, 5, 12, 0.14, 9),
    alt_ghost_paths: fan([bTurn[0], bTurn[1]], [frames.players[keys.h4_decision.frame][idx.H5][0] + 12, frames.players[keys.h4_decision.frame][idx.H5][1] + 4], 30, 2, 10, 0.88, 4),
    alt_label: 'Switch to Hagen (#5)',
  },
]

// --- overlays per segment ---------------------------------------------------------------------
let oN = 0
const ms = (frame) => Math.round(frame * 100)
const O = (segment_id, frame, dur_s, slot, type, priority, lang, headline, body, payload = {}, evidence = []) =>
  ({ id: `o${String(++oN).padStart(3, '0')}`, match_id: MATCH_ID, segment_id, start_ms: ms(frame), duration_ms: dur_s * 1000, slot, type, priority, lang, headline, body, payload, evidence })
const sAt = (frame) => stats[Math.min(stats.length - 1, Math.floor(frame / 10))]
const goalF = kGoal.frame + 8
const restartF = goalF + 52
const pct = (v) => `${Math.round(v * 100)} %`

const analyst = 'analyst-de'
const fan_home = 'club_fan-home-en'
const fan_away = 'club_fan-away-en'
const focus = 'player_focus-H10-es'
const overlays = {
  '*': [
    O('*', 2, 4, 'ticker', 'event_card', 30, 'en', 'Kick-off', 'FC Northbridge v Harbour City', { event: 'kickoff' }),
  ],
  [analyst]: [
    O(analyst, 60, 8, 'side_panel', 'stat_card', 40, 'de', 'Kontrolle vs. Chaos', 'Ruhiger Spielaufbau von Northbridge', { metric: 'control', value: sAt(60).control.chaos, rows: [
      { label: 'Ballbesitz', home: pct(sAt(60).teams.home.possession), away: pct(sAt(60).teams.away.possession) },
      { label: 'Passquote', home: pct(sAt(60).teams.home.pass_accuracy ?? 0), away: pct(sAt(60).teams.away.pass_accuracy ?? 0.5) },
    ] }),
    O(analyst, 150, 7, 'side_panel', 'stat_card', 45, 'de', 'Pressing-Index', 'Harbour City presst nach Ballgewinn hoch', { metric: 'pressing', rows: [
      { label: 'Pressing', home: String(sAt(150).pressing.home ?? 0), away: String(sAt(150).pressing.away ?? 0) },
      { label: 'Ballwechsel / min', home: String(sAt(150).control.possession_changes_per_min), away: '' },
    ] }),
    O(analyst, kAway.frame + 2, 6, 'lower_third', 'event_card', 70, 'de', 'Großchance Harbour City', `Moreau aus 22 m · xG ${events.find((e) => e.id === kAway.event).meta.xg} · ${events.find((e) => e.id === kAway.event).meta.shot_speed_kmh} km/h · gehalten`, { event: 'shot', team: 'away', player_id: 'A9' }, [kAway.event]),
    O(analyst, kAway.frame + 14, 14, 'pitch', 'sliding_doors', 90, 'de', 'Sliding Doors: Schuss oder Ablage?', 'Ablage auf Nakamura: 24 % statt 9 % Torchance', { insight_id: 'i1' }, ['i1']),
    O(analyst, kThrough.frame + 4, 6, 'ticker', 'alert', 55, 'de', 'Passschwierigkeit 82/100', 'Strand → Marchetti überspielt zwei Linien', { metric: 'pass_difficulty', value: 82 }, [kThrough.event]),
    O(analyst, goalF, 7, 'lower_third', 'event_card', 85, 'de', 'TOR · Northbridge 1–0', 'Okoro nach Querpass von Marchetti · xG 0,34', { event: 'goal', team: 'home', player_id: 'H9' }, [kGoal.goalEvent]),
    O(analyst, goalF + 12, 16, 'pitch', 'sliding_doors', 95, 'de', 'Sliding Doors: Querpass vs. Abschluss', 'Der Querpass machte das Tor rund 3× wahrscheinlicher (34 % vs. 11 %)', { insight_id: 'i2' }, ['i2']),
    O(analyst, goalF + 30, 12, 'side_panel', 'insight', 60, 'de', 'Warum das Tor fiel', 'Zwei Linien mit einem Pass überspielt, dann die bessere Option gewählt. 2 von 3 Hypothesen verworfen.', { insight_id: 'i2', confidence: 'clear' }, ['i2']),
    O(analyst, kTurn.frame + 2, 5, 'lower_third', 'event_card', 70, 'de', 'Ballverlust im Aufbau', 'Asante-Rhys unter Druck · Druckindex 1,4', { event: 'interception', team: 'away', player_id: 'A9' }, [kTurn.event]),
    O(analyst, kMiss.frame + 10, 14, 'pitch', 'sliding_doors', 90, 'de', 'Sliding Doors: Spielverlagerung', 'Verlagerung auf Hagen: Ballverlustrisiko 12 % statt 47 %', { insight_id: 'i3' }, ['i3']),
    O(analyst, 820, 8, 'side_panel', 'stat_card', 40, 'de', 'Rhythmus', 'Tempo steigt nach dem Tor', { metric: 'rhythm', rows: [
      { label: 'Aktionen / min', home: String(sAt(820).rhythm.actions_per_min), away: '' },
      { label: 'Chaos', home: String(sAt(820).control.chaos), away: '' },
    ] }),
  ],
  [fan_home]: [
    O(fan_home, 90, 6, 'scorebug', 'momentum', 35, 'en', 'We are on top', 'Northbridge control the ball', { home_share: 0.64 }),
    O(fan_home, kAway.frame + 2, 6, 'lower_third', 'alert', 70, 'en', 'Huge save, Vell!', 'Moreau from 22 m, kept out by our keeper', { event: 'shot', team: 'away', player_id: 'H1' }, [kAway.event]),
    O(fan_home, goalF, 5, 'fullscreen', 'event_card', 100, 'en', 'GOAL!', 'Sami Okoro · Northbridge 1–0', { event: 'goal', team: 'home', player_id: 'H9', big: true }, [kGoal.goalEvent]),
    O(fan_home, goalF + 50, 12, 'pitch', 'sliding_doors', 95, 'en', 'The pass that made it', "Marchetti's square ball made our goal 3x more likely", { insight_id: 'i2', simple: true }, ['i2']),
    O(fan_home, restartF + 20, 6, 'scorebug', 'momentum', 35, 'en', 'Riding the wave', '62 % possession since the goal', { home_share: 0.62 }),
    O(fan_home, kTurn.frame + 2, 5, 'lower_third', 'alert', 75, 'en', 'Careful at the back!', 'Ball lost 24 m from our goal', { event: 'interception', team: 'away' }, [kTurn.event]),
    O(fan_home, kMiss.frame + 4, 5, 'lower_third', 'alert', 70, 'en', 'Phew. Wide.', 'Nakamura drags it past the post', { event: 'shot', team: 'away' }, [kMiss.event]),
  ],
  [fan_away]: [
    O(fan_away, kAway.frame + 2, 6, 'lower_third', 'event_card', 70, 'en', 'So close!', 'Moreau forces a save from 22 m', { event: 'shot', team: 'away', player_id: 'A9' }, [kAway.event]),
    O(fan_away, kAway.frame + 14, 14, 'pitch', 'sliding_doors', 90, 'en', 'What if he had squared it?', 'A lay-off to Nakamura: 24 % instead of 9 %', { insight_id: 'i1', simple: true }, ['i1']),
    O(fan_away, goalF, 6, 'lower_third', 'event_card', 80, 'en', 'Conceded', 'Okoro scores · 1–0 Northbridge', { event: 'goal', team: 'home' }, [kGoal.goalEvent]),
  ],
  [focus]: [
    O(focus, 40, 6, 'pitch', 'player_tag', 50, 'es', 'Marchetti #10', 'Mediapunta', { player_id: 'H10' }),
    O(focus, 120, 6, 'side_panel', 'stat_card', 45, 'es', 'Leo Marchetti', 'Tu jugador en directo', { player_id: 'H10', rows: [
      { label: 'Pases', value: `${sAt(120).players.H10.passes_completed}/${sAt(120).players.H10.passes}` },
      { label: 'Velocidad máx.', value: `${sAt(120).players.H10.top_speed_kmh} km/h` },
    ] }),
    O(focus, kThrough.frame + 4, 6, 'pitch', 'player_tag', 60, 'es', 'Marchetti recibe entre líneas', '', { player_id: 'H10' }, [kThrough.event]),
    O(focus, goalF, 8, 'lower_third', 'event_card', 90, 'es', 'ASISTENCIA DE MARCHETTI', 'Okoro marca · Northbridge 1–0', { event: 'goal', team: 'home', player_id: 'H10' }, [kGoal.goalEvent]),
    O(focus, goalF + 12, 16, 'pitch', 'sliding_doors', 95, 'es', '¿Tirar o pasar?', 'El pase de Marchetti hizo el gol unas 3 veces más probable (34 % frente a 11 %)', { insight_id: 'i2' }, ['i2']),
    O(focus, restartF + 30, 7, 'side_panel', 'stat_card', 45, 'es', 'Leo Marchetti', 'Partido hasta ahora', { player_id: 'H10', rows: [
      { label: 'Pases', value: `${sAt(restartF + 30).players.H10.passes_completed}/${sAt(restartF + 30).players.H10.passes}` },
      { label: 'Asistencias', value: '1' },
      { label: 'Velocidad máx.', value: `${sAt(restartF + 30).players.H10.top_speed_kmh} km/h` },
    ] }),
    O(focus, 840, 6, 'pitch', 'player_tag', 55, 'es', 'Marchetti conduce', '', { player_id: 'H10' }),
  ],
}

const match = {
  match_id: MATCH_ID, home: HOME, away: AWAY,
  players: players.map(({ id, team, name, number, position }) => ({ id, team, name, number, position })),
  fps: FPS, n_frames: N, duration_ms: N * 100, clock_scale: CLOCK_SCALE, final_score: score, video: null,
}

mkdirSync(OUT, { recursive: true })
const files = { 'match.json': match, 'frames.json': frames, 'events.json': events, 'moments.json': moments, 'insights.json': insights, 'stats.json': stats, 'overlays.json': overlays }
for (const [name, data] of Object.entries(files)) writeFileSync(join(OUT, name), JSON.stringify(data))
console.log(`wrote ${Object.keys(files).length} files to ${OUT}: ${N} frames, ${events.length} events, score ${score.join('-')}`)
console.log('keys', Object.fromEntries(Object.entries(keys).map(([k, v]) => [k, v.frame])))
