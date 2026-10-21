from app.models import MatchEvent
from app.stats.moments import detect_moments


def ev(id_, type_, frame, team="home", outcome=None, meta=None, start_xy=None, player="H9", target=None):
    return MatchEvent(id=id_, match_id="m", t_ms=frame * 100, frame=frame, type=type_, team=team, outcome=outcome,
                      meta=meta or {}, start_xy=start_xy, player_id=player, target_id=target)


def test_goal_beats_nearby_pass_and_kinds_are_detected():
    events = [
        ev("p1", "pass", 100, outcome="complete", meta={"threat_gain": 0.08, "difficulty": 40}, target="H10"),
        ev("s1", "shot", 120, outcome="goal", meta={"xg": 0.3, "distance_m": 12}),  # 2 s later: same moment
        ev("s2", "shot", 1000, outcome="saved", meta={"xg": 0.2, "distance_m": 14}),
        ev("s3", "shot", 2000, outcome="off_target", meta={"xg": 0.05, "distance_m": 28}),  # not a big chance
        ev("t1", "interception", 3000, team="away", start_xy=(12.0, 34.0), player="A4", target="H2"),
        ev("t2", "interception", 4000, team="away", start_xy=(60.0, 34.0), player="A4", target="H2"),  # midfield
    ]
    moments = detect_moments(events)
    assert [m.kind for m in moments] == ["goal", "big_chance", "dangerous_turnover"]
    goal = moments[0]
    assert goal.score == 1.0 and goal.event_ids == ["s1"]
    turnover = moments[2]
    assert turnover.team == "away" and turnover.player_ids == ["H2", "A4"]


def test_limit_keeps_most_important_but_returns_chronological():
    events = [
        ev("a", "shot", 100, outcome="saved", meta={"xg": 0.13, "distance_m": 15}),
        ev("b", "shot", 900, outcome="goal", meta={"xg": 0.2, "distance_m": 10}),
        ev("c", "shot", 1800, outcome="saved", meta={"xg": 0.4, "distance_m": 6}),
    ]
    moments = detect_moments(events, limit=2)
    assert [m.event_ids[0] for m in moments] == ["b", "c"]
