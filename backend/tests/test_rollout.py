import numpy as np
import pytest

from app.models import Intervention
from app.rollout.engine import RolloutEngine, expected_goals
from app.rollout.scenarios import final_third_attack

engine = RolloutEngine()


def test_xg_decreases_with_distance():
    pos = np.array([[99.0, 34.0], [94.0, 34.0], [80.0, 34.0]])
    xg = expected_goals(pos, np.array([True, True, True]), np.zeros(3))
    assert xg[0] > xg[1] > xg[2]
    assert 0.45 < xg[0] < 0.7  # ~6 m central
    assert xg[2] < 0.1  # ~25 m


def test_deterministic_with_seed():
    state = final_third_attack()
    a = engine.run(state, n=200, seed=7)
    b = engine.run(state, n=200, seed=7)
    assert a.p_goal_for == b.p_goal_for
    assert a.sample_paths == b.sample_paths


def test_probabilities_are_consistent():
    r = engine.run(final_third_attack(), n=500, seed=1)
    total = r.p_goal_for + r.p_goal_against + r.p_retained
    assert total <= 1.0 + 1e-9
    assert 0.0 <= r.outcome_entropy <= 1.0
    assert len(r.sample_paths) == 50


def test_close_range_shot_beats_long_range_shot():
    shoot = Intervention(kind="swap_action", params={"action": "shoot"})
    near = engine.run(final_third_attack("H9", (97.0, 34.0)), n=1000, seed=3, intervention=shoot)
    far = engine.run(final_third_attack("H9", (75.0, 34.0)), n=1000, seed=3, intervention=shoot)
    assert near.p_goal_for > far.p_goal_for + 0.2


def _p_goal(intervention: Intervention | None) -> float:
    state = final_third_attack()
    return sum(engine.run(state, n=1000, seed=s, intervention=intervention).p_goal_for for s in (11, 12, 13)) / 3


def test_through_ball_beats_long_shot():
    # The kind of statement the demo makes: "the pass was ~3x better than shooting".
    through = _p_goal(Intervention(kind="swap_action", params={"action": "pass", "target_id": "H9"}))
    shot = _p_goal(Intervention(kind="swap_action", params={"action": "shoot"}))
    assert through > 2 * shot


def test_back_pass_lowers_goal_chance():
    back = _p_goal(Intervention(kind="swap_action", params={"action": "pass", "target_id": "H3"}))
    assert back < _p_goal(None)


def test_requires_ball_owner():
    state = final_third_attack()
    state.ball.owner_id = None
    with pytest.raises(ValueError):
        engine.run(state, n=10)
