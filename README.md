# Sliding Doors

[![CI](https://github.com/JonStojkaj/Inside-The-Game-Hackathon/actions/workflows/ci.yml/badge.svg)](https://github.com/JonStojkaj/Inside-The-Game-Hackathon/actions/workflows/ci.yml)

**One match. Millions of fans. Every one of them gets their own broadcast — and every insight is proven, not guessed.**

Sliding Doors is an AI match-intelligence layer that runs alongside a live football match. It ingests match events,
turns them into football statistics, explains *why* key moments mattered, and renders timed, machine-readable
overlays that look genuinely different for an analyst, a club fan, a fan following one player, or a casual viewer —
in their language.

Its signature feature: at every key moment it **replays the match from that exact game state hundreds of times**
and compares the real decision with the alternatives. AI agents form hypotheses ("the assist was the best option",
"tighter marking would have prevented the goal") and *test* them in a simulator before anything reaches the screen.
Every number on screen comes from code, never from a language model. A live AI commentator talks the viewer
through the whole match in their mode's voice, and every viewer can search 500+ live statistics.

**Pitch in one line:** *agents propose, the simulation proves, rules decide* — and every fan gets that intelligence
as their own broadcast. Short pitch for the submission: [`docs/PITCH.md`](docs/PITCH.md); demo video script and checklist: [`docs/SUBMISSION.md`](docs/SUBMISSION.md).

> Built for the *Inside the Game* hackathon (Premier League × Microsoft), challenge *The Synthetic Match Insights
> Engine for Premier League Studio*. All data is synthetic; clubs and players are fictional.

**Live demo:** https://ca-web-ym7yowlldzrcg.happymoss-fe33e89e.swedencentral.azurecontainerapps.io/
(scales to zero — the first load can take ~15 s)

---

## What it does — the five stages of the brief

| Stage | In Sliding Doors |
|---|---|
| **a · Ingest** | A synthetic match (positions of all 22 players + ball, 10× per second) is streamed in match time; events are derived live — passes, shots, tackles, interceptions, pressure, carries, set pieces, goals — and published only once their outcome is knowable (no look-ahead). |
| **b · Interpret** | Stats engine: possession, pass accuracy, **pass difficulty** (distance, lane, receiver marking, pressure), threat gain, xG, **ball and shot speed**, player speed and sprints, **pressure index**, **control vs chaos**, **game rhythm**. |
| **c · Explain** | A deterministic moment detector picks goals, big chances, decisive passes and dangerous turnovers. The **explain team** (Analyst → Experimenter → Critic) runs counterfactual simulations and keeps only findings that are meaningful, stable across seeds and football-plausible. |
| **d · Render** | An overlay scheduler turns insights, stats, alerts and recaps into **timed, machine-readable overlays** (`start_ms`, `duration_ms`, slot, priority, payload, evidence) — the format a broadcast rendering partner consumes. Max two on screen, insights only in dead-ball windows, freshest key moment first. |
| **e · Personalise** | The **production team** (Producer → Narrator → Recap) works per *segment* (mode × club × player × language), not per viewer, so cost is independent of audience size. Four genuinely different experiences, chosen on first visit and switchable any time. |

### Every point of the brief, and where it is

| Brief | Sliding Doors | Where |
|---|---|---|
| (i) one pipeline, five stages | ingest → interpret → explain → render → personalise, all from a recorded synthetic match, live replay over WebSocket | `backend/app/{source,stats,agents,overlay,personalization}` |
| (ii) player identification | real-time **name tags** on the pitch (player-tag overlays, focus player always tagged), **speed indicators** when a player passes a threshold (top speed km/h, sprints) | `frontend/src/components/Pitch.tsx`, `Overlays.tsx` |
| (ii) pass quality | distance, accuracy, **difficulty rating** (lane, receiver marking, pressure) per pass and per player | `backend/app/stats/metrics.py` |
| (ii) speed metrics | **ball speed and shot speed**, player speed and distance | `backend/app/stats/metrics.py` |
| (ii) auto-eventing from video | not built — events come from tracking data (see *Honest limitations*) | — |
| (iii) narratives, player context, milestones, recaps | live commentator with momentum swings, goal build-ups, game state since a goal, quarter-hour summaries, **season milestones**; player rating vs season average; checked **full-time recap** | `backend/app/commentary/`, `backend/app/agents/production.py` |
| (iv) explainability: why moments matter | **Sliding Doors** counterfactuals at every key moment (what happened vs. what could have happened, proven in simulation) + **control vs chaos**, **pressure changes**, **game rhythm** | `backend/app/agents/`, `backend/app/rollout/`, `backend/app/stats/` |
| (v) data innovation | a new synthetic dataset: GRF matches with full tracking (22 players + ball, 10 Hz), derived event stream, rendered video, calibration set | `spikes/grf/`, `backend/app/source/` |
| (vi) multi-language | English, German, Spanish: UI, commentary text and voices, agent output | `backend/app/personalization/i18n.py`, `frontend/src/lib/strings.ts` |
| personalisation: modes, club, player, language, one metric | 4 modes, favourite club, favourite player (player focus), language, **★-pinned stats** a viewer cares about | `frontend/src/components/Onboarding.tsx`, `lib/statCatalog.ts` |
| timed, machine-readable overlays for a rendering partner | `overlays.json`: `start_ms`, `duration_ms`, slot, priority, payload, evidence | `backend/app/overlay/`, `GET /api/matches/{id}/overlays.json` |
| responsive enough for live play | events are published as soon as their outcome is knowable (no look-ahead); stats and commentary per frame; agents ~10–30 s per moment, which fits the replay window | *Measurements* |

### Four viewers, one moment

| Mode | What you see |
|---|---|
| **Analyst** | One stat board with a **search over 500+ live stats** (team vs team, each of the 22 players, the match; EN/DE/ES, ★ to pin), a **tactics layer** on the 2D pitch (lanes, half-spaces, thirds, zone 14; each team's lines with the back four drawn *intact* or *broken*), the full Sliding Doors card with every tested hypothesis. Dry, numbers-first commentator. |
| **Club fan** | League table and what is at stake, live win probability, fan mood, partisan commentator ("we", "us"), Sliding Doors for your team's key moments. |
| **Player focus** | Camera follows your player; live rating vs his season average, his duel, his decisions rated by Sliding Doors, and **all his numbers ranked among all 22 players**. |
| **Big moments** | **TV-style highlights**: playback cuts from moment to moment (*Highlights* / *Extended* / *Full match*), one line on why each moment mattered, full-time recap. |

Languages: English, German, Spanish.

## The live AI commentator

Continuous commentary (about 70 % of match time, never more than ~7 s of silence) in four characters, three
languages, with **Azure AI Speech Dragon HD voices** (one voice per mode: excitable home-end fan, TV voice, calm
analyst, player-cam). It does not just read events: a narrative layer
([`backend/app/commentary/narrative.py`](backend/app/commentary/narrative.py)) analyses the game as it goes —

- **momentum swings and pressure phases** ("The game has turned. Harbour City are on top now."),
- **the move behind every goal** ("Won by Nakamura, in the net 3 seconds later."),
- **the game state since a goal** ("Since going behind, Northbridge have had 75 % of the ball."),
- **a summary every quarter of an hour**, **season milestones** ("Strand's 2nd goal of the season") and the table,
- **why a key moment matters** (a ball lost 22 m from goal, a shot 3 s later) and the Sliding Doors verdict.

Templates per mode × language, numbers filled from code, timed to match time without ever spoiling an event
before it is knowable. No LLM tokens at match time; audio is pre-rendered for the demo segments and synthesized
on demand (cached) for every other viewer.

## How Sliding Doors works

```
key moment (e.g. 50', decisive pass)
   │
   ├─ Experiment menu (code): "had shot", "had passed to X", "had carried", "defender Y 5 m closer" …
   ├─ Analyst (LLM agent): may probe the simulator via tools, picks 1–3 hypotheses from the menu — it cannot invent physics
   ├─ Experimenter (code): 500 simulated futures × 3 seeds per hypothesis vs. what really happened
   ├─ Critic (LLM): accepts or rejects; hard rules overrule it
   │     · effect ≥ 1.5 points and larger than the seed noise
   │     · football prior (tighter marking may not help the attacker)
   │     · every number in the claim must be one we computed — otherwise a template is used
   └─ one retry with the rejected hypotheses as feedback
```

Goals are explained through the **assist** ("what made it possible"), solo goals from the defending side;
turnovers are judged on the chance to **keep the ball**, attacking moments on the chance to **score**.

## Agent architecture

The agents run on the **Microsoft Agent Framework** (`agent-framework-core` 1.23 + `agent-framework-openai`,
[`backend/app/agents/framework.py`](backend/app/agents/framework.py), [`workflow.py`](backend/app/agents/workflow.py)).

- **Framework agents.** Analyst, Critic, Producer, Narrator and Recap are each an `agent_framework.Agent` on an
  Azure OpenAI chat-completions client (deployment `fast` = gpt-5-mini, keyless via `DefaultAzureCredential`).
  Every agent answers with a pydantic schema as structured output (`AnalystPlan`, `CriticReview`, `NarratorDraft` …).
- **Function tools.** The Analyst gets two tools bound to the moment: `get_match_stats()` (score, shots, passes,
  pressure on the player on the ball, computed by code) and `run_experiment(experiment_id)` (runs one menu
  experiment in the rollout engine, 500 futures × 3 seeds). The tool refuses ids that are not on the remaining
  menu and stops after 4 experiments per round. In the demo match the Analyst made 38 `run_experiment` and
  11 `get_match_stats` calls across 9 moments.
- **Workflow.** The explain team is a framework `Workflow` with explicit hand-offs and a retry loop:

  ```
  analyst ──> experimenter ──> critic ──(nothing claimable, round left)──> analyst
     └──(menu used up)──> finalize <──(no hypothesis)──┘  └──(done)──> finalize ──> Insight
  ```

  `experimenter` and `finalize` are code executors. The production team (Producer → Narrator, Recap) runs the same
  framework agents per viewer segment.
- **Guards stay in code.** Both runtimes call the same step functions: menu restriction, `passes_rule` (effect ≥ 1.5
  points and above the seed noise) and `plausible` (football prior) overrule the Critic, `numbers_are_ours` +
  player-id check and a **roster-name check** (an invented first name rejects the draft) on every LLM text,
  template fallback for the claim and for Narrator/Recap texts.
- **Ask Sliding Doors (live).** A fan pauses and asks "What if Holt had shot?" in EN/DE/ES. The deployed API
  runs the same explain workflow on Azure for that moment (`POST /api/matches/{id}/ask`, streamed steps): the
  Analyst maps the question onto the experiment menu (or declines politely if nothing on it tests the question),
  1,500 simulations per experiment, Critic + rules, number check, then a translation that must keep every number.
  ~10–15 s end to end; one question at a time, rate-limited, feature flag `ASK_ENABLED`, keyless via the
  container's managed identity.
- **Visible to the viewer.** Every Sliding Doors break shows the chain that produced it — *Analyst agent: 3
  what-ifs proposed → Simulator: 6,000 futures played → Critic agent: 2 kept · 1 rejected → Rules: clear verdict* —
  and the full-time recap says whether the Recap agent wrote it (names and numbers checked against the data) or
  it was computed from the data because the agent's draft failed a check.
- **Offline and replayable.** `LLM_PROVIDER=fake` swaps in a deterministic fake chat client that still drives the
  framework's tool loop (tests and offline demos need no network). A chat middleware caches every model call
  (`LLM_CACHE=readwrite|replay|off`); on replay the tools simply run again as code. `AGENT_RUNTIME=sdk` selects
  the original hand-written loop on the plain OpenAI SDK. Both runtimes give identical insights on the fake model
  and share the single-turn cache entries.

## Architecture

```mermaid
flowchart LR
  GRF[Google Research Football<br/>synthetic match + video] --> SRC[Loader + event derivation]
  SRC --> BUS[Event bus · live replay]
  BUS --> STATS[Stats engine]
  STATS --> MOM[Moment detector]
  MOM --> EXP[Explain team<br/>Analyst · Experimenter · Critic]
  EXP <--> SIM[Rollout engine<br/>calibrated Monte-Carlo]
  EXP --> PROD[Production team<br/>Producer · Narrator · Recap]
  PROD --> SCHED[Overlay scheduler]
  SCHED --> API[FastAPI + WebSocket]
  API --> WEB[Web player<br/>React · TV view · 4 modes]
  EXP -. Azure OpenAI .-> AOAI[(gpt-5-mini<br/>Microsoft Foundry)]
  PROD -. Azure OpenAI .-> AOAI
```

### Microsoft / Azure technologies

| Technology | Role |
|---|---|
| **Microsoft Agent Framework** (Python) | Agents with function tools and structured outputs; explain team as a workflow with a Critic-gated retry loop |
| **Azure OpenAI in Microsoft Foundry** (gpt-5-mini) | All agents (Analyst, Critic, Producer, Narrator, Recap) with structured outputs; **keyless** access via Microsoft Entra ID (`DefaultAzureCredential` + RBAC role), no API keys anywhere |
| **Azure AI Speech** (Dragon HD neural voices) | The live commentator: one voice character per mode in EN/DE/ES, emotion from the text; key as a Container Apps secret |
| **Azure Container Apps** | Hosts the single container (API + web player + baked match data), scale 0–1 |
| **Azure Container Registry** | Image registry, pulled with a managed identity |
| **Application Insights + Log Analytics** | OpenTelemetry tracing of the API, ingestion capped at 1 GB/day |
| **Azure Developer CLI + Bicep** | Infrastructure as code, one-command deploy (`azd up`), see [`infra/README.md`](infra/README.md) |

Production path: the deployed app only *serves* pre-computed exports; agent runs happen in the pipeline and are
cached (`data/cache/llm/`), so the demo replays deterministically without model calls. Live mode is switchable.

## Measurements

| What | Result |
|---|---|
| Rollout engine | ~1,700 simulated futures per second (500 futures in ~0.3 s) |
| Calibration vs. GRF (150 real game states, 15 s horizon) | goals per possession **0.060 vs 0.060**, tackles/15 s 0.67 vs 0.70, passes/15 s 3.6 vs 3.1, turnovers 0.88 vs 0.77 |
| Decision sanity gate | inside 12 m, shooting beats dribbling at all 6 test spots (e.g. penalty spot 24 % vs 17 %) |
| Explain team | ~10–30 s per key moment with gpt-5-mini (Agent Framework workflow incl. tool calls), 9 key moments in the demo match |
| Unverified numbers on screen | 0 — the backend validates every claim, the web player re-audits every % against the rollouts |
| Video in the player | 30 fps 1080p (10 rendered fps, AI frame interpolation with RIFE), 0 dropped frames (the picture is the master clock, data follows it) |
| Commentator | ~70 % talk time, max ~7 s silence, all 4 modes × 3 languages, 1,041 pre-rendered lines |
| Tests | 142 backend tests (pytest), `ruff` + `mypy` clean; frontend `eslint` + `tsc` clean; GitHub Actions CI |

## Synthetic data

- **Google Research Football** is used purely as a physics-based football simulator (no reinforcement learning):
  bot-vs-bot matches yield the positions of all 22 players and the ball 10× per second.
- An own scenario balances the teams and runs in **deterministic mode**; the demo match is rendered to video and
  recorded **in the same pass**, so every video frame matches its data frame.
- GRF plays 5 minutes of football on a 90' broadcast clock. Comparisons therefore use shares, rates and speeds
  (work rate in m/min, not km); counts like passes are counts of those 5 minutes.
- **Season context** is synthetic too: a 20-club league table before this matchday, season ratings, appearances,
  goals and assists per player ([`frontend/public/league.json`](frontend/public/league.json)).

## Run it locally

```bash
# backend
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/python -m pytest
# API on :8000 (serves data/export/demo-109; set AZURE_SPEECH_KEY in .env for the commentator's voice)
cd backend && .venv/bin/uvicorn app.api.main:app --port 8000
# web player on :5173, talks to the API (or ?src=/mock/demo-109 for the bundled mock without a backend)
cd frontend && npm install && npm run dev
# full pipeline for a recorded match (offline with LLM_PROVIDER=fake, or azure with az login)
LLM_PROVIDER=azure backend/.venv/bin/python spikes/explain_demo.py spikes/grf/out/matches/demo-109 data/insights/demo-109.json
```

Recording new matches needs Docker (GRF, see [`CLAUDE.md`](CLAUDE.md)); deploying: [`infra/README.md`](infra/README.md).

## Honest limitations

- The rollout engine is a simple calibrated model, not a physics engine: it still over-predicts turnovers
  (~0.88 vs 0.77), so Sliding Doors only makes **comparative** claims ("clearly better than"), never exact forecasts.
- In production the simulator would be calibrated on real tracking data, and fans would pick their real
  Premier League club; the demo uses two fictional clubs because only synthetic data is allowed.
- GRF draws player names into its video that cannot be fully covered by our overlays. Its bots also play loosely:
  the back four holds its line only ~15 % of the time, which the tactics layer shows honestly.
- GRF has no stoppages: after a goal or a shot off the post it jumps to the restart within 0.1 s. The player
  plays the last 1.5 s before such restarts in slow motion, and Sliding Doors waits for the commentator's sentence.
  The GRF render is 1280×720 at 10 fps; the 30 fps picture is AI-interpolated (RIFE) and colour-graded.
- **No auto-eventing from video yet**: events come from the simulator's tracking data, not from a model over the
  video feed. That is the next step on the roadmap.
- The agents run on the Microsoft Agent Framework in our own container against Azure OpenAI in Foundry, not on the
  Foundry Agent Service.
- The demo Speech resource is on the free tier (20 syntheses/minute); pre-rendered audio covers the demo segments.
- The demo serves pre-computed (cached) agent output for reliability; the live agent path takes 10–20 s per moment,
  which fits a broadcast replay window but not an instant reaction. The Analyst's tool calls make a run slower
  than the plain loop (53 model calls for 9 moments instead of ~27).

## Repository

```
backend/    FastAPI, stats, rollout engine, agents, overlays (Python 3.12)
frontend/   web player (React + Vite + TypeScript)
infra/      azd + Bicep for Azure Container Apps
spikes/     GRF Docker image, recorder/renderer, pipeline scripts
data/       insights + LLM cache (match exports and videos are generated)
docs/       pitch, challenge + judging criteria, handoff, devil's-advocate review
```
