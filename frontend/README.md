# Sliding Doors · web player

The broadcast front end: the TV picture (or a 2D tactical pitch) with timed, per-segment overlays,
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

Layout: **the TV picture is the main stage** (`match.video`), a slim sidebar on the right carries a few
mode-specific blocks, the match-story strip is at the bottom. Without a video (or when the browser
cannot decode it) the 2D tactical pitch is the stage. The pitch also appears during a Sliding Doors
break (ghost futures).

- **Onboarding always first**: opening the page asks "How would you describe yourself?" (four cards,
  then club or player, EN/DE/ES). The last answer (`localStorage` `sliding-doors.profile.v1`) is
  pre-selected ("Last time"), never auto-applied. Demo takes skip it with
  `?profile=analyst|club_fan|player_focus|casual&club=home|away&player=A20&lang=de`, `?view=split|control`
  or `?shot`; `?onboarding` forces it. The answer click unlocks audio and starts the match.
- **Top bar**: profile chip left ("Watching as …", click = switch mode / club / player / language or
  start over); right: Producer view, Ask Sliding Doors (only with a backend), commentary on/off.
- **Stage graphics on the video**: our scorebug sits on GRF's scoreboard (x210-602, y15-42 of the
  1280x720 render), our radar (drawn from tracking data; gold ring = followed player) on GRF's minimap
  (x535-745, y565-690). Nothing tints the picture. The video is slaved to the frame clock; while it
  buffers or seeks the clock waits (`pb.hold`), so picture, sidebar and ticker never drift apart.
- **Sidebar per mode** (`components/side/`; numbers only from the export, never totals that depend on
  match length since GRF plays 5 minutes on a 90' clock):
  - *Club fan*: mood meter + "we/us" line + **win probability** for us (line over the match; model
    estimate, `lib/models.ts winProbability`: Poisson goals in the remaining minutes from a prior of
    1.35 goals/90 per team, home x1.08 / away x0.92, blended with the xG rate so far up to 60 %);
    **live league table** with what's at stake (`public/league.json`, fictional 20-club league,
    standings before this match; only this match is live: "If it ends like this: 3rd ▲2", "Win → 3rd ·
    Draw → 5th · Loss → 6th", rivals tagged); our latest events. Stage: big GOAL! banner for our goals,
    opponent goals as a sober grey line, "So close!" for our big chances.
  - *Player focus*: **live rating 1–10** (`lib/models.ts`: 6 + 3.5·tanh(S/3), S = completed pass
    +0.05 + 0.10·difficulty/100, failed pass −0.12, shot +0.15 + 2·xG, goal +1.2, tackle won /
    interception +0.30, pressure won (ball won within 3 s) +0.15) vs his season average from
    `league.json` (`season_ratings`), the four parts, his **best action** (click = watch it); **his duel**
    vs the direct opponent (mirrored position): rating, pass accuracy, pass difficulty; **his decisions**
    replayed by Sliding Doors (✓ right call / ✗ better option, click = open it). Pitch fallback: camera
    follows him; video: gold ring in the radar.
  - *Analyst*: control vs chaos + tempo, pressing, xG flow, last pass difficulty; the production's stat
    card when on air; during a break every hypothesis tested; latest events.
  - *Casual*: the score, big; big moments so far (goals, big chances) with one line each (click =
    watch it). Stage: one short card per goal / big chance.
- **Sliding Doors = pause, then continue** (`components/DoorsBreak.tsx`, break logic in `App.tsx`):
  when the clock crosses the start of one of the viewer's Sliding Doors overlays the match pauses, the
  stage shows the pitch with the ghost futures and a compact card (verdict, one sentence, what
  happened vs best alternative with the metric, Continue ▶, Ask about this moment). It continues by
  itself after 8 s (or when the moment's commentator clip has finished, max 20 s; held while the Ask
  panel is open). Playing again by any means ends the break: there is never a frozen Sliding Doors view
  while the clock runs. Timeline click on a moment = jump there, same break, Continue plays from 4 s
  before the moment. Player focus shows the decision record, analyst the hypotheses in the sidebar.
- **Producer view · same moment, three viewers**: three columns (analyst DE, club fan EN, player focus
  ES), each stage + sidebar; the first column drives breaks and commentary. **Control room**: the agent
  log next to the stage.
- **Match story strip** (bottom, `MatchStory.tsx`): momentum chart (home control above the line, away
  below, chaos as the gold band, goals as gold lines) with the key moments as chips; hover = why it
  mattered, click = that moment's break.
- Transport: space play/pause, ←/→ ±5 s, `1`/`5`/`0` speed 1×/5×/10×, Esc closes a break.
- **Commentator** (`Commentator.tsx`, `lib/audio.ts`): optional `audio.json`
  `[{id, segment_id, start_ms, duration_ms, file: "audio/<name>.mp3", lang, text}]`. One shared audio
  element, unlocked by the first click (the onboarding answer); clips of the next 25 s are prefetched as
  blobs; a clip starts when the clock reaches `start_ms` (or up to 1.5 s later, e.g. after a seek),
  pauses and resumes with the match, plays only at 1×; during a break the moment's clip plays (matched by
  insight id, else by start time) and may finish after Continue. Caption on the stage (also when muted).
- Demo takes: `?f=1600&speed=1&play` starts at a frame, `?moment=<moment id>` opens that moment's break,
  `?cr=<insight id>` picks the control-room log, `?shot` skips enter animations and the countdown
  (screenshots, `scripts/shots.mjs`), `?syncdebug` prints data frame vs video frame.

## Ask Sliding Doors (live agents)

`components/AskPanel.tsx`, `lib/ask.ts`, strings in `lib/strings-ask.ts`. The gold **Ask Sliding Doors** button
(top bar, every view) pauses the match and opens a panel: the moment the question is about (`GET
/api/matches/{id}/ask?frame=N`), 2–3 suggested questions phrased in the viewer's language from that moment's
experiment menu, and a free-text field. `POST /api/matches/{id}/ask` streams NDJSON steps (Analyst → simulations →
Critic → number check), shown live; the verified answer is added as an insight and opens as a Sliding Doors replay
on every screen with the fan's question as headline (ghost futures, both probabilities, `verify.ts` audit as for
any insight). Questions nothing on the menu can test get a polite "can't test that" plus suggestions; disabled /
busy / rate-limited / timeout get a localised message. The button is hidden when no backend answers
`/api/features` (static demo); `?ask=<api origin>` points it at a backend, `?ask_open` opens the panel (demo takes).
Dev: `API_PROXY=http://localhost:8000 npm run dev` with the API started with `ASK_ENABLED=true`.

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

Shown during a break (see above): the pitch freezes on
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
- `insight.numbers.n_rollouts` (and `n_seeds`) so the "replayed N times" line is read, not assumed (500).
- `audio.json` segment ids must equal `ViewerProfile.segment_id` (`analyst-de`, `club_fan-away-en`, ...);
  clips for segments nobody watches are never played.
- The GRF render still shows the engine's player-name labels and its own "GOAL FOR …" banner across the
  top of the picture; disable both in the render (our graphics cover only the scoreboard and minimap).
- `public/league.json` assumes the two clubs of the match (`short` or `name`) are in the league; a match
  between other clubs hides the table and season averages (`season_ratings` is keyed by player name).
