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


INTERCEPT_PAIR_MS = 10_000  # an interception within 10 s of a failed pass by its victim is the same turnover

# possession changes per minute of *play* (physical time) that map to chaos 0 and 1 on that term,
# calibrated on GRF recordings (40 s windows over full-34 + grf-1..6: p5 1.5, median 6, p95 12 per min):
CHAOS_CHANGES_CALM = 1.5
CHAOS_CHANGES_WILD = 12.0
CHAOS_SPELL_LONG_S = 20.0  # an average possession this long counts as fully "settled"


def possession_changes(events: Sequence[MatchEvent]) -> int:
    """Tackles + interceptions + failed passes that no interception accounts for.

    Event derivation emits an intercepted pass twice ("pass incomplete" and "interception");
    that is one turnover, not two.
    """
    steals = [e for e in events if e.type == "interception"]
    changes = sum(e.type in ("interception", "tackle") for e in events)
    for p in events:
        if p.type == "pass" and p.outcome == "incomplete":
            paired = any(s.target_id == p.player_id and 0 <= s.t_ms - p.t_ms <= INTERCEPT_PAIR_MS for s in steals)
            changes += not paired
    return changes


def control_chaos(events: Sequence[MatchEvent], window_s: float) -> dict[str, float | str | None]:
    """Game state over a window of events: 0 = controlled, 1 = chaotic.

    chaos = 60 % possession changes per minute of play (CHAOS_CHANGES_CALM -> 0, CHAOS_CHANGES_WILD -> 1)
          + 25 % failed passes (no passes in the window counts as 50 %)
          + 15 % short possession spells (average spell vs CHAOS_SPELL_LONG_S).
    `window_s` is physical match time (GRF plays a 90' clock in 5 minutes, so rates are per real
    minute of play). The scale is calibrated on GRF so a typical window sits mid-gauge and the
    gauge moves both ways. The team with more completed passes in the window is "in control".
    """
    minutes = max(window_s / 60.0, 1e-9)
    changes = possession_changes(events)
    passes = [e for e in events if e.type == "pass"]
    completion = sum(p.outcome == "complete" for p in passes) / len(passes) if passes else 0.5
    spell_s = window_s / (changes + 1)
    rate = (changes / minutes - CHAOS_CHANGES_CALM) / (CHAOS_CHANGES_WILD - CHAOS_CHANGES_CALM)
    chaos = (0.6 * min(max(rate, 0.0), 1.0) + 0.25 * (1.0 - completion)
             + 0.15 * (1.0 - min(spell_s / CHAOS_SPELL_LONG_S, 1.0)))
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


def rhythm(
    current: Sequence[MatchEvent], previous: Sequence[MatchEvent], window_s: float, previous_s: float | None = None
) -> dict[str, float | str]:
    """Actions per minute in the current window and the trend versus what came before.

    `previous` covers `previous_s` seconds (default: one window of the same length); the stats
    engine passes the whole match before the current window, so the trend reads "faster / slower
    than the match so far".
    """
    minutes = max(window_s / 60.0, 1e-9)
    before_minutes = max((window_s if previous_s is None else previous_s) / 60.0, 1e-9)
    now = sum(e.type in RHYTHM_EVENTS for e in current) / minutes
    before = sum(e.type in RHYTHM_EVENTS for e in previous) / before_minutes
    change = (now - before) / before if before else 0.0
    trend = "rising" if change > 0.2 else "falling" if change < -0.2 else "steady"
    return {"actions_per_min": round(now, 1), "change": round(change, 2), "trend": trend}
