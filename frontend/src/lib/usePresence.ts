import { useEffect, useState } from 'react'

/**
 * Keeps the previous item mounted for `ms` after it disappears or is replaced, so CSS exit
 * animations can run. Returns the item to render and whether it is leaving.
 */
export function usePresence<T extends { id: string }>(item: T | undefined, ms = 420): { shown: T | undefined; leaving: boolean } {
  const [shown, setShown] = useState(item)
  const [leaving, setLeaving] = useState(false)

  useEffect(() => {
    if (item?.id === shown?.id) {
      if (item !== shown) setShown(item)
      return
    }
    if (!shown) {
      setShown(item)
      setLeaving(false)
      return
    }
    setLeaving(true)
    const t = setTimeout(() => {
      setShown(item)
      setLeaving(false)
    }, ms)
    return () => clearTimeout(t)
  }, [item, shown, ms])

  return { shown, leaving }
}
