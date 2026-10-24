"""Live AI commentator: timeline rules, mode tone, numbers from data, audio keys, API + Speech-off fallback.
No network: the synthesizer is a fake."""

from __future__ import annotations

import json
import re
import string
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.commentary import CommentaryService
from app.api.main import create_app
from app.commentary.data import League, load_match
from app.commentary.engine import GAP_MS, LANGS, MAX_WORDS, MODES, Segment, build_timeline, word_count
from app.commentary.phrases import PHRASES
from app.commentary.speech import AudioCache, SpeechSettings

ROSTER = [("H1", "home", "Tomas Vell", 1, "GK"), ("H8", "home", "Emil Strand", 8, "CM"), ("H20", "home", "Leo Marchetti", 20, "CM"),
          ("H9", "home", "Mateo Brann", 9, "CF"), ("A1", "away", "Arne Dahl", 1, "GK"), ("A20", "away", "Kai Nakamura", 20, "CM"),
          ("A11", "away", "Bastian Holt", 11, "LM"), ("A2", "away", "Callum Reyes", 2, "RB")]
LEAGUE = {"clubs": [
    {"name": "Kingsmere Rovers", "short": "KMR", "played": 9, "won": 7, "drawn": 1, "lost": 1, "gf": 21, "ga": 8, "form": "WWWDW", "rivals": ["NOR"]},
    {"name": "Ashford Vale", "short": "ASV", "played": 9, "won": 5, "drawn": 2, "lost": 2, "gf": 15, "ga": 9, "form": "WDWWL", "rivals": []},
    {"name": "FC Northbridge", "short": "NOR", "played": 9, "won": 4, "drawn": 4, "lost": 1, "gf": 13, "ga": 9, "form": "DWWWW",
     "rivals": ["HCY", "KMR"]},
    {"name": "Harbour City", "short": "HCY", "played": 9, "won": 4, "drawn": 3, "lost": 2, "gf": 14, "ga": 11, "form": "LWWDW", "rivals": ["NOR"]},
], "season_ratings": {"Leo Marchetti": 6.8}, "default_rating": 6.6}


def ev(i: int, frame: int, type_: str, team: str | None = None, player: str | None = None, known: int | None = None, **kw) -> dict:
    meta = kw.pop("meta", {})
    if known is not None:
        meta["known_frame"] = known
    return {"id": f"t-{frame:05d}-{type_}-{i}", "match_id": "t", "t_ms": frame * 100, "frame": frame, "type": type_, "team": team,
            "player_id": player, "target_id": kw.get("target"), "start_xy": kw.get("xy", [60.0, 30.0]), "end_xy": None,
            "outcome": kw.get("outcome"), "meta": meta}


def events() -> list[dict]:
    out = [ev(0, 0, "kickoff", "home", meta={"score": [0, 0]})]
    for k, (a, b) in enumerate([("H8", "H20"), ("H20", "H9"), ("H9", "H8"), ("H8", "H20"), ("H20", "H9")]):
        out.append(ev(1 + k, 50 + 15 * k, "pass", "home", a, known=60 + 15 * k, target=b, outcome="complete",
                      meta={"distance_m": 12.0, "difficulty": 40.0, "threat_gain": 0.01}))
    out.append(ev(10, 160, "shot", "home", "H9", known=170, outcome="saved", meta={"distance_m": 21.3, "shot_speed_kmh": 98.4, "xg": 0.07}))
    out.append(ev(11, 172, "pass", "away", "A1", known=180, target="A20", outcome="complete", meta={"distance_m": 20.0}))
    out.append(ev(12, 200, "tackle", "home", "H20", target="A20", outcome="won"))
    out.append(ev(13, 230, "pass", "home", "H20", known=238, target="H8", outcome="complete", meta={"distance_m": 9.0, "threat_gain": 0.09}))
    out.append(ev(14, 240, "shot", "home", "H8", known=246, outcome="goal", meta={"distance_m": 16.7, "shot_speed_kmh": 124.4, "xg": 0.13}))
    out.append(ev(15, 246, "goal", "home", "H8", meta={"score": [1, 0], "shot_id": "t-00240-shot-14"}))
    out.append(ev(16, 420, "interception", "away", "A11", target="H20"))
    out.append(ev(17, 440, "shot", "away", "A20", known=446, outcome="goal", meta={"distance_m": 10.0, "shot_speed_kmh": 125.0, "xg": 0.31}))
    out.append(ev(18, 446, "goal", "away", "A20", meta={"score": [1, 1], "shot_id": "t-00440-shot-17"}))
    return out


