"""Ask Sliding Doors: the fan's question mapped onto the menu, live explain team, streaming, flag, rate limit (fake LLM)."""

import json

import pytest
from conftest import make_match, own
from fastapi.testclient import TestClient

pytest.importorskip("agent_framework")

from app.agents.ask import SimMatch, ask_team, fake_ask_llm, pick_moment, suggestions, translate  # noqa: E402
from app.agents.experiments import ExperimentRunner, decision_context  # noqa: E402
from app.agents.framework import FrameworkLLM  # noqa: E402
from app.agents.llm import FakeLLM  # noqa: E402
from app.api.ask import AskError, AskService, AskSettings, Limiter  # noqa: E402
from app.api.main import create_app  # noqa: E402
from app.export.exporter import export_match  # noqa: E402
from app.models import MatchEvent, Moment  # noqa: E402

PASS_FRAME = 30


def sim_match() -> SimMatch:
    """Home 9 on the ball 17 m from goal passes to Home 10 at frame 30 (a key moment)."""
    match = make_match(n_frames=80)
    match.match_id = "ask-test"
    match.pos[:, 8] = (88.0, 34.0)
    match.pos[:, 9] = (80.0, 20.0)
    own(match, 8, 0, PASS_FRAME)
    e = MatchEvent(id="e-pass", match_id="ask-test", t_ms=PASS_FRAME * 100, frame=PASS_FRAME, type="pass", team="home",
                   player_id="H9", target_id="H10", start_xy=(88.0, 34.0), end_xy=(80.0, 20.0), outcome="complete")
    m = Moment(id="ask-test-m00030-decisive_pass", match_id="ask-test", frame=PASS_FRAME, t_ms=PASS_FRAME * 100,
               clock_s=PASS_FRAME * 1.8, kind="decisive_pass", score=0.5, team="home", player_ids=["H9", "H10"],
               event_ids=["e-pass"], reason="test")
    return SimMatch(match, [e], [m])


def runner() -> ExperimentRunner:
    return ExperimentRunner(n=60, seeds=(1, 2, 3))


@pytest.fixture
def sim() -> SimMatch:
    return sim_match()


def app_with(tmp_path, sim, settings: AskSettings, raw: bool = True, llm=None) -> tuple[TestClient, AskService]:
    root = tmp_path / "export"
    export_match(sim.match, root / "ask-test", events=sim.events)
    if raw:
        (root / "ask-test" / "raw.jsonl").write_text("{}")
    service = AskService(settings, lambda m: root / m, llm=llm or FrameworkLLM("fake", "off", fake_ask_llm()), runner=runner(),
                         loader=lambda _: sim)
    return TestClient(create_app(root, frontend_dir=tmp_path / "dist", ask=service)), service


def lines(res) -> list[dict]:
    return [json.loads(x) for x in res.text.splitlines() if x]


ON = AskSettings(enabled=True, max_per_minute=10, timeout_s=60)


