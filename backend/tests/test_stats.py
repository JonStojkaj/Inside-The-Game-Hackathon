import asyncio

import numpy as np
from conftest import own

from app.bus.memory import InMemoryBus
from app.source.events import derive_events
from app.source.replayer import EVENTS, FRAMES, replay
from app.stats.engine import StatsEngine


def run_stats(match):
    engine = StatsEngine(match.match_id)
    for f in range(match.n_frames):
        engine.on_frame(match.frame_state(f))
    for e in derive_events(match):
        engine.on_event(e)
    return engine.snapshot()


def test_distance_and_speed(match):
    match.pos[:, 5, 0] = 20.0 + 0.5 * np.arange(match.n_frames)  # 0.5 m per 0.1 s = 5 m/s
    match.vel[:, 5] = [5.0, 0.0]
    h6 = run_stats(match).players["H6"]
    assert abs(h6.distance_m - 0.5 * (match.n_frames - 1)) < 1e-6
    assert abs(h6.top_speed_kmh - 18.0) < 1e-6


def test_reset_jumps_do_not_count_as_running(match):
    match.pos[20:, 5] += [40.0, 0.0]
    assert run_stats(match).players["H6"].distance_m == 0.0


def test_possession_and_passing(match):
    own(match, 5, 0, 9)
    own(match, 7, 15, 24)
    own(match, 15, 30, 39)
    snap = run_stats(match)
    home, away = snap.teams["home"], snap.teams["away"]
    assert abs(home.possession - 20 / 30) < 1e-3 and abs(away.possession - 10 / 30) < 1e-3
    assert (home.passes, home.passes_completed) == (2, 1)
    assert home.pass_accuracy == 0.5
    assert away.interceptions == 1


def test_replay_publishes_every_frame_and_event(match):
    own(match, 5, 0, 9)
    own(match, 7, 15, 25)
    events = derive_events(match)

    async def main():
        bus = InMemoryBus()
        frames_sub, events_sub = bus.subscribe(FRAMES), bus.subscribe(EVENTS)

        async def collect(sub):
            return [m async for m in sub]

        tasks = [asyncio.create_task(collect(frames_sub)), asyncio.create_task(collect(events_sub))]
        await replay(match, events, bus, realtime=False)
        return await asyncio.gather(*tasks)

    frames, published = asyncio.run(main())
    assert len(frames) == match.n_frames
    assert [e.id for e in published] == [e.id for e in events]
