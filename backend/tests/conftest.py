import numpy as np
import pytest

from app.source.grf import GrfMatch, PlayerInfo
from app.source.roster import AWAY, HOME


def make_match(n_frames: int = 40) -> GrfMatch:
    """A static synthetic match: home on the left half, away on the right, nobody owns the ball."""
    players = [PlayerInfo(id=f"H{i}", team="home", name=f"Home {i}", number=i, position="GK" if i == 1 else "CM") for i in range(1, 12)]
    players += [PlayerInfo(id=f"A{i}", team="away", name=f"Away {i}", number=i, position="GK" if i == 1 else "CM") for i in range(1, 12)]
    base = np.array([[10.0 + 4 * i, 10.0 + 4 * i] for i in range(11)] + [[95.0 - 4 * i, 10.0 + 4 * i] for i in range(11)])
    return GrfMatch(
        match_id="test",
        home=HOME,
        away=AWAY,
        players=players,
        pos=np.repeat(base[None], n_frames, axis=0),
        vel=np.zeros((n_frames, 22, 2)),
        ball=np.tile([52.5, 34.0, 0.0], (n_frames, 1)),
        ball_vel=np.zeros((n_frames, 3)),
        owner_team=np.full(n_frames, -1),
        owner_idx=np.full(n_frames, -1),
        game_mode=np.zeros(n_frames, dtype=int),
        score=np.zeros((n_frames, 2), dtype=int),
        jump=np.zeros(n_frames, dtype=bool),
    )


def own(match: GrfMatch, player: int, start: int, end: int) -> None:
    """Give the ball to player index `player` for frames [start, end] and put it at his feet."""
    match.owner_idx[start : end + 1] = player
    match.owner_team[start : end + 1] = 0 if player < 11 else 1
    match.ball[start : end + 1, :2] = match.pos[start : end + 1, player]


@pytest.fixture
def match() -> GrfMatch:
    return make_match()