def test_disabled_by_default_without_azure(tmp_path, sim, monkeypatch):
    monkeypatch.delenv("ASK_ENABLED", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    assert AskSettings.from_env().enabled is False
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://x.openai.azure.com/openai/v1/")
    assert AskSettings.from_env().enabled is True
    monkeypatch.setenv("ASK_ENABLED", "false")
    assert AskSettings.from_env().enabled is False

    client, _ = app_with(tmp_path, sim, AskSettings(enabled=False))
    assert client.get("/api/features").json() == {"ask": False}
    assert client.get("/api/matches/ask-test/ask?frame=30").json() == {"enabled": False}
    res = client.post("/api/matches/ask-test/ask", json={"frame": 30, "question": "What if he had shot?"})
    assert res.status_code == 503 and res.json()["error"] == "disabled"


def test_menu_offers_suggestions_for_the_moment(tmp_path, sim):
    client, _ = app_with(tmp_path, sim, ON)
    data = client.get("/api/matches/ask-test/ask?frame=35").json()
    assert data["enabled"] and data["moment"]["id"] == "ask-test-m00030-decisive_pass" and data["moment"]["key_moment"]
    kinds = [s["kind"] for s in data["suggestions"]]
    assert kinds[0] == "shoot" and 2 <= len(kinds) <= 3 and len(set(kinds)) == len(kinds)
    assert data["suggestions"][0]["question"] == "What if Home 9 had shot?"


def test_streamed_answer_tests_the_fans_question(tmp_path, sim):
    client, _ = app_with(tmp_path, sim, ON)
    res = client.post("/api/matches/ask-test/ask", json={"frame": 32, "question": "What if Home 9 had shot?"})
    assert res.status_code == 200 and res.headers["content-type"].startswith("application/x-ndjson")
    msgs = lines(res)
    codes = [m["code"] for m in msgs if m["type"] == "step"]
    for code in ("moment", "baseline", "analyst", "simulating", "hypotheses", "critic", "verdicts", "finalize", "done"):
        assert code in codes
    result = msgs[-1]
    assert result["type"] == "result" and result["answered"] and not result["cached"]
    # the Analyst picked the menu experiment the fan asked about, nothing else
    assert [h["intervention"]["params"]["action"] for h in result["hypotheses"]] == ["shoot"]
    assert result["insight"]["claim"] == result["claim"] == result["claim_en"]
    assert result["numbers"]["n_rollouts"] == 60 and result["numbers"]["n_seeds"] == 3
    assert result["ghost_paths"] and result["timings"]["total_ms"] >= 0
    assert result["workflow"][0] == "analyst" and result["workflow"][-1] == "finalize"
    # numbers in the answer come from the simulator: baseline and the tested alternative
    h = result["hypotheses"][0]
    for p in (h["baseline_p_goal"], h["counterfactual_p_goal"]):
        assert f"{p * 100:.1f}%" in result["claim"]


def test_question_nothing_on_the_menu_tests_is_declined_politely(tmp_path, sim):
    client, _ = app_with(tmp_path, sim, ON)
    result = client.post("/api/matches/ask-test/ask?stream=false", json={"frame": 30, "question": "What if it had rained?"}).json()
    assert result["answered"] is False and result["reason"] == "no_matching_experiment"
    assert result["hypotheses"] == [] and result["insight"] is None
    assert 2 <= len(result["suggestions"]) <= 3 and "We can't test that" in result["claim"]


def test_identical_question_comes_from_the_cache_without_using_the_limit(tmp_path, sim):
    client, service = app_with(tmp_path, sim, AskSettings(enabled=True, max_per_minute=1))
    body = {"frame": 30, "question": "What if Home 9 had shot?"}
    first = client.post("/api/matches/ask-test/ask?stream=false", json=body).json()
    again = client.post("/api/matches/ask-test/ask?stream=false", json={**body, "question": "what if home 9 had  shot"}).json()
    assert again["cached"] is True and again["claim"] == first["claim"]
    other = client.post("/api/matches/ask-test/ask?stream=false", json={**body, "question": "What if Home 9 had carried it?"})
    assert other.status_code == 429 and other.json()["error"] == "rate_limited" and other.json()["retry_after_s"] > 0


def test_limiter_one_at_a_time_and_per_minute():
    now = [0.0]
    lim = Limiter(per_minute=2, clock=lambda: now[0])
    lim.acquire()
    with pytest.raises(AskError) as busy:
        lim.acquire()
    assert busy.value.error == "busy" and busy.value.status == 429
    lim.release()
    lim.acquire()
    lim.release()
    with pytest.raises(AskError) as limited:
        lim.acquire()
    assert limited.value.error == "rate_limited"
    now[0] = 61.0
    lim.acquire()


def test_errors_are_clear_json(tmp_path, sim):
    client, _ = app_with(tmp_path, sim, ON)
    post = lambda body: client.post("/api/matches/ask-test/ask", json=body)  # noqa: E731
    assert post({"frame": 30, "question": "What if he had shot?", "lang": "fr"}).json()["error"] == "bad_request"
    assert post({"frame": 30, "question": ""}).status_code == 422
    assert post({"frame": 999, "question": "What if he had shot?"}).json()["error"] == "bad_request"
    assert client.post("/api/matches/nope/ask", json={"frame": 1, "question": "abc"}).status_code == 404

    no_raw, _ = app_with(tmp_path / "b", sim, ON, raw=False)
    res = no_raw.post("/api/matches/ask-test/ask", json={"frame": 30, "question": "What if he had shot?"})
    assert res.status_code == 503 and res.json()["error"] == "unavailable"

    quiet, _ = app_with(tmp_path / "c", SimMatch(sim.match, [], []), ON)  # nobody passes or shoots
    res = quiet.post("/api/matches/ask-test/ask", json={"frame": 30, "question": "What if he had shot?"})
    assert res.status_code == 422 and res.json()["error"] == "no_moment"


def test_failure_in_the_agents_is_reported_and_releases_the_limit(tmp_path, sim):
    broken = FakeLLM({})  # no handlers: the Analyst raises
    client, service = app_with(tmp_path, sim, ON, llm=broken)
    msgs = lines(client.post("/api/matches/ask-test/ask", json={"frame": 30, "question": "What if he had shot?"}))
    assert msgs[-1]["type"] == "error" and msgs[-1]["error"] == "failed"
    assert service.limiter.busy is False


def test_german_answer_keeps_the_verified_numbers(sim):
    llm = FakeLLM({**fake_ask_llm().handlers})
    assert translate(llm, "Von 6.5% auf 9.1%.", "de") == "Von 6.5% auf 9.1%."
    llm.handlers["translator"] = lambda p: type("T", (), {"model_dump": lambda self: {"text": "Von 6,5 % auf 12 %."}})()
    assert translate(llm, "From 6.5% to 9.1%.", "de") is None  # a changed number: keep the English claim


def test_moment_picking_prefers_key_moments_then_the_carriers_next_action(sim):
    m, ev = sim.match, sim.events
    assert pick_moment(m, ev, sim.moments, 100).id == sim.moments[0].id  # within 12 s
    adhoc = pick_moment(m, ev, [], 10)
    assert adhoc is not None and adhoc.kind == "decisive_pass" and "-ask" in adhoc.id
    assert pick_moment(m, ev, [], 79 + 200) is None
    ctx = decision_context(m, sim.moments[0], ev)
    assert {s["kind"] for s in suggestions(ctx)} <= {"shoot", "pass", "tight", "carry"}


def test_sdk_runtime_answers_the_same(sim):
    from app.agents.ask import answer

    steps: list[dict] = []
    sdk = answer(sim, sim.moments[0], "What if Home 9 had shot?", "en", fake_ask_llm(), runner(), steps.append)
    af = answer(sim, sim.moments[0], "What if Home 9 had shot?", "en", FrameworkLLM("fake", "off", fake_ask_llm()), runner())
    assert sdk["claim"] == af["claim"] and sdk["hypotheses"] == af["hypotheses"]
    assert steps[-1]["code"] == "done"
    assert isinstance(ask_team(fake_ask_llm(), None, "q", None).analyst_system(), str)
