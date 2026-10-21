import json

import pytest

from app.agents.llm import FakeLLM
from app.agents.production import (
    Narrator,
    NarratorDraft,
    Producer,
    ProducerDecision,
    RecapAgent,
    RecapDraft,
    allowed_numbers,
    fake_production_llm,
    numbers_are_ours,
    numbers_in,
)
from app.models import Hypothesis, Insight, Intervention, Moment, ViewerProfile
from app.overlay.cues import MatchContext, PlayerRef
from app.personalization.segments import (
    build_segment,
    cue_priority,
    demo_segments,
    moment_relevance,
    side,
)

ANALYST = build_segment(ViewerProfile(mode="analyst", language="en"))
HOME_FAN = build_segment(ViewerProfile(mode="club_fan", language="en", favourite_club="home"))
AWAY_FAN_DE = build_segment(ViewerProfile(mode="club_fan", language="de", favourite_club="away"))
PLAYER_ES = build_segment(ViewerProfile(mode="player_focus", language="es", favourite_players=["A20"]))
CASUAL = build_segment(ViewerProfile(mode="casual", language="en"))


def ctx() -> MatchContext:
    players = {
        "H9": PlayerRef("H9", "home", "Mateo Brann", 9, "CF"),
        "H7": PlayerRef("H7", "home", "Idris Calloway", 7, "RM"),
        "A20": PlayerRef("A20", "away", "Kai Nakamura", 20, "CM"),
        "A4": PlayerRef("A4", "away", "Oscar Lindqvist", 4, "CB"),
    }
    return MatchContext(match_id="m", clubs={"home": "FC Northbridge", "away": "Harbour City"}, players=players,
                        end_ms=300_000, clock_of=lambda t: t * 18 / 1000, final_score=(1, 2))


def moment(kind="big_chance", team="home", players=("H9",), t_ms=10_000) -> Moment:
    return Moment(id=f"m-{kind}-{team}", match_id="m", frame=t_ms // 100, t_ms=t_ms, clock_s=t_ms * 18 / 1000, kind=kind,
                  score=0.6, team=team, player_ids=list(players), event_ids=["e1"], reason="test")


def insight(m: Moment, actual=0.148, best=0.055) -> Insight:
    h = Hypothesis(text="A pass would have been better", intervention=Intervention(kind="swap_action",
                   params={"action": "pass", "target_id": "H7"}), baseline_p_goal=actual, counterfactual_p_goal=best,
                   seed_spread=0.005, verdict="accepted")
    return Insight(id=f"{m.id}-insight", moment_id=m.id, claim="Passing to Calloway would have lowered the chance from 14.8% to 5.5%.",
                   evidence=["e1", "rollout:x:actual:101"], numbers={"actual_p_goal": actual, "best_alt_p_goal": best,
                   "delta_p_goal": best - actual}, verified=True, confidence="clear", hypotheses=[h])


# --- segments -----------------------------------------------------------------------------------

def test_demo_segment_ids():
    assert [s.id for s in demo_segments()] == [
        "analyst-en", "analyst-de", "club_fan-home-en", "club_fan-away-de", "player_focus-A20-es", "casual-en"]


def test_selection_differs_between_profiles():
    home_chance, away_pass = moment("big_chance", "home", ["H9"]), moment("decisive_pass", "away", ["A20", "A4"])
    assert moment_relevance(ANALYST, home_chance) is not None and moment_relevance(ANALYST, away_pass) is not None
    # club fans: their own chance matters more than the opponent's, the opponent's build-up not at all
    assert moment_relevance(HOME_FAN, home_chance) > moment_relevance(AWAY_FAN_DE, home_chance)
    assert moment_relevance(HOME_FAN, away_pass) is None
    # player focus: only moments involving the followed player
    assert moment_relevance(PLAYER_ES, away_pass) == 1.0 and moment_relevance(PLAYER_ES, home_chance) is None
    # casual: no tactical moments
    assert moment_relevance(CASUAL, away_pass) is None


def test_sides_and_live_cue_rules():
    assert side(HOME_FAN, "home") == "for" and side(HOME_FAN, "away") == "against"
    assert side(PLAYER_ES, "away") == "for" and side(ANALYST, "home") == "neutral"
    sprint = {"kind": "sprint", "team": "away", "players": ["A20"], "data": {}}
    assert cue_priority(PLAYER_ES, **sprint) is not None
    assert cue_priority(ANALYST, **sprint) is None
    assert cue_priority(HOME_FAN, **sprint) is None and cue_priority(AWAY_FAN_DE, **sprint) is not None
    assert cue_priority(PLAYER_ES, "shot", "home", ["H9"], {}) is None  # not our player
    stat = {"kind": "stat", "team": None, "players": [], "data": {"key": "pass_difficulty"}}
    assert cue_priority(ANALYST, **stat) is not None and cue_priority(CASUAL, **stat) is None


# --- number validation --------------------------------------------------------------------------

def test_numbers_in_normalises_locales():
    assert numbers_in("von 14,8 % auf 5,5 % (12')") == ["14.8", "5.5", "12"]
    assert numbers_in("15.0 km/h") == ["15"]


