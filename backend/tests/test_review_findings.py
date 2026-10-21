"""Devil's-advocate review (docs/review/devils-advocate.md): tests that pinned real bugs (R1-R7).

They started as xfail(strict=True) and became regular regression tests when each bug was fixed.
"""

import numpy as np
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


# R4 fixed: the finisher is found from the last sharp ball acceleration before the goal
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
    events = derive_events(match)
    goal = next(e for e in events if e.type == "goal")
    assert goal.player_id == "H11"
    shot = next(e for e in events if e.type == "shot")
    assert shot.player_id == "H11" and shot.frame == 10 and shot.meta["shot_speed_kmh"] > 100
    assist = next(e for e in events if e.type == "pass")  # the roll to the finisher becomes the assist
    assert (assist.player_id, assist.target_id, assist.outcome) == ("H10", "H11", "complete")


# --- stats ----------------------------------------------------------------------------------

# R6 fixed: an interception that answers a failed pass is one possession change
def test_one_interception_is_one_possession_change():
    events = [ev(1, "pass", outcome="incomplete"), ev(2, "interception", team="away")]
    assert control_chaos(events, 60.0)["possession_changes_per_min"] == 1.0
    # a failed pass nobody intercepted (e.g. into touch, picked up later) still counts once
    lone = [ev(1, "pass", outcome="incomplete", t_ms=0), ev(2, "interception", team="away", t_ms=30_000)]
    assert control_chaos(lone, 60.0)["possession_changes_per_min"] == 2.0


# R3 fixed: the window is 40 s of physical play and the trend compares it with the match so far
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

# R1 fixed: density/goal-dependent dispossession + keeper off his line, calibrated with a ranking gate
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


# R2 fixed: move experiments replay the actual decision via params["then_action"]
def test_a_zero_metre_defender_move_reproduces_the_actual_decision():
    from app.agents.experiments import ExperimentRunner

    ctx = _shot_context()
    tight = next(e for e in experiment_menu(ctx) if e.intervention.kind == "move_player")
    null = Intervention(kind="move_player", params={**tight.intervention.params, "dx": 0.0, "dy": 0.0})
    runner = ExperimentRunner(n=500, seeds=(1,))
    base, _ = runner.baseline(ctx)
    moved, _ = runner.run(ctx, "null", "nobody moves", null)
    assert moved.p_goal == base.p_goal  # same seeds, same state, same decision -> identical futures
    assert tight.intervention.params["then_action"] == ctx.actual.params


# --- explain team: claim validation ---------------------------------------------------------

# R7 fixed: plain integers and number words must come from code too
def test_claim_with_invented_non_percentage_numbers_is_rejected():
    assert not numbers_are_ours("Shooting made a goal 3 times more likely; the full back was 6 m too high.", {"4.0%"})
    assert not numbers_are_ours("Shooting would have doubled his chance.", {"4.0%"})
    assert numbers_are_ours("If defender Kim had stood 5 m closer, 4.0%.", {"4.0%"}, allowed_plain={"5"})


def _result(eid: str, p_goal: float, spread: float = 0.001) -> ExperimentResult:
    return ExperimentResult(experiment_id=eid, description=f"{eid} instead", p_goal=p_goal, p_turnover=0.8,
                            p_conceded=0.0, seed_spread=spread, rollout_ids=[f"rollout:{eid}"])


# R7 fixed: only the baseline and accepted findings may be stated as fact
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


def test_hypothesis_texts_and_critic_notes_cannot_carry_invented_numbers(monkeypatch):
    ctx = _shot_context()
    monkeypatch.setattr(explain, "decision_context", lambda *a: ctx)
    rollout = type("Rollout", (), {"sample_paths": []})()

    class Runner:
        def baseline(self, ctx):
            return _result("actual", 0.040), rollout

        def run(self, ctx, eid, description, iv):
            return _result(eid, 0.120), rollout

    exp = experiment_menu(ctx)[0]
    llm = FakeLLM({
        "analyst": lambda p: AnalystPlan(hypotheses=[AnalystHypothesis(experiment_id=exp.id, text="This triples the chance to 25%.")]),
        "critic": lambda p: CriticReview(verdicts=[CriticVerdict(experiment_id=exp.id, verdict="accepted", note="3 times better")],
                                         claim=""),
    })
    h = ExplainTeam(llm, runner=Runner(), max_rounds=1).explain(None, ctx.moment, []).hypotheses[0]  # type: ignore[arg-type]
    assert h.text == f"If {exp.description}."
    assert "3 times" not in h.critic_note


def test_shoot_is_only_offered_within_30_m_of_goal():
    carry = Intervention(kind="swap_action", params={"action": "carry"})
    near, far = _shot_context((80.0, 34.0)), _shot_context((50.0, 34.0))
    near.actual = far.actual = carry
    assert "shoot" in {e.id for e in experiment_menu(near)}
    assert "shoot" not in {e.id for e in experiment_menu(far)}
