"""Live cues: every graphic-worthy thing that happens in the match, computed by code (no LLM).

A cue is segment-neutral ("A20 sprinted at 27.6 km/h"); app.overlay.cards decides per segment
whether and how to show it. Sources:

  events     goal, shot, turnover (tackle / interception), key pass, player tag
  frames     sprint alerts (speed threshold with cooldown)
  milestones first goal, first shot on target, fastest shot, top speed of the match
  periodic   momentum (control vs chaos), stat cards, "my metric" card, player card + heatmap

Only duration-independent numbers are used: GRF plays 5 minutes on a 90' clock, so totals such as
kilometres run or pass counts would be wrong by a factor of 18.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from app.models import PITCH_LENGTH, PITCH_WIDTH, FrameState, MatchEvent, Team
from app.personalization.segments import METRICS, TEAM_STATS, CueKind
from app.stats.engine import StatsEngine, StatsSnapshot
from app.stats.metrics import control_chaos

SPRINT_KMH = 30.0  # production threshold (PLAN.md §6)
GRF_SPRINT_KMH = 27.5  # GRF caps players at ~28 km/h; 27.5 is its 99th percentile, used for the demo
SPRINT_COOLDOWN_MS = 60_000  # per player
TOP_SPEED_MIN_MS = 60_000  # no "top speed of the match" record in the first minute of play
CONTROL_WINDOW_MS = 30_000  # momentum looks at the last 30 s of play (~9 broadcast minutes)
MOMENTUM_EVERY_MS = 10_000
METRIC_EVERY_MS = 15_000
STAT_EVERY_MS = 25_000
STAT_FIRST_MS = 20_000
KEY_PASS_DIFFICULTY = 45.0
DECISIVE_THREAT_GAIN = 0.04
DANGER_ZONE_M = 30.0
HEATMAP_BINS = (6, 4)  # x, y


@dataclass
class PlayerRef:
    id: str
    team: Team
    name: str
    number: int
    position: str


@dataclass
class MatchContext:
    """What the production layer needs to know about a match, independent of the data source."""

    match_id: str
    clubs: dict[str, str]  # team -> club name
    players: dict[str, PlayerRef]
    end_ms: int
    clock_of: Callable[[int], float]  # replay t_ms -> broadcast clock seconds
    final_score: tuple[int, int] = (0, 0)
    extras: dict[str, Any] = field(default_factory=dict)

    def name(self, player_id: str | None) -> str:
        return self.players[player_id].name if player_id in self.players else ""


def context_from_grf(match: Any) -> MatchContext:
    """Build a MatchContext from an app.source.grf.GrfMatch."""
    from app.source.grf import STEP_S

    players = {p.id: PlayerRef(p.id, p.team, p.name, p.number, p.position) for p in match.players}
    step_ms = int(STEP_S * 1000)
    last = match.n_frames - 1
    return MatchContext(
        match_id=match.match_id,
        clubs={"home": match.home.name, "away": match.away.name},
        players=players,
        end_ms=match.t_ms(last),
        clock_of=lambda t_ms: match.clock_s(min(t_ms // step_ms, last)),
        final_score=(int(match.score[-1, 0]), int(match.score[-1, 1])),
    )


class Cue(BaseModel):
    id: str
    kind: CueKind
    t_ms: int
    clock_s: float
    team: Team | None = None
    player_ids: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)


def _goal_distance(team: str, xy: Sequence[float]) -> float:
    """Distance from `team`'s own goal (home defends x = 0)."""
    goal_x = 0.0 if team == "home" else PITCH_LENGTH
    return math.hypot(xy[0] - goal_x, xy[1] - PITCH_WIDTH / 2)


def _other(team: str) -> Team:
    return "away" if team == "home" else "home"


# --- event cues ---------------------------------------------------------------------------------

