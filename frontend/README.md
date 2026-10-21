# Sliding Doors · web player

The broadcast front end: a 2D tactical pitch (or the TV picture) with timed, per-segment overlays,
three viewer profiles side by side, the Sliding Doors replay and the control room. React + Vite +
TypeScript, no UI framework; the pitch is a canvas, everything else is DOM + CSS animation.

```bash
npm install
npm run dev            # http://localhost:5173 (real demo match full-34, public/mock/full-34)
npm run build && npm run lint && npx tsc -b
node scripts/make-mock.mjs   # regenerate the small hand-scripted mock in public/mock/demo/ (?src=/mock/demo)
node scripts/sync-export.mjs --export ../data/export/full-34 [--insights f] [--overlays f] \
  [--production-log f] [--video f] [--out public/mock/full-34]   # refresh the bundled real match
node scripts/shots.mjs http://localhost:5173 shots   # 1920x1080 PNGs of the demo shots (headless Chrome)
```

`public/mock/full-34/` is the real GRF export with the Azure explain-team insights
(`data/insights/full-34.json`). Its overlays come from a `LLM_PROVIDER=fake` production pass over those
insights (plus a `club_fan-away-en` segment for the 3-up shot), so every number on screen matches the
insights; replace them with the Azure production run once it is re-done on the current insights.

## Data sources

The player reads the export format in `data/export/<match_id>/` (`match`, `frames`, `events`,
`moments`, `insights`, `stats`, `overlays` .json, optional `video.mp4`). Only `match.json` and
`frames.json` are required; everything else may be missing or empty.

| How | Example |
|---|---|
| Bundled real match (default) | `http://localhost:5173/` |
| Bundled hand-made mock | `/?src=/mock/demo` |
| Static export folder (dev server serves `../data/export` at `/export`, override with `EXPORT_DIR=...`) | `/?src=/export/full-34` |
| Backend API (`GET {api}/api/matches/{id}/{file}`) | `/?api=http://localhost:8000&match=full-34` |
| Env vars instead of query | `VITE_DATA_SOURCE=static\|api`, `VITE_DATA_BASE`, `VITE_API_BASE`, `VITE_MATCH_ID` |

Types in `src/types.ts` mirror `backend/app/models/__init__.py`.

## Views and controls

- **Onboarding** (first visit): "How would you describe yourself?" with four cards (analyst, club fan
  → pick a club, player focus → pick a player from `match.json`, casual) plus EN/DE/ES. The choice is
  saved in `localStorage` (`sliding-doors.profile.v1`; works without storage too). Demo takes skip it
  with `?profile=analyst|club_fan|player_focus|casual&club=home|away&player=A20&lang=de`; `?onboarding`
  forces it; `?shot` and `view=split|control` skip it.
- **My broadcast** (default): one viewer. The top bar always shows the profile ("Watching as …");
  clicking it switches mode / club / player / language at any time, or starts over.
- **The four views** (same match, same moment, different on first glance; `src/lib/derive.ts`):
  - *Analyst*: data HUD (control vs chaos, pressing both teams, rhythm with trend sparkline, last pass
    with difficulty, last shot with xG), the segment's metric cards, full Sliding Doors card plus
    every hypothesis tested (real → counterfactual, confirmed / refuted / rejected).
  - *Club fan*: stage themed in the club colour, partisan card ("We lead 2–1", "We're on top", us-vs-them
    momentum bar, no numbers otherwise), full-screen GOAL! banner for our goals, "So close!" for our big
    chances, opponent goals as a sober strip; ticker and alerts only for our team; Sliding Doors only
    for our players' decisions, as a club-coloured one-liner.
  - *Player focus*: player cam (camera follows him), live card (speed, top speed, pass accuracy, average
    pass difficulty, decisions right / analysed, heatmap from the tracking data), alerts for his goals,
    shots (xG), ball wins, key / hard passes and sprints; Sliding Doors only for his decisions, with a
    decision record ("Best of N options": his action vs the swap_action rollouts, noise rejected by the
    critic shown greyed) instead of the two probability boxes.
  - *Casual*: centred scorebug, no gauges, no ticker; only goals and big chances as short cards with one
    line on why they mattered (score before/after: opens the scoring, takes the lead, level again…;
    big chance: "would have made it 1–1"), Sliding Doors one-liners for goals / big chances, full-time recap.
  Produced overlays are used when the production team made exactly the viewer's segment; otherwise the
  overlays (goal cards, Sliding Doors text, recap) are templated in the viewer's language from insights,
  moments and stats (numbers only from the data, so the claim audit applies unchanged). Totals that
  depend on match length (pass/shot counts, distance) are not shown: GRF plays 5 minutes on a 90' clock.
- **Producer view · same moment, three viewers** (top bar): the 3-up (analyst DE, club fan HCY EN,
  player focus #20 ES), each a tall "second screen", and the control room tab.
- **Control room**: the selected insight's hypotheses replayed as an agent log (detector → analyst →
  experimenter → critic → explain team → production per segment), counters for accepted / rejected /
  unverified claims shown.
