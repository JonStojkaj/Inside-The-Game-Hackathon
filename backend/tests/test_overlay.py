import random
from itertools import pairwise

from conftest import make_match, own

from app.agents.production import fake_production_llm
from app.models import Hypothesis, Insight, Intervention, MatchEvent, Moment, Overlay, ViewerProfile
from app.overlay.cues import context_from_grf, event_cues
from app.overlay.pipeline import produce
from app.overlay.scheduler import MAX_VISIBLE, PERSISTENT_SLOTS, Candidate, Timeline, build_timeline, schedule
from app.personalization.segments import build_segment


def popups(overlays: list[Overlay]) -> list[Overlay]:
    return [o for o in overlays if o.slot not in PERSISTENT_SLOTS]


def assert_screen_rules(overlays: list[Overlay]) -> None:
    shown = popups(overlays)
    for o in shown:
        at = [x for x in shown if x.start_ms <= o.start_ms < x.start_ms + x.duration_ms]
        assert len(at) <= MAX_VISIBLE, f"{len(at)} overlays at {o.start_ms}"
        assert len({x.slot for x in at}) == len(at), f"two overlays share a slot at {o.start_ms}"
    for slot in PERSISTENT_SLOTS:
        same = sorted((o for o in overlays if o.slot == slot), key=lambda o: o.start_ms)
        assert all(a.start_ms + a.duration_ms <= b.start_ms for a, b in pairwise(same))


def cand(id_, ready, prio, slot="lower_third", timing="live", dur=4000, min_dur=2000, delay=3000, type_="event_card"):
    return Candidate(id=id_, type=type_, slot=slot, ready_ms=ready, duration_ms=dur, min_duration_ms=min_dur, priority=prio,
                     timing=timing, max_delay_ms=delay)


# --- scheduler rules ----------------------------------------------------------------------------

def test_higher_priority_wins_the_slot_and_lower_is_delayed_or_dropped():
    tl = Timeline(end_ms=60_000)
    res = schedule([cand("low", 1000, 10, delay=0), cand("high", 1000, 90), cand("later", 1000, 50, delay=6000)], tl, "s", "m")
    by_id = {o.id.split(":")[1]: o for o in res.overlays}
    assert by_id["high"].start_ms == 1000
    assert by_id["later"].start_ms == 5000  # waits until the slot is free
    assert res.dropped == ["low"]


def test_never_more_than_two_popups():
    tl = Timeline(end_ms=60_000)
    cs = [cand(f"c{i}", 1000, 50 + i, slot=s) for i, s in enumerate(["lower_third", "ticker", "pitch", "fullscreen"])]
    res = schedule(cs, tl, "s", "m")
    assert_screen_rules(res.overlays)
    assert len([o for o in res.overlays if o.start_ms == 1000]) == 2


def test_insights_only_in_stoppages_and_never_during_an_attack():
    tl = Timeline(end_ms=100_000, attacks=[(10_000, 20_000), (26_000, 40_000)], stoppages=[(22_000, 26_000), (50_000, 58_000)])
    sd = cand("sd", 12_000, 90, slot="pitch", timing="stoppage", dur=9000, min_dur=4000, delay=60_000, type_="sliding_doors")
    res = schedule([sd], tl, "s", "m")
    o = res.overlays[0]
    # the first stoppage leaves only 4 s before the next attack: exactly the minimum
    assert (o.start_ms, o.duration_ms) == (22_000, 4_000)
    assert not tl.overlaps_attack(o.start_ms, o.start_ms + o.duration_ms)


def test_insight_too_long_for_any_window_is_dropped():
    tl = Timeline(end_ms=100_000, attacks=[(10_000, 20_000), (23_000, 40_000)], stoppages=[(21_000, 23_000)])
    sd = cand("sd", 12_000, 90, slot="pitch", timing="stoppage", dur=9000, min_dur=4000, delay=30_000)
    assert schedule([sd], tl, "s", "m").dropped == ["sd"]


