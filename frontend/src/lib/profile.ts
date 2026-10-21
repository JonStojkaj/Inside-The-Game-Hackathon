import type { EventType, Lang, OverlaysBySegment, ViewerProfile } from '../types'

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

export const PRESETS: ViewerProfile[] = [
  { mode: 'analyst', language: 'de', favourite_club: null, favourite_players: [] },
  { mode: 'club_fan', language: 'en', favourite_club: 'home', favourite_players: [] },
  { mode: 'player_focus', language: 'es', favourite_club: null, favourite_players: ['H10'] },
]

type Dict = Record<string, string>
const T: Record<Lang, Dict> = {
  en: {
    analyst: 'Analyst', club_fan: 'Club fan', player_focus: 'Player focus', casual: 'Casual',
    live: 'Live', replay: 'Sliding Doors', what_happened: 'What happened', alternative: 'Best alternative',
    goal_chance: 'goal chance', p_goal: 'chance to score', p_keep: 'chance to keep the ball', no_better: 'No better alternative found', turnover_risk: 'turnover risk', goal_against: 'goal-against chance',
    verified: 'Verified', tested: 'hypotheses tested', rejected: 'rejected', clear: 'Clearly', slight: 'Slightly',
    control: 'Control', chaos: 'Chaos', momentum: 'Momentum', possession: 'Possession', pass_acc: 'Pass accuracy',
    xg: 'xG', pressure: 'Pressure on ball', top_speed: 'Top speed', passes: 'Passes', futures: 'simulated futures',
    in_control: 'in control', your_player: 'Your player', simulated: 'Replayed from this exact moment',
  },
  de: {
    analyst: 'Analyst', club_fan: 'Fan', player_focus: 'Spielerfokus', casual: 'Gelegenheit',
    live: 'Live', replay: 'Sliding Doors', what_happened: 'Was passiert ist', alternative: 'Beste Alternative',
    goal_chance: 'Torchance', p_goal: 'Torchance', p_keep: 'Chance auf Ballbesitz', no_better: 'Keine bessere Alternative', turnover_risk: 'Ballverlustrisiko', goal_against: 'Gegentorrisiko',
    verified: 'Verifiziert', tested: 'Hypothesen getestet', rejected: 'verworfen', clear: 'Deutlich', slight: 'Leicht',
    control: 'Kontrolle', chaos: 'Chaos', momentum: 'Momentum', possession: 'Ballbesitz', pass_acc: 'Passquote',
    xg: 'xG', pressure: 'Druck auf Ball', top_speed: 'Topspeed', passes: 'Pässe', futures: 'simulierte Zukünfte',
    in_control: 'kontrolliert', your_player: 'Dein Spieler', simulated: 'Aus genau diesem Moment neu gespielt',
  },
  es: {
    analyst: 'Analista', club_fan: 'Aficionado', player_focus: 'Jugador', casual: 'Casual',
    live: 'En directo', replay: 'Sliding Doors', what_happened: 'Lo que pasó', alternative: 'Mejor alternativa',
    goal_chance: 'prob. de gol', p_goal: 'prob. de marcar', p_keep: 'prob. de conservar el balón', no_better: 'Ninguna alternativa mejor', turnover_risk: 'riesgo de pérdida', goal_against: 'prob. de gol en contra',
    verified: 'Verificado', tested: 'hipótesis probadas', rejected: 'descartadas', clear: 'Claramente', slight: 'Ligeramente',
    control: 'Control', chaos: 'Caos', momentum: 'Dominio', possession: 'Posesión', pass_acc: 'Precisión de pase',
    xg: 'xG', pressure: 'Presión al balón', top_speed: 'Vel. máx.', passes: 'Pases', futures: 'futuros simulados',
    in_control: 'domina', your_player: 'Tu jugador', simulated: 'Rejugado desde este instante',
  },
}

const EVENTS: Record<Lang, Partial<Record<EventType, string>>> = {
  en: { kickoff: 'Kick-off', pass: 'Pass', shot: 'Shot', goal: 'Goal', tackle: 'Tackle', interception: 'Interception', pressure: 'Press', carry: 'Carry', set_piece: 'Set piece', out_of_play: 'Out' },
  de: { kickoff: 'Anstoß', pass: 'Pass', shot: 'Schuss', goal: 'Tor', tackle: 'Zweikampf', interception: 'Abgefangen', pressure: 'Pressing', carry: 'Dribbling', set_piece: 'Standard', out_of_play: 'Aus' },
  es: { kickoff: 'Saque inicial', pass: 'Pase', shot: 'Tiro', goal: 'Gol', tackle: 'Entrada', interception: 'Intercepción', pressure: 'Presión', carry: 'Conducción', set_piece: 'Balón parado', out_of_play: 'Fuera' },
}

export const t = (lang: Lang, key: string): string => T[lang]?.[key] ?? T.en[key] ?? key
export const eventLabel = (lang: Lang, type: EventType): string => EVENTS[lang]?.[type] ?? type
export const LANGS: Lang[] = ['en', 'de', 'es']
