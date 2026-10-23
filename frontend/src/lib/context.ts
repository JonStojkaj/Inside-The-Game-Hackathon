import { createContext, useContext } from 'react'
import type { Insight, Moment, Overlay } from '../types'
import type { MatchIndex } from './match'
import type { Playback } from './playback'

/**
 * A Sliding Doors break: playback is paused, the stage shows the ghost futures and a compact card,
 * then the match continues (button or countdown). It never exists while the clock runs.
 */
export interface DoorsBreak {
  key: string
  /** Auto break: the primary viewer's sliding_doors overlay whose start the clock crossed. */
  overlay?: Overlay
  /** Manual break: timeline, control room or an Ask Sliding Doors answer. */
  insightId?: string
  /** Continue by itself after the countdown (not for Ask answers, which the viewer reads). */
  auto: boolean
  /** Where Continue plays from (timeline: a few seconds before the moment); default: where we are. */
  resumeFrame?: number
}

export interface MatchCtx {
  m: MatchIndex
  pb: Playback
  doorsBreak: DoorsBreak | null
  openDoors: (b: Omit<DoorsBreak, 'key'>) => void
  /** Close the break; `resume` plays on (from resumeFrame if set). */
  closeDoors: (resume: boolean) => void
  /** Timeline click: jump to the moment and open its Sliding Doors (or just play into it). */
  openMoment: (mo: Moment) => void
  /** Insight of a manual break (kept for the control room and Ask panel). */
  forcedInsight: string | null
  setForcedInsight: (id: string | null) => void
  /** Ask Sliding Doors: answers computed live are added as insights (m.insight finds them) with the fan's question. */
  addAsked: (insight: Insight, question: string) => void
  askedQuestion: (insightId: string | null) => string | undefined
}

export const MatchContext = createContext<MatchCtx | null>(null)

export function useMatch(): MatchCtx {
  const ctx = useContext(MatchContext)
  if (!ctx) throw new Error('useMatch outside MatchContext')
  return ctx
}