def stats() -> list[dict]:
    snaps = []
    for s in range(60):
        teams = {t: {"team": t, "possession": p, "distance_km": 0.04 * s, "passes": 0} for t, p in (("home", 0.58), ("away", 0.42))}
        players = {pid: {"id": pid, "team": team, "top_speed_kmh": 20.0 + i + (s > 30) * 6.5} for i, (pid, team, *_r) in enumerate(ROSTER)}
        snaps.append({"t_ms": s * 1000, "teams": teams, "players": players,
                      "control": {"control_team": "home", "control_share": 0.7, "chaos": 0.3, "possession_changes_per_min": 4.0},
                      "rhythm": {"actions_per_min": 20.0, "trend": "steady"}})
    return snaps


MOMENT = {"id": "t-m00230-decisive_pass", "frame": 230, "t_ms": 23000, "kind": "decisive_pass", "team": "home",
          "player_ids": ["H20", "H8"], "event_ids": ["t-00230-pass-13"]}
INSIGHT = {"moment_id": MOMENT["id"], "verified": True, "metric": "p_goal", "decision_frame": 230,
           "numbers": {"actual_p_goal": 0.0647, "best_alt_p_goal": 0.1007, "delta_p_goal": 0.036},
           "hypotheses": [{"verdict": "accepted", "counterfactual_p_goal": 0.1007, "intervention": {"kind": "swap_action", "params": {"action": "carry"}}}]}


def write_export(root: Path, match_id: str = "t") -> Path:
    folder = root / match_id
    folder.mkdir(parents=True)
    meta = {"match_id": match_id, "home": {"key": "home", "name": "FC Northbridge", "short": "NOR"},
            "away": {"key": "away", "name": "Harbour City", "short": "HCY"},
            "players": [{"id": p, "team": t, "name": n, "number": no, "position": pos} for p, t, n, no, pos in ROSTER],
            "fps": 10, "n_frames": 600, "duration_ms": 60000, "clock_scale": 18.0, "final_score": [1, 1]}
    for name, data in (("match.json", meta), ("events.json", events()), ("stats.json", stats()), ("moments.json", [MOMENT]),
                       ("insights.json", [INSIGHT]), ("league.json", LEAGUE), ("frames.json", {"t_ms": []}), ("overlays.json", {})):
        (folder / name).write_text(json.dumps(data))
    return folder


@pytest.fixture
def md(tmp_path):
    return load_match(write_export(tmp_path), League.load(tmp_path / "t" / "league.json"))


def all_segments(md):
    for lang in LANGS:
        for mode in MODES:
            if mode == "club_fan":
                yield from (Segment.make(md, mode, lang, club=c) for c in ("home", "away"))
            elif mode == "player_focus":
                yield from (Segment.make(md, mode, lang, player=p) for p in ("H20", "A20"))
            else:
                yield Segment.make(md, mode, lang)


def test_timeline_spacing_no_overlap_short_lines_and_determinism(md):
    for seg in all_segments(md):
        lines = build_timeline(md, seg)
        assert len(lines) >= 6, seg.id
        for a, b in zip(lines, lines[1:]):
            assert b.start_ms >= a.start_ms + a.duration_ms + GAP_MS, (seg.id, a, b)
        for ln in lines:
            assert word_count(ln.text) <= MAX_WORDS, ln.text
            assert 0 <= ln.start_ms and ln.end_ms <= 60000
            assert "{" not in ln.text
        assert [(x.start_ms, x.text) for x in build_timeline(md, seg)] == [(x.start_ms, x.text) for x in lines]


