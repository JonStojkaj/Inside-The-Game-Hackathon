import { useEffect, useState } from 'react'
import type { MatchInfo, Team } from '../types'

/** public/league.json: a fictional 20-club league (standings before this match) + season ratings. */
export interface LeagueClub {
  name: string
  short: string
  color: string
  played: number
  won: number
  drawn: number
  lost: number
  gf: number
  ga: number
  form: string
  rivals: string[]
}

export interface League {
  season: string
  matchday: number
  clubs: LeagueClub[]
  season_ratings: Record<string, number>
  default_rating: number
}

export interface TableRow extends LeagueClub {
  pts: number
  gd: number
  pos: number
  /** Position before this match. */
  before: number
  /** One of the two clubs of this match (their row includes the live score). */
  live: boolean
}

let cache: Promise<League | null> | null = null

function loadLeague(): Promise<League | null> {
  cache ??= fetch(`${import.meta.env.BASE_URL}league.json`)
    .then((r) => (r.ok ? (r.json() as Promise<League>) : null))
    .then((l) => (l && Array.isArray(l.clubs) ? l : null))
    .catch(() => null)
  return cache
}

export function useLeague(): League | null {
  const [league, setLeague] = useState<League | null>(null)
  useEffect(() => {
    let on = true
    void loadLeague().then((l) => on && setLeague(l))
    return () => {
      on = false
    }
  }, [])
  return league
}

const findClub = (l: League, c: { name: string; short: string }) => l.clubs.find((x) => x.short === c.short || x.name === c.name)

/** Does the league know both clubs of this match? */
export function inLeague(l: League | null, match: MatchInfo): l is League {
  return Boolean(l && findClub(l, match.home) && findClub(l, match.away))
}

function rank(rows: (LeagueClub & { pts: number; gd: number })[]): string[] {
  return [...rows].sort((a, b) => b.pts - a.pts || b.gd - a.gd || b.gf - a.gf || a.name.localeCompare(b.name)).map((r) => r.short)
}

const withPts = (c: LeagueClub) => ({ ...c, pts: c.won * 3 + c.drawn, gd: c.gf - c.ga })

/**
 * The table with this match counted as if it ended at `score` (home, away). Ranking: points, goal
 * difference, goals scored, name. Only this match is live; the rest of the matchday has not started.
 */
export function liveTable(l: League, match: MatchInfo, score: [number, number]): TableRow[] {
  const h = findClub(l, match.home)!.short
  const a = findClub(l, match.away)!.short
  const beforeOrder = rank(l.clubs.map(withPts))
  const rows = l.clubs.map((c) => {
    if (c.short !== h && c.short !== a) return withPts(c)
    const [us, them] = c.short === h ? score : [score[1], score[0]]
    const r = { ...c, played: c.played + 1, gf: c.gf + us, ga: c.ga + them, won: c.won + (us > them ? 1 : 0), drawn: c.drawn + (us === them ? 1 : 0), lost: c.lost + (us < them ? 1 : 0) }
    return withPts(r)
  })
  const order = rank(rows)
  return order.map((s, i) => {
    const r = rows.find((x) => x.short === s)!
    return { ...r, pos: i + 1, before: beforeOrder.indexOf(s) + 1, live: s === h || s === a }
  })
}

/** Where `team` would finish the matchday if this match ended as a win / draw / loss for them by one goal. */
export function stakes(l: League, match: MatchInfo, team: Team, score: [number, number]): { win: number; draw: number; loss: number } {
  const pos = (s: [number, number]) => liveTable(l, match, s).find((r) => r.short === findClub(l, match[team])!.short)!.pos
  const lead = (d: number): [number, number] => {
    // one-goal outcome from the current score, so goal difference stays realistic
    const base = Math.max(score[0], score[1])
    const us = d > 0 ? base + 1 : d === 0 ? base : base
    const them = d > 0 ? base : d === 0 ? base : base + 1
    return team === 'home' ? [us, them] : [them, us]
  }
  return { win: pos(lead(1)), draw: pos(lead(0)), loss: pos(lead(-1)) }
}

export const leagueClub = (l: League, c: { name: string; short: string }): LeagueClub | undefined => findClub(l, c)

/** 1st, 2nd, 3rd ... (English); de/es use the plain ordinal. */
export function ordinal(n: number, lang: string): string {
  if (lang === 'de') return `${n}.`
  if (lang === 'es') return `${n}.º`
  const s = n % 100 >= 11 && n % 100 <= 13 ? 'th' : (['th', 'st', 'nd', 'rd'][n % 10] ?? 'th')
  return `${n}${s}`
}
