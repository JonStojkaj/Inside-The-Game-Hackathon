import type {
  AudioClip,
  Frames,
  Insight,
  MatchBundle,
  MatchEvent,
  MatchInfo,
  Moment,
  Overlay,
  OverlaysBySegment,
  ProductionLog,
  StatsSnapshot,
} from '../types'

/**
 * Where the export comes from. Resolution order: URL query, then env vars, then the bundled mock.
 *
 *   ?src=/export/full-34          static folder (served by vite from ../data/export in dev)
 *   ?api=http://localhost:8000&match=full-34   backend API: GET {api}/api/matches/{id}/{file}
 *   VITE_DATA_SOURCE=static|api, VITE_DATA_BASE, VITE_API_BASE, VITE_MATCH_ID
 */
export interface SourceConfig {
  kind: 'static' | 'api'
  base: string // static: folder URL; api: API origin
  matchId: string
}

export function resolveSource(search = window.location.search): SourceConfig {
  const q = new URLSearchParams(search)
  const env = import.meta.env
  const matchId = q.get('match') ?? env.VITE_MATCH_ID ?? 'demo'
  if (q.has('api')) return { kind: 'api', base: q.get('api') || env.VITE_API_BASE || '', matchId }
  if (q.has('src')) return { kind: 'static', base: q.get('src')!, matchId }
  if (env.VITE_DATA_SOURCE === 'api') return { kind: 'api', base: env.VITE_API_BASE ?? '', matchId }
  return { kind: 'static', base: env.VITE_DATA_BASE ?? '/mock/demo-109', matchId }
}

function fileUrl(cfg: SourceConfig, file: string): string {
  const base = cfg.base.replace(/\/$/, '')
  return cfg.kind === 'api' ? `${base}/api/matches/${encodeURIComponent(cfg.matchId)}/${file}` : `${base}/${file}`
}

async function getJson<T>(cfg: SourceConfig, file: string, fallback?: T): Promise<T> {
  const res = await fetch(fileUrl(cfg, file))
  if (!res.ok) {
    if (fallback !== undefined) return fallback
    throw new Error(`${file}: HTTP ${res.status}`)
  }
  try {
    return (await res.json()) as T
  } catch (e) {
    // dev servers answer missing files with index.html: treat as absent when optional
    if (fallback !== undefined) return fallback
    throw e
  }
}

export async function loadMatch(cfg: SourceConfig = resolveSource()): Promise<MatchBundle> {
  // match + frames are required; everything the pipeline adds later is optional so the player
  // still works on a partial export.
  const [match, frames, events, moments, insights, stats, overlays, production, audio] = await Promise.all([
    getJson<MatchInfo>(cfg, 'match.json'),
    getJson<Frames>(cfg, 'frames.json'),
    getJson<MatchEvent[]>(cfg, 'events.json', []),
    getJson<Moment[]>(cfg, 'moments.json', []),
    getJson<Insight[]>(cfg, 'insights.json', []),
    getJson<StatsSnapshot[]>(cfg, 'stats.json', []),
    getJson<OverlaysBySegment | Overlay[]>(cfg, 'overlays.json', {}),
    getJson<ProductionLog | null>(cfg, 'production_log.json', null),
    getJson<AudioClip[]>(cfg, 'audio.json', []),
  ])
  events.sort((a, b) => a.t_ms - b.t_ms)
  return { match, frames, events, moments, insights, stats, overlays: bySegment(overlays), production, audio: Array.isArray(audio) ? audio : [], baseUrl: fileUrl(cfg, '').replace(/\/$/, '') }
}

/** overlays.json may be {segment: Overlay[]} or a flat list. */
function bySegment(o: OverlaysBySegment | Overlay[]): OverlaysBySegment {
  if (!Array.isArray(o)) return o
  const out: OverlaysBySegment = {}
  for (const x of o) (out[x.segment_id] ??= []).push(x)
  return out
}
