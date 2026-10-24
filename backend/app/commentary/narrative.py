"""The match as a story, not a list of events: the analysis the commentator talks about between the actions.

Pure functions over one exported match (MatchData), all numbers from the data:
  momentum      who is pushing, second by second (decayed weight of threatening actions per team)
  swings        when momentum changes hands and stays there (the "the game has turned" moments)
  pushes        peaks of one side's pressure ("they're turning the screw")
  build_up      the move behind a goal: passes, seconds, how it started and who started it
  turnover      what a ball loss led to: where it was lost, how fast the opponent shot
  window        shots / share of the ball for both teams between two times ("since the goal")
Home attacks towards x = 105 for the whole match.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.commentary.data import Event, MatchData, other

HALF_LIFE_S = 20.0  # real seconds (x clock_scale on the broadcast clock)
SWING_HOLD_S = 6  # the new side must stay on top this long
SWING_GAP_S = 25  # and swings at least this far apart
SWING_SHARE = 0.35  # "on top" = momentum beyond this share of the match's peak


def _weight(e: Event) -> float:
    """How much an action pushes its team towards a goal."""
    m = e.meta
    x = e.start_xy[0] if e.start_xy else 52.5
    att_x = x if e.team == "home" else 105 - x
    if e.type == "shot":
        return 2.0 + 8.0 * float(m.get("xg", 0.0))
    if e.type == "pass" and e.outcome == "complete":
        return 0.3 + 10.0 * max(0.0, float(m.get("threat_gain", 0.0))) + (0.5 if att_x > 70 else 0.0)
    if e.type == "carry":
        return 0.3 + (0.4 if att_x > 70 else 0.0)
    if e.type in ("tackle", "interception"):
        return 0.6 + (0.6 if att_x > 52.5 else 0.0)  # winning it high up counts double
    if e.type == "pressure":
        return 0.15
    if e.type == "set_piece":
        return 0.8 if m.get("mode") == "corner" else 0.4
    return 0.0


def momentum(md: MatchData) -> list[float]:
    """Per real second: home push minus away push (exponentially decayed)."""
    n = max(1, math.ceil((md.duration_ms or (md.events[-1].known_ms if md.events else 0)) / 1000) + 1)
    decay = 0.5 ** (1 / HALF_LIFE_S)
    add = [0.0] * n
    for e in md.events:
        if e.team in ("home", "away"):
            s = min(n - 1, e.known_ms // 1000)
            add[s] += _weight(e) * (1 if e.team == "home" else -1)
    out, cur = [], 0.0
    for a in add:
        cur = cur * decay + a
        out.append(cur)
    return out


@dataclass
class Swing:
    t_ms: int  # when it is clear (start + hold)
    team: str  # who is on top now
    flip: bool  # the other side was on top before (not just from an even game)
    since_ms: int  # when this spell started


def swings(md: MatchData) -> list[Swing]:
    mo = momentum(md)
    peak = max((abs(v) for v in mo), default=0.0)
    if peak <= 0:
        return []
    thr = SWING_SHARE * peak
    out: list[Swing] = []
    top: str | None = None
    cand: str | None = None
    cand_since = 0
    for s, v in enumerate(mo):
        side = "home" if v >= thr else "away" if v <= -thr else None
        if side is None or side == top:
            cand = None
            continue
        if side != cand:
            cand, cand_since = side, s
        if s - cand_since >= SWING_HOLD_S and (not out or s * 1000 - out[-1].t_ms >= SWING_GAP_S * 1000):
            out.append(Swing(s * 1000, side, flip=top is not None, since_ms=cand_since * 1000))
            top, cand = side, None
    return out


@dataclass
class Push:
    t_ms: int
    team: str
    shots: int  # shots by that team in the 30 s before the peak


PUSH_SHARE = 0.6
PUSH_GAP_S = 30


def pushes(md: MatchData) -> list[Push]:
    """Local peaks of one side's momentum (above PUSH_SHARE of the match peak), at least PUSH_GAP_S apart."""
    mo = momentum(md)
    peak = max((abs(v) for v in mo), default=0.0)
    out: list[Push] = []
    for s in range(1, len(mo) - 1):
        v = mo[s]
        if abs(v) < PUSH_SHARE * peak or abs(v) < abs(mo[s - 1]) or abs(v) < abs(mo[s + 1]):
            continue
        if out and s * 1000 - out[-1].t_ms < PUSH_GAP_S * 1000:
            continue
        team = "home" if v > 0 else "away"
        out.append(Push(s * 1000, team, window(md, s * 1000 - 30_000, s * 1000).shots[team]))
    return out


