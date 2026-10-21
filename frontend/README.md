# Sliding Doors · web player

The broadcast front end: a 2D tactical pitch (or the TV picture) with timed, per-segment overlays,
three viewer profiles side by side, the Sliding Doors replay and the control room. React + Vite +
TypeScript, no UI framework; the pitch is a canvas, everything else is DOM + CSS animation.

```bash
npm install
npm run dev            # http://localhost:5173 (bundled mock match)
npm run build && npm run lint
node scripts/make-mock.mjs   # regenerate public/mock/demo/
```

## Data sources

The player reads the export format in `data/export/<match_id>/` (`match`, `frames`, `events`,
`moments`, `insights`, `stats`, `overlays` .json, optional `video.mp4`). Only `match.json` and
`frames.json` are required; everything else may be missing or empty.

| How | Example |
|---|---|
| Bundled mock (default) | `http://localhost:5173/` |
| Static export folder (dev server serves `../data/export` at `/export`, override with `EXPORT_DIR=...`) | `/?src=/export/full-34` |
| Backend API (`GET {api}/api/matches/{id}/{file}`) | `/?api=http://localhost:8000&match=full-34` |
| Env vars instead of query | `VITE_DATA_SOURCE=static\|api`, `VITE_DATA_BASE`, `VITE_API_BASE`, `VITE_MATCH_ID` |

Types in `src/types.ts` mirror `backend/app/models/__init__.py`.

## Views and controls

- **Broadcast**: one viewer. Profile picker (mode, club, player, language) resolves to the overlay
  segment exactly like `ViewerProfile.segment_id`, with a fallback to the same mode in another language.
- **3-up**: three profiles on one timeline (default: analyst DE, club fan NOR EN, player focus #10 ES),
  each a tall "second screen".
- **Control room**: the selected insight's hypotheses replayed as an agent log (detector → analyst →
  experimenter → critic → explain team → production per segment), counters for accepted / rejected /
  unverified claims shown.
- **TV**: enabled when `match.video` is set; the video is slaved to the frame clock and our scorebug
  and a bottom mask cover GRF's own HUD. The data stays the master clock.
- Transport: space play/pause, ←/→ ±5 s, `1`/`5`/`0` speed 1×/5×/10×, Esc closes a manual Sliding Doors.
  Diamonds on the timeline are moments (click = jump 4 s before); `SD1..n` opens an insight's
  Sliding Doors on every screen.
- Demo takes: `?view=split&f=480&speed=1&play` starts at a frame. `?tv` starts in TV mode.

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

## Sliding Doors

Shown when a `sliding_doors` overlay is active (or opened by hand): the pitch freezes on
`insight.decision_frame`, the camera zooms onto the futures, `ghost_paths` (white) and then
`alt_ghost_paths` (gold, `alt_label`) are drawn growing out of the decision point, and a card shows
the overlay's headline/body (localised) or `insight.claim`, plus the two probabilities from
`insight.numbers`: `actual_p_goal` vs `best_alt_p_goal`, or `actual_p_turnover` vs
`best_alt_p_turnover` when both goal values are 0.

## What the player needs from the backend

- `overlays.json` keyed by segment id (`analyst-de`, `club_fan-home-en`, `player_focus-H10-es`, `*`),
  using the payload keys above; Sliding Doors overlays during dead-ball windows, ~12–16 s.
- `insights.json` with `decision_frame`, ~30 `ghost_paths` + ~30 `alt_ghost_paths` of 10–15 points
  each (metres), `alt_label`, numbers as above, and `hypotheses` with baseline/counterfactual/spread.
- Optional `numbers.best_alt_p_turnover` for defensive (turnover) insights.
- `stats.json`: `teams.*.xg` would be nice for the club-fan widget (falls back to 0.00).
- `match.video` + `video.mp4` for the TV view.