def test_min_display_time_is_respected():
    tl = Timeline(end_ms=60_000)
    res = schedule([cand("a", 1000, 90, dur=4000), cand("b", 3000, 50, dur=4000, min_dur=3000, delay=0)], tl, "s", "m")
    assert [o.id for o in res.overlays] == ["s:a"] and res.dropped == ["b"]


def test_random_candidates_keep_all_rules():
    rng = random.Random(7)
    attacks = sorted({(a, a + rng.randint(2000, 9000)) for a in range(5000, 290_000, 20_000)})
    tl = Timeline(end_ms=300_000, attacks=attacks, stoppages=[(b, b + 6000) for _, b in attacks])
    slots = ["lower_third", "ticker", "pitch"]
    cs = []
    for i in range(300):
        timing = rng.choice(["live", "calm", "stoppage"])
        cs.append(cand(f"c{i}", rng.randint(0, 290_000), rng.randint(0, 100), slot=rng.choice(slots), timing=timing,
                       dur=rng.randint(3000, 9000), min_dur=2500, delay=rng.choice([0, 2000, 20_000])))
    cs += [cand(f"p{i}", i * 10_000, 30, slot="scorebug", timing="persistent", dur=10_000) for i in range(30)]
    res = schedule(cs, tl, "s", "m")
    assert_screen_rules(res.overlays)
    by_id = {c.id: c for c in cs}
    for o in popups(res.overlays):
        c = by_id[o.id.split(":")[1]]
        assert o.duration_ms >= c.min_duration_ms
        assert c.ready_ms <= o.start_ms <= c.ready_ms + c.max_delay_ms
        if c.timing in ("calm", "stoppage"):
            assert not tl.overlaps_attack(o.start_ms, o.start_ms + o.duration_ms)
        if c.timing == "stoppage":
            assert tl.stoppage_at(o.start_ms) is not None
    assert len(res.overlays) + len(res.dropped) == len(cs)


# --- end to end on a small synthetic match ------------------------------------------------------

def synthetic_match():
    m = make_match(n_frames=900)
    # H10 (index 9) carries the ball into the final third between frames 100 and 200 and scores at 150
    m.pos[100:201, 9] = [80.0, 34.0]
    own(m, 9, 100, 149)
    m.score[155:] = [1, 0]
    # A20 doesn't exist in make_match: follow A5 (index 15)
    ev = [
        MatchEvent(id="shot1", match_id="test", t_ms=14_900, frame=149, type="shot", team="home", player_id="H10",
                   start_xy=(80.0, 34.0), outcome="goal", meta={"distance_m": 25.0, "shot_speed_kmh": 101.0, "xg": 0.1}),
        MatchEvent(id="goal1", match_id="test", t_ms=15_500, frame=155, type="goal", team="home", player_id="H10",
                   meta={"score": [1, 0], "shot_id": "shot1"}),
        MatchEvent(id="tk1", match_id="test", t_ms=40_000, frame=400, type="tackle", team="away", player_id="A5",
                   target_id="H3", start_xy=(20.0, 34.0), outcome="won"),
        MatchEvent(id="out1", match_id="test", t_ms=60_000, frame=600, type="out_of_play", team="home"),
    ]
    moments = [
        Moment(id="mo-goal", match_id="test", frame=149, t_ms=14_900, clock_s=268.2, kind="goal", score=1.0, team="home",
               player_ids=["H10"], event_ids=["shot1"], reason="goal"),
        Moment(id="mo-turn", match_id="test", frame=400, t_ms=40_000, clock_s=720.0, kind="dangerous_turnover", score=0.6,
               team="away", player_ids=["H3", "A5"], event_ids=["tk1"], reason="turnover"),
    ]

    def ins(mo: Moment, actual: float, best: float, iv: Intervention) -> Insight:
        h = Hypothesis(text="alt", intervention=iv, baseline_p_goal=actual, counterfactual_p_goal=best, seed_spread=0.002,
                       verdict="accepted")
        return Insight(id=f"{mo.id}-insight", moment_id=mo.id, claim="test claim", evidence=[*mo.event_ids, "rollout:1"],
                       numbers={"actual_p_goal": actual, "best_alt_p_goal": best, "delta_p_goal": best - actual},
                       verified=True, confidence="clear", hypotheses=[h], ghost_paths=[[(1.0, 2.0)]])

    insights = [ins(moments[0], 0.21, 0.08, Intervention(kind="swap_action", params={"action": "carry"})),
                ins(moments[1], 0.02, 0.06, Intervention(kind="move_player", params={"player_id": "A5", "dx": 3.0, "dy": 4.0}))]
    return m, ev, moments, insights


