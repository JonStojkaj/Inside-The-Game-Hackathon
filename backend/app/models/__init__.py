"""Data contracts shared by all modules (PLAN.md §5).

Coordinates are metres on a 105 x 68 pitch, origin bottom-left.
Convention: team "home" attacks towards x = 105, team "away" towards x = 0.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0

Team = Literal["home", "away"]


class PlayerState(BaseModel):
    id: str
    team: Team
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    role: Literal["gk", "outfield"] = "outfield"


class BallState(BaseModel):
    x: float
    y: float
    z: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    owner_id: str | None = None


class FrameState(BaseModel):
    match_id: str
    t_ms: int
    frame: int = 0
    players: list[PlayerState]
    ball: BallState
    game_mode: str = "normal"
    score: tuple[int, int] = (0, 0)


class Intervention(BaseModel):
    """A counterfactual change applied to a FrameState before rolling out.

    kinds:
      move_player    params: {"player_id": str, "dx": float, "dy": float}
      swap_action    params: {"action": "shoot" | "carry"} or {"action": "pass", "target_id": str}
      remove_player  params: {"player_id": str}
    """

    kind: Literal["move_player", "swap_action", "remove_player"]
    params: dict[str, Any] = Field(default_factory=dict)


class RolloutResult(BaseModel):
    n: int
    seed: int
    horizon_s: float
    attacking_team: Team
    p_goal_for: float
    p_goal_against: float
    p_turnover: float
    p_retained: float
    outcome_entropy: float  # 0 = fully predictable future ("control"), 1 = maximal spread ("chaos")
    sample_paths: list[list[tuple[float, float]]]  # ball path per sampled future, for ghost rendering
    elapsed_ms: float
