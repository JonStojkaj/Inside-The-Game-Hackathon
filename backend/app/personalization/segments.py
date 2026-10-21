"""Viewer segments (stage e): who sees what, how deep, from whose side, in which language.

Production runs once per *segment* (mode x focus x language), never per viewer, so the cost of a
match does not grow with the audience. A segment bundles the five personalisation dimensions of
PLAN.md §8 as plain rules:

  selection     which moments / live cues are relevant (and how much: a base priority)
  depth         deep (numbers, full Sliding Doors view) | medium | light (one line)
  perspective   neutral | partisan ("we") | player (from the followed player's side)
  persistent    elements that stay on screen: momentum bar, player card, "my metric" card
  alerts        sprints and milestones, filtered to what the segment cares about

Rules are deterministic; the Producer agent may only fine-tune what the rules let through.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models import Moment, Team, ViewerProfile

Depth = Literal["deep", "medium", "light"]
Perspective = Literal["neutral", "partisan", "player"]
Persistent = Literal["momentum", "player_card", "metric_card"]
AlertKind = Literal["sprint", "milestone"]

# Cue kinds produced by app.overlay.cues (live, code-only graphics)
CueKind = Literal[
    "goal", "shot", "turnover", "key_pass", "sprint", "milestone", "stat", "momentum", "player_card",
    "metric_card", "player_tag",
]

# Duration-independent stats only: GRF plays 5 minutes on a 90' clock, so totals (km, pass counts) lie.
TEAM_STATS = ("possession", "pass_accuracy", "avg_pass_distance", "pass_difficulty", "pressing", "max_shot_speed")
METRICS = ("pass_difficulty", "pressure_index", "possession", "pass_accuracy", "top_speed", "chaos")


class Segment(BaseModel):
    profile: ViewerProfile
    depth: Depth
    perspective: Perspective
    tone: str  # instruction for the Narrator / Recap agents
    stat_keys: list[str] = Field(default_factory=list)  # stat-card rotation
    persistent: list[Persistent] = Field(default_factory=list)
    alerts: list[AlertKind] = Field(default_factory=list)
    sliding_doors_view: Literal["full", "one_line"] = "one_line"
    player_team: Team | None = None  # club of the followed player (player focus)

    @property
    def id(self) -> str:
        return self.profile.segment_id

    @property
    def mode(self) -> str:
        return self.profile.mode

    @property
    def language(self) -> str:
        return self.profile.language

    @property
    def club(self) -> Team | None:
        return self.profile.favourite_club if self.mode == "club_fan" else None

    @property
    def player(self) -> str | None:
        return self.profile.favourite_players[0] if self.mode == "player_focus" and self.profile.favourite_players else None

    @property
    def metric(self) -> str | None:
        return self.profile.my_metric if self.profile.my_metric in METRICS else None


_MODE_RULES: dict[str, dict] = {
    "analyst": {
        "depth": "deep", "perspective": "neutral", "sliding_doors_view": "full",
        "tone": "precise, neutral and tactical, like a TV match analyst; numbers are welcome; no hype",
        "stat_keys": ["pass_difficulty", "pressing", "possession", "pass_accuracy", "avg_pass_distance", "max_shot_speed"],
        "persistent": ["momentum", "metric_card"], "alerts": ["milestone"],
    },
    "club_fan": {
        "depth": "light", "perspective": "partisan", "sliding_doors_view": "one_line",
        "tone": "passionate and partisan, first person plural ('we', 'our', 'us') for the viewer's club; "
                "one punchy line; celebrate our moments, lament theirs; never insulting",
        "stat_keys": ["possession", "pass_accuracy", "max_shot_speed"],
        "persistent": ["momentum", "metric_card"], "alerts": ["sprint", "milestone"],
    },
    "player_focus": {
        "depth": "medium", "perspective": "player", "sliding_doors_view": "full",
        "tone": "personal and close to the followed player, judging every decision from that player's side; "
                "warm but honest; refer to the player by surname",
        "stat_keys": [], "persistent": ["momentum", "player_card"], "alerts": ["sprint", "milestone"],
    },
    "casual": {
        "depth": "light", "perspective": "neutral", "sliding_doors_view": "one_line",
        "tone": "friendly and simple, no jargon, one short sentence a newcomer understands",
        "stat_keys": ["possession"], "persistent": ["momentum"], "alerts": ["milestone"],
    },
}


def build_segment(profile: ViewerProfile) -> Segment:
    player_team: Team | None = None
    if profile.mode == "player_focus" and profile.favourite_players:
        # roster convention (app.source.roster): ids are "H<number>" for home, "A<number>" for away
        player_team = "home" if profile.favourite_players[0].startswith("H") else "away"
    return Segment(profile=profile, player_team=player_team, **_MODE_RULES[profile.mode])


# The demo match: FC Northbridge (home) vs Harbour City (away). A20 = Kai Nakamura, the most involved
# player of the demo recording (goal 42', decisive pass 50', 15 actions on the ball).
DEMO_PLAYER = "A20"

DEMO_PROFILES: list[ViewerProfile] = [
    ViewerProfile(mode="analyst", language="en", my_metric="pass_difficulty"),
    ViewerProfile(mode="analyst", language="de", my_metric="pressure_index"),
    ViewerProfile(mode="club_fan", language="en", favourite_club="home", my_metric="possession"),
    ViewerProfile(mode="club_fan", language="de", favourite_club="away", my_metric="possession"),
    ViewerProfile(mode="player_focus", language="es", favourite_players=[DEMO_PLAYER], my_metric="top_speed"),
    ViewerProfile(mode="casual", language="en"),
]


def demo_segments() -> list[Segment]:
    return [build_segment(p) for p in DEMO_PROFILES]


# --- selection rules ----------------------------------------------------------------------------

def side(segment: Segment, team: str | None) -> Literal["for", "against", "neutral"]:
    """Is something that happened to `team` good or bad news for this segment?"""
    focus = segment.club or segment.player_team
    if focus is None or team is None:
        return "neutral"
    return "for" if team == focus else "against"


# base relevance (0..1) per moment kind; for club fans split by whose moment it was
_ANALYST_W = {"goal": 1.0, "big_chance": 0.8, "decisive_pass": 0.9, "dangerous_turnover": 0.9}
_FAN_W = {
    ("goal", "for"): 1.0, ("goal", "against"): 0.7,
    ("big_chance", "for"): 0.8, ("big_chance", "against"): 0.4,
    ("decisive_pass", "for"): 0.6,
    ("dangerous_turnover", "for"): 0.6, ("dangerous_turnover", "against"): 0.5,
}
_CASUAL_W = {"goal": 0.9, "big_chance": 0.6}


def moment_relevance(segment: Segment, moment: Moment) -> float | None:
    """0..1 relevance of a key moment's Sliding Doors insight for this segment; None = not shown."""
    if segment.mode == "analyst":
        return _ANALYST_W.get(moment.kind)
    if segment.mode == "club_fan":
        return _FAN_W.get((moment.kind, side(segment, moment.team)))
    if segment.mode == "player_focus":
        return 1.0 if segment.player in moment.player_ids else None
    return _CASUAL_W.get(moment.kind)