def test_no_template_repeats_within_a_minute(md):
    lines = build_timeline(md, Segment.make(md, "club_fan", "en", club="home"))
    seen: dict[str, int] = {}
    for ln in lines:
        assert ln.template not in seen or ln.start_ms - seen[ln.template] >= 60000, ln
        seen[ln.template] = ln.start_ms


def test_never_spoils_an_event_before_it_is_known(md):
    lines = build_timeline(md, Segment.make(md, "casual", "en"))
    goals = [ln for ln in lines if ln.kind == "goal"]
    assert [g.start_ms >= 24600 for g in goals][0] and goals[1].start_ms >= 44600


def test_club_fan_is_biased_own_goal_vs_opponent_goal(md):
    home = {ln.kind + str(i): ln for i, ln in enumerate(x for x in build_timeline(md, Segment.make(md, "club_fan", "en", club="home")) if x.kind == "goal")}
    first, second = list(home.values())
    assert first.tone == "us" and second.tone == "them"
    assert re.search(r"\b(us|YES|Get in)\b", first.text) and "!" in first.text
    assert re.search(r"\b(them|They've)\b", second.text)
    away = [x for x in build_timeline(md, Segment.make(md, "club_fan", "en", club="away")) if x.kind == "goal"]
    assert away[0].tone == "them" and away[1].tone == "us"


def test_analyst_states_numbers_casual_is_a_tv_commentator(md):
    analyst = build_timeline(md, Segment.make(md, "analyst", "en"))
    assert all(ln.tone in ("a", "n") for ln in analyst)
    numeric = [ln for ln in analyst if re.search(r"\d", ln.text)]
    assert len(numeric) >= len(analyst) / 3
    assert any("xG" in ln.text for ln in analyst)
    casual = build_timeline(md, Segment.make(md, "casual", "en"))
    assert all(ln.tone == "n" for ln in casual)


def test_player_focus_follows_the_chosen_player(md):
    lines = build_timeline(md, Segment.make(md, "player_focus", "en", player="H20"))
    assert lines[1].kind == "intro_player" and "Leo Marchetti" in lines[1].text
    assert sum("Marchetti" in ln.text for ln in lines) >= 3


def test_numbers_come_from_the_data(md):
    """Templates hold no digits; the digits spoken about a shot / Sliding Doors are exactly the data's."""
    for lang, pool in PHRASES.items():
        for kind, tones in pool.items():
            for templates in tones.values():
                for t in templates:
                    assert not re.search(r"\d", t), (lang, kind, t)
                    assert {f for _, f, _, _ in string.Formatter().parse(t) if f} <= {
                        "home", "away", "us", "them", "team", "scorer", "score", "dist", "speed", "xg", "assist", "player", "gk",
                        "target", "count", "n", "acc", "gain", "action", "action_noun", "action_cap", "alt", "actual", "keep",
                        "pos", "ph", "pa", "p", "done", "total", "sh", "sa", "xh", "xa", "km", "share", "changes", "apm", "minute",
                        "minute_ord", "win", "rival", "rpos", "wins", "full", "num", "rating", "season", "k"}, t
    lines = build_timeline(md, Segment.make(md, "analyst", "en"))
    saved = next(ln for ln in lines if ln.kind == "shot_saved")
    assert set(re.findall(r"\d+(?:\.\d+)?", saved.text)) <= {"21", "98", "0.07"}
    sd = next(ln for ln in lines if ln.kind.startswith("sd_"))
    assert "10.1%" in sd.text and "6.5%" in sd.text
    de = next(ln for ln in build_timeline(md, Segment.make(md, "analyst", "de")) if ln.kind.startswith("sd_"))
    assert "10,1 %" in de.text


def test_club_fan_table_stakes_from_the_league(md):
    lines = build_timeline(md, Segment.make(md, "club_fan", "en", club="home"))
    intro = next(ln for ln in lines if ln.kind == "intro_fan")
    assert "3rd" in intro.text and "2nd" in intro.text  # NOR 3rd before kick-off; a win -> 19 pts, 2nd behind KMR


def test_bad_segment_parameters():
    md_ = None
    with pytest.raises(ValueError):
        Segment.make(md_, "pundit", "en")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Segment.make(md_, "casual", "fr")  # type: ignore[arg-type]


