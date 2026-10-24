"""Inputs of the commentator: one exported match (data/export/<id>/) and the fictional league table.

Everything is read from the export (the same files the web player uses), so the commentator never needs the raw
recording, the stats engine or the simulator at request time. The league (frontend/public/league.json, also baked
into frontend/dist) gives table stakes and rivals for the club fan; without it those lines are simply skipped.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TEAMS = ("home", "away")


def other(team: str) -> str:
    return "away" if team == "home" else "home"


@dataclass(frozen=True)
class Player:
    id: str
    team: str
    name: str
    number: int
    position: str

    @property
    def surname(self) -> str:
        return self.name.split(" ", 1)[-1] if " " in self.name else self.name


@dataclass
class Event:
    """A MatchEvent as exported, plus the time it is *known* (a pass is complete only once received)."""

    id: str
    t_ms: int
    known_ms: int
    frame: int
    type: str
    team: str | None
    player_id: str | None
    target_id: str | None
    start_xy: tuple[float, float] | None
    outcome: str | None
    meta: dict[str, Any]


@dataclass
class MatchData:
    match_id: str
    clubs: dict[str, dict[str, str]]  # home/away -> {name, short, ...}
    players: dict[str, Player]
    fps: int
    duration_ms: int
    clock_scale: float
    final_score: tuple[int, int]
    events: list[Event]
    stats: list[dict[str, Any]]  # one snapshot per second of match time
    moments: list[dict[str, Any]]
    insights: dict[str, dict[str, Any]]  # moment_id -> insight (ghost paths dropped)
    league: League | None = None

    def club_name(self, team: str) -> str:
        """Spoken club name: 'FC Northbridge' -> 'Northbridge'."""
        name = self.clubs[team]["name"]
        for affix in ("FC ", " FC", "SC ", " SC"):
            name = name.replace(affix, "")
        return name.strip()

    def minute(self, t_ms: int) -> int:
        return max(1, min(90, math.ceil(t_ms / 1000 * self.clock_scale / 60)))

    def stats_at(self, t_ms: int) -> dict[str, Any] | None:
        if not self.stats:
            return None
        return self.stats[max(0, min(len(self.stats) - 1, t_ms // 1000))]

    def score_at(self, t_ms: int) -> tuple[int, int]:
        score = (0, 0)
        for e in self.events:
            if e.known_ms > t_ms:
                break
            if e.type == "goal" and "score" in e.meta:
                score = (int(e.meta["score"][0]), int(e.meta["score"][1]))
        return score

    def goalkeeper(self, team: str) -> Player | None:
        return next((p for p in self.players.values() if p.team == team and p.position == "GK"), None)


def _event(raw: dict[str, Any], fps: int) -> Event:
    meta = dict(raw.get("meta") or {})
    known = max(int(raw["frame"]), int(meta.get("known_frame", raw["frame"])))
    xy = raw.get("start_xy")
    return Event(
        id=raw["id"], t_ms=int(raw["t_ms"]), known_ms=int(round(known * 1000 / fps)), frame=int(raw["frame"]),
        type=raw["type"], team=raw.get("team"), player_id=raw.get("player_id"), target_id=raw.get("target_id"),
        start_xy=(float(xy[0]), float(xy[1])) if xy else None, outcome=raw.get("outcome"), meta=meta,
    )


def load_match(folder: str | Path, league: League | None = None) -> MatchData:
    folder = Path(folder)

    def read(name: str, default: Any) -> Any:
        path = folder / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default

    meta = read("match.json", None)
    if meta is None:
        raise FileNotFoundError(folder / "match.json")
    fps = int(meta.get("fps", 10))
    events = sorted((_event(e, fps) for e in read("events.json", [])), key=lambda e: (e.known_ms, e.frame, e.id))
    insights = {}
    for ins in read("insights.json", []):
        if ins.get("verified", True) and ins.get("moment_id"):
            insights[ins["moment_id"]] = {k: v for k, v in ins.items() if k not in ("ghost_paths", "alt_ghost_paths")}
    return MatchData(
        match_id=meta["match_id"],
        clubs={t: meta[t] for t in TEAMS},
        players={p["id"]: Player(p["id"], p["team"], p["name"], int(p["number"]), p["position"]) for p in meta["players"]},
        fps=fps,
        duration_ms=int(meta.get("duration_ms", 0)),
        clock_scale=float(meta.get("clock_scale", 1.0)),
        final_score=(int(meta.get("final_score", [0, 0])[0]), int(meta.get("final_score", [0, 0])[1])),
        events=events,
        stats=read("stats.json", []),
        moments=read("moments.json", []),
        insights=insights,
        league=league,
    )


# ------------------------------------------------------------------------------------------------ league


@dataclass
class League:
    """Standings before this match (fictional). Same ranking as frontend/src/lib/league.ts:
    points, goal difference, goals scored, name. Only this match is live."""

    clubs: list[dict[str, Any]]
    season_ratings: dict[str, float] = field(default_factory=dict)
    default_rating: float = 6.6

    @classmethod
    def load(cls, path: str | Path) -> League | None:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(raw.get("clubs"), list):
            return None
        return cls(raw["clubs"], raw.get("season_ratings", {}), float(raw.get("default_rating", 6.6)))

    def club(self, short: str) -> dict[str, Any] | None:
        return next((c for c in self.clubs if c["short"] == short), None)

    def table(self, home: str, away: str, score: tuple[int, int] | None) -> list[dict[str, Any]]:
        """Rows sorted by rank, with this match counted as ending at `score` (None = before the match)."""
        rows = []
        for c in self.clubs:
            r = dict(c)
            if score is not None and c["short"] in (home, away):
                us, them = score if c["short"] == home else (score[1], score[0])
                r.update(played=c["played"] + 1, gf=c["gf"] + us, ga=c["ga"] + them, won=c["won"] + (us > them),
                         drawn=c["drawn"] + (us == them), lost=c["lost"] + (us < them))
            r["pts"] = r["won"] * 3 + r["drawn"]
            r["gd"] = r["gf"] - r["ga"]
            rows.append(r)
        rows.sort(key=lambda r: (-r["pts"], -r["gd"], -r["gf"], r["name"]))
        for i, r in enumerate(rows):
            r["pos"] = i + 1
        return rows

    def position(self, short: str, home: str, away: str, score: tuple[int, int] | None) -> int:
        return next(r["pos"] for r in self.table(home, away, score) if r["short"] == short)

    def points(self, short: str, home: str, away: str, score: tuple[int, int] | None) -> int:
        return next(r["pts"] for r in self.table(home, away, score) if r["short"] == short)

    def stakes(self, team: str, home: str, away: str, score: tuple[int, int]) -> dict[str, int]:
        """Final position of `team` if the match ended a one-goal win / draw / one-goal loss from the current score."""
        base = max(score)

        def outcome(d: int) -> tuple[int, int]:
            us, them = (base + 1, base) if d > 0 else (base, base) if d == 0 else (base, base + 1)
            return (us, them) if team == "home" else (them, us)

        short = home if team == "home" else away
        return {k: self.position(short, home, away, outcome(d)) for k, d in (("win", 1), ("draw", 0), ("loss", -1))}


def find_league(candidates: list[Path]) -> League | None:
    for path in candidates:
        if path.is_file():
            league = League.load(path)
            if league is not None:
                return league
    return None
