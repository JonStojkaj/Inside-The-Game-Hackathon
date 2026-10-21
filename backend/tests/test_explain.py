from app.agents.experiments import ExperimentResult
from app.agents.explain import headline, numbers_are_ours, passes_rule, plausible, points


def res(p_goal, spread=0.002, exp_id="x"):
    return ExperimentResult(experiment_id=exp_id, description=exp_id, p_goal=p_goal, p_turnover=0.8,
                            p_conceded=0.0, seed_spread=spread, rollout_ids=[])


BASE = res(0.108)


def test_numbers_must_come_from_our_results():
    allowed = {"10.8%", "14.5%"}
    deltas = {points(BASE, res(0.145))}  # "3.7"
    assert numbers_are_ours("The chance rose from 10.8% to 14.5%.", allowed, deltas)
    assert numbers_are_ours("A rise of 3.7 points in minute 42 by number 9.", allowed, deltas, {"42", "9"})
    assert not numbers_are_ours("A rise of 3.7 points in minute 42.", allowed, deltas)  # integer not from code
    assert not numbers_are_ours("The chance rose to 15%.", allowed, deltas)  # invented percentage
    assert not numbers_are_ours("a 3.8-point increase", allowed, deltas)  # LLM did its own arithmetic
    assert not numbers_are_ours("an xG of 0.31", allowed, deltas)  # unexplained decimal


def test_headline_prefers_a_better_option_and_turnovers_need_a_safer_one():
    worse_big, better_small = res(0.04, exp_id="pass"), res(0.13, exp_id="carry")
    assert headline(BASE, [worse_big, better_small]).experiment_id == "carry"
    assert headline(BASE, [worse_big]).experiment_id == "pass"  # the actual choice was the best tested one
    keep = BASE.model_copy(update={"p_keep": 0.20})
    riskier = res(0.0, exp_id="riskier").model_copy(update={"p_keep": 0.10})
    safer = res(0.0, exp_id="safer").model_copy(update={"p_keep": 0.30})
    assert headline(keep, [riskier], "p_keep") is None  # "even riskier than the lost pass" is no insight
    assert headline(keep, [riskier, safer], "p_keep").experiment_id == "safer"


def test_stability_rule():
    assert passes_rule(BASE, res(0.15))
    assert not passes_rule(BASE, res(0.115))  # too small
    assert not passes_rule(BASE, res(0.15, spread=0.03))  # noisy across seeds


def test_football_prior_rejects_implausible_direction():
    tighter_marking = -1
    assert plausible(res(0.06), BASE, tighter_marking)
    assert not plausible(res(0.145), BASE, tighter_marking)  # closer defender cannot help the attacker
    assert plausible(res(0.145), BASE, None)
