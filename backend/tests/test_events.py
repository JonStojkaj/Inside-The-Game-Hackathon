import numpy as np
from conftest import own

from app.source.events import derive_events


def types(events, kind):
    return [e for e in events if e.type == kind]


def test_completed_pass(match):
    own(match, 5, 0, 9)
    own(match, 7, 15, 25)
    passes = types(derive_events(match), "pass")
    assert len(passes) == 1
    p = passes[0]
    assert (p.player_id, p.target_id, p.outcome, p.team) == ("H6", "H8", "complete", "home")
    assert p.meta["distance_m"] > 0


def test_intercepted_pass(match):
    own(match, 5, 0, 9)
    own(match, 15, 16, 25)
    events = derive_events(match)
    assert [p.outcome for p in types(events, "pass")] == ["incomplete"]
    interceptions = types(events, "interception")
    assert len(interceptions) == 1 and interceptions[0].player_id == "A5"


def test_tackle_when_players_are_together(match):
    match.pos[:, 15] = match.pos[:, 5] + [1.0, 0.0]  # opponent right next to the carrier
    own(match, 5, 0, 9)
    own(match, 15, 10, 25)
    events = derive_events(match)
    tackles = types(events, "tackle")
    assert len(tackles) == 1
    assert (tackles[0].player_id, tackles[0].target_id) == ("A5", "H6")
    assert not types(events, "interception")


def test_goal_and_shot(match):
    match.pos[:, 9] = [90.0, 34.0]  # home striker 15 m from goal
    own(match, 9, 0, 9)
    match.ball_vel[10:13, :2] = [25.0, 0.0]  # 90 km/h straight at goal
    match.score[12:] = [1, 0]
    own(match, 11, 20, 30)  # away keeper restarts
    events = derive_events(match)
    shots = types(events, "shot")
    assert len(shots) == 1 and shots[0].outcome == "goal"
    assert shots[0].meta["shot_speed_kmh"] == 90.0
    goals = types(events, "goal")
    assert [(g.team, g.player_id) for g in goals] == [("home", "H10")]


def test_live_replay_never_publishes_an_outcome_before_it_happens(match):
    import asyncio

    from app.source.replayer import EVENTS, FRAMES, publish_frame, replay

    match.pos[:, 9] = [90.0, 34.0]
    own(match, 9, 0, 9)
    match.ball_vel[10:13, :2] = [25.0, 0.0]
    match.score[12:] = [1, 0]  # the ball crosses the line at frame 12
    own(match, 11, 20, 30)
    events = derive_events(match)

    class Recorder:
        def __init__(self):
            self.log: list[tuple[str, object]] = []

        async def publish(self, topic, message):
            self.log.append((topic, message))

        async def close(self):
            pass

    bus = Recorder()
    asyncio.run(replay(match, events, bus, realtime=False))  # type: ignore[arg-type]
    frame_now = -1
    for topic, msg in bus.log:
        if topic == FRAMES:
            frame_now += 1
        elif topic == EVENTS:
            assert frame_now >= publish_frame(msg) >= msg.frame  # type: ignore[attr-defined]
    shot = types(events, "shot")[0]
    assert shot.frame == 9 and publish_frame(shot) == 12  # released at 9, known to be a goal at 12
    complete = [i for i, (t, m) in enumerate(bus.log) if t == EVENTS and m is shot][0]
    assert sum(t == FRAMES for t, _ in bus.log[:complete]) == 13  # frames 0..12 went out first


def test_pressure_needs_sustained_closeness(match):
    match.pos[:, 15] = match.pos[:, 5] + [2.0, 0.0]
    own(match, 5, 0, 20)
    pressure = types(derive_events(match), "pressure")
    assert len(pressure) == 1
    assert (pressure[0].player_id, pressure[0].target_id) == ("A5", "H6")


def test_events_sorted_by_frame(match):
    own(match, 5, 0, 9)
    own(match, 7, 15, 25)
    own(match, 15, 30, 39)
    frames = [e.frame for e in derive_events(match)]
    assert frames == sorted(frames)
    assert np.all(np.diff(frames) >= 0)
