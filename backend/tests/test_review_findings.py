"""Devil's-advocate review (docs/review/devils-advocate.md): failing tests that pin real bugs.

Each test is xfail(strict=True): it documents the correct behaviour, keeps the suite green today,
and turns into an XPASS failure once the bug is fixed, so the marker gets removed with the fix.
"""

import numpy as np
import pytest
from conftest import own

from app.agents import explain
from app.agents.experiments import DecisionContext, ExperimentResult, experiment_menu
from app.agents.explain import (
    AnalystHypothesis,
    AnalystPlan,
    CriticReview,
    CriticVerdict,
    ExplainTeam,
    numbers_are_ours,
)
from app.agents.llm import FakeLLM
from app.models import Intervention, MatchEvent, Moment
from app.rollout.engine import RolloutEngine
from app.rollout.scenarios import final_third_attack
from app.source.events import derive_events
from app.stats.engine import StatsEngine
from app.stats.metrics import control_chaos


def ev(i, type_, t_ms=0, team="home", outcome=None):
    return MatchEvent(id=str(i), match_id="m", t_ms=t_ms, frame=0, type=type_, team=team, outcome=outcome)


# --- event derivation -----------------------------------------------------------------------

# R5 fixed in 0ae244d (passer excluded from intended receivers)
def test_failed_pass_is_never_intended_for_the_passer(match):
    match.pos[:, 15] = match.pos[:, 5] + [3.0, 0.0]  # interceptor 3 m from the passer, ball lost after a loose spell
    own(match, 5, 0, 9)
    own(match, 15, 16, 25)
    failed = [e for e in derive_events(match) if e.type == "pass" and e.outcome == "incomplete"]
    assert failed and failed[0].meta["intended_receiver"] != failed[0].player_id


@pytest.mark.xfail(strict=True, reason="R4: one-touch finishes have no ownership frame in GRF, so the goal is credited to "
                                       "the last owner (full-34 11': CB Felix Ondo 'scores from 20 m at 5 km/h', real finisher A20)")
def test_one_touch_finish_is_credited_to_the_finisher(match):
    own(match, 9, 0, 5)  # H10 rolls the ball slowly to H11 ...
    start, touch = match.ball[5, :2].copy(), match.pos[10, 10].copy()
    for k, f in enumerate(range(6, 11)):
        match.ball[f, :2] = start + (touch - start) * (k + 1) / 5
    for k, f in enumerate(range(11, 15)):  # ... who hits it first time into the goal, without ever "owning" it
        match.ball[f, :2] = touch + (np.array([105.0, 34.0]) - touch) * (k + 1) / 4
    match.ball_vel[1:, :2] = np.diff(match.ball[:, :2], axis=0) / 0.1
    match.score[15:] = [1, 0]
    own(match, 16, 20, 25)  # away kick-off
    goal = next(e for e in derive_events(match) if e.type == "goal")
    assert goal.player_id == "H11"


# --- stats ----------------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="R6: an intercepted pass emits 'pass incomplete' + 'interception'; control_chaos counts both")
def test_one_interception_is_one_possession_change():
    events = [ev(1, "pass", outcome="incomplete"), ev(2, "interception", team="away")]
    assert control_chaos(events, 60.0)["possession_changes_per_min"] == 1.0


@pytest.mark.xfail(strict=True, reason="R3: WINDOW_S = 300 s equals the whole 5-minute GRF match, so the 'previous' window "
                                       "is always empty and rhythm.trend is 'steady' for the entire demo")
def test_rhythm_trend_can_change_within_a_grf_match():
    from conftest import make_match

    m = make_match(3000)
    stats = StatsEngine(m.match_id)
    stats.on_frame(m.frame_state(0))
    for i, t in enumerate(range(0, 150_000, 30_000)):  # quiet first half: 5 actions
        stats.on_event(ev(i, "pass", t_ms=t, outcome="complete"))
    for i, t in enumerate(range(150_000, 299_000, 3_000)):  # frantic second half: 50 actions
        stats.on_event(ev(100 + i, "pass", t_ms=t, outcome="complete"))
    stats.on_frame(m.frame_state(2999))
    assert stats.snapshot().rhythm["trend"] == "rising"


