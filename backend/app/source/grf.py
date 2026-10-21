"""Load a recorded GRF match (raw.jsonl) into metre-based arrays and FrameStates.

GRF facts this relies on (measured on recordings, see PLAN.md §15):
- one step = 0.1 s of physical time (top speeds ~8.7 m/s); a full match is 3000 steps,
  the broadcast clock is scaled so that 3000 steps read as 90 minutes
- coordinates: x in [-1, 1], y in [-0.42, 0.42] with y pointing down; the left team
  ("home") attacks towards x = +1 for the whole match (no side switch)
- players are teleported on resets (goals, set pieces): displacements above
  MAX_STEP_M are treated as jumps, not movement
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.models import PITCH_LENGTH, PITCH_WIDTH, BallState, FrameState, PlayerState
from app.source.roster import AWAY, HOME, Club, assign

STEP_S = 0.1
MATCH_STEPS = 3000
CLOCK_SCALE = 90 * 60 / (MATCH_STEPS * STEP_S)  # broadcast seconds per physical second
GRF_Y_HALF = 0.42
MAX_STEP_M = 1.5  # anything faster than 15 m/s between steps is a reset jump

GAME_MODES = {0: "normal", 1: "kickoff", 2: "goal_kick", 3: "free_kick", 4: "corner", 5: "throw_in", 6: "penalty"}


def to_metres_x(x: np.ndarray) -> np.ndarray:
    return (x + 1.0) / 2.0 * PITCH_LENGTH


def to_metres_y(y: np.ndarray) -> np.ndarray:
    return (GRF_Y_HALF - y) / (2 * GRF_Y_HALF) * PITCH_WIDTH


@dataclass
class PlayerInfo:
    id: str
    team: str
    name: str
    number: int
    position: str


@dataclass
class GrfMatch:
    match_id: str
    home: Club
    away: Club
    players: list[PlayerInfo]  # index 0..10 home, 11..21 away
    pos: np.ndarray  # (T, 22, 2) metres
    vel: np.ndarray  # (T, 22, 2) m/s, reset jumps zeroed
    ball: np.ndarray  # (T, 3) metres (z in metres)
    ball_vel: np.ndarray  # (T, 3) m/s
    owner_team: np.ndarray  # (T,) -1 none, 0 home, 1 away
    owner_idx: np.ndarray  # (T,) 0..21 or -1
    game_mode: np.ndarray  # (T,)
    score: np.ndarray  # (T, 2)
    jump: np.ndarray = field(repr=False)  # (T,) True where a reset happened before this frame

    @property
    def n_frames(self) -> int:
        return len(self.pos)

    def t_ms(self, frame: int) -> int:
        return int(round(frame * STEP_S * 1000))

    def clock_s(self, frame: int) -> float:
        """Broadcast match clock (0..5400 s): real time for full-length recordings,
        scaled up for GRF's default 5-minute matches."""
        physical_s = (self.n_frames - 1) * STEP_S
        scale = 90 * 60 / physical_s if physical_s < 90 * 60 else 1.0
        return frame * STEP_S * scale

    def team_of(self, idx: int) -> str:
        return "home" if idx < 11 else "away"

    def frame_state(self, frame: int) -> FrameState:
        owner = int(self.owner_idx[frame])
        players = [
            PlayerState(
                id=p.id,
                team=p.team,  # type: ignore[arg-type]
                x=float(self.pos[frame, i, 0]),
                y=float(self.pos[frame, i, 1]),
                vx=float(self.vel[frame, i, 0]),
                vy=float(self.vel[frame, i, 1]),
                role="gk" if p.position == "GK" else "outfield",
                name=p.name,
                number=p.number,
                position=p.position,
            )
            for i, p in enumerate(self.players)
        ]
        bx, by, bz = self.ball[frame]
        bvx, bvy, bvz = self.ball_vel[frame]
        return FrameState(
            match_id=self.match_id,
            t_ms=self.t_ms(frame),
            frame=frame,
            players=players,
            ball=BallState(
                x=float(bx), y=float(by), z=float(bz), vx=float(bvx), vy=float(bvy), vz=float(bvz),
                owner_id=self.players[owner].id if owner >= 0 else None,
            ),
            game_mode=GAME_MODES.get(int(self.game_mode[frame]), "normal"),
            score=(int(self.score[frame, 0]), int(self.score[frame, 1])),
        )


def load_grf_match(path: str | Path, match_id: str | None = None) -> GrfMatch:
    path = Path(path)
    raw_file = path / "raw.jsonl" if path.is_dir() else path
    rows = [json.loads(line) for line in raw_file.read_text().splitlines() if line]

    left = np.array([r["left_team"] for r in rows], dtype=float)
    right = np.array([r["right_team"] for r in rows], dtype=float)
    grf = np.concatenate([left, right], axis=1)  # (T, 22, 2)
    pos = np.stack([to_metres_x(grf[..., 0]), to_metres_y(grf[..., 1])], axis=-1)

    disp = np.zeros_like(pos)
    disp[1:] = pos[1:] - pos[:-1]
    step_len = np.linalg.norm(disp, axis=-1)
    jump = np.zeros(len(rows), dtype=bool)
    jump[1:] = (step_len[1:] > MAX_STEP_M).any(axis=1)
    # velocities from GRF's own movement vectors (per step), not from position deltas:
    # repositioning at restarts would otherwise show up as sprints
    dirs = np.concatenate(
        [np.array([r["left_team_direction"] for r in rows]), np.array([r["right_team_direction"] for r in rows])], axis=1
    )
    vel = np.stack([dirs[..., 0] / 2.0 * PITCH_LENGTH, -dirs[..., 1] / (2 * GRF_Y_HALF) * PITCH_WIDTH], axis=-1) / STEP_S

    ball_grf = np.array([r["ball"] for r in rows], dtype=float)
    # GRF ball z is in its own units (~1 unit = 1 m judging by crossbar height ~2.4)
    ball = np.stack([to_metres_x(ball_grf[:, 0]), to_metres_y(ball_grf[:, 1]), ball_grf[:, 2]], axis=-1)
    ball_disp = np.zeros_like(ball)
    ball_disp[1:] = ball[1:] - ball[:-1]
    ball_jump = np.linalg.norm(ball_disp[:, :2], axis=1) > 6.0  # > 60 m/s cannot be a kick
    ball_vel = np.where(ball_jump[:, None] | jump[:, None], 0.0, ball_disp / STEP_S)

    owner_team = np.array([r["ball_owned_team"] for r in rows])
    owner_player = np.array([r["ball_owned_player"] for r in rows])
    owner_idx = np.where(owner_team == 0, owner_player, np.where(owner_team == 1, 11 + owner_player, -1))

    players = [
        PlayerInfo(id=pid, team="home", name=name, number=num, position=posn)
        for pid, name, num, posn in assign(HOME, rows[0]["left_team_roles"])
    ] + [
        PlayerInfo(id=pid, team="away", name=name, number=num, position=posn)
        for pid, name, num, posn in assign(AWAY, rows[0]["right_team_roles"])
    ]

    return GrfMatch(
        match_id=match_id or (path.name if path.is_dir() else path.parent.name),
        home=HOME,
        away=AWAY,
        players=players,
        pos=pos,
        vel=vel,
        ball=ball,
        ball_vel=ball_vel,
        owner_team=owner_team,
        owner_idx=owner_idx,
        game_mode=np.array([r["game_mode"] for r in rows]),
        score=np.array([r["score"] for r in rows]),
        jump=jump,
    )
