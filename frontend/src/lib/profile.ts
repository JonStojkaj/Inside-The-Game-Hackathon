import type { EventType, Lang, OverlaysBySegment, PlayerInfo, ProfileMode, Team, ViewerProfile } from '../types'
import { EXTRA } from './strings'
import { ASK } from './strings-ask'
import { UX } from './strings-ux'
import { V2 } from './strings-v2'

/** Same rule as ViewerProfile.segment_id in the backend. */
export function segmentId(p: ViewerProfile): string {
  const focus = p.mode === 'club_fan' ? p.favourite_club : (p.favourite_players[0] ?? '')
  return [p.mode, focus ?? '', p.language].filter(Boolean).join('-')
}

/**
 * The segment whose overlays this profile sees. Falls back to the same mode and focus in another
 * language, then the same mode, so a partial export still shows something.
 */
export function resolveSegment(overlays: OverlaysBySegment, p: ViewerProfile): { id: string; exact: boolean } {
  const want = segmentId(p)
  if (overlays[want]) return { id: want, exact: true }
  const prefix = want.slice(0, want.length - p.language.length - 1)
  const keys = Object.keys(overlays).filter((k) => k !== '*')
  const sameFocus = keys.find((k) => k.startsWith(prefix + '-') || k === prefix)
  const sameMode = keys.find((k) => k.split('-')[0] === p.mode)
  return { id: sameFocus ?? sameMode ?? want, exact: false }
}

/**
 * The demo's three viewers (PLAN.md §16): analyst in German, a club fan in English, player focus in
 * Spanish. Club and player come from the segments the production team actually produced, so the
 * presets always land on an exact segment (away fan and the focus player of the demo match).
 */
export function presets(overlays: OverlaysBySegment, players: PlayerInfo[]): ViewerProfile[] {
  const keys = Object.keys(overlays)
  const fanClub: Team = keys.some((k) => k.startsWith('club_fan-away-')) || !keys.some((k) => k.startsWith('club_fan-home-')) ? 'away' : 'home'
  const focusKey = keys.find((k) => k.startsWith('player_focus-') && k.endsWith('-es')) ?? keys.find((k) => k.startsWith('player_focus-'))
  const focus = focusKey?.split('-')[1] ?? players.find((p) => p.position === 'CF')?.id ?? players[0]?.id
  return [
    { mode: 'analyst', language: 'de', favourite_club: null, favourite_players: [] },
    { mode: 'club_fan', language: 'en', favourite_club: fanClub, favourite_players: [] },
    { mode: 'player_focus', language: 'es', favourite_club: null, favourite_players: focus ? [focus] : [] },
  ]
}

