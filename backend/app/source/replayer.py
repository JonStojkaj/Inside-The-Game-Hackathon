"""Stream a recorded match onto the event bus as if it were happening live."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from app.bus.memory import EventBus
from app.models import MatchEvent
from app.source.grf import STEP_S, GrfMatch

FRAMES = "frames"
EVENTS = "events"


async def replay(
    match: GrfMatch,
    events: list[MatchEvent],
    bus: EventBus,
    speed: float = 1.0,
    start_frame: int = 0,
    end_frame: int | None = None,
    realtime: bool = True,
) -> None:
    """Publish every frame (10 Hz of match time) and each event at its frame.

    speed=10 plays ten times faster than real time; realtime=False publishes as
    fast as consumers keep up (tests, batch processing).
    """
    end = match.n_frames if end_frame is None else min(end_frame, match.n_frames)
    by_frame: dict[int, list[MatchEvent]] = defaultdict(list)
    for event in events:
        by_frame[event.frame].append(event)

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