- **TV**: enabled when `match.video` is set; the video is slaved to the frame clock (paused: video
  frame N for data frame N; playing: drift absorbed with the playback rate, hard seek beyond 0.25 s).
  Our scorebug lands on GRF's scoreboard and our radar (drawn from the tracking data) on GRF's minimap.
  During Sliding Doors the picture cross-fades to the pitch. Without video, or if the browser cannot
  decode it (needs H.264, yuv420p), the pitch is shown. Test bundle: `public/dev/` (gitignored), built
  with `sync-export.mjs` from a GRF render; `?syncdebug` prints data frame vs video frame.
- Transport: space play/pause, ←/→ ±5 s, `1`/`5`/`0` speed 1×/5×/10×, Esc closes a manual Sliding Doors.
  Diamonds on the timeline are moments (click = jump 4 s before); `SD1..n` opens an insight's
  Sliding Doors on every screen.
- Demo takes: `?view=split&f=1695&speed=1&play` starts at a frame (`scripts/shots.mjs` lists all takes,
  including each single-viewer mode at f=1695). `?tv` starts in TV mode,
  `?cr=<insight id>` picks the control-room log, `?shot` skips enter animations (screenshots).
  §16 shots on full-34: 3-up live `f=1580`, 3-up Sliding Doors (all three screens) `f=1695`,
  broadcast Sliding Doors `f=2129`, control room `view=control&f=2131&cr=full-34-m01663-decisive_pass-insight`,
  full-time recap `f=3090`.

## Overlay rendering

At match time `t`, overlays of the segment plus `"*"` with `start_ms <= t < start_ms + duration_ms`
are active; per slot the highest `priority` wins (ties: the later one). A `fullscreen` overlay hides
the lower third; a Sliding Doors moment hides lower third, side panel and persistent widgets.

| Slot | Rendered as | Payload keys used |
|---|---|---|
| `scorebug` | strip under the scorebug | `home_share` (type `momentum`: bar) |
| `lower_third` | name-strap, accent = team colour (alerts gold) | `team`, `player_id` (shirt number in the accent) |
| `side_panel` | card top-right | `rows: [{label, home, away}]` or `[{label, value}]`, `player_id`, `insight_id` (adds confidence + "verified") |
| `pitch` | `player_tag`: label above the player on the canvas; `sliding_doors`: the replay | `player_id`; `insight_id`, `simple` (hide hypothesis count) |
| `ticker` | takes over the bottom ticker | – |
| `fullscreen` | big centred card (goal) | `team`, `bullets: string[]` (recap) |

`evidence` is printed small on lower thirds and side panels.

## Claim audit (what "verified" means on screen)

`src/lib/verify.ts` does not trust `Insight.verified`. For every on-screen text that cites an insight
(Sliding Doors card, insight side panels, narrator output in the control room) it checks that each
probability (`12.5%`, `12,5 %`) and point delta (`8.3 points`, `−8,3 Punkte`) is a number the rollout
engine produced for that moment (insight numbers, hypothesis baseline/counterfactual, or a difference
of two, up to display rounding), and that every evidence id resolves (event id, rollout id of the same
moment, `stats:`/`frame:` reference). The control room's "unverified claims shown" counter is the
number of on-screen texts failing that check. Accepted hypotheses whose measured effect goes against
the Analyst's prediction (`expected_direction`, or read from the hypothesis text) are shown as
**refuted**, not as confirmed.

## Sliding Doors

Shown when a `sliding_doors` overlay is active (or opened by hand): the pitch freezes on
`insight.decision_frame`, the camera zooms onto the futures, `ghost_paths` (white) and then
`alt_ghost_paths` (gold, `alt_label`) are drawn growing out of the decision point, and a card shows
the overlay's headline/body (localised) or `insight.claim`, plus the two probabilities from
`numbers` for `insight.metric`: `actual_<metric>` vs `best_alt_<metric>`, labelled "chance to score"
(`p_goal`) or "chance to keep the ball" (`p_keep`), with the delta in points. No `best_alt_*` means
"no better alternative found". `pitch`/`insight` overlays (club fan, casual) get the one-line version
of the same replay. Ghost paths are cut at the first restart teleport.

## What the player needs from the backend

- Re-run the Azure production team on the current `data/insights/full-34.json` (the committed Azure
  overlays predate `metric` and use `actual_p_turnover`), and add a `club_fan-away-en` segment to
  `DEMO_PROFILES` for the 3-up shot (analyst-de, club_fan-away-en, player_focus-A20-es).
- `match.video`: H.264 / yuv420p mp4 with `+faststart`, exactly one frame per data frame (10 fps);
  GRF renders MPEG-4 Part 2, which Chrome cannot play. Disable GRF's player-name labels in the render
  (they cannot be covered, they move); scoreboard and minimap are covered by us.
- `alt_label` localised per segment (it is English in every language today).
- `expected_direction` on `AnalystHypothesis` (the player falls back to reading the text).
- Scheduler: the 50' insight airs at 63:50 for analyst-de (13 match minutes late); at f=1695 both
  analyst segments air the 45' turnover instead, so the producer-view shot shows two different moments
  (analyst 45', fan and player 50').
- player_focus-A20-es gets `player_tag` overlays for H20 (Marchetti) instead of A20 (Nakamura).
- Ghost paths continue through restarts (shot, then ball teleported to the centre spot).
- `stats.json`: `teams.*.xg` for the club-fan widget (falls back to shots on target).
