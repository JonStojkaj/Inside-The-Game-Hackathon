// Mirrors backend/app/models/__init__.py (pydantic) and the export format in data/export/<match_id>/.
// Coordinates are metres on a 105 x 68 pitch, origin bottom-left (y up); home attacks towards x = 105.

export type Team = 'home' | 'away'
export type XY = [number, number]

// --- match.json ---------------------------------------------------------------------------

export interface Club {
  key: Team
  name: string
  short: string
  color: string
}

export interface PlayerInfo {
  id: string
  team: Team
  name: string
  number: number
  position: string // GK, CB, LB, RB, DM, CM, LM, RM, AM, CF
}

export interface MatchInfo {
  match_id: string
  home: Club
  away: Club
  players: PlayerInfo[]
  fps: number
  n_frames: number
  duration_ms: number
  clock_scale: number // broadcast seconds per match second
  final_score: [number, number]
  video: null | { file: string; fps: number }
}

// --- frames.json (compact, index = frame) -----------------------------------------------

export interface Frames {
  t_ms: number[]
  ball: [number, number, number][]
  players: XY[][] // per frame, 22 positions in match.players order
  owner: number[] // player index or -1
  score: [number, number][]
  mode: string[]
}

// --- events.json --------------------------------------------------------------------------

export type EventType =
  | 'kickoff'
  | 'pass'
  | 'shot'
  | 'goal'
  | 'tackle'
  | 'interception'
  | 'pressure'
  | 'carry'
  | 'set_piece'
  | 'out_of_play'

export interface MatchEvent {
  id: string
  match_id: string
  t_ms: number
  frame: number
  type: EventType
  team: Team | null
  player_id: string | null
  target_id: string | null
  start_xy: XY | null
  end_xy: XY | null
  outcome: string | null
  meta: Record<string, unknown>
}

// --- moments.json / insights.json ---------------------------------------------------------

export type MomentKind = 'goal' | 'big_chance' | 'decisive_pass' | 'dangerous_turnover'

export interface Moment {
  id: string
  match_id: string
  frame: number
  t_ms: number
  clock_s: number
  kind: MomentKind
  score: number
  team: Team
  player_ids: string[]
  event_ids: string[]
  reason: string
}

export interface Intervention {
  kind: 'move_player' | 'swap_action' | 'remove_player'
  params: Record<string, unknown>
}

/** What a probability measures: chance to score, or chance to keep the ball (turnover moments). */
export type Metric = 'p_goal' | 'p_keep'

export interface Hypothesis {
  text: string
  metric?: Metric // values below are in this metric despite the field names
  intervention: Intervention | null
  baseline_p_goal: number | null
  counterfactual_p_goal: number | null
  seed_spread: number | null
  verdict: 'accepted' | 'rejected' | 'pending'
  critic_note: string
}

export interface Insight {
  id: string
  moment_id: string
  claim: string
  evidence: string[]
  // keys: actual_<metric>, best_alt_<metric>, delta_<metric> (best_alt missing = no better alternative)
  numbers: Record<string, number>
  verified: boolean
  confidence: 'clear' | 'slight'
  metric?: Metric
  hypotheses: Hypothesis[]
  decision_frame: number | null
  ghost_paths: XY[][]
  alt_ghost_paths: XY[][]
  alt_label: string
}

// --- stats.json ---------------------------------------------------------------------------

export interface TeamStats {
  team: string
  possession: number
  passes: number
  passes_completed: number
  pass_accuracy: number | null
  avg_pass_distance_m?: number | null
  shots: number
  shots_on_target: number
  goals: number
  max_shot_speed_kmh: number
  tackles?: number
  interceptions?: number
  pressures?: number
  xg?: number
}

export interface PlayerStats {
  id: string
  name: string
  team: string
  number: number
  position: string
  speed_kmh: number
  top_speed_kmh: number
  passes: number
  passes_completed: number
  shots: number
  goals: number
  tackles?: number
  interceptions?: number
  pressures?: number
}

export interface StatsSnapshot {
  match_id: string
  t_ms: number
  clock_s: number
  score: [number, number]
  teams: Record<Team, TeamStats>
  players: Record<string, PlayerStats>
  ball_speed_kmh: number
  pressure_on_ball: number
  pressing: Partial<Record<Team, number>>
  control: {
    chaos?: number
    control_team?: Team | null
    control_share?: number | null
    possession_changes_per_min?: number
  }
  rhythm: { actions_per_min?: number; change?: number; trend?: 'rising' | 'falling' | 'steady' }
}

// --- overlays.json ------------------------------------------------------------------------

export type ProfileMode = 'analyst' | 'club_fan' | 'player_focus' | 'casual'
export type OverlaySlot = 'scorebug' | 'lower_third' | 'side_panel' | 'pitch' | 'ticker' | 'fullscreen'
export type OverlayType =
  | 'event_card'
  | 'stat_card'
  | 'player_tag'
  | 'alert'
  | 'insight'
  | 'sliding_doors'
  | 'momentum'
  | 'recap'

export interface Overlay {
  id: string
  match_id?: string
  segment_id: string // "*" = every segment
  start_ms: number // match time
  duration_ms: number
  slot: OverlaySlot
  type: OverlayType
  priority: number // 0..100
  lang: string
  headline: string
  body: string
  payload: Record<string, unknown>
  evidence: string[]
}

export type OverlaysBySegment = Record<string, Overlay[]>

// --- viewer profile (mirrors ViewerProfile.segment_id) ------------------------------------

export type Lang = 'en' | 'de' | 'es'

export interface ViewerProfile {
  mode: ProfileMode
  language: Lang
  favourite_club: Team | null
  favourite_players: string[]
}

export interface ProductionStep {
  segment_id: string
  agent: string // producer | narrator | recap | scheduler
  moment_id: string | null
  decision: string
  detail: Record<string, unknown>
}

export interface ProductionLog {
  stats: Record<string, Record<string, number>>
  steps: ProductionStep[]
}

export interface MatchBundle {
  match: MatchInfo
  frames: Frames
  events: MatchEvent[]
  moments: Moment[]
  insights: Insight[]
  stats: StatsSnapshot[]
  overlays: OverlaysBySegment
  production: ProductionLog | null
  baseUrl: string // where match.video etc. are served from
}
