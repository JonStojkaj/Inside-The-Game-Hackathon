import numpy as np

from app.models import MatchEvent
from app.stats.metrics import control_chaos, lane_clearance, pass_difficulty, pressure_index, rhythm, threat


def ev(i, type_, team="home", outcome=None, t_ms=0):
    return MatchEvent(id=str(i), match_id="m", t_ms=t_ms, frame=0, type=type_, team=team, outcome=outcome)


def test_threat_grows_towards_goal_and_respects_direction():
    assert threat(100, 34, True) > threat(80, 34, True) > threat(50, 34, True)
    assert threat(100, 34, False) < 0.01  # far from the goal home attacks... for away it is their own goal
    assert abs(threat(5, 34, False) - threat(100, 34, True)) < 1e-9  # symmetric


def test_lane_clearance():
    opponents = np.array([[10.0, 2.0], [30.0, 30.0]])
    assert abs(lane_clearance((0, 0), (20, 0), opponents) - 2.0) < 1e-9
    assert lane_clearance((0, 0), (5, 0), np.array([[10.0, 0.0]])) == 5.0  # beyond the end of the lane


def test_pass_difficulty_orders_passes_sensibly():
    easy = pass_difficulty(distance_m=8, lane_m=10, receiver_open_m=10, passer_pressure_m=10)
    hard = pass_difficulty(distance_m=35, lane_m=0.5, receiver_open_m=1, passer_pressure_m=1)
    assert 0 <= easy < 20 < 70 < hard <= 100


def test_pressure_index():
    carrier = (50.0, 34.0)
    assert pressure_index(carrier, np.array([[80.0, 34.0]])) == 0.0
    assert abs(pressure_index(carrier, np.array([[51.0, 34.0], [50.0, 37.5]])) - (0.8 + 0.3)) < 1e-9


def test_control_vs_chaos():
    calm = [ev(i, "pass", outcome="complete") for i in range(30)]
    wild = [ev(i, "interception" if i % 2 else "tackle", team="away") for i in range(30)]
    c, w = control_chaos(calm, 300), control_chaos(wild, 300)
    assert c["chaos"] < 0.2 < 0.6 < w["chaos"]
    assert c["control_team"] == "home" and c["control_share"] == 1.0


def test_rhythm_trend():
    fast = [ev(i, "pass") for i in range(60)]
    slow = [ev(i, "pass") for i in range(20)]
    assert rhythm(fast, slow, 300)["trend"] == "rising"
    assert rhythm(slow, fast, 300)["trend"] == "falling"
    assert rhythm(slow, slow, 300)["actions_per_min"] == 4.0
