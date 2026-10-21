"""Fictional clubs and players for the synthetic matches (no real names or brands)."""

from __future__ import annotations

from dataclasses import dataclass

# GRF role ids -> position code
GRF_POSITIONS = ["GK", "CB", "LB", "RB", "DM", "CM", "LM", "RM", "AM", "CF"]
_NUMBERS = {"GK": [1], "RB": [2], "LB": [3], "CB": [4, 5], "DM": [6], "RM": [7], "CM": [8, 16], "CF": [9, 19], "AM": [10], "LM": [11]}


@dataclass(frozen=True)
class Club:
    key: str  # "home" | "away"
    name: str
    short: str
    color: str
    players: tuple[str, ...]  # 11 names, assigned in roster order


HOME = Club(
    key="home",
    name="FC Northbridge",
    short="NOR",
    color="#d6262e",
    players=(
        "Tomas Vell", "Idris Calloway", "Mateo Brann", "Kofi Asante-Rhys", "Lukas Hagen",
        "Ruben Saldo", "Noah Fairley", "Emil Strand", "Sami Okoro", "Leo Marchetti", "Jonah Pike",
    ),
)
AWAY = Club(
    key="away",
    name="Harbour City",
    short="HCY",
    color="#1f5fbf",
    players=(
        "Arne Dahl", "Marcus Quill", "Yusuf Benali", "Dario Kesh", "Oscar Lindqvist",
        "Felix Ondo", "Callum Reyes", "Theo Varga", "Ilan Moreau", "Kai Nakamura", "Bastian Holt",
    ),
)


def assign(club: Club, grf_roles: list[int]) -> list[tuple[str, str, int, str]]:
    """Return (player_id, name, shirt number, position) per GRF player index."""
    used: dict[str, int] = {}
    spare = iter(range(20, 40))
    out = []
    for i, role in enumerate(grf_roles):
        position = GRF_POSITIONS[role]
        options = _NUMBERS[position]
        k = used.get(position, 0)
        used[position] = k + 1
        number = options[k] if k < len(options) else next(spare)
        player_id = f"{'H' if club.key == 'home' else 'A'}{number}"
        out.append((player_id, club.players[i % len(club.players)], number, position))
    return out
