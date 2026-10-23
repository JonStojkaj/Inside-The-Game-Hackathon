"""Microsoft Agent Framework runtime: same insights as the hand-written loop, same guards, offline + cached."""

import json

import pytest

pytest.importorskip("agent_framework")

from app.agents import explain  # noqa: E402
from app.agents.experiments import DecisionContext, ExperimentResult, ExperimentRunner, experiment_menu  # noqa: E402
from app.agents.explain import (  # noqa: E402
    AnalystHypothesis,
    AnalystPlan,
    CriticReview,
    CriticVerdict,
    ExplainTeam,
    explain_team_from_env,
    fake_explain_llm,
)
from app.agents.framework import FrameworkLLM  # noqa: E402
from app.agents.llm import FakeLLM, agent_runtime, llm_from_env  # noqa: E402
from app.agents.production import Narrator, Producer, RecapAgent, fake_production_llm  # noqa: E402
from app.agents.workflow import FrameworkExplainTeam, analyst_tools  # noqa: E402
from app.models import Intervention, Moment  # noqa: E402
from app.rollout.scenarios import final_third_attack  # noqa: E402


def _shot_context() -> DecisionContext:
    state = final_third_attack("H9", (80.0, 34.0))
    moment = Moment(id="m1", match_id="demo-001", frame=0, t_ms=0, clock_s=0, kind="big_chance", score=0.6,
                    team="home", player_ids=["H9"], event_ids=["e1"], reason="test")
    return DecisionContext(moment, 0, state, "H9", Intervention(kind="swap_action", params={"action": "shoot"}), "shoot")


@pytest.fixture
def ctx(monkeypatch):
    c = _shot_context()
    monkeypatch.setattr(explain, "decision_context", lambda *a: c)
    return c


def runner() -> ExperimentRunner:
    return ExperimentRunner(n=120, seeds=(1, 2, 3))


def test_framework_workflow_gives_the_same_insight_as_the_handwritten_loop(ctx):
    sdk = ExplainTeam(fake_explain_llm(), runner=runner()).explain(None, ctx.moment, [])  # type: ignore[arg-type]
    team = FrameworkExplainTeam(FrameworkLLM("fake", "off", fake_explain_llm()), runner=runner())
    af = team.explain(None, ctx.moment, [])  # type: ignore[arg-type]
    assert af.model_dump() == sdk.model_dump()
    assert team.last_path[:3] == ["analyst", "experimenter", "critic"] and team.last_path[-1] == "finalize"


def test_critic_is_overruled_and_invented_numbers_fall_back_to_the_template(ctx):
    rollout = type("Rollout", (), {"sample_paths": []})()

    def result(eid, p_goal, spread=0.001):
        return ExperimentResult(experiment_id=eid, description=f"{eid} instead", p_goal=p_goal, p_turnover=0.8,
                                p_conceded=0.0, seed_spread=spread, rollout_ids=[f"rollout:{eid}"])

    class Noisy:
        def baseline(self, ctx):
            return result("actual", 0.040), rollout

        def run(self, ctx, eid, description, iv):
            return result(eid, 0.070, spread=0.02), rollout  # within noise -> the rule rejects

    menu_id = experiment_menu(ctx)[0].id
    fake = FakeLLM({
        "analyst": lambda p: AnalystPlan(hypotheses=[AnalystHypothesis(experiment_id=menu_id, text="x"),
                                                     AnalystHypothesis(experiment_id="not_on_menu", text="y")]),
        "critic": lambda p: CriticReview(verdicts=[CriticVerdict(experiment_id=menu_id, verdict="accepted", note="big")],
                                         claim="Passing would have raised the chance from 4.0% to 7.0%."),
    })
    team = FrameworkExplainTeam(FrameworkLLM("fake", "off", fake), runner=Noisy(), max_rounds=1)  # type: ignore[arg-type]
    insight = team.explain(None, ctx.moment, [])  # type: ignore[arg-type]
    assert [h.verdict for h in insight.hypotheses] == ["rejected"]  # off-menu id dropped, Critic overruled
    assert insight.hypotheses[0].critic_note.startswith("overruled by rule")
    assert "7.0%" not in insight.claim  # numbers_are_ours -> template claim


