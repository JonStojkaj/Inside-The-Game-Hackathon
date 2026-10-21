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

export const SHOTS = [
  { name: '0-onboarding', q: 'shot&onboarding&f=1580', wait: 2500 },
  { name: '1-split-live', q: 'shot&view=split&f=1580', wait: 3000 },
  { name: '2-split-sliding-doors', q: 'shot&view=split&f=1695', wait: 7000 },
  { name: '3-analyst-sliding-doors', q: `shot&${AN}&f=1695`, wait: 7000 },
  { name: '3b-fan-sliding-doors', q: `shot&${FAN}&f=1695`, wait: 7000 },
  { name: '3c-player-sliding-doors', q: `shot&${PF}&f=1695`, wait: 7000 },
  { name: '3d-casual-1695', q: `shot&${CAS}&f=1695`, wait: 7000 },
  { name: '4-control-room', q: 'shot&view=control&f=2131&cr=full-34-m01663-decisive_pass-insight', wait: 12000 },
  { name: '5-analyst-live', q: `shot&${AN}&f=1580`, wait: 3000 },
  { name: '5b-fan-goal', q: `shot&${FAN}&f=1415`, wait: 3000 },
  { name: '5c-player-live', q: `shot&${PF}&f=1580`, wait: 3000 },
  { name: '5d-casual-goal', q: `shot&${CAS}&f=1415`, wait: 3000 },
  { name: '6-fulltime-recap', q: 'shot&view=split&f=3090', wait: 4000 },
  // segments the production team did not produce: derived client-side in the viewer's language
  { name: '7-analyst-es-derived', q: 'shot&profile=analyst&lang=es&f=1695', wait: 7000 },
  { name: '7b-fan-home-de-derived', q: 'shot&profile=club_fan&club=home&lang=de&f=1490', wait: 7000 },
  { name: '7c-player-H20-de-recap', q: 'shot&profile=player_focus&player=H20&lang=de&f=3090', wait: 4000 },
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
