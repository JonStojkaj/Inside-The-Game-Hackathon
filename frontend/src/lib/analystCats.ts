import { useState } from 'react'

/** Analyst dashboard categories, picked per session. */
export const CATS = ['control', 'pressing', 'passing', 'shooting', 'physical', 'players'] as const
export type Cat = (typeof CATS)[number]
const DEFAULT: Cat[] = ['control', 'pressing', 'passing', 'shooting']
const KEY = 'sliding-doors.analyst-cats.v1'

export function useAnalystCats(): [Cat[], (c: Cat) => void] {
  const [cats, setCats] = useState<Cat[]>(() => {
    try {
      const v = JSON.parse(sessionStorage.getItem(KEY) ?? 'null') as unknown
      if (Array.isArray(v)) return CATS.filter((c) => v.includes(c))
    } catch {
      // no storage
    }
    return DEFAULT
  })
  const toggle = (c: Cat) => {
    const next = cats.includes(c) ? cats.filter((x) => x !== c) : CATS.filter((x) => x === c || cats.includes(x))
    setCats(next)
    try {
      sessionStorage.setItem(KEY, JSON.stringify(next))
    } catch {
      // no storage
    }
  }
  return [cats, toggle]
}
