"""Stream a recorded match onto the event bus as if it were happening live."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from app.bus.memory import EventBus
from app.models import MatchEvent
from app.source.grf import STEP_S, GrfMatch

FRAMES = "frames"
EVENTS = "events"


def publish_frame(event: MatchEvent) -> int:
    """First frame at which `event` (including its outcome) is known: no lookahead in live mode."""
    return max(event.frame, int(event.meta.get("known_frame", event.frame)))


async def replay(
    match: GrfMatch,
    events: list[MatchEvent],
    bus: EventBus,
    speed: float = 1.0,
    start_frame: int = 0,
    end_frame: int | None = None,
    realtime: bool = True,
) -> None:
    """Publish every frame (10 Hz of match time) and each event once it is knowable.

    An event is published at `publish_frame(event)`: its own frame, or later when its outcome is
    only decided later (a pass is complete when received, a shot is a goal when the score changes).
    The event keeps its original frame/t_ms, so consumers still see when the action started.

    speed=10 plays ten times faster than real time; realtime=False publishes as
    fast as consumers keep up (tests, batch processing).
    """
    end = match.n_frames if end_frame is None else min(end_frame, match.n_frames)
    by_frame: dict[int, list[MatchEvent]] = defaultdict(list)
    for event in sorted(events, key=lambda e: (publish_frame(e), e.frame)):
        by_frame[publish_frame(event)].append(event)

    loop = asyncio.get_running_loop()
    t0 = loop.time()
    for frame in range(start_frame, end):
        if realtime:
            due = t0 + (frame - start_frame) * STEP_S / speed
            delay = due - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
        await bus.publish(FRAMES, match.frame_state(frame))
        for event in by_frame.get(frame, ()):
            await bus.publish(EVENTS, event)
    await bus.close()
