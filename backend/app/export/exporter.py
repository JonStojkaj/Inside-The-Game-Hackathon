"""Export a recorded match into the static files the web player and the API serve.

Layout of `data/export/<match_id>/` (contract with the frontend):
  match.json     clubs, roster, fps, n_frames, duration_ms, clock_scale, final_score, video
  frames.json    compact per-frame arrays (index = frame), metres rounded to 0.1
  events.json    list[MatchEvent]
  moments.json   list[Moment]
  insights.json  list[Insight]                 (produced by the explain team, copied in)
  stats.json     list[StatsSnapshot], every STATS_EVERY frames, players trimmed
  overlays.json  {segment_id: list[Overlay]}   (produced by the production team, copied in)
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, TypeAdapter

from app.models import Insight, MatchEvent, Moment, Overlay
from app.source.events import derive_events
from app.source.grf import GAME_MODES, STEP_S, GrfMatch, load_grf_match
from app.stats.engine import StatsEngine
from app.stats.moments import detect_moments

FPS = round(1 / STEP_S)
STATS_EVERY = 10  # frames between stats snapshots (1 s of match time)
PLAYER_STAT_FIELDS = (
    "id", "name", "team", "number", "position",
    "speed_kmh", "top_speed_kmh", "passes", "passes_completed", "shots", "goals",
)
FILES = ("match.json", "frames.json", "events.json", "moments.json", "insights.json", "stats.json", "overlays.json")
VIDEO_FILE = "video.mp4"

_insights = TypeAdapter(list[Insight])
_overlays = TypeAdapter(dict[str, list[Overlay]])
_overlay_list = TypeAdapter(list[Overlay])


def clock_scale(match: GrfMatch) -> float:
    """Broadcast seconds per match second: frame f shows the clock f * STEP_S * clock_scale."""
    return match.clock_s(1) / STEP_S if match.n_frames > 1 else 1.0


def match_meta(match: GrfMatch, video: bool = False) -> dict[str, Any]:
    def club(c: Any) -> dict[str, str]:
        return {"key": c.key, "name": c.name, "short": c.short, "color": c.color}

    return {
        "match_id": match.match_id,
        "home": club(match.home),
        "away": club(match.away),
        "players": [
            {"id": p.id, "team": p.team, "name": p.name, "number": p.number, "position": p.position}
            for p in match.players
        ],
        "fps": FPS,
        "n_frames": match.n_frames,
        "duration_ms": match.t_ms(match.n_frames - 1),
        "clock_scale": round(clock_scale(match), 6),
        "final_score": [int(x) for x in match.score[-1]],
        "video": {"file": VIDEO_FILE, "fps": FPS} if video else None,
    }


def _round(a: np.ndarray) -> list:
    return (np.round(a, 1) + 0.0).tolist()  # + 0.0 turns -0.0 into 0.0


def frames_payload(match: GrfMatch) -> dict[str, list]:
    return {
        "t_ms": [match.t_ms(f) for f in range(match.n_frames)],
        "ball": _round(match.ball),
        "players": _round(match.pos),
        "owner": [int(o) for o in match.owner_idx],
        "score": match.score.astype(int).tolist(),
        "mode": [GAME_MODES.get(int(m), "normal") for m in match.game_mode],
    }


def stats_snapshots(match: GrfMatch, events: list[MatchEvent], every: int = STATS_EVERY) -> list[dict[str, Any]]:
    """Run the stats engine over the match in replay order and sample it every `every` frames."""
    by_frame: dict[int, list[MatchEvent]] = defaultdict(list)
    for e in events:
        by_frame[e.frame].append(e)
    engine = StatsEngine(match.match_id)
    out = []
    for f in range(match.n_frames):
        engine.on_frame(match.frame_state(f), clock_s=match.clock_s(f))
        for e in by_frame.get(f, ()):
            engine.on_event(e)
        if f % every == 0 or f == match.n_frames - 1:
            snap = engine.snapshot().model_dump(mode="json")
            snap["frame"] = f
            snap["players"] = {
                pid: {k: round(p[k], 1) if isinstance(p[k], float) else p[k] for k in PLAYER_STAT_FIELDS}
                for pid, p in snap["players"].items()
            }
            out.append(snap)
    return out


def load_insights(data: Any) -> list[dict[str, Any]]:
    """Validate a list[Insight] JSON value and return it unchanged, so fields added by newer
    versions of the model (e.g. `metric`) survive the copy."""
    _insights.validate_python(data)
    return list(data)


def load_overlays(data: Any) -> dict[str, list[dict[str, Any]]]:
    """Accept {segment_id: [Overlay]} or a flat [Overlay] list (grouped by segment_id); validated, kept as is."""
    if isinstance(data, list):
        _overlay_list.validate_python(data)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for o in data:
            grouped[o["segment_id"]].append(o)
        return dict(grouped)
    _overlays.validate_python(data)
    return dict(data)


def _dump(item: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return item.model_dump(mode="json") if isinstance(item, BaseModel) else item


def _write(path: Path, data: Any) -> int:
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def export_match(
    match: GrfMatch,
    out_dir: str | Path,
    *,
    events: list[MatchEvent] | None = None,
    insights: Sequence[Insight | dict[str, Any]] | None = None,
    overlays: Mapping[str, Sequence[Overlay | dict[str, Any]]] | None = None,
    video: str | Path | None = None,
) -> dict[str, int]:
    """Write all export files to `out_dir`; returns {file name: size in bytes}."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    events = derive_events(match) if events is None else events
    moments: list[Moment] = detect_moments(events, match.clock_s)

    sizes: dict[str, int] = {}
    if video is not None:
        shutil.copyfile(video, out / VIDEO_FILE)
        sizes[VIDEO_FILE] = (out / VIDEO_FILE).stat().st_size
    sizes["match.json"] = _write(out / "match.json", match_meta(match, video=video is not None))
    sizes["frames.json"] = _write(out / "frames.json", frames_payload(match))
    sizes["events.json"] = _write(out / "events.json", [e.model_dump(mode="json") for e in events])
    sizes["moments.json"] = _write(out / "moments.json", [m.model_dump(mode="json") for m in moments])
    sizes["insights.json"] = _write(out / "insights.json", [_dump(i) for i in insights or []])
    sizes["stats.json"] = _write(out / "stats.json", stats_snapshots(match, events))
    sizes["overlays.json"] = _write(
        out / "overlays.json",
        {seg: [_dump(o) for o in items] for seg, items in (overlays or {}).items()},
    )
    return sizes


def export_from_dir(
    match_dir: str | Path,
    out_root: str | Path,
    *,
    match_id: str | None = None,
    insights_path: str | Path | None = None,
    overlays_path: str | Path | None = None,
    video_path: str | Path | None = None,
) -> tuple[Path, dict[str, int]]:
    """Export a recording folder (raw.jsonl [+ video.mp4]) to `out_root/<match_id>/`."""
    match_dir = Path(match_dir)
    match = load_grf_match(match_dir, match_id=match_id)
    insights = load_insights(json.loads(Path(insights_path).read_text())) if insights_path else None
    overlays = load_overlays(json.loads(Path(overlays_path).read_text())) if overlays_path else None
    if video_path is None and (match_dir / VIDEO_FILE).exists():
        video_path = match_dir / VIDEO_FILE
    out = Path(out_root) / match.match_id
    return out, export_match(match, out, insights=insights, overlays=overlays, video=video_path)