def test_pipeline_end_to_end_with_fake_llm():
    m, ev, moments, insights = synthetic_match()
    segments = [build_segment(p) for p in [
        ViewerProfile(mode="analyst", language="en", my_metric="possession"),
        ViewerProfile(mode="club_fan", language="en", favourite_club="home"),
        ViewerProfile(mode="club_fan", language="de", favourite_club="away"),
        ViewerProfile(mode="player_focus", language="es", favourite_players=["A5"]),
        ViewerProfile(mode="casual", language="en"),
    ]]
    frames = [m.frame_state(f) for f in range(m.n_frames)]
    timeline = build_timeline(frames, ev)
    assert timeline.attacks and timeline.attacks[0][0] == 10_000
    result = produce(context_from_grf(m), frames, ev, moments, insights, segments, fake_production_llm())
    ov = result.overlays

    for sid, overlays in ov.items():
        assert_screen_rules(overlays[:-1])
        assert overlays[-1].type == "recap" and overlays[-1].slot == "fullscreen"
        assert all(o.segment_id == sid and o.match_id == "test" for o in overlays)
        for o in overlays:
            if o.type in ("insight", "sliding_doors"):
                assert not timeline.overlaps_attack(o.start_ms, o.start_ms + o.duration_ms)
                assert timeline.stoppage_at(o.start_ms) is not None and o.evidence

    goal_cards = {sid: next(o for o in ovs if o.type == "event_card" and "goal1" in o.evidence) for sid, ovs in ov.items()}
    assert goal_cards["club_fan-home-en"].headline.startswith("GOAL!") and "for us" in goal_cards["club_fan-home-en"].body
    assert goal_cards["club_fan-away-de"].headline == "Gegentor"
    assert goal_cards["player_focus-A5-es"].headline == "Gol en contra"

    sd = {sid: [o for o in ovs if o.type in ("insight", "sliding_doors")] for sid, ovs in ov.items()}
    assert {o.payload["moment_id"] for o in sd["player_focus-A5-es"]} == {"mo-turn"}  # only A5's moment
    assert sd["analyst-en"][0].type == "sliding_doors" and "hypotheses" in sd["analyst-en"][0].payload
    assert sd["casual-en"] and all(o.type == "insight" and "hypotheses" not in o.payload for o in sd["casual-en"])
    assert {o.payload["moment_id"] for o in sd["casual-en"]} == {"mo-goal"}  # no tactical moments for casual viewers

    # persistent elements differ: analyst follows a metric, player focus gets the player card with a heatmap
    assert any(o.payload.get("my_metric") for o in ov["analyst-en"])
    cards = [o for o in ov["player_focus-A5-es"] if o.slot == "side_panel"]
    assert cards and all("heatmap" in o.payload for o in cards)
    assert result.stats["player_focus-A5-es"]["llm_calls"] < result.stats["analyst-en"]["llm_calls"]


def test_event_cues_have_evidence_and_no_duration_totals():
    m, ev, _, _ = synthetic_match()
    cues = event_cues(ev, context_from_grf(m))
    assert {c.kind for c in cues} >= {"goal", "player_tag", "milestone", "turnover"}
    assert all(c.evidence for c in cues)
    assert not any(k in c.data for c in cues for k in ("distance_km", "passes", "pass_count"))
