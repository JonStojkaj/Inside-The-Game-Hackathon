import { createContext, useContext } from 'react'
import type { MatchIndex } from './match'
import type { Playback } from './playback'

export interface MatchCtx {
  m: MatchIndex
  pb: Playback
  /** Insight opened by hand (timeline / control room); shown on every screen until closed. */
  forcedInsight: string | null
  setForcedInsight: (id: string | null) => void
}

export const MatchContext = createContext<MatchCtx | null>(null)

export function useMatch(): MatchCtx {
  const ctx = useContext(MatchContext)
  if (!ctx) throw new Error('useMatch outside MatchContext')
  return ctx
}
