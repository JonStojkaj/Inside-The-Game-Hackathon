"""M4 stats engine (stage b): live statistics from frames and events.

Consumes only FrameState and MatchEvent, so it works with any data source
(GRF recordings today, an official tracking + event feed in production).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from app.models import FrameState, MatchEvent
from app.stats.metrics import control_chaos, pressure_index, rhythm

MAX_STEP_M = 1.5  # displacement per frame above this is a reset jump, not running
ON_TARGET = {"goal", "saved"}
# rolling window for control/chaos, rhythm and pressing, in PHYSICAL match time: GRF plays a 90' clock
# in 5 minutes (x18), so 40 s of play is about 12 broadcast minutes. (300 s was the whole GRF match.)
WINDOW_S = 40.0


class PlayerStats(BaseModel):
    id: str
    name: str
    team: str
    number: int
    position: str
    distance_m: float = 0.0
    speed_kmh: float = 0.0
    top_speed_kmh: float = 0.0
    passes: int = 0
    passes_completed: int = 0
    shots: int = 0
    goals: int = 0
    tackles: int = 0
    interceptions: int = 0
    pressures: int = 0

    @property
    def pass_accuracy(self) -> float | None:
        return self.passes_completed / self.passes if self.passes else None


class TeamStats(BaseModel):
    team: str
    possession: float = 0.5
    passes: int = 0
    passes_completed: int = 0
    pass_accuracy: float | None = None
    avg_pass_distance_m: float | None = None
    shots: int = 0
    shots_on_target: int = 0
    goals: int = 0
    max_shot_speed_kmh: float = 0.0
    tackles: int = 0
    interceptions: int = 0
    pressures: int = 0
    distance_km: float = 0.0


class StatsSnapshot(BaseModel):
    match_id: str
    t_ms: int
    clock_s: float
    score: tuple[int, int]
    teams: dict[str, TeamStats]
    players: dict[str, PlayerStats]
    ball_speed_kmh: float = 0.0
    pressure_on_ball: float = 0.0  # pressure index on the current ball carrier
    pressing: dict[str, float] = {}  # avg pressure each team applied in the window
    control: dict[str, Any] = {}  # control vs chaos over the window
    rhythm: dict[str, Any] = {}  # actions per minute + trend


@dataclass
class _TeamAcc:
    possession_frames: int = 0
    pass_distance_sum: float = 0.0
    stats: TeamStats = field(default_factory=lambda: TeamStats(team=""))


class StatsEngine:
    def __init__(self, match_id: str) -> None:
        self.match_id = match_id
        self.players: dict[str, PlayerStats] = {}
        self.teams = {t: _TeamAcc(stats=TeamStats(team=t)) for t in ("home", "away")}
        self._last: FrameState | None = None
        self._clock_s = 0.0
        self._ball_speed = 0.0
        self._pressure_on_ball = 0.0
        self._events: list[MatchEvent] = []  # whole match: rhythm compares the window with the match so far
        self._press: dict[str, deque[tuple[int, float]]] = {"home": deque(), "away": deque()}

    # --- frames ---------------------------------------------------------------
    def on_frame(self, frame: FrameState, clock_s: float | None = None) -> None:
        if not self.players:
            for p in frame.players:
                self.players[p.id] = PlayerStats(id=p.id, name=p.name, team=p.team, number=p.number, position=p.position)
        prev = {p.id: p for p in self._last.players} if self._last else {}
        for p in frame.players:
            ps = self.players[p.id]
            ps.speed_kmh = (p.vx**2 + p.vy**2) ** 0.5 * 3.6
            ps.top_speed_kmh = max(ps.top_speed_kmh, ps.speed_kmh)
            if p.id in prev:
                step = ((p.x - prev[p.id].x) ** 2 + (p.y - prev[p.id].y) ** 2) ** 0.5
                if step <= MAX_STEP_M:
                    ps.distance_m += step
        owner = next((p for p in frame.players if p.id == frame.ball.owner_id), None)
        self._pressure_on_ball = 0.0
        if owner is not None:
            self.teams[owner.team].possession_frames += 1
            defenders = np.array([[p.x, p.y] for p in frame.players if p.team != owner.team])
            self._pressure_on_ball = pressure_index((owner.x, owner.y), defenders)
            pressing_team = "away" if owner.team == "home" else "home"
            self._press[pressing_team].append((frame.t_ms, self._pressure_on_ball))
        horizon = frame.t_ms - WINDOW_S * 1000
        for samples in self._press.values():
            while samples and samples[0][0] < horizon:
                samples.popleft()
        self._ball_speed = (frame.ball.vx**2 + frame.ball.vy**2) ** 0.5 * 3.6
        self._clock_s = clock_s if clock_s is not None else frame.t_ms / 1000
        self._last = frame

    # --- events ---------------------------------------------------------------
    def on_event(self, event: MatchEvent) -> None:
        self._events.append(event)
        team = self.teams[event.team].stats if event.team else None
        player = self.players.get(event.player_id) if event.player_id else None
        if event.type == "pass" and team and player:
            team.passes += 1
            player.passes += 1
            if event.outcome == "complete":
                team.passes_completed += 1
                player.passes_completed += 1
            self.teams[event.team].pass_distance_sum += float(event.meta.get("distance_m", 0.0))  # type: ignore[index]
        elif event.type == "shot" and team and player:
            team.shots += 1
            player.shots += 1
            team.shots_on_target += event.outcome in ON_TARGET
            team.max_shot_speed_kmh = max(team.max_shot_speed_kmh, float(event.meta.get("shot_speed_kmh", 0.0)))
            if event.outcome == "goal":
                player.goals += 1
        elif event.type == "goal" and team:
            team.goals += 1
        elif event.type == "tackle" and team and player:
            team.tackles += 1
            player.tackles += 1
        elif event.type == "interception" and team and player:
            team.interceptions += 1
            player.interceptions += 1
        elif event.type == "pressure" and team and player:
            team.pressures += 1
            player.pressures += 1

    # --- output ---------------------------------------------------------------
    def snapshot(self) -> StatsSnapshot:
        total_poss = sum(acc.possession_frames for acc in self.teams.values()) or 1
        teams = {}
        for key, acc in self.teams.items():
            s = acc.stats.model_copy()
            s.possession = round(acc.possession_frames / total_poss, 3)
            s.pass_accuracy = round(s.passes_completed / s.passes, 3) if s.passes else None
            s.avg_pass_distance_m = round(acc.pass_distance_sum / s.passes, 1) if s.passes else None
            s.distance_km = round(sum(p.distance_m for p in self.players.values() if p.team == key) / 1000, 2)
            teams[key] = s
        last = self._last
        now = last.t_ms if last else 0
        window_ms = WINDOW_S * 1000
        current = [e for e in self._events if now - window_ms < e.t_ms <= now]
        elapsed_s = min(WINDOW_S, now / 1000) or WINDOW_S
        # trend baseline: the match before this window, once there is at least one window of it
        before_s = now / 1000 - WINDOW_S
        previous = [e for e in self._events if e.t_ms <= now - window_ms] if before_s >= WINDOW_S else []
        return StatsSnapshot(
            match_id=self.match_id,
            t_ms=now,
            clock_s=round(self._clock_s, 1),
            score=last.score if last else (0, 0),
            teams=teams,
            players={k: v.model_copy() for k, v in self.players.items()},
            ball_speed_kmh=round(self._ball_speed, 1),
            pressure_on_ball=round(self._pressure_on_ball, 2),
            pressing={t: round(float(np.mean([v for _, v in s])), 3) if s else 0.0 for t, s in self._press.items()},
            control=control_chaos(current, elapsed_s),
            rhythm=rhythm(current, previous, elapsed_s, max(before_s, WINDOW_S)),
        )