@dataclass
class Window:
    shots: dict[str, int]
    xg: dict[str, float]
    share: dict[str, float]  # share of passes + carries (on the ball)


def window(md: MatchData, t0: int, t1: int) -> Window:
    shots = {"home": 0, "away": 0}
    xg = {"home": 0.0, "away": 0.0}
    ball = {"home": 0, "away": 0}
    for e in md.events:
        if e.known_ms < t0 or e.team not in ("home", "away"):
            continue
        if e.known_ms > t1:
            break
        if e.type == "shot":
            shots[e.team] += 1
            xg[e.team] += float(e.meta.get("xg", 0.0))
        elif e.type in ("pass", "carry"):
            ball[e.team] += 1
    total = ball["home"] + ball["away"]
    share = {t: (ball[t] / total if total else 0.5) for t in ball}
    return Window(shots, xg, share)


@dataclass
class Move:
    passes: int
    seconds: float  # real seconds of play (what the picture shows)
    start: str  # "regain" | "set_piece" | "kickoff" | "open"
    starter: str | None  # who started it (the regain / the first pass)
    players: int  # different players involved


def build_up(md: MatchData, shot: Event) -> Move:
    """Walk back from the shot through the same team's chain until the ball was won or play restarted."""
    i = next((k for k, e in enumerate(md.events) if e.id == shot.id), -1)
    passes, first, involved = 0, shot, {shot.player_id}
    start, starter = "open", None
    for e in reversed(md.events[:i]):
        if shot.t_ms - e.t_ms > 30_000:
            break
        if e.type == "pressure" or e.t_ms >= shot.t_ms or (e.type == "set_piece" and e.team is None):
            continue  # the opponent's pressing, and restarts the engine logs after the shot
        if e.team != shot.team or e.type in ("shot", "goal", "out_of_play") or (e.type == "pass" and e.outcome != "complete"):
            break
        if e.type in ("tackle", "interception"):
            start, starter, first = "regain", e.player_id, e
            involved.add(e.player_id)
            break
        if e.type in ("set_piece", "kickoff"):
            start, first = ("set_piece" if e.type == "set_piece" else "kickoff"), e
            starter = starter or e.player_id
            break
        if e.type == "pass":
            passes += 1
        first, starter = e, e.player_id
        involved.add(e.player_id)
    secs = max(0.0, (shot.t_ms - first.t_ms) / 1000)
    return Move(passes, secs, start, starter, len({p for p in involved if p}))


@dataclass
class TurnoverStory:
    loser: str | None
    winner: str | None
    own_half: bool
    metres_from_goal: float  # from the loser's own goal line
    shot_after_s: float | None  # real seconds until the winners shot, if they did within 15 s
    shot_outcome: str | None


def turnover(md: MatchData, ev: Event) -> TurnoverStory:
    """`ev` is the tackle/interception that won the ball (its target_id lost it)."""
    x = ev.start_xy[0] if ev.start_xy else 52.5
    loser_team = other(ev.team or "home")
    from_goal = x if loser_team == "home" else 105 - x
    shot = next((e for e in md.events if e.type == "shot" and e.team == ev.team and 0 <= e.t_ms - ev.t_ms <= 15_000), None)
    return TurnoverStory(ev.target_id, ev.player_id, from_goal < 52.5, from_goal,
                         (shot.t_ms - ev.t_ms) / 1000 if shot else None, shot.outcome if shot else None)