# --- rollout engine + experiments -----------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="R1: carries are nearly tackle-free, so dribbling beats shooting even from the "
                                       "penalty spot; Sliding Doors tells every goal-scorer in full-34 to 'carry instead'")
def test_shooting_from_the_penalty_spot_beats_dribbling():
    state = final_third_attack("H9", (94.0, 34.0))
    engine = RolloutEngine()
    p = {a: engine.run(state, n=2000, seed=1, intervention=Intervention(kind="swap_action", params={"action": a})).p_goal_for
         for a in ("shoot", "carry")}
    assert p["shoot"] > p["carry"]


def _shot_context(owner_xy=(80.0, 34.0)) -> DecisionContext:
    state = final_third_attack("H9", owner_xy)
    moment = Moment(id="m1", match_id="demo-001", frame=0, t_ms=0, clock_s=0, kind="big_chance", score=0.6,
                    team="home", player_ids=["H9"], event_ids=["e1"], reason="test")
    return DecisionContext(moment, 0, state, "H9", Intervention(kind="swap_action", params={"action": "shoot"}), "shoot")


@pytest.mark.xfail(strict=True, reason="R2: 'defender stands closer' experiments drop the actual decision (shoot), so they "
                                       "compare 'defender moved + free choice' with 'forced shot'; a 0 m move already changes p_goal")
def test_a_zero_metre_defender_move_reproduces_the_actual_decision():
    from app.agents.experiments import ExperimentRunner

    ctx = _shot_context()
    tight = next(e for e in experiment_menu(ctx) if e.intervention.kind == "move_player")
    null = Intervention(kind="move_player", params={**tight.intervention.params, "dx": 0.0, "dy": 0.0})
    runner = ExperimentRunner(n=500, seeds=(1,))
    base, _ = runner.baseline(ctx)
    moved, _ = runner.run(ctx, "null", "nobody moves", null)
    assert moved.p_goal == pytest.approx(base.p_goal, abs=0.01)


# --- explain team: claim validation ---------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="R7: since 0ae244d decimals and points are checked, but plain integers ('3 times', '6 m') still pass by design")
def test_claim_with_invented_non_percentage_numbers_is_rejected():
    assert not numbers_are_ours("Shooting made a goal 3 times more likely; the full back was 6 m too high.", {"4.0%"})


def _result(eid: str, p_goal: float, spread: float = 0.001) -> ExperimentResult:
    return ExperimentResult(experiment_id=eid, description=f"{eid} instead", p_goal=p_goal, p_turnover=0.8,
                            p_conceded=0.0, seed_spread=spread, rollout_ids=[f"rollout:{eid}"])


@pytest.mark.xfail(strict=True, reason="R7: the allowed-number set includes REJECTED experiments, so the Critic can state a "
                                       "rejected finding as fact and the claim still passes validation")
def test_claim_cannot_state_a_rejected_finding_as_fact(monkeypatch):
    ctx = _shot_context()
    monkeypatch.setattr(explain, "decision_context", lambda *a: ctx)

    rollout = type("Rollout", (), {"sample_paths": []})()

    class Runner:
        def baseline(self, ctx):
            return _result("actual", 0.040), rollout

        def run(self, ctx, eid, description, iv):
            return _result(eid, 0.070, spread=0.02), rollout  # within noise -> rule rejects

    menu_id = experiment_menu(ctx)[0].id
    llm = FakeLLM({
        "analyst": lambda p: AnalystPlan(hypotheses=[AnalystHypothesis(experiment_id=menu_id, text="x")]),
        "critic": lambda p: CriticReview(verdicts=[CriticVerdict(experiment_id=menu_id, verdict="rejected", note="noise")],
                                         claim="Passing instead would have raised the chance from 4.0% to 7.0%."),
    })
    insight = ExplainTeam(llm, runner=Runner(), max_rounds=1).explain(None, ctx.moment, [])  # type: ignore[arg-type]
    assert all(h.verdict == "rejected" for h in insight.hypotheses)
    assert "7.0%" not in insight.claim
