
/**
 * Commentator audio plumbing. One shared <audio> element plays every clip: it is unlocked once by
 * the first user gesture (onboarding click), so later clips are never blocked by the browser's
 * autoplay policy (Safari unlocks per element). Clips are prefetched as blobs, so they start
 * instantly when the clock reaches them.
 */

let el: HTMLAudioElement | null = null
let unlocked = false
const blobs = new Map<string, string>()
const pending = new Set<string>()

export function audioEl(): HTMLAudioElement {
  if (!el) {
    el = new Audio()
    el.preload = 'auto'
    if (import.meta.env.DEV) (window as unknown as { __audio: HTMLAudioElement }).__audio = el
  }
  return el
}

/** 50 ms of silence as a WAV data URI (played inside the first gesture to unlock the element). */
function silentWav(): string {
  const n = 400
  const buf = new ArrayBuffer(44 + n)
  const v = new DataView(buf)
  const w = (o: number, s: string) => [...s].forEach((ch, i) => v.setUint8(o + i, ch.charCodeAt(0)))
  w(0, 'RIFF')
  v.setUint32(4, 36 + n, true)
  w(8, 'WAVE')
  w(12, 'fmt ')
  v.setUint32(16, 16, true)
  v.setUint16(20, 1, true) // PCM
  v.setUint16(22, 1, true) // mono
  v.setUint32(24, 8000, true)
  v.setUint32(28, 8000, true)
  v.setUint16(32, 1, true)
  v.setUint16(34, 8, true)
  w(36, 'data')
  v.setUint32(40, n, true)
  for (let i = 0; i < n; i++) v.setUint8(44 + i, 128)
  let s = ''
  new Uint8Array(buf).forEach((b) => (s += String.fromCharCode(b)))
  return `data:audio/wav;base64,${btoa(s)}`
}

/** Call from a user gesture (click / key). Idempotent. */
export function unlockAudio(): void {
  if (unlocked) return
  unlocked = true
  const a = audioEl()
  if (a.src && !a.src.startsWith('data:')) return
  a.src = silentWav()
  a.play().catch(() => {
    unlocked = false // try again on the next gesture
  })
}

export const audioUnlocked = (): boolean => unlocked

/** Prefetch a clip into a blob URL so it starts without a network round trip. */
export function preloadClip(url: string): void {
  if (blobs.has(url) || pending.has(url)) return
  pending.add(url)
  fetch(url)
    .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(String(r.status)))))
    .then((b) => blobs.set(url, URL.createObjectURL(b)))
    .catch(() => undefined)
    .finally(() => pending.delete(url))
}

export const clipSrc = (url: string): string => blobs.get(url) ?? url

/** Until when (performance.now) an audible clip is speaking; the Sliding Doors pause waits for it. */
export const speaking = { until: 0 }

/** The line being spoken right now (caption on the stage, also when muted). */
export interface Caption {
  id: string
  text: string
}
let current: Caption | null = null
const captionListeners = new Set<() => void>()
export const caption = {
  get: (): Caption | null => current,
  set(c: Caption | null) {
    if (c === current) return
    current = c
    captionListeners.forEach((fn) => fn())
  },
  subscribe(fn: () => void): () => void {
    captionListeners.add(fn)
    return () => captionListeners.delete(fn)
  },
}
