"""spikes/export_demo.py CLI: --insights / --overlays / --video, id-agnostic. Synthetic data only."""

import importlib.util
import json
from pathlib import Path

import pytest
from conftest import make_match

from app.export.exporter import VIDEO_FILE, export_match
from app.models import Insight, Overlay

SPIKE = Path(__file__).resolve().parents[2] / "spikes" / "export_demo.py"
ROW = {"left_team": [[-0.5, 0.0]] * 11, "right_team": [[0.5, 0.0]] * 11,
       "left_team_direction": [[0.0, 0.0]] * 11, "right_team_direction": [[0.0, 0.0]] * 11,
       "ball": [0.0, 0.0, 0.1], "ball_owned_team": -1, "ball_owned_player": -1, "game_mode": 0,
       "score": [0, 0], "left_team_roles": list(range(10)) + [9], "right_team_roles": list(range(10)) + [9]}


@pytest.fixture(scope="module")
def cli():
    spec = importlib.util.spec_from_file_location("export_demo", SPIKE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def recording(root: Path, name: str, video: bytes | None = None) -> Path:
    rec = root / "matches" / name
    rec.mkdir(parents=True)
    (rec / "raw.jsonl").write_text("\n".join(json.dumps(ROW) for _ in range(5)))
    if video is not None:
        (rec / VIDEO_FILE).write_bytes(video)
    return rec


def write_inputs(root: Path, match_id: str) -> tuple[Path, Path]:
    insight = Insight(id="i1", moment_id="m1", claim="c", evidence=["e"], numbers={"p_goal": 0.2}, verified=True,
                      confidence="clear").model_dump(mode="json") | {"metric": "p_goal"}
    overlays = [
        Overlay(id=f"o{i}", match_id=match_id, segment_id=seg, start_ms=100 * i, duration_ms=2000,
                slot="lower_third", type="event_card", headline=f"o{i}").model_dump(mode="json")
        for i, seg in enumerate(["analyst-en", "casual-de", "*"])
    ]
    ins, ovl = root / "insights.json", root / "overlays.json"
    ins.write_text(json.dumps([insight]))
    ovl.write_text(json.dumps(overlays))  # flat list, grouped by segment_id on export
    return ins, ovl


def load(path: Path, name: str):
    return json.loads((path / name).read_text())


def test_all_flags_and_match_id_from_folder_name(cli, tmp_path, capsys):
    rec = recording(tmp_path, "demo-107")
    ins, ovl = write_inputs(tmp_path, "demo-107")
    video = tmp_path / "rendered.mp4"
    video.write_bytes(b"\x01" * 32)

    out = cli.main([str(rec), str(tmp_path / "export"), "--insights", str(ins), "--overlays", str(ovl),
                    "--video", str(video)])

    assert out == tmp_path / "export" / "demo-107"
    meta = load(out, "match.json")
    assert meta["match_id"] == "demo-107"
    assert meta["video"] == {"file": "video.mp4", "fps": 10}
    assert (out / VIDEO_FILE).read_bytes() == b"\x01" * 32
    assert load(out, "insights.json")[0]["metric"] == "p_goal"
    assert {seg: [o["id"] for o in items] for seg, items in load(out, "overlays.json").items()} == {
        "analyst-en": ["o0"], "casual-de": ["o1"], "*": ["o2"]}
    printed = capsys.readouterr().out
    assert "exported demo-107" in printed and "insights: 1" in printed and "video.mp4" in printed


def test_match_id_override_and_default_video_from_recording(cli, tmp_path):
    rec = recording(tmp_path, "full-104", video=b"\x02" * 8)
    out = cli.main([str(rec), str(tmp_path / "export"), "--match-id", "demo-104"])
    assert out.name == "demo-104"
    assert load(out, "match.json")["match_id"] == "demo-104"
    assert load(out, "match.json")["video"] == {"file": "video.mp4", "fps": 10}
    assert (out / VIDEO_FILE).stat().st_size == 8
    assert load(out, "insights.json") == [] and load(out, "overlays.json") == {}


def test_without_video(cli, tmp_path):
    out = cli.main([str(recording(tmp_path, "demo-1")), str(tmp_path / "export")])
    assert load(out, "match.json")["video"] is None
    assert not (out / VIDEO_FILE).exists()


@pytest.mark.parametrize("flag", ["--insights", "--overlays", "--video"])
def test_missing_input_files_fail_fast(cli, tmp_path, flag):
    rec = recording(tmp_path, "demo-2")
    with pytest.raises(SystemExit):
        cli.main([str(rec), str(tmp_path / "export"), flag, str(tmp_path / "nope.json")])
    assert not (tmp_path / "export").exists()


def test_folder_without_recording_fails(cli, tmp_path):
    with pytest.raises(SystemExit):
        cli.main([str(tmp_path), str(tmp_path / "export")])


def test_reexport_without_video_removes_stale_video(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"\x00" * 4)
    export_match(make_match(), tmp_path / "out", video=video)
    assert (tmp_path / "out" / VIDEO_FILE).exists()
    export_match(make_match(), tmp_path / "out")
    assert not (tmp_path / "out" / VIDEO_FILE).exists()
    assert load(tmp_path / "out", "match.json")["video"] is None


def test_video_already_in_place_is_kept(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / VIDEO_FILE).write_bytes(b"\x03" * 5)
    sizes = export_match(make_match(), out, video=out / VIDEO_FILE)
    assert sizes[VIDEO_FILE] == 5 and (out / VIDEO_FILE).read_bytes() == b"\x03" * 5


def test_missing_video_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        export_match(make_match(), tmp_path / "out", video=tmp_path / "missing.mp4")
