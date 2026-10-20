"""Hand-built game states for tests, benchmarks and the demo (fictional teams)."""

from __future__ import annotations

from app.models import BallState, FrameState, PlayerState

# home = "FC Northbridge" (attacks right), away = "Harbour City" (attacks left)
_HOME = [
    ("H1", 10, 34, "gk"),
    ("H2", 45, 10, "outfield"),
    ("H3", 40, 27, "outfield"),
    ("H4", 40, 41, "outfield"),
    ("H5", 45, 58, "outfield"),
    ("H6", 60, 20, "outfield"),
    ("H7", 72, 40, "outfield"),
    ("H8", 66, 52, "outfield"),
    ("H9", 84, 34, "outfield"),
    ("H10", 80, 14, "outfield"),
    ("H11", 82, 56, "outfield"),
]
_AWAY = [
    ("A1", 102, 34, "gk"),
    ("A2", 88, 12, "outfield"),
    ("A3", 90, 28, "outfield"),
    ("A4", 90, 40, "outfield"),
    ("A5", 88, 56, "outfield"),
    ("A6", 78, 18, "outfield"),
    ("A7", 76, 32, "outfield"),
    ("A8", 77, 46, "outfield"),
    ("A9", 79, 60, "outfield"),
    ("A10", 60, 30, "outfield"),
    ("A11", 58, 42, "outfield"),
]


def final_third_attack(owner_id: str = "H7", owner_xy: tuple[float, float] | None = None) -> FrameState:
    """Home team in possession around the edge of the final third."""
    players = [PlayerState(id=i, team="home", x=x, y=y, role=r) for i, x, y, r in _HOME] + [
        PlayerState(id=i, team="away", x=x, y=y, role=r) for i, x, y, r in _AWAY
    ]
    if owner_xy is not None:
        for p in players:
            if p.id == owner_id:
                p.x, p.y = owner_xy
    owner = next(p for p in players if p.id == owner_id)
    return FrameState(
        match_id="demo-001",
        t_ms=63 * 60 * 1000,
        players=players,
        ball=BallState(x=owner.x, y=owner.y, owner_id=owner_id),
    )
