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
    name: str = ""
    number: int = 0
    position: str = ""  # GK, CB, LB, RB, DM, CM, LM, RM, AM, CF


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


EventType = Literal[
    "kickoff",
    "pass",
    "shot",
    "goal",
    "tackle",
    "interception",
    "pressure",
    "carry",
    "set_piece",
    "out_of_play",
]


class MatchEvent(BaseModel):
    """A football event derived from the frame stream (all positions in metres)."""

    id: str
    match_id: str
    t_ms: int
    frame: int
    type: EventType
    team: Team | None = None
    player_id: str | None = None
    target_id: str | None = None  # pass receiver, tackled/pressed player, ...
    start_xy: tuple[float, float] | None = None
    end_xy: tuple[float, float] | None = None
    outcome: str | None = None  # complete | incomplete | out | goal | saved | off_target | won | ...
    meta: dict[str, Any] = Field(default_factory=dict)


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


# --- explanation + broadcast contract (stages c-e) ------------------------------------------

MomentKind = Literal["goal", "big_chance", "decisive_pass", "dangerous_turnover"]


class Moment(BaseModel):
    """A key moment picked by the deterministic Moment Detector."""

    id: str
    match_id: str
    frame: int
    t_ms: int
    clock_s: float
    kind: MomentKind
    score: float  # 0..1 importance
    team: Team
    player_ids: list[str]
    event_ids: list[str]
    reason: str  # human-readable trigger, e.g. "shot from 14 m, xG 0.31"


class Hypothesis(BaseModel):
    """One step of the explain team's work, kept for the control-room panel."""

    text: str
    intervention: Intervention | None = None
    baseline_p_goal: float | None = None
    counterfactual_p_goal: float | None = None
    seed_spread: float | None = None
    verdict: Literal["accepted", "rejected", "pending"] = "pending"
    critic_note: str = ""


class Insight(BaseModel):
    """A verified explanation of why a moment mattered. Numbers come from code, never from the LLM."""

    id: str
    moment_id: str
    claim: str  # neutral English master text; narrators adapt it per segment
    evidence: list[str]  # event ids, rollout ids
    numbers: dict[str, float]
    verified: bool
    confidence: Literal["clear", "slight"]
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    ghost_paths: list[list[tuple[float, float]]] = Field(default_factory=list)


ProfileMode = Literal["analyst", "club_fan", "player_focus", "casual"]


class ViewerProfile(BaseModel):
    mode: ProfileMode
    language: str = "en"
    favourite_club: Team | None = None
    favourite_players: list[str] = Field(default_factory=list)
    my_metric: str | None = None

    @property
    def segment_id(self) -> str:
        """Production runs per segment, not per viewer (cost independent of audience size)."""
        focus = self.favourite_club if self.mode == "club_fan" else (self.favourite_players[:1] or [""])[0]
        return "-".join(x for x in (self.mode, focus or "", self.language) if x)


OverlaySlot = Literal["scorebug", "lower_third", "side_panel", "pitch", "ticker", "fullscreen"]
OverlayType = Literal[
    "event_card", "stat_card", "player_tag", "alert", "insight", "sliding_doors", "momentum", "recap"
]


class Overlay(BaseModel):
    """Timed, machine-readable graphic for one segment: what a broadcast rendering partner consumes."""

    id: str
    match_id: str
    segment_id: str  # "*" = every segment
    start_ms: int  # match time at which it appears
    duration_ms: int
    slot: OverlaySlot
    type: OverlayType
    priority: int = 50  # 0..100, scheduler drops the lowest when slots collide
    lang: str = "en"
    headline: str = ""
    body: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
