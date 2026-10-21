"""Pure football metrics on positions (metres) and events. No state, no LLM.

Every formula is deliberately simple and documented so an analyst can check it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from app.models import PITCH_LENGTH, PITCH_WIDTH, MatchEvent

GOAL_Y = PITCH_WIDTH / 2
GOAL_HALF_WIDTH = 7.32 / 2
PRESSURE_RADIUS = 5.0  # m


def threat(x: float, y: float, attacks_right: bool) -> float:
    """Location value 0..~0.6: chance that a shot from here scores (distance + goal angle).

    Used xT-style: a pass that moves the ball to a higher-threat location is a "progressive" one.
    """
    gx = PITCH_LENGTH if attacks_right else 0.0
    ax, ay = gx - x, GOAL_Y - GOAL_HALF_WIDTH - y
    bx, by = gx - x, GOAL_Y + GOAL_HALF_WIDTH - y
    cos = (ax * bx + ay * by) / (math.hypot(ax, ay) * math.hypot(bx, by) + 1e-9)
    angle = math.acos(max(-1.0, min(1.0, cos)))
    dist = math.hypot(gx - x, GOAL_Y - y)
    return 1.0 / (1.0 + math.exp(-(-1.0 + 1.6 * angle - 0.09 * dist)))


def lane_clearance(start: Sequence[float], end: Sequence[float], opponents: np.ndarray) -> float:
    """Distance (m) from the closest opponent to the straight pass lane start -> end."""
    a, b = np.asarray(start, float), np.asarray(end, float)
    seg = b - a
    t = np.clip(((opponents - a) @ seg) / (seg @ seg + 1e-9), 0.0, 1.0)
    closest = a + t[:, None] * seg
    return float(np.linalg.norm(opponents - closest, axis=1).min())


def pass_difficulty(distance_m: float, lane_m: float, receiver_open_m: float, passer_pressure_m: float) -> float:
    """0 (trivial) .. 100 (very hard).

    35 % distance (40 m+ = max), 30 % lane blocked, 20 % receiver marked, 15 % passer under pressure.
    """
    d = min(distance_m / 40.0, 1.0)
    lane = math.exp(-lane_m / 2.0)
    marked = math.exp(-receiver_open_m / 3.0)
    pressed = math.exp(-passer_pressure_m / 2.0)
    return round(100.0 * (0.35 * d + 0.30 * lane + 0.20 * marked + 0.15 * pressed), 1)


def pressure_index(carrier_xy: Sequence[float], opponents: np.ndarray) -> float:
    """Pressure on the ball carrier: sum over opponents within 5 m of (1 - d/5). 0 = free, >1 = swarmed."""
    d = np.linalg.norm(opponents - np.asarray(carrier_xy, float), axis=1)
    return float(np.clip(1.0 - d / PRESSURE_RADIUS, 0.0, None).sum())


def control_chaos(events: Sequence[MatchEvent], window_s: float) -> dict[str, float | str | None]:
    """Game state over a window of events: 0 = controlled, 1 = chaotic.

    chaos = 60 % possession changes per minute (5/min = max; real matches average ~2-3)
          + 25 % failed passes (no passes in the window counts as 50 %)
          + 15 % short possession spells (< 10 s).
    A typical match sits around 0.35, so the gauge has room to move both ways.
    The team with more completed passes in the window is the one "in control".
    """
    minutes = max(window_s / 60.0, 1e-9)
    changes = sum(e.type in ("interception", "tackle") or (e.type == "pass" and e.outcome == "incomplete") for e in events)
    passes = [e for e in events if e.type == "pass"]
    completion = sum(p.outcome == "complete" for p in passes) / len(passes) if passes else 0.5
    spell_s = window_s / (changes + 1)
    chaos = 0.6 * min(changes / minutes / 5.0, 1.0) + 0.25 * (1.0 - completion) + 0.15 * (1.0 - min(spell_s / 10.0, 1.0))
    completed = {t: sum(p.team == t and p.outcome == "complete" for p in passes) for t in ("home", "away")}
    total = sum(completed.values())
    leader = max(completed, key=completed.get) if total else None  # type: ignore[arg-type]
    return {
        "chaos": round(min(max(chaos, 0.0), 1.0), 3),
        "control_team": leader,
        "control_share": round(completed[leader] / total, 3) if leader else None,
        "possession_changes_per_min": round(changes / minutes, 2),
    }


RHYTHM_EVENTS = {"pass", "shot", "tackle", "interception", "carry"}


def rhythm(current: Sequence[MatchEvent], previous: Sequence[MatchEvent], window_s: float) -> dict[str, float | str]:
    """Actions per minute in the current window and the trend versus the previous window."""
    minutes = max(window_s / 60.0, 1e-9)
    now = sum(e.type in RHYTHM_EVENTS for e in current) / minutes
    before = sum(e.type in RHYTHM_EVENTS for e in previous) / minutes
    change = (now - before) / before if before else 0.0
    trend = "rising" if change > 0.2 else "falling" if change < -0.2 else "steady"
    return {"actions_per_min": round(now, 1), "change": round(change, 2), "trend": trend}