def insight_priority(relevance: float) -> int:
    return round(40 + 50 * relevance)


def cue_priority(segment: Segment, kind: str, team: str | None, players: list[str], data: dict) -> int | None:
    """Base priority 0..100 of a live cue for this segment; None = this segment does not see it."""
    mode, s = segment.mode, side(segment, team)
    mine = segment.player is not None and segment.player in players
    if kind == "goal":
        return 95
    if kind == "player_tag":
        return 55 if mine or data.get("reason") == "goal" else None
    if kind == "shot":
        if mode == "analyst":
            return 60
        if mode == "club_fan":
            return 65 if s == "for" else 45
        if mode == "player_focus":
            return 75 if mine else None
        return 50 if float(data.get("xg", 0)) >= 0.12 else None
    if kind == "turnover":
        if mode == "analyst":
            return 45 if data.get("danger") else None
        if mode == "club_fan":
            return 45 if s == "for" and data.get("danger") else None
        if mode == "player_focus":
            return 60 if mine else None
        return None
    if kind == "key_pass":
        if mode == "analyst":
            return 50 if data.get("decisive") else None
        if mode == "player_focus":
            return 55 if mine else None
        if mode == "club_fan":
            return 40 if s == "for" and data.get("decisive") else None
        return None
    if kind == "sprint":
        if "sprint" not in segment.alerts:
            return None
        if mode == "player_focus":
            return 70 if mine else None
        return 45 if s == "for" else None
    if kind == "milestone":
        if "milestone" not in segment.alerts:
            return None
        if mode == "player_focus":
            return 65 if mine or data.get("scope") == "match" and data.get("milestone") == "first_goal" else None
        if mode == "club_fan":
            return 50 if s == "for" or data.get("scope") == "match" else None
        return 40
    if kind == "stat":
        return 35 if data.get("key") in segment.stat_keys else None
    if kind in ("momentum", "player_card", "metric_card"):
        return 30 if kind in segment.persistent else None
    return None
