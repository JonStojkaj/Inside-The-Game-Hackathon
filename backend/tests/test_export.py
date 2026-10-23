import json

import pytest
from conftest import make_match, own

from app.export.exporter import (
    FILES,
    PLAYER_STAT_FIELDS,
    STATS_EVERY,
    export_from_dir,
    export_match,
    load_overlays,
)
from app.models import Insight, Overlay


def overlay(id_: str, segment: str, start_ms: int) -> Overlay:
    return Overlay(id=id_, match_id="test", segment_id=segment, start_ms=start_ms, duration_ms=2000,
                   slot="lower_third", type="event_card", headline=id_)


@pytest.fixture
def exported(tmp_path):
    match = make_match(n_frames=45)
    match.pos[:, 0, 0] += 0.04  # 10.04 -> rounds to 10.0
    match.score[30:] = [1, 0]
    own(match, 5, 10, 20)
    sizes = export_match(match, tmp_path)
    return match, tmp_path, sizes


def load(path, name):
    return json.loads((path / name).read_text())


def test_writes_every_file_and_reports_sizes(exported):
    _, out, sizes = exported
    assert set(sizes) == set(FILES)
    for name in FILES:
        assert (out / name).stat().st_size == sizes[name]
    assert load(out, "insights.json") == []
    assert load(out, "overlays.json") == {}


def test_match_json_contract(exported):
    match, out, _ = exported
    meta = load(out, "match.json")
    assert set(meta) == {"match_id", "home", "away", "players", "fps", "n_frames", "duration_ms",
                         "clock_scale", "final_score", "video"}
    assert meta["home"] == {"key": "home", "name": "FC Northbridge", "short": "NOR", "color": "#d6262e"}
    assert meta["fps"] == 10 and meta["n_frames"] == 45 and meta["duration_ms"] == 4400
    assert meta["final_score"] == [1, 0] and meta["video"] is None
    assert [p["id"] for p in meta["players"]] == [p.id for p in match.players]
    assert set(meta["players"][0]) == {"id", "team", "name", "number", "position"}
    # frame f shows clock f * 0.1 * clock_scale, the last frame shows 90'
    assert meta["clock_scale"] * 0.1 * 44 == pytest.approx(5400, abs=0.01)


def test_frames_json_contract(exported):
    _, out, _ = exported
    fr = load(out, "frames.json")
    assert set(fr) == {"t_ms", "ball", "players", "owner", "score", "mode"}
    assert all(len(v) == 45 for v in fr.values())
    assert fr["t_ms"][:3] == [0, 100, 200]
    assert fr["ball"][0] == [52.5, 34.0, 0.0]
    assert len(fr["players"][0]) == 22 and fr["players"][0][0] == [10.0, 10.0]
    assert fr["owner"][9:12] == [-1, 5, 5]
    assert fr["score"][29:31] == [[0, 0], [1, 0]]
    assert fr["mode"][0] == "normal"


def test_stats_sampled_and_trimmed(exported):
    _, out, _ = exported
    stats = load(out, "stats.json")
    assert [s["frame"] for s in stats] == [0, 10, 20, 30, 40, 44]
    assert STATS_EVERY == 10
    snap = stats[-1]
    for key in ("t_ms", "clock_s", "score", "teams", "players", "pressure_on_ball", "pressing", "control", "rhythm"):
        assert key in snap
    assert set(snap["players"]["H5"]) == set(PLAYER_STAT_FIELDS)
    assert snap["score"] == [1, 0]


def test_events_and_moments_are_model_lists(exported):
    _, out, _ = exported
    events = load(out, "events.json")
    assert events[0]["type"] == "kickoff"
    assert isinstance(load(out, "moments.json"), list)


def test_insights_overlays_and_video_are_copied_in(tmp_path):
    match = make_match()
    video = tmp_path / "in.mp4"
    video.write_bytes(b"\x00" * 64)
    insight = Insight(id="i1", moment_id="m1", claim="c", evidence=["e1"], numbers={"p": 0.3}, verified=True,
                      confidence="clear", ghost_paths=[[(1.0, 2.0), (3.0, 4.0)]])
    overlays = load_overlays([overlay("o1", "analyst-en", 1000).model_dump(), overlay("o2", "*", 0).model_dump()])
    sizes = export_match(match, tmp_path / "out", insights=[insight], overlays=overlays, video=video)
    out = tmp_path / "out"
    assert sizes["video.mp4"] == 64
    assert load(out, "match.json")["video"] == {"file": "video.mp4", "fps": 10}
    assert load(out, "insights.json")[0]["ghost_paths"] == [[[1.0, 2.0], [3.0, 4.0]]]
    assert set(load(out, "overlays.json")) == {"analyst-en", "*"}


def test_demo_size_budget():
    # a 3001-frame recording must stay well below the 5 MB budget for frames.json
    match = make_match(n_frames=3001)
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        sizes = export_match(match, Path(d))
    assert sizes["frames.json"] < 5 * 1024 * 1024


def test_export_from_dir_keeps_unknown_insight_fields_and_picks_up_video(tmp_path):
    rec = tmp_path / "demo-7"
    rec.mkdir()
    row = {"left_team": [[-0.5, 0.0]] * 11, "right_team": [[0.5, 0.0]] * 11,
           "left_team_direction": [[0.0, 0.0]] * 11, "right_team_direction": [[0.0, 0.0]] * 11,
           "ball": [0.0, 0.0, 0.1], "ball_owned_team": -1, "ball_owned_player": -1, "game_mode": 0,
           "score": [0, 0], "left_team_roles": list(range(10)) + [9], "right_team_roles": list(range(10)) + [9]}
    (rec / "raw.jsonl").write_text("\n".join(json.dumps(row) for _ in range(5)))
    (rec / "video.mp4").write_bytes(b"\x00" * 8)
    insight = Insight(id="i1", moment_id="m1", claim="c", evidence=[], numbers={}, verified=True,
                      confidence="slight").model_dump(mode="json") | {"metric": "p_keep"}
    (tmp_path / "insights.json").write_text(json.dumps([insight]))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"id": "x"}]))

    out, sizes = export_from_dir(rec, tmp_path / "export", insights_path=tmp_path / "insights.json")
    assert out == tmp_path / "export" / "demo-7"
    assert load(out, "insights.json")[0]["metric"] == "p_keep"
    assert load(out, "match.json")["video"] == {"file": "video.mp4", "fps": 10}
    assert sizes["video.mp4"] == 8
    assert (out / "raw.jsonl").read_text() == (rec / "raw.jsonl").read_text()  # for Ask Sliding Doors
    assert sizes["raw.jsonl"] > 0
    with pytest.raises(ValueError):
        export_from_dir(rec, tmp_path / "export", insights_path=bad)
