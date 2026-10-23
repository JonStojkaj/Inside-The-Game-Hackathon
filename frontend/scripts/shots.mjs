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

// single-viewer takes pin the profile in the URL (?profile=...), which skips onboarding;
// ?moment=<id> opens that moment's Sliding Doors break (the match pauses there)
const FAN = 'profile=club_fan&club=home&lang=en'
const PF = 'profile=player_focus&player=H20&lang=en'
const AN = 'profile=analyst&lang=en'
const CAS = 'profile=casual&lang=en'

// frames refer to demo-109 (goals f=407 home and f=1505 away); headless Chrome does not decode the
// TV video under virtual time, so these show the pitch fallback: check the video stage by hand
export const SHOTS = [
  { name: '0-onboarding', q: 'shot&onboarding&f=1200', wait: 2500 },
  { name: '1-fan-goal', q: `shot&${FAN}&f=415`, wait: 3000 },
  { name: '2-fan-key-moment', q: `shot&${FAN}&moment=demo-109-m00407-goal`, wait: 6000 },
  { name: '3-player', q: `shot&${PF}&f=1300`, wait: 3000 },
  { name: '3b-player-key-moment', q: `shot&${PF}&moment=demo-109-m01203-big_chance`, wait: 6000 },
  { name: '4-analyst', q: `shot&${AN}&f=1300`, wait: 3000 },
  { name: '4b-analyst-key-moment', q: `shot&${AN}&moment=demo-109-m01505-goal`, wait: 6000 },
  { name: '5-casual', q: `shot&${CAS}&f=1520`, wait: 3000 },
  { name: '8-fulltime-recap', q: `shot&${CAS}&f=2990`, wait: 4000 },
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
