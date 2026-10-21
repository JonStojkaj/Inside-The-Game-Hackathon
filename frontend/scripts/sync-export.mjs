// Copies a backend export (data/export/<id>/) into a static folder the player can load, optionally
// replacing insights / overlays / production log with newer pipeline output, and shrinks the JSON
// (coordinates rounded to cm, probabilities kept at 4 decimals). Read-only on the inputs.
//
//   node scripts/sync-export.mjs --export ../data/export/full-34 \
//     [--insights ../data/insights/full-34.json] [--overlays .../overlays.json] \
//     [--production-log .../production_log.json] [--video video.mp4] [--out public/mock/full-34]
//
// match.json `video` is set when a video is copied (and cleared when the export has none).
import { copyFileSync, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const args = Object.fromEntries(
  process.argv
    .slice(2)
    .reduce((acc, a, i, all) => (a.startsWith('--') ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
)
if (!args.export) {
  console.error('usage: sync-export.mjs --export <dir> [--insights f] [--overlays f] [--production-log f] [--video f] [--out dir]')
  process.exit(1)
}
const SRC = resolve(args.export)
const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const read = (f) => JSON.parse(readFileSync(f, 'utf8'))
const match = read(join(SRC, 'match.json'))
const OUT = resolve(args.out ?? join(ROOT, 'public', 'mock', match.match_id))
mkdirSync(OUT, { recursive: true })

// Numbers: positions get 2 decimals, everything else 4. Keys that are ids/clock stay as they are.
const round = (v, d) => (Number.isInteger(v) ? v : Math.round(v * 10 ** d) / 10 ** d)
function shrink(v, d = 4) {
  if (typeof v === 'number') return round(v, d)
  if (Array.isArray(v)) return v.map((x) => shrink(x, d))
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, shrink(x, k.endsWith('paths') || k.endsWith('_xy') ? 2 : d)]))
  return v
}

const sizes = {}
function write(name, data, digits = 4) {
  const s = JSON.stringify(shrink(data, digits))
  writeFileSync(join(OUT, name), s)
  sizes[name] = s.length
}

const optional = (name, override) => {
  const f = override ? resolve(override) : join(SRC, name)
  return existsSync(f) ? read(f) : undefined
}

let video = null
const videoSrc = args.video ? resolve(args.video) : join(SRC, 'video.mp4')
if (existsSync(videoSrc)) {
  copyFileSync(videoSrc, join(OUT, 'video.mp4'))
  sizes['video.mp4'] = statSync(videoSrc).size
  video = { file: 'video.mp4', fps: match.video?.fps ?? match.fps }
}
write('match.json', { ...match, video })

const frames = read(join(SRC, 'frames.json'))
write('frames.json', { ...frames, ball: shrink(frames.ball, 2), players: shrink(frames.players, 2) })

for (const [name, override] of [
  ['events.json'],
  ['moments.json'],
  ['stats.json'],
  ['insights.json', args.insights],
  ['overlays.json', args.overlays],
  ['production_log.json', args['production-log']],
]) {
  const data = optional(name, override)
  if (data !== undefined) write(name, data)
}

console.log(`${basename(SRC)} -> ${OUT}`)
for (const [k, v] of Object.entries(sizes)) console.log(`  ${k.padEnd(20)} ${(v / 1024).toFixed(1).padStart(8)} KB`)
