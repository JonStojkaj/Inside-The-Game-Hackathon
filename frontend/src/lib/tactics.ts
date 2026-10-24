import { useState } from 'react'
import type { Team } from '../types'
import { frameAt, PITCH_L, PITCH_W, type MatchIndex } from './match'

/**
 * Tactical layer of the analyst's 2D pitch, both parts switchable:
 *   zones  the five vertical lanes (wing / half-space / centre, split at the box and six-yard box
 *          edges), the thirds and zone 14 in front of each box
 *   shape  each team's lines (back line, midfield, attack) connected, the back line strong with its
 *          name ("back four"), and the formation it adds up to (4-4-2)
 * Lines come from the players' roles (the set-up), drawn through their current positions; a line
 * that is torn open right now (someone stepped out, a big gap) is drawn broken. Home attacks towards
 * x = 105 for the whole match.
 */
export interface TacticsOn {
  zones: boolean
  shape: boolean
}

const KEY = 'sliding-doors.tactics.v1'

export function useTactics(): [TacticsOn, (k: keyof TacticsOn) => void] {
  const [on, setOn] = useState<TacticsOn>(() => {
    try {
      const v = JSON.parse(localStorage.getItem(KEY) ?? 'null') as Partial<TacticsOn> | null
      if (v) return { zones: Boolean(v.zones), shape: Boolean(v.shape) }
    } catch {
      // no storage
    }
    return { zones: true, shape: true }
  })
  const toggle = (k: keyof TacticsOn) => {
    const next = { ...on, [k]: !on[k] }
    setOn(next)
    try {
      localStorage.setItem(KEY, JSON.stringify(next))
    } catch {
      // no storage
    }
  }
  return [on, toggle]
}

/** Lane edges across the pitch (y, metres): box edge 13.84 / 54.16, six-yard box edge 24.84 / 43.16. */
export const LANES = [0, 13.84, 24.84, 43.16, 54.16, PITCH_W]

export interface TeamShape {
  team: Team
  /** Player indices per line (back line first), each sorted across the pitch. */
  lines: number[][]
  /** Per line: does it hold (players level, no big gap) or is it torn open right now? */
  intact: boolean[]
  formation: string
}

/** Lines by role, the way the coach set the team up (stable, unlike clustering GRF's chaotic positions). */
const ROLE_LINE: Record<string, number> = {
  CB: 0, LB: 0, RB: 0, LWB: 0, RWB: 0, DM: 1, CM: 2, LM: 2, RM: 2, AM: 3, LW: 3, RW: 3, CF: 4, ST: 4,
}
/** A line holds when nobody is more than this far out of it (metres of depth) and no gap across is wider. */
const MAX_STEP_OUT = 7
const MAX_GAP = 24

export function teamShapes(m: MatchIndex, frame: number): TeamShape[] {
  const players = m.bundle.match.players
  const now = frameAt(m.bundle, frame).players
  return (['home', 'away'] as Team[]).map((team) => {
    const groups = new Map<number, number[]>()
    players.forEach((p, k) => {
      if (p.team !== team || p.position === 'GK') return
      const line = ROLE_LINE[p.position] ?? 2
      groups.set(line, [...(groups.get(line) ?? []), k])
    })
    const lines = [...groups.entries()].sort((a, b) => a[0] - b[0]).map(([, ks]) => ks.sort((a, b) => now[a][1] - now[b][1]))
    const depth = (k: number) => (team === 'home' ? now[k][0] : PITCH_L - now[k][0])
    const intact = lines.map((ks) => {
      if (ks.length < 2) return true
      const ds = ks.map(depth).sort((a, b) => a - b)
      const median = ds[Math.floor(ds.length / 2)]
      const level = ds.every((d) => Math.abs(d - median) <= MAX_STEP_OUT)
      const gaps = ks.slice(1).every((k, i) => now[k][1] - now[ks[i]][1] <= MAX_GAP)
      return level && gaps
    })
    return { team, lines, intact, formation: lines.map((l) => l.length).join('-') }
  })
}

/** "Back four" / "Viererkette" / "Línea de cuatro" for 3-5 defenders, else null. */
export const BROKEN = { en: 'broken', de: 'offen', es: 'rota' } as const

export function backLineName(n: number, lang: 'en' | 'de' | 'es'): string | null {
  const names = {
    en: { 3: 'Back three', 4: 'Back four', 5: 'Back five' },
    de: { 3: 'Dreierkette', 4: 'Viererkette', 5: 'Fünferkette' },
    es: { 3: 'Línea de tres', 4: 'Línea de cuatro', 5: 'Línea de cinco' },
  } as const
  return n >= 3 && n <= 5 ? names[lang][n as 3 | 4 | 5] : null
}

