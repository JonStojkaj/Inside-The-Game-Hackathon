// 1920x1080 screenshots of the demo shots (PLAN.md §16) with headless Chrome, against a running
// dev server. Usage: node scripts/shots.mjs [baseUrl] [outDir] [onlyName]
//   CHROME=/path/to/chrome  (default: macOS Google Chrome)
// Each shot is a player URL (see README "Demo takes"); `wait` is virtual time in ms so the
// enter animations and ghost futures have finished.
import { execFileSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'

const BASE = process.argv[2] ?? 'http://localhost:5173'
const OUT = resolve(process.argv[3] ?? 'shots')
const ONLY = process.argv[4]
const CHROME = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

// single-viewer takes pin the profile in the URL (?profile=...), which skips onboarding
const AN = 'profile=analyst&lang=de'
const FAN = 'profile=club_fan&club=away&lang=en'
const PF = 'profile=player_focus&player=A20&lang=es'
const CAS = 'profile=casual&lang=en'

// frames refer to the default bundle demo-109 (goal events f=415 and f=1519; analyst Sliding Doors
// airs f=1549-1639, player focus f=1555-1645)
export const SHOTS = [
  { name: '0-onboarding', q: 'shot&onboarding&f=1200', wait: 2500 },
  { name: '1-analyst-strip-hint', q: `shot&${AN}&f=1200&hint`, wait: 3000 },
  { name: '2-analyst-sliding-doors', q: `shot&${AN}&f=1600`, wait: 7000 },
  { name: '3-fan-live', q: `shot&${FAN}&f=1200`, wait: 3000 },
  { name: '3b-fan-goal', q: `shot&${FAN}&f=1530`, wait: 3000 },
  { name: '4-player-live', q: `shot&${PF}&f=1200`, wait: 3000 },
  { name: '5-casual-live', q: `shot&${CAS}&f=1200`, wait: 3000 },
  { name: '6-producer-key-moment', q: 'shot&view=split&f=1600', wait: 7000 },
  { name: '7-control-room', q: 'shot&view=control&f=1600&cr=demo-109-m01505-goal-insight', wait: 12000 },
  { name: '8-fulltime-recap', q: 'shot&view=split&f=2990', wait: 4000 },
  // commentator caption; needs a bundle with audio.json (local stub: public/dev/audio-test, gitignored)
  { name: '9-commentator', src: process.env.AUDIO_SRC ?? '/dev/audio-test', q: 'shot&profile=analyst&lang=en&f=1195&play&speed=1', wait: 6000 },
]

mkdirSync(OUT, { recursive: true })
for (const s of SHOTS) {
  if (ONLY && s.name !== ONLY) continue
  const url = `${BASE}/?${s.src ? `src=${s.src}&` : ''}${s.q}`
  const file = join(OUT, `${s.name}.png`)
  execFileSync(CHROME, [
    '--headless=new',
    '--hide-scrollbars',
    '--mute-audio',
    '--autoplay-policy=no-user-gesture-required',
    `--user-data-dir=${join(tmpdir(), 'sd-shots-chrome')}`,
    '--window-size=1920,1080',
    `--virtual-time-budget=${s.wait}`, // no video decoding under virtual time: TV view is checked by hand
    `--screenshot=${file}`,
    url,
  ], { stdio: 'ignore' })
  console.log(`${s.name.padEnd(28)} ${url} -> ${file}`)
}