# ------------------------------------------------------------------------------------------------ API


class FakeSpeech:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, ssml: str) -> bytes:
        self.calls.append(ssml)
        return b"ID3fake-mp3"


def client_for(tmp_path: Path, speech: FakeSpeech | None, key: str = "") -> tuple[TestClient, CommentaryService]:
    write_export(tmp_path / "export")
    audio = AudioCache(tmp_path / "cache", SpeechSettings(key=key, per_minute=2), speech)
    service = CommentaryService(tmp_path / "export", [], audio)
    return TestClient(create_app(tmp_path / "export", frontend_dir=tmp_path / "nodist", commentary=service)), service


def test_api_contract_and_lazy_cached_synthesis(tmp_path):
    speech = FakeSpeech()
    client, _ = client_for(tmp_path, speech)
    res = client.get("/api/matches/t/commentary?mode=club_fan&club=away&lang=de")
    assert res.status_code == 200
    body = res.json()
    assert body["segment"] == "club_fan-away-de" and body["speech"] is True
    line = body["lines"][0]
    assert set(line) == {"id", "start_ms", "duration_ms", "text", "kind", "priority", "audio_url"}
    url = line["audio_url"]
    assert url.startswith("/api/matches/t/commentary/audio/") and ".mp3?" in url
    audio = client.get(url)
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg" and audio.content == b"ID3fake-mp3"
    assert "de-DE-ConradNeural" in speech.calls[0] and "rate='+10%'" in speech.calls[0]
    assert client.get(url).status_code == 200 and len(speech.calls) == 1  # cached on disk

    # a fresh process (empty registry) still accepts the URL thanks to its segment parameters
    client2, _ = client_for(tmp_path / "again", FakeSpeech())
    assert client2.get(body["lines"][1]["audio_url"]).status_code == 200


def test_unknown_keys_rejected_and_rate_limited(tmp_path):
    speech = FakeSpeech()
    client, _ = client_for(tmp_path, speech)
    for path in ("/api/matches/t/commentary/audio/" + "0" * 24 + ".mp3", "/api/matches/t/commentary/audio/../../etc.mp3",
                 "/api/matches/t/commentary/audio/hello.mp3?mode=casual", "/api/matches/t/commentary/audio/" + "a" * 24 + ".wav"):
        assert client.get(path).status_code == 404, path
    assert speech.calls == []
    lines = client.get("/api/matches/t/commentary?mode=analyst").json()["lines"]
    assert [client.get(ln["audio_url"]).status_code for ln in lines[:3]] == [200, 200, 429]
    assert client.get("/api/matches/t/commentary?mode=pundit").status_code == 422
    assert client.get("/api/matches/t/commentary?mode=player_focus&player=X99").status_code == 422
    assert client.get("/api/matches/nope/commentary").status_code == 404


def test_speech_off_falls_back_to_captions_and_serves_prewarmed(tmp_path):
    client, service = client_for(tmp_path, None)
    body = client.get("/api/matches/t/commentary?mode=casual&lang=es").json()
    assert body["speech"] is False and all(ln["audio_url"] is None for ln in body["lines"]) and body["lines"][0]["text"]
    # a prewarmed file (baked into the image) is served even without Speech
    _, lines = service.timeline("t", "casual", "es", None, None)
    from app.commentary.engine import line_key

    key = line_key(lines[0], "es")
    (tmp_path / "export" / "t" / "commentary").mkdir()
    (tmp_path / "export" / "t" / "commentary" / f"{key}.mp3").write_bytes(b"ID3pre")
    first = client.get("/api/matches/t/commentary?mode=casual&lang=es").json()["lines"][0]
    assert first["audio_url"] and client.get(first["audio_url"]).content == b"ID3pre"
    second = client.get("/api/matches/t/commentary?mode=casual&lang=es").json()["lines"][1]
    assert second["audio_url"] is None
    assert client.get(f"/api/matches/t/commentary/audio/{line_key(lines[1], 'es')}.mp3?mode=casual&lang=es").status_code == 503