def test_run_experiment_tool_only_runs_menu_experiments_within_budget(ctx):
    team = FrameworkExplainTeam(FrameworkLLM("fake", "off", fake_explain_llm()), runner=runner())
    ep = team.start(None, ctx.moment, [])  # type: ignore[arg-type]
    stats, run = analyst_tools(team, ep)
    assert json.loads(stats.func())["minute"] == 0  # type: ignore[misc]
    assert "error" in json.loads(run.func(experiment_id="teleport"))  # type: ignore[misc]
    ids = list(team.available(ep))
    out = json.loads(run.func(experiment_id=ids[0]))  # type: ignore[misc]
    assert out["experiment_id"] == ids[0] and "passes_rules" in out and ids[0] in ep.probes
    for i in ids[1:]:
        run.func(experiment_id=i)  # type: ignore[misc]
    assert len(ep.probes) == min(len(ids), 4)


def test_framework_cache_replays_without_the_model(ctx, tmp_path):
    first = FrameworkLLM("fake", "readwrite", fake_explain_llm(), cache_dir=tmp_path)
    a = FrameworkExplainTeam(first, runner=runner()).explain(None, ctx.moment, [])  # type: ignore[arg-type]
    assert first.misses > 0 and first.hits == 0
    replay = FrameworkLLM("fake", "replay", FakeLLM({}), cache_dir=tmp_path)  # no handlers: the cache must answer
    b = FrameworkExplainTeam(replay, runner=runner()).explain(None, ctx.moment, [])  # type: ignore[arg-type]
    assert replay.misses == 0 and replay.hits == first.misses
    assert a.model_dump() == b.model_dump()


def test_production_team_runs_on_framework_agents():
    from test_production import ANALYST, AWAY_FAN_DE, FINAL, GOALS, HOME_FAN, insight, moment
    from test_production import ctx as match_ctx

    af = FrameworkLLM("fake", "off", fake_production_llm())
    sdk = fake_production_llm()
    m = moment()
    for seg in (ANALYST, HOME_FAN, AWAY_FAN_DE):
        assert Producer(af).decide(seg, m, insight(m), match_ctx()) == Producer(sdk).decide(seg, m, insight(m), match_ctx())
        assert Narrator(af).write(seg, m, insight(m), match_ctx()) == Narrator(sdk).write(seg, m, insight(m), match_ctx())
    assert RecapAgent(af).write(HOME_FAN, match_ctx(), GOALS, FINAL, []) == RecapAgent(sdk).write(HOME_FAN, match_ctx(), GOALS, FINAL, [])


def test_single_turn_answers_are_shared_with_the_sdk_cache(tmp_path):
    from test_production import HOME_FAN, insight, moment
    from test_production import ctx as match_ctx

    from app.agents.llm import CachedLLM

    m = moment()
    sdk = CachedLLM(fake_production_llm(), "readwrite", cache_dir=tmp_path)  # model name "fake"
    written = Narrator(sdk).write(HOME_FAN, m, insight(m), match_ctx())
    replay = FrameworkLLM("fake", "replay", FakeLLM({}), cache_dir=tmp_path)  # framework agent, cache only
    assert Narrator(replay).write(HOME_FAN, m, insight(m), match_ctx()) == written
    assert replay.hits == 1 and replay.misses == 0


def test_runtime_is_selected_by_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("LLM_CACHE", "off")
    monkeypatch.delenv("AGENT_RUNTIME", raising=False)
    assert agent_runtime() == "framework"
    assert isinstance(llm_from_env(fake_explain_llm()), FrameworkLLM)
    assert isinstance(explain_team_from_env(), FrameworkExplainTeam)
    monkeypatch.setenv("AGENT_RUNTIME", "sdk")
    assert not isinstance(explain_team_from_env(), FrameworkExplainTeam)