def event_cues(events: list[MatchEvent], ctx: MatchContext) -> list[Cue]:
    out: list[Cue] = []
    first_goal = first_on_target = False
    fastest = 0.0
    for e in events:
        clock = float(e.meta.get("clock_s", ctx.clock_of(e.t_ms)))

        def add(suffix: str, kind: CueKind, players: list[str], data: dict[str, Any], evidence: list[str] | None = None,
                e: MatchEvent = e, clock: float = clock) -> None:
            out.append(Cue(id=f"{e.id}:{suffix}", kind=kind, t_ms=e.t_ms, clock_s=clock, team=e.team, player_ids=players,
                           data=data, evidence=evidence or [e.id]))

        if e.type == "goal" and e.team:
            shot_id = e.meta.get("shot_id")
            evidence = [e.id, *([shot_id] if shot_id else [])]
            add("card", "goal", [e.player_id or ""], {"score": list(e.meta.get("score", ctx.final_score))}, evidence)
            if e.player_id:
                add("tag", "player_tag", [e.player_id], {"reason": "goal"}, evidence)
            if not first_goal:
                first_goal = True
                add("ms", "milestone", [e.player_id or ""], {"milestone": "first_goal", "scope": "match"}, evidence)
        elif e.type == "shot" and e.team and e.player_id:
            speed = float(e.meta.get("shot_speed_kmh", 0.0))
            if e.outcome != "goal":  # a scored shot is announced by the goal card
                add("card", "shot", [e.player_id], {"outcome": e.outcome, "distance_m": e.meta.get("distance_m"),
                                                    "speed_kmh": speed, "xg": e.meta.get("xg", 0.0)})
            if e.outcome in ("goal", "saved") and not first_on_target:
                first_on_target = True
                add("ms-target", "milestone", [e.player_id], {"milestone": "first_on_target", "scope": "match"})
            if fastest and speed > fastest:
                add("ms-speed", "milestone", [e.player_id], {"milestone": "fastest_shot", "scope": "match", "speed_kmh": speed})
            fastest = max(fastest, speed)
        elif e.type in ("tackle", "interception") and e.team and e.player_id and e.target_id and e.start_xy:
            dist = _goal_distance(_other(e.team), e.start_xy)
            add("card", "turnover", [e.player_id, e.target_id],
                {"how": e.type, "distance_m": round(dist, 1), "danger": dist <= DANGER_ZONE_M})
        elif e.type == "pass" and e.outcome == "complete" and e.team and e.player_id and e.target_id:
            difficulty = float(e.meta.get("difficulty", 0.0))
            decisive = float(e.meta.get("threat_gain", 0.0)) >= DECISIVE_THREAT_GAIN
            if decisive or difficulty >= KEY_PASS_DIFFICULTY:
                add("card", "key_pass", [e.player_id, e.target_id],
                    {"distance_m": e.meta.get("distance_m"), "difficulty": difficulty, "decisive": decisive})
    return out


# --- frame + periodic cues ----------------------------------------------------------------------

def _windowed_control(events: list[MatchEvent], now_ms: int) -> dict[str, Any]:
    window = [e for e in events if now_ms - CONTROL_WINDOW_MS < e.t_ms <= now_ms]
    elapsed_s = min(CONTROL_WINDOW_MS, max(now_ms, 1)) / 1000
    return control_chaos(window, elapsed_s)


def _avg_difficulty(events: list[MatchEvent], team: str | None = None, player: str | None = None) -> float | None:
    vals = [float(e.meta["difficulty"]) for e in events if e.type == "pass" and e.outcome == "complete"
            and "difficulty" in e.meta and (team is None or e.team == team) and (player is None or e.player_id == player)]
    return round(float(np.mean(vals)), 1) if vals else None


def _team_stat(key: str, snap: StatsSnapshot, seen: list[MatchEvent]) -> dict[str, float] | None:
    values: dict[str, float | None] = {}
    for team in ("home", "away"):
        s = snap.teams[team]
        values[team] = {
            "possession": s.possession,
            "pass_accuracy": s.pass_accuracy,
            "avg_pass_distance": s.avg_pass_distance_m,
            "pass_difficulty": _avg_difficulty(seen, team=team),
            "pressing": snap.pressing.get(team),
            "max_shot_speed": s.max_shot_speed_kmh or None,
        }[key]
    if any(v is None for v in values.values()):
        return None
    return {k: float(v) for k, v in values.items() if v is not None}


