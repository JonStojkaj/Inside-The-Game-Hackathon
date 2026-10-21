"""Live replay of an exported match: frames, events, moments, stats and overlays in match time.

Same idea as app.source.replayer, but driven by the export files, so the API needs neither
the raw recording nor the stats engine at request time.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ExportedMatch:
    meta: dict[str, Any]
    frames: dict[str, list]
    events: list[dict[str, Any]]
    moments: list[dict[str, Any]]
    stats: list[dict[str, Any]]
    overlays: dict[str, list[dict[str, Any]]]

    @classmethod
    def load(cls, folder: Path) -> ExportedMatch:
        def read(name: str, default: Any) -> Any:
            path = folder / name
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

        return cls(
            meta=read("match.json", {}),
            frames=read("frames.json", {}),
            events=read("events.json", []),
            moments=read("moments.json", []),
            stats=read("stats.json", []),
            overlays=read("overlays.json", {}),
        )

    def frame_message(self, f: int) -> dict[str, Any]:
        fr = self.frames
        return {
            "type": "frame",
            "frame": f,
            "t_ms": fr["t_ms"][f],
            "ball": fr["ball"][f],
            "players": fr["players"][f],
            "owner": fr["owner"][f],
            "score": fr["score"][f],
            "mode": fr["mode"][f],
        }

    def overlays_for(self, segment: str | None) -> list[dict[str, Any]]:
        """All overlays when `segment` is None (control room), else that segment's plus the "*" ones."""
        if segment is None:
            return [o for items in self.overlays.values() for o in items]
        return [*self.overlays.get(segment, []), *self.overlays.get("*", [])]


async def live_messages(
    match: ExportedMatch,
    speed: float = 10.0,
    step: int = 1,
    start_frame: int = 0,
    segment: str | None = None,
    realtime: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    """Yield replay messages in match-time order.

    Every `step`-th frame is sent; events, moments and stats snapshots at their frame, and
    overlays once their `start_ms` is reached (never skipped by `step`). speed=10 plays ten
    times faster than real time; realtime=False yields as fast as the consumer reads.
    """
    n = len(match.frames.get("t_ms", []))
    t_ms = match.frames.get("t_ms", [])
    by_frame: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for e in match.events:
        by_frame[e["frame"]].append({"type": "event", "event": e})
    for m in match.moments:
        by_frame[m["frame"]].append({"type": "moment", "moment": m})
    for s in match.stats:
        by_frame[s["frame"]].append({"type": "stats", "stats": s})
    overlays = sorted(match.overlays_for(segment), key=lambda o: o["start_ms"])
    start_ms = t_ms[start_frame] if start_frame < n else 0
    overlays = [o for o in overlays if o["start_ms"] + o.get("duration_ms", 0) > start_ms]
    next_overlay = 0

    yield {"type": "hello", "match": match.meta, "speed": speed, "step": step, "start_frame": start_frame,
           "segment": segment}
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    for f in range(start_frame, n):
        if realtime:
            delay = t0 + (t_ms[f] - start_ms) / 1000 / speed - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
        if (f - start_frame) % step == 0 or f == n - 1:
            yield match.frame_message(f)
        for msg in by_frame.get(f, ()):
            yield msg
        while next_overlay < len(overlays) and overlays[next_overlay]["start_ms"] <= t_ms[f]:
            yield {"type": "overlay", "overlay": overlays[next_overlay]}
            next_overlay += 1
    yield {"type": "end", "frame": n - 1}