def test_numbers_are_ours_allows_rounding_but_not_inventions():
    allowed = allowed_numbers(["14,8 %", "5,5 %", "12"])
    assert numbers_are_ours("Torchance 14,8 % statt 5,5 % in Minute 12", allowed)
    assert numbers_are_ours("about 15% instead of 6%", allowed)  # whole-number rounding of our values
    assert not numbers_are_ours("3 times better", allowed)
    assert not numbers_are_ours("a 9.3 point swing", allowed)


# --- producer -----------------------------------------------------------------------------------

def test_producer_skips_irrelevant_moments_without_calling_the_llm():
    no_handlers = FakeLLM({})  # any call would raise
    m = moment("decisive_pass", "away", ["A20", "A4"])
    assert Producer(no_handlers).decide(HOME_FAN, m, insight(m), ctx()) is None


def test_producer_priority_is_clamped_and_goals_always_air():
    llm = FakeLLM({"producer": lambda p: ProducerDecision(show=False, priority=0, angle="meh")})
    goal = moment("goal", "home", ["H9"])
    d = Producer(llm).decide(HOME_FAN, goal, insight(goal), ctx())
    assert d is not None and d.show and d.priority == 90 - 15
    chance = moment("big_chance", "home", ["H9"])
    d = Producer(llm).decide(HOME_FAN, chance, insight(chance), ctx())
    assert d is not None and not d.show


def test_unverified_insights_never_reach_the_producer():
    m = moment()
    bad = insight(m).model_copy(update={"verified": False})
    assert Producer(FakeLLM({})).decide(ANALYST, m, bad, ctx()) is None


# --- narrator -----------------------------------------------------------------------------------

def narrator_returning(headline: str, body: str) -> Narrator:
    return Narrator(FakeLLM({"narrator": lambda p: NarratorDraft(headline=headline, body=body)}))


def test_narrator_keeps_valid_llm_text():
    m = moment()
    out = narrator_returning("We had it!", "Our shot: 14.8% chance, a pass only 5.5%.").write(HOME_FAN, m, insight(m), ctx())
    assert out.source == "llm" and out.body.startswith("Our shot")


def test_narrator_falls_back_to_template_on_invented_numbers():
    m = moment()
    out = narrator_returning("3x better!", "Shooting was three times better: 44% vs 5.5%.").write(HOME_FAN, m, insight(m), ctx())
    assert out.source == "template" and "numbers not in our facts" in out.note
    assert "14.8%" in out.body and "5.5%" in out.body


def test_narrator_falls_back_on_overlong_text():
    m = moment()
    out = narrator_returning("ok", "x" * 500).write(CASUAL, m, insight(m), ctx())
    assert out.source == "template" and "too long" in out.note


def test_narrator_prompt_is_localised_and_template_is_in_target_language():
    seen = {}

    def capture(prompt: str) -> NarratorDraft:
        seen.update(json.loads(prompt))
        return NarratorDraft(**seen["plain_template"])

    m = moment("big_chance", "home", ["H9"])
    out = Narrator(FakeLLM({"narrator": capture})).write(AWAY_FAN_DE, m, insight(m), ctx())
    assert seen["target_language"] == "de" and seen["FACTS"]["actual_chance_to_score"] == "14,8 %"
    assert "Torchance" in out.body and "Calloway" in out.body  # alternative rendered by code, in German
    assert out.source == "llm"


@pytest.mark.parametrize("segment", [ANALYST, HOME_FAN, AWAY_FAN_DE, PLAYER_ES, CASUAL])
def test_fake_production_llm_end_to_end_texts_are_valid(segment):
    llm = fake_production_llm()
    m = moment("decisive_pass", "away", ["A20", "A4"])
    out = Narrator(llm).write(segment, m, insight(m), ctx(), angle="test")
    assert out.source == "llm" and out.headline and out.body


# --- recap --------------------------------------------------------------------------------------

GOALS = [(12, "A4", "away"), (19, "H9", "home"), (43, "A20", "away")]
FINAL = {"possession": {"home": 0.41, "away": 0.59}, "pass_accuracy": {"home": 0.6, "away": 0.75},
         "player": {"top_speed_kmh": 27.8, "pass_accuracy": 1.0}}


def test_recap_template_per_perspective_and_language():
    llm = fake_production_llm()
    home = RecapAgent(llm).write(HOME_FAN, ctx(), GOALS, FINAL, [])
    away = RecapAgent(llm).write(AWAY_FAN_DE, ctx(), GOALS, FINAL, [])
    player = RecapAgent(llm).write(PLAYER_ES, ctx(), GOALS, FINAL, [])
    assert "not our day" in home.headline and "Sieg" in away.headline
    assert "Nakamura" in player.headline and any("27,8" in b for b in player.bullets)


def test_recap_rejects_invented_numbers():
    llm = FakeLLM({"recap": lambda p: RecapDraft(headline="Full time", body="They ran 112 km.", bullets=["ok"])})
    out = RecapAgent(llm).write(ANALYST, ctx(), GOALS, FINAL, [])
    assert out.source == "template" and "112" not in out.body
