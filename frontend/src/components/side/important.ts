import type { MatchEvent } from '../../types'

/** Events worth a line in the sidebar's "Latest" block: goals, shots, ball wins, set pieces and hard passes. */
export function important(e: MatchEvent): boolean {
  if (e.type === 'goal' || e.type === 'interception' || e.type === 'set_piece') return true
  if (e.type === 'shot') return e.outcome !== 'goal' // the goal event has its own line
  if (e.type === 'tackle') return e.outcome === 'won'
  if (e.type === 'pass') return e.outcome === 'complete' && Number(e.meta.difficulty ?? 0) >= 60
  return false
}