type Dict = Record<string, string>
const BASE: Record<Lang, Dict> = {
  en: {
    analyst: 'Analyst', club_fan: 'Club fan', player_focus: 'Player focus', casual: 'Big moments',
    live: 'Live', replay: 'Sliding Doors', what_happened: 'What happened', alternative: 'Best alternative',
    goal_chance: 'goal chance', p_goal: 'chance to score', p_keep: 'chance to keep the ball', no_better: 'No better alternative found', turnover_risk: 'turnover risk', goal_against: 'goal-against chance',
    verified: 'Verified', tested: 'hypotheses tested', rejected: 'rejected', clear: 'Clearly', slight: 'Slightly',
    control: 'Control', chaos: 'Chaos', momentum: 'Momentum', possession: 'Possession', pass_acc: 'Pass accuracy',
    xg: 'xG', shots: 'Shots (on target)', pressure: 'Pressure on ball', top_speed: 'Top speed', passes: 'Passes', futures: 'simulated futures',
    in_control: 'in control', your_player: 'Your player', simulated: 'Replayed from this exact moment',
    right_call: 'Right call', better_existed: 'A better option existed', numbers_traced: 'numbers traced to rollouts', evidence: 'evidence ids',
    pts: 'pts',
  },
  de: {
    analyst: 'Analyst', club_fan: 'Fan', player_focus: 'Spielerfokus', casual: 'Highlights',
    live: 'Live', replay: 'Sliding Doors', what_happened: 'Was passiert ist', alternative: 'Beste Alternative',
    goal_chance: 'Torchance', p_goal: 'Torchance', p_keep: 'Chance auf Ballbesitz', no_better: 'Keine bessere Alternative', turnover_risk: 'Ballverlustrisiko', goal_against: 'Gegentorrisiko',
    verified: 'Verifiziert', tested: 'Hypothesen getestet', rejected: 'verworfen', clear: 'Deutlich', slight: 'Leicht',
    control: 'Kontrolle', chaos: 'Chaos', momentum: 'Momentum', possession: 'Ballbesitz', pass_acc: 'Passquote',
    xg: 'xG', shots: 'Schüsse (aufs Tor)', pressure: 'Druck auf Ball', top_speed: 'Topspeed', passes: 'Pässe', futures: 'simulierte Zukünfte',
    in_control: 'kontrolliert', your_player: 'Dein Spieler', simulated: 'Aus genau diesem Moment neu gespielt',
    right_call: 'Richtige Wahl', better_existed: 'Es gab die bessere Option', numbers_traced: 'Zahlen aus Simulationen belegt', evidence: 'Belege',
    pts: 'Pkt.',
  },
  es: {
    analyst: 'Analista', club_fan: 'Aficionado', player_focus: 'Jugador', casual: 'Grandes momentos',
    live: 'En directo', replay: 'Sliding Doors', what_happened: 'Lo que pasó', alternative: 'Mejor alternativa',
    goal_chance: 'prob. de gol', p_goal: 'prob. de marcar', p_keep: 'prob. de conservar el balón', no_better: 'Ninguna alternativa mejor', turnover_risk: 'riesgo de pérdida', goal_against: 'prob. de gol en contra',
    verified: 'Verificado', tested: 'hipótesis probadas', rejected: 'descartadas', clear: 'Claramente', slight: 'Ligeramente',
    control: 'Control', chaos: 'Caos', momentum: 'Dominio', possession: 'Posesión', pass_acc: 'Precisión de pase',
    xg: 'xG', shots: 'Tiros (a puerta)', pressure: 'Presión al balón', top_speed: 'Vel. máx.', passes: 'Pases', futures: 'futuros simulados',
    in_control: 'domina', your_player: 'Tu jugador', simulated: 'Rejugado desde este instante',
    right_call: 'Decisión correcta', better_existed: 'Había una opción mejor', numbers_traced: 'cifras trazadas a simulaciones', evidence: 'pruebas',
    pts: 'pts',
  },
}

const T: Record<Lang, Dict> = {
  en: { ...BASE.en, ...EXTRA.en, ...UX.en, ...ASK.en, ...V2.en },
  de: { ...BASE.de, ...EXTRA.de, ...UX.de, ...ASK.de, ...V2.de },
  es: { ...BASE.es, ...EXTRA.es, ...UX.es, ...ASK.es, ...V2.es },
}

const EVENTS: Record<Lang, Partial<Record<EventType, string>>> = {
  en: { kickoff: 'Kick-off', pass: 'Pass', shot: 'Shot', goal: 'Goal', tackle: 'Tackle', interception: 'Interception', pressure: 'Press', carry: 'Carry', set_piece: 'Set piece', out_of_play: 'Out' },
  de: { kickoff: 'Anstoß', pass: 'Pass', shot: 'Schuss', goal: 'Tor', tackle: 'Zweikampf', interception: 'Abgefangen', pressure: 'Pressing', carry: 'Dribbling', set_piece: 'Standard', out_of_play: 'Aus' },
  es: { kickoff: 'Saque inicial', pass: 'Pase', shot: 'Tiro', goal: 'Gol', tackle: 'Entrada', interception: 'Intercepción', pressure: 'Presión', carry: 'Conducción', set_piece: 'Balón parado', out_of_play: 'Fuera' },
}

