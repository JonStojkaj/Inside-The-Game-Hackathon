"""Overlay scheduler (stage d): deterministic rules that turn candidates into a timed Overlay list.

Rules (per segment):
  * at most MAX_VISIBLE pop-up overlays on screen at once, at most one per slot
  * persistent elements (scorebug momentum, side-panel cards) live in their own slots and replace
    themselves; they do not count towards MAX_VISIBLE
  * higher priority is placed first; a lower-priority candidate that no longer fits is dropped
  * every overlay stays up for at least its min_duration_ms, or is not shown at all
  * timing "live"      start within max_delay_ms of the cue (event cards, alerts, tags)
           "calm"      like live, but never on screen during an attack (stat cards)
           "stoppage"  starts only in a dead-ball window (ball out, set piece, after a goal, full time)
                       and must be gone before the next attack: Sliding Doors / insights, like a
                       broadcast replay that waits for the next stoppage

Times are replay milliseconds on the same timeline as MatchEvent.t_ms.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models import PITCH_LENGTH, FrameState, MatchEvent, Overlay, OverlaySlot, OverlayType

MAX_VISIBLE = 2
PERSISTENT_SLOTS: set[str] = {"scorebug", "side_panel"}
ATTACK_THIRD_M = PITCH_LENGTH / 3
ATTACK_MERGE_MS = 1_000  # attack phases closer than this are one attack
STOPPAGE_MS = 8_000  # how long after the whistle a stoppage overlay may still start
POST_MATCH_MS = 8_000  # full-time window before the recap takes over

Timing = Literal["live", "calm", "stoppage", "persistent"]


class Timeline(BaseModel):
    """Match phases the scheduler needs: attacks (no insights) and dead-ball windows."""

    end_ms: int
    attacks: list[tuple[int, int]] = Field(default_factory=list)  # [start, end)
    stoppages: list[tuple[int, int]] = Field(default_factory=list)  # (whistle, latest start)

    def next_attack_start(self, t_ms: int) -> int | None:
        return next((a for a, _ in self.attacks if a >= t_ms), None)

    def overlaps_attack(self, start: int, end: int) -> bool:
        return any(a < end and start < b for a, b in self.attacks)

    def stoppage_at(self, t_ms: int) -> tuple[int, int] | None:
        return next(((s, e) for s, e in self.stoppages if s <= t_ms <= e), None)


def build_timeline(frames: Sequence[FrameState], events: Sequence[MatchEvent]) -> Timeline:
    """Attack = a team has the ball in its attacking third. Stoppage = ball out / set piece / goal, until the
    next attack starts or STOPPAGE_MS have passed; plus the window after the final whistle."""
    team_of = {p.id: p.team for p in frames[0].players} if frames else {}
    attacks: list[list[int]] = []
    for f in frames:
        owner = team_of.get(f.ball.owner_id or "")
        attacking = (owner == "home" and f.ball.x >= PITCH_LENGTH - ATTACK_THIRD_M) or \
                    (owner == "away" and f.ball.x <= ATTACK_THIRD_M)
        if not attacking:
            continue
        if attacks and f.t_ms - attacks[-1][1] <= ATTACK_MERGE_MS:
            attacks[-1][1] = f.t_ms + 100
        else:
            attacks.append([f.t_ms, f.t_ms + 100])
    end_ms = frames[-1].t_ms if frames else max((e.t_ms for e in events), default=0)
    timeline = Timeline(end_ms=end_ms, attacks=[(a, b) for a, b in attacks])
    stoppages = []
    for e in events:
        if e.type in ("out_of_play", "goal", "set_piece"):
            nxt = timeline.next_attack_start(e.t_ms)
            latest = e.t_ms + STOPPAGE_MS if nxt is None else min(e.t_ms + STOPPAGE_MS, nxt)
            stoppages.append((e.t_ms, latest))
    stoppages.append((end_ms, end_ms + POST_MATCH_MS))
    timeline.stoppages = sorted(set(stoppages))
    return timeline


class Candidate(BaseModel):
    """Something a segment could see, before the scheduler decides when (and whether) it does."""

    id: str
    type: OverlayType
    slot: OverlaySlot
    ready_ms: int  # earliest start: cue time, or cue time + analysis latency for insights
    duration_ms: int
    min_duration_ms: int
    priority: int
    timing: Timing = "live"
    max_delay_ms: int = 3_000
    lang: str = "en"
    headline: str = ""
    body: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)


class ScheduleResult(BaseModel):
    overlays: list[Overlay]
    dropped: list[str]  # candidate ids that did not fit


class _Placed(BaseModel):
    start: int
    end: int
    slot: str


def _visible_ok(placed: list[_Placed], start: int, end: int, slot: str) -> bool:
    overlapping = [p for p in placed if p.start < end and start < p.end]
    if any(p.slot == slot for p in overlapping):
        return False
    # count concurrent overlays at every point where the count can change inside [start, end)
    points = {start} | {p.start for p in overlapping if start < p.start < end}
    return all(sum(p.start <= t < p.end for p in overlapping) < MAX_VISIBLE for t in points)


def _latest_end(c: Candidate, start: int, timeline: Timeline, placed: list[_Placed]) -> int:
    end = start + c.duration_ms
    if c.timing in ("calm", "stoppage"):
        nxt = timeline.next_attack_start(start)
        if nxt is not None:
            end = min(end, nxt)
    # shrink to end where a conflict would begin (same slot, or the screen gets full)
    for p in sorted(placed, key=lambda p: p.start):
        if start < p.start < end and not _visible_ok(placed, start, p.start + 1, c.slot):
            end = p.start
            break
    return end


def _start_options(c: Candidate, timeline: Timeline, placed: list[_Placed]) -> list[int]:
    lo, hi = c.ready_ms, c.ready_ms + c.max_delay_ms
    options = {lo} | {p.end for p in placed if lo <= p.end <= hi} | {b for _, b in timeline.attacks if lo <= b <= hi}
    options |= {max(s, lo) for s, e in timeline.stoppages if max(s, lo) <= min(e, hi)}
    return sorted(options)


def _try_place(c: Candidate, timeline: Timeline, placed: list[_Placed]) -> tuple[int, int] | None:
    for start in _start_options(c, timeline, placed):
        if c.timing == "stoppage" and timeline.stoppage_at(start) is None:
            continue
        if c.timing == "calm" and timeline.overlaps_attack(start, start + 1):
            continue
        end = _latest_end(c, start, timeline, placed)
        if end - start < c.min_duration_ms:
            continue
        if c.timing in ("calm", "stoppage") and timeline.overlaps_attack(start, end):
            continue
        if _visible_ok(placed, start, end, c.slot):
            return start, end
    return None


def _to_overlay(c: Candidate, segment_id: str, match_id: str, start: int, end: int) -> Overlay:
    return Overlay(
        id=f"{segment_id}:{c.id}", match_id=match_id, segment_id=segment_id, start_ms=start, duration_ms=end - start,
        slot=c.slot, type=c.type, priority=c.priority, lang=c.lang, headline=c.headline, body=c.body,
        payload=c.payload, evidence=c.evidence,
    )


def schedule(candidates: Sequence[Candidate], timeline: Timeline, segment_id: str, match_id: str) -> ScheduleResult:
    overlays: list[Overlay] = []
    dropped: list[str] = []

    # persistent elements: each one stays until the next one in the same slot replaces it
    persistent = sorted((c for c in candidates if c.timing == "persistent"), key=lambda c: (c.slot, c.ready_ms))
    for i, c in enumerate(persistent):
        nxt = persistent[i + 1] if i + 1 < len(persistent) and persistent[i + 1].slot == c.slot else None
        end = nxt.ready_ms if nxt else max(c.ready_ms + c.duration_ms, timeline.end_ms)
        if end > c.ready_ms:
            overlays.append(_to_overlay(c, segment_id, match_id, c.ready_ms, end))

    placed: list[_Placed] = []
    popups = sorted((c for c in candidates if c.timing != "persistent"), key=lambda c: (-c.priority, c.ready_ms, c.id))
    for c in popups:
        if c.slot in PERSISTENT_SLOTS:
            raise ValueError(f"{c.id}: slot {c.slot} is reserved for persistent elements")
        spot = _try_place(c, timeline, placed)
        if spot is None:
            dropped.append(c.id)
            continue
        placed.append(_Placed(start=spot[0], end=spot[1], slot=c.slot))
        overlays.append(_to_overlay(c, segment_id, match_id, *spot))
    overlays.sort(key=lambda o: (o.start_ms, -o.priority, o.id))
    return ScheduleResult(overlays=overlays, dropped=dropped)