def periodic_cues(frames: Sequence[FrameState], events: list[MatchEvent], ctx: MatchContext,
                  focus_players: Sequence[str] = (), sprint_kmh: float = GRF_SPRINT_KMH) -> list[Cue]:
    stats = StatsEngine(ctx.match_id)
    out: list[Cue] = []
    seen: list[MatchEvent] = []
    pending = sorted(events, key=lambda e: e.t_ms)
    ei = 0
    next_mom, next_metric, next_stat, stat_tick = 0, METRIC_EVERY_MS, STAT_FIRST_MS, 0
    last_sprint: dict[str, int] = {}
    in_sprint: dict[str, bool] = {}
    top_speed = 0.0
    last_record_ms = -SPRINT_COOLDOWN_MS
    heat = {p: np.zeros(HEATMAP_BINS) for p in focus_players}

    for f in frames:
        while ei < len(pending) and pending[ei].t_ms <= f.t_ms:
            stats.on_event(pending[ei])
            seen.append(pending[ei])
            ei += 1
        clock = ctx.clock_of(f.t_ms)
        stats.on_frame(f, clock_s=clock)
        # sprints + top speed record
        for p in f.players:
            speed = math.hypot(p.vx, p.vy) * 3.6
            fast = speed >= sprint_kmh
            if fast and not in_sprint.get(p.id) and f.t_ms - last_sprint.get(p.id, -SPRINT_COOLDOWN_MS) >= SPRINT_COOLDOWN_MS:
                last_sprint[p.id] = f.t_ms
                out.append(Cue(id=f"sprint:{p.id}:{f.t_ms}", kind="sprint", t_ms=f.t_ms, clock_s=clock, team=p.team,
                               player_ids=[p.id], data={"speed_kmh": round(speed, 1), "threshold_kmh": sprint_kmh},
                               evidence=[f"frame:{f.frame}"]))
            in_sprint[p.id] = fast
            if speed > top_speed + 0.3 and f.t_ms >= TOP_SPEED_MIN_MS and speed >= sprint_kmh \
                    and f.t_ms - last_record_ms >= SPRINT_COOLDOWN_MS:
                last_record_ms = f.t_ms
                out.append(Cue(id=f"ms-top:{p.id}:{f.t_ms}", kind="milestone", t_ms=f.t_ms, clock_s=clock, team=p.team,
                               player_ids=[p.id], data={"milestone": "top_speed", "scope": "match", "speed_kmh": round(speed, 1)},
                               evidence=[f"frame:{f.frame}"]))
            top_speed = max(top_speed, speed)
            if p.id in heat:
                bx = min(int(p.x / PITCH_LENGTH * HEATMAP_BINS[0]), HEATMAP_BINS[0] - 1)
                by = min(int(p.y / PITCH_WIDTH * HEATMAP_BINS[1]), HEATMAP_BINS[1] - 1)
                heat[p.id][max(bx, 0), max(by, 0)] += 1

        if f.t_ms >= next_mom:
            next_mom += MOMENTUM_EVERY_MS
            cc = _windowed_control(seen, f.t_ms)
            snap = stats.snapshot()
            out.append(Cue(id=f"momentum:{f.t_ms}", kind="momentum", t_ms=f.t_ms, clock_s=clock,
                           team=cc.get("control_team"),  # type: ignore[arg-type]
                           data={**cc, "score": list(f.score), "pressing": snap.pressing,
                                 "possession": {t: snap.teams[t].possession for t in ("home", "away")}},
                           evidence=[f"stats:control_chaos@{f.t_ms}"]))
        if f.t_ms >= next_metric:
            next_metric += METRIC_EVERY_MS
            snap = stats.snapshot()
            out.extend(_metric_cues(snap, seen, f, clock))
            for pid in focus_players:
                out.append(_player_card(snap, seen, pid, heat[pid], f, clock))
        if f.t_ms >= next_stat:
            next_stat += STAT_EVERY_MS
            snap = stats.snapshot()
            for key in TEAM_STATS:
                values = _team_stat(key, snap, seen)
                if values is not None:
                    out.append(Cue(id=f"stat:{key}:{f.t_ms}", kind="stat", t_ms=f.t_ms, clock_s=clock,
                                   data={"key": key, "values": values, "tick": stat_tick},
                                   evidence=[f"stats:{key}@{f.t_ms}"]))
            stat_tick += 1
    return out


def _metric_cues(snap: StatsSnapshot, seen: list[MatchEvent], f: FrameState, clock: float) -> list[Cue]:
    out = []
    top = max(snap.players.values(), key=lambda p: p.top_speed_kmh, default=None)
    for metric in METRICS:
        values: dict[str, Any]
        if metric == "top_speed":
            if top is None:
                continue
            values = {"value": round(top.top_speed_kmh, 1), "player_id": top.id}
        elif metric == "chaos":
            values = {"value": snap.control.get("chaos")}
        else:
            key = "pressing" if metric == "pressure_index" else metric
            team_values = _team_stat(key, snap, seen)
            if team_values is None:
                continue
            values = dict(team_values)
        out.append(Cue(id=f"metric:{metric}:{f.t_ms}", kind="metric_card", t_ms=f.t_ms, clock_s=clock,
                       data={"metric": metric, "values": values}, evidence=[f"stats:{metric}@{f.t_ms}"]))
    return out


def _player_card(snap: StatsSnapshot, seen: list[MatchEvent], pid: str, heat: np.ndarray, f: FrameState, clock: float) -> Cue:
    ps = snap.players[pid]
    total = heat.sum() or 1.0
    return Cue(
        id=f"card:{pid}:{f.t_ms}", kind="player_card", t_ms=f.t_ms, clock_s=clock, team=ps.team,  # type: ignore[arg-type]
        player_ids=[pid],
        data={"top_speed_kmh": round(ps.top_speed_kmh, 1), "speed_kmh": round(ps.speed_kmh, 1),
              "pass_accuracy": round(ps.pass_accuracy, 3) if ps.pass_accuracy is not None else None,
              "avg_pass_difficulty": _avg_difficulty(seen, player=pid),
              "heatmap": (heat / total).round(3).tolist(), "heatmap_bins": list(HEATMAP_BINS)},
        evidence=[f"stats:player:{pid}@{f.t_ms}"],
    )


def build_cues(frames: Sequence[FrameState], events: list[MatchEvent], ctx: MatchContext,
               focus_players: Sequence[str] = (), sprint_kmh: float = GRF_SPRINT_KMH) -> list[Cue]:
    cues = event_cues(events, ctx) + periodic_cues(frames, events, ctx, focus_players, sprint_kmh)
    return sorted(cues, key=lambda c: (c.t_ms, c.id))
