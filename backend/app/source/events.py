"""Derive football events from a recorded frame stream (stage a: ingest).

GRF only tells us who owns the ball in each frame. We split the match into
possession spells (consecutive frames owned by one player) and classify what
happens between two spells:

  same team, other player        -> pass (complete)
  other team, ball travelled     -> pass (incomplete) + interception
  other team, players together   -> tackle
  ball sent fast towards goal    -> shot (goal | saved | off_target | blocked)
  game mode changes              -> set_piece; ball went out -> out_of_play

Within a spell we add carries (ball moved far) and pressure (an opponent close
to the carrier for a while). All thresholds are named constants below.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.models import PITCH_LENGTH, PITCH_WIDTH, MatchEvent
from app.source.grf import GAME_MODES, STEP_S, GrfMatch
from app.stats.metrics import lane_clearance, pass_difficulty, threat

GOAL_Y = PITCH_WIDTH / 2
SHOT_MIN_SPEED = 12.0  # m/s right after release
SHOT_MAX_DIST = 35.0  # m from goal centre at release
SHOT_GOAL_MARGIN = 6.0  # m outside the posts still counts as "on its way to goal"
TACKLE_MAX_GAP = 1  # loose-ball frames between the two owners
TACKLE_MAX_DIST = 2.5  # m between loser and winner at the change
CARRY_MIN_DIST = 8.0  # m
PRESSURE_DIST = 3.0  # m
PRESSURE_MIN_FRAMES = 5  # 0.5 s


@dataclass
class Spell:
    player: int
    start: int
    end: int


def _spells(match: GrfMatch) -> list[Spell]:
    spells: list[Spell] = []
    for f in range(match.n_frames):
        o = int(match.owner_idx[f])
        if o < 0:
            continue
        last = spells[-1] if spells else None
        if last and last.player == o and not match.jump[last.end + 1 : f + 1].any():
            last.end = f
        else:
            spells.append(Spell(o, f, f))
    return spells


def _xy(arr: np.ndarray) -> tuple[float, float]:
    return (round(float(arr[0]), 2), round(float(arr[1]), 2))


class _Builder:
    def __init__(self, match: GrfMatch) -> None:
        self.match = match
        self.events: list[MatchEvent] = []

    def add(self, frame: int, type_: str, player: int | None = None, **kw) -> MatchEvent:
        m = self.match
        event = MatchEvent(
            id=f"{m.match_id}-{frame:05d}-{type_}-{len(self.events)}",
            match_id=m.match_id,
            t_ms=m.t_ms(frame),
            frame=frame,
            type=type_,  # type: ignore[arg-type]
            team=m.team_of(player) if player is not None else kw.pop("team", None),  # type: ignore[arg-type]
            player_id=m.players[player].id if player is not None else None,
            **kw,
        )
        event.meta.setdefault("clock_s", round(m.clock_s(frame), 1))
        self.events.append(event)
        return event


def _attack_goal_x(team_idx: int) -> float:
    return PITCH_LENGTH if team_idx == 0 else 0.0


def _shot_info(match: GrfMatch, shooter: int, release: int, until: int) -> dict | None:
    """Return shot details if the ball left `shooter` fast towards the opponent goal."""
    team = 0 if shooter < 11 else 1
    goal_x = _attack_goal_x(team)
    start = match.ball[release, :2]
    dist = float(np.hypot(goal_x - start[0], GOAL_Y - start[1]))
    if dist > SHOT_MAX_DIST:
        return None
    window = range(release + 1, min(release + 4, until + 1, match.n_frames))
    speeds = [float(np.linalg.norm(match.ball_vel[f, :2])) for f in window]
    if not speeds or max(speeds) < SHOT_MIN_SPEED:
        return None
    v = match.ball_vel[release + 1 + int(np.argmax(speeds)), :2]
    towards = (goal_x - start[0]) * v[0] > 0
    if not towards or abs(v[0]) < 1e-6:
        return None
    y_at_line = start[1] + v[1] * (goal_x - start[0]) / v[0]
    if abs(y_at_line - GOAL_Y) > 3.66 + SHOT_GOAL_MARGIN:
        return None
    return {
        "distance_m": round(dist, 1),
        "shot_speed_kmh": round(max(speeds) * 3.6, 1),
        "xg": round(threat(float(start[0]), float(start[1]), team == 0), 3),
    }


def derive_events(match: GrfMatch) -> list[MatchEvent]:
    m = match
    b = _Builder(m)
    spells = _spells(m)
    b.add(0, "kickoff", team="home", meta={"score": [0, 0]})

    # goals and set pieces come straight from score / game-mode changes
    for f in range(1, m.n_frames):
        if (m.score[f] != m.score[f - 1]).any():
            scorer_team = "home" if m.score[f, 0] > m.score[f - 1, 0] else "away"
            b.add(f, "goal", team=scorer_team, meta={"score": m.score[f].tolist()})
            b.add(f, "kickoff", team="away" if scorer_team == "home" else "home", meta={"score": m.score[f].tolist()})
        if m.game_mode[f] != m.game_mode[f - 1] and m.game_mode[f] != 0:
            b.add(f, "set_piece", team=None, start_xy=_xy(m.ball[f]), meta={"mode": GAME_MODES.get(int(m.game_mode[f]), "?")})

    for a, nxt in zip(spells, spells[1:] + [None]):
        _within_spell(b, a)
        if nxt is None:
            continue
        restart = bool(m.jump[a.end + 1 : nxt.start + 1].any()) or bool((m.game_mode[a.end + 1 : nxt.start + 1] != 0).any())
        scored = bool((m.score[nxt.start] != m.score[a.end]).any())
        shot = _shot_info(m, a.player, a.end, nxt.start)
        team_a = 0 if a.player < 11 else 1
        team_b = 0 if nxt.player < 11 else 1
        release_xy = _xy(m.ball[a.end])
        receive_xy = _xy(m.ball[nxt.start])
        gap = nxt.start - a.end - 1

        if shot is not None or scored:
            if scored:
                outcome = "goal"
            elif team_b != team_a and m.players[nxt.player].position == "GK":
                outcome = "saved"
            elif restart:
                outcome = "off_target"
            else:
                outcome = "blocked"
            if shot is None:  # scored without a fast shot (tap-in, deflection): describe it from the position
                attacks_right = a.player < 11
                goal_x = _attack_goal_x(0 if attacks_right else 1)
                shot = {
                    "distance_m": round(float(np.hypot(goal_x - release_xy[0], GOAL_Y - release_xy[1])), 1),
                    "shot_speed_kmh": round(float(np.linalg.norm(m.ball_vel[min(a.end + 1, m.n_frames - 1), :2])) * 3.6, 1),
                    "xg": round(threat(*release_xy, attacks_right), 3),
                }
            b.add(a.end, "shot", a.player, start_xy=release_xy, outcome=outcome, meta=shot)
            continue

        if restart:
            b.add(a.end, "out_of_play", a.player, start_xy=release_xy)
            continue

        if team_a == team_b:
            if nxt.player != a.player:
                b.add(a.end, "pass", a.player, target_id=m.players[nxt.player].id, start_xy=release_xy,
                      end_xy=receive_xy, outcome="complete",
                      meta=_pass_meta(m, a.player, a.end, nxt.start, release_xy, receive_xy, nxt.player))
            continue

        together = float(np.linalg.norm(m.pos[nxt.start, a.player] - m.pos[nxt.start, nxt.player]))
        if gap <= TACKLE_MAX_GAP and together <= TACKLE_MAX_DIST:
            b.add(nxt.start, "tackle", nxt.player, target_id=m.players[a.player].id, start_xy=receive_xy, outcome="won")
        else:
            b.add(a.end, "pass", a.player, start_xy=release_xy, end_xy=receive_xy, outcome="incomplete",
                  meta=_pass_meta(m, a.player, a.end, nxt.start, release_xy, receive_xy, None))
            b.add(nxt.start, "interception", nxt.player, target_id=m.players[a.player].id, start_xy=receive_xy)

    b.events.sort(key=lambda e: (e.frame, e.id))
    _credit_scorers(b.events)
    return b.events


def _credit_scorers(events: list[MatchEvent]) -> None:
    """Goal events come from score changes; attach the scorer from the preceding goal shot."""
    last_goal_shot: MatchEvent | None = None
    for e in events:
        if e.type == "shot" and e.outcome == "goal":
            last_goal_shot = e
        elif e.type == "goal" and last_goal_shot is not None and last_goal_shot.team == e.team:
            e.player_id = last_goal_shot.player_id
            e.meta["shot_id"] = last_goal_shot.id
            last_goal_shot = None


def _pass_meta(m: GrfMatch, passer: int, release: int, receive: int, start: tuple, end: tuple, receiver: int | None) -> dict:
    speeds = [float(np.linalg.norm(m.ball_vel[f, :2])) for f in range(release + 1, min(release + 4, receive + 1))]
    distance = float(np.hypot(end[0] - start[0], end[1] - start[1]))
    own = slice(0, 11) if passer < 11 else slice(11, 22)
    opp = slice(11, 22) if passer < 11 else slice(0, 11)
    opponents = m.pos[release, opp]
    if receiver is None:  # intended receiver of a failed pass: team-mate closest to where it ended
        mates = m.pos[receive, own]
        receiver = int(np.argmin(np.linalg.norm(mates - np.asarray(end), axis=1))) + own.start
    receiver_open = float(np.linalg.norm(opponents - m.pos[release, receiver], axis=1).min())
    passer_free = float(np.linalg.norm(opponents - m.pos[release, passer], axis=1).min())
    attacks_right = passer < 11
    return {
        "distance_m": round(distance, 1),
        "ball_speed_kmh": round(max(speeds, default=0.0) * 3.6, 1),
        "flight_s": round((receive - release) * STEP_S, 1),
        "difficulty": pass_difficulty(distance, lane_clearance(start, end, opponents), receiver_open, passer_free),
        "threat_gain": round(threat(*end, attacks_right) - threat(*start, attacks_right), 4),
        "intended_receiver": m.players[receiver].id,
    }


def _within_spell(b: _Builder, s: Spell) -> None:
    m = b.match
    start, end = m.ball[s.start, :2], m.ball[s.end, :2]
    dist = float(np.linalg.norm(end - start))
    if dist >= CARRY_MIN_DIST:
        b.add(s.start, "carry", s.player, start_xy=_xy(start), end_xy=_xy(end), meta={"distance_m": round(dist, 1)})

    opponents = slice(11, 22) if s.player < 11 else slice(0, 11)
    frames = np.arange(s.start, s.end + 1)
    d = np.linalg.norm(m.pos[frames, opponents] - m.pos[frames, s.player][:, None, :], axis=-1)  # (F, 11)
    close = d.min(axis=1) <= PRESSURE_DIST
    run = 0
    for i, c in enumerate(close):
        run = run + 1 if c else 0
        if run == PRESSURE_MIN_FRAMES:
            f = int(frames[i - PRESSURE_MIN_FRAMES + 1])
            presser = int(np.argmin(d[i - PRESSURE_MIN_FRAMES + 1])) + (11 if s.player < 11 else 0)
            b.add(f, "pressure", presser, target_id=m.players[s.player].id, start_xy=_xy(m.pos[f, s.player]),
                  meta={"distance_m": round(float(d[i - PRESSURE_MIN_FRAMES + 1].min()), 1)})
            break