/** Probability (0..1) as broadcast text: "12.5%" / "12,5 %". */
export function fmtPct(lang: Lang, p: number, digits = 1): string {
  const v = (p * 100).toFixed(digits)
  return lang === 'en' ? `${v}%` : `${v.replace('.', ',')} %`
}

/** Signed difference of two probabilities in percentage points: "+4.2 pts" / "−6,8 Pkt.". */
export function fmtPts(lang: Lang, d: number): string {
  const v = Math.abs(d * 100).toFixed(1)
  return `${d >= 0 ? '+' : '−'}${lang === 'en' ? v : v.replace('.', ',')} ${t(lang, 'pts')}`
}

export const t = (lang: Lang, key: string): string => T[lang]?.[key] ?? T.en[key] ?? key
export const eventLabel = (lang: Lang, type: EventType): string => EVENTS[lang]?.[type] ?? type
export const LANGS: Lang[] = ['en', 'de', 'es']

/** t() with `{key}` placeholders filled. */
export function tf(lang: Lang, key: string, vars: Record<string, string | number>): string {
  return t(lang, key).replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? ''))
}

/** Plain number in the viewer's locale: 0.57 / 0,57. */
export function fmtNum(lang: Lang, v: number, digits = 1): string {
  const s = v.toFixed(digits)
  return lang === 'en' ? s : s.replace('.', ',')
}

/** Last name for tight spaces ("Kai Nakamura" -> "Nakamura"). */
export const surname = (name: string): string => name.split(' ').slice(-1)[0]

export const MODES: ProfileMode[] = ['analyst', 'club_fan', 'player_focus', 'casual']

// ---------------------------------------------------------------- persistence + demo URLs

const KEY = 'sliding-doors.profile.v1'

function valid(p: Partial<ViewerProfile> | null, players: PlayerInfo[]): ViewerProfile | null {
  if (!p || !MODES.includes(p.mode as ProfileMode) || !LANGS.includes(p.language as Lang)) return null
  const club = p.favourite_club === 'home' || p.favourite_club === 'away' ? p.favourite_club : null
  const fav = (p.favourite_players ?? []).filter((id) => players.some((x) => x.id === id))
  if (p.mode === 'club_fan' && !club) return null
  if (p.mode === 'player_focus' && !fav.length) return null
  return {
    mode: p.mode as ProfileMode,
    language: p.language as Lang,
    favourite_club: p.mode === 'club_fan' ? club : null,
    favourite_players: p.mode === 'player_focus' ? fav.slice(0, 1) : [],
  }
}

/** Saved profile; localStorage may be unavailable (private window, blocked storage). */
export function loadProfile(players: PlayerInfo[]): ViewerProfile | null {
  try {
    const raw = window.localStorage.getItem(KEY)
    return raw ? valid(JSON.parse(raw) as Partial<ViewerProfile>, players) : null
  } catch {
    return null
  }
}

export function saveProfile(p: ViewerProfile | null): void {
  try {
    if (p) window.localStorage.setItem(KEY, JSON.stringify(p))
    else window.localStorage.removeItem(KEY)
  } catch {
    /* storage blocked: the profile lives for this page view only */
  }
}

/**
 * Demo recordings skip onboarding with a profile in the URL:
 *   ?profile=analyst|club_fan|player_focus|casual&club=home|away&player=A20&lang=en|de|es
 */
export function profileFromQuery(players: PlayerInfo[], search = window.location.search): ViewerProfile | null {
  const q = new URLSearchParams(search)
  const mode = q.get('profile') as ProfileMode | null
  if (!mode) return null
  const player = q.get('player') ?? players.find((p) => p.position === 'CF')?.id ?? players[0]?.id
  return valid({ mode, language: (q.get('lang') ?? 'en') as Lang, favourite_club: (q.get('club') ?? 'home') as Team, favourite_players: player ? [player] : [] }, players)
}
