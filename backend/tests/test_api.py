import asyncio

import pytest
from conftest import make_match
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.live import ExportedMatch, live_messages
from app.api.main import create_app
from app.export.exporter import export_match, load_overlays
from app.models import Overlay


def overlay(id_: str, segment: str, start_ms: int) -> dict:
    return Overlay(id=id_, match_id="test", segment_id=segment, start_ms=start_ms, duration_ms=1000,
                   slot="lower_third", type="event_card").model_dump()


@pytest.fixture
def root(tmp_path):
    overlays = load_overlays([overlay("o-an", "analyst-en", 1500), overlay("o-all", "*", 500),
                              overlay("o-fan", "club_fan-home-en", 2000)])
    export_match(make_match(n_frames=40), tmp_path / "test", overlays=overlays)
    return tmp_path


@pytest.fixture
def client(root):
    return TestClient(create_app(root))


def test_list_matches(client):
    res = client.get("/api/matches")
    assert res.status_code == 200
    [m] = res.json()
    assert m["match_id"] == "test" and m["n_frames"] == 40 and m["home"]["short"] == "NOR"


def test_serves_export_files_with_cors(client):
    res = client.get("/api/matches/test/frames.json", headers={"Origin": "http://localhost:5173"})
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "*"
    assert len(res.json()["t_ms"]) == 40
    assert client.get("/api/matches/test/insights.json").json() == []


@pytest.mark.parametrize("path", ["/api/matches/test/raw.jsonl", "/api/matches/nope/match.json",
                                  "/api/matches/test/video.mp4", "/api/matches/..%2F..%2Fetc/match.json"])
def test_unknown_things_are_404(client, path):
    assert client.get(path).status_code == 404


def test_websocket_replays_frames_events_and_segment_overlays(client):
    with client.websocket_connect("/api/matches/test/live?speed=1000&step=2&segment=analyst-en") as ws:
        messages = []
        while True:
            msg = ws.receive_json()
            messages.append(msg)
            if msg["type"] == "end":
                break
    assert messages[0]["type"] == "hello" and messages[0]["match"]["match_id"] == "test"
    frames = [m["frame"] for m in messages if m["type"] == "frame"]
    assert frames == [*range(0, 40, 2), 39]
    assert any(m["type"] == "event" and m["event"]["type"] == "kickoff" for m in messages)
    assert [m["stats"]["frame"] for m in messages if m["type"] == "stats"] == [0, 10, 20, 30, 39]
    overlays = [(m["overlay"]["id"], i) for i, m in enumerate(messages) if m["type"] == "overlay"]
    assert [o for o, _ in overlays] == ["o-all", "o-an"]
    # an overlay arrives once match time reaches its start_ms (frame 15 itself is skipped by step=2)
    before = [m for m in messages[: overlays[1][1]] if m["type"] == "frame"][-1]
    after = next(m for m in messages[overlays[1][1]:] if m["type"] == "frame")
    assert (before["t_ms"], after["t_ms"]) == (1400, 1600)


def test_websocket_unknown_match_is_closed(client):
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/matches/nope/live") as ws:
        ws.receive_json()


def test_live_messages_all_segments_and_start_frame(root):
    match = ExportedMatch.load(root / "test")

    async def collect():
        return [m async for m in live_messages(match, start_frame=18, segment=None, realtime=False)]

    messages = asyncio.run(collect())
    assert next(m["frame"] for m in messages if m["type"] == "frame") == 18
    # o-all (500..1500 ms) ended before frame 18 (1800 ms); o-an is still on screen and is sent at once
    assert [m["overlay"]["id"] for m in messages if m["type"] == "overlay"] == ["o-an", "o-fan"]


def test_serves_export_folder_and_built_frontend(root, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>player</html>")
    client = TestClient(create_app(root, frontend_dir=dist))
    assert client.get("/").text == "<html>player</html>"
    assert client.get("/export/test/match.json").json()["match_id"] == "test"
    assert client.get("/api/matches").status_code == 200  # not shadowed by the "/" mount
    assert client.get("/export/test/raw.jsonl").status_code == 404


def test_no_frontend_mount_without_build(client):
    assert client.get("/").status_code == 404
