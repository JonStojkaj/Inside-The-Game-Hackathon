import type { AudioClip, MatchBundle, ViewerProfile } from '../types'
import { askBase } from './ask'
import { segmentId } from './profile'

/**
 * Commentator lines for one viewer. Source of truth is the backend:
 *   GET {api}/api/matches/{id}/commentary?mode=&club=&player=&lang=
 *   -> {"lines": [{id, start_ms, duration_ms, text, kind, priority, audio_url}]}
 * (audio_url relative to the API origin, may be null: caption only). Without that endpoint (static
 * export, backend down) the recorded audio.json clips are used: the viewer's own segment, else the
 * closest neutral one in the same language, so every profile combination gets a commentator.
 */
export interface CommentaryLine {
  id: string
  start_ms: number
  duration_ms: number
  text: string
  kind: string
  priority: number
  /** Absolute URL, or null: caption only. */
  audio: string | null
}

interface ApiLine {
  id?: unknown
  start_ms?: unknown
  duration_ms?: unknown
  text?: unknown
  kind?: unknown
  priority?: unknown
  audio_url?: unknown
}

export function commentaryUrl(matchId: string, p: ViewerProfile, base = askBase()): string {
  const q = new URLSearchParams({ mode: p.mode, lang: p.language })
  if (p.mode === 'club_fan' && p.favourite_club) q.set('club', p.favourite_club)
  if (p.mode === 'player_focus' && p.favourite_players[0]) q.set('player', p.favourite_players[0])
  return `${base}/api/matches/${encodeURIComponent(matchId)}/commentary?${q}`
}

function resolveAudio(url: unknown, base: string): string | null {
  if (typeof url !== 'string' || !url) return null
  try {
    return new URL(url, base ? `${base}/` : window.location.origin + '/').href
  } catch {
    return null
  }
}

function fromApi(raw: unknown, base: string): CommentaryLine[] | null {
  const lines = (raw as { lines?: unknown })?.lines
  if (!Array.isArray(lines)) return null
  const out: CommentaryLine[] = []
  for (const l of lines as ApiLine[]) {
    const start = Number(l.start_ms)
    const text = typeof l.text === 'string' ? l.text.trim() : ''
    if (!Number.isFinite(start) || !text) continue
    out.push({
      id: String(l.id ?? `line-${start}`),
      start_ms: start,
      duration_ms: Math.max(1500, Number(l.duration_ms) || text.split(/\s+/).length * 380),
      text,
      kind: String(l.kind ?? ''),
      priority: Number(l.priority) || 0,
      audio: resolveAudio(l.audio_url, base),
    })
  }
  return out.sort((a, b) => a.start_ms - b.start_ms)
}

/** The recorded clips that fit this viewer best (exact segment first, then neutral ones in the same language). */
export function fallbackLines(bundle: MatchBundle, p: ViewerProfile): CommentaryLine[] {
  const clips = bundle.audio
  const seg = segmentId(p)
  const lang = p.language
  const bySeg = (s: string) => clips.filter((c) => c.segment_id === s || c.segment_id === '*')
  const candidates = [
    seg,
    // same mode and language (a club fan only gets clips of the same club: "we" must be us)
    ...(p.mode === 'club_fan' ? [] : [...new Set(clips.filter((c) => c.segment_id.startsWith(`${p.mode}-`) && c.segment_id.endsWith(`-${lang}`)).map((c) => c.segment_id))]),
    `analyst-${lang}`,
    `casual-${lang}`,
  ]
  let pick: AudioClip[] = []
  for (const s of candidates) {
    pick = bySeg(s).filter((c) => c.segment_id !== '*' || s === seg)
    if (pick.length) break
  }
  return pick
    .map((c) => ({
      id: c.id,
      start_ms: c.start_ms,
      duration_ms: c.duration_ms,
      text: c.text,
      kind: 'clip',
      priority: 0,
      audio: c.file ? `${bundle.baseUrl}/${c.file}` : null,
    }))
    .sort((a, b) => a.start_ms - b.start_ms)
}

const cache = new Map<string, Promise<CommentaryLine[] | null>>()

/** The backend's lines for this viewer, or null when the endpoint is not there. */
export function fetchCommentary(matchId: string, p: ViewerProfile): Promise<CommentaryLine[] | null> {
  const base = askBase()
  const url = commentaryUrl(matchId, p, base)
  let hit = cache.get(url)
  if (!hit) {
    hit = fetch(url, { headers: { Accept: 'application/json' } })
      .then((r) => (r.ok && (r.headers.get('content-type') ?? '').includes('json') ? r.json() : null))
      .then((j) => (j ? fromApi(j, base) : null))
      .catch(() => null)
    cache.set(url, hit)
  }
  return hit
}
