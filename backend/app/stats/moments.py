"""Moment Detector (M6a): picks the key moments of a match from events. Deterministic, no LLM.

Triggers (PLAN.md §3):
  goal                 shot that scored                                   importance 1.0
  big_chance           shot with xG >= 0.12 that did not score            0.5 + xG
  decisive_pass        completed pass that raised the threat a lot        0.3 + 4 * threat_gain
  dangerous_turnover   ball lost within 30 m of the loser's own goal      0.45 + closeness bonus

Moments closer than MIN_GAP_S to a more important one are dropped, so a goal is not
reported again as the pass and the turnover that led to it.
"""

from __future__ import annotations

import math

from app.models import PITCH_LENGTH, PITCH_WIDTH, MatchEvent, Moment

BIG_CHANCE_XG = 0.12
DECISIVE_THREAT_GAIN = 0.04
DANGER_ZONE_M = 30.0
MIN_GAP_S = 8.0


def _own_goal_distance(team: str, xy: tuple[float, float]) -> float:
    goal_x = 0.0 if team == "home" else PITCH_LENGTH
    return math.hypot(xy[0] - goal_x, xy[1] - PITCH_WIDTH / 2)


def _candidates(events: list[MatchEvent], clock_of) -> list[Moment]:
    by_id = {e.id: e for e in events}
    out: list[Moment] = []

    def add(e: MatchEvent, kind: str, score: float, reason: str, players: list[str], extra_ids: list[str] = []) -> None:
        out.append(
            Moment(
                id=f"{e.match_id}-m{e.frame:05d}-{kind}",
                match_id=e.match_id,
                frame=e.frame,
                t_ms=e.t_ms,
                clock_s=round(clock_of(e.frame), 1),
                kind=kind,  # type: ignore[arg-type]
                score=round(min(score, 1.0), 3),
                team=e.team,  # type: ignore[arg-type]
                player_ids=[p for p in players if p],
                event_ids=[e.id, *extra_ids],
                reason=reason,
            )
        )

    for e in events:
        if e.type == "shot" and e.team:
            xg = float(e.meta.get("xg", 0.0))
            if e.outcome == "goal":
                add(e, "goal", 1.0, f"goal from {e.meta.get('distance_m')} m, xG {xg:.2f}", [e.player_id or ""])
            elif xg >= BIG_CHANCE_XG:
                add(e, "big_chance", 0.5 + xg, f"{e.outcome} shot from {e.meta.get('distance_m')} m, xG {xg:.2f}", [e.player_id or ""])
        elif e.type == "pass" and e.outcome == "complete" and e.team:
            gain = float(e.meta.get("threat_gain", 0.0))
            if gain >= DECISIVE_THREAT_GAIN:
                add(e, "decisive_pass", 0.3 + 4 * gain,
                    f"pass raised scoring chance by {gain:.0%} (difficulty {e.meta.get('difficulty')})",
                    [e.player_id or "", e.target_id or ""])
        elif e.type in ("interception", "tackle") and e.team and e.start_xy:
            loser_team = "away" if e.team == "home" else "home"
            dist = _own_goal_distance(loser_team, e.start_xy)
            if dist <= DANGER_ZONE_M:
                lost = next((x for x in events if x.type == "pass" and x.frame <= e.frame and x.team == loser_team
                             and x.outcome == "incomplete" and e.frame - x.frame < 40), None)
                add(e, "dangerous_turnover", 0.45 + 0.3 * (1 - dist / DANGER_ZONE_M),
                    f"{loser_team} lost the ball {dist:.0f} m from their own goal",
                    [e.target_id or "", e.player_id or ""], [lost.id] if lost else [])
    del by_id
    return out


def detect_moments(events: list[MatchEvent], clock_of=lambda frame: frame / 10.0, limit: int | None = None) -> list[Moment]:
    """Key moments sorted by time. `clock_of(frame)` gives the broadcast clock in seconds."""
    chosen: list[Moment] = []
    for m in sorted(_candidates(events, clock_of), key=lambda m: -m.score):
        if all(abs(m.t_ms - c.t_ms) >= MIN_GAP_S * 1000 for c in chosen):
            chosen.append(m)
    if limit is not None:
        chosen = chosen[:limit]
    return sorted(chosen, key=lambda m: m.t_ms)
