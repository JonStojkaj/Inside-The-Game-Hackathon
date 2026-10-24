"""Live AI commentator over HTTP (app.commentary): a per-mode timeline + lazily synthesized audio.

  GET /api/matches/{id}/commentary?mode=casual&lang=en[&club=home][&player=H8]
      {"match_id", "segment", "mode", "lang", "club", "player", "speech": bool,
       "lines": [{"id", "start_ms", "duration_ms", "text", "kind", "priority", "audio_url"}]}
      start_ms is match time (= video time, 10 fps frames * 100 ms); lines never overlap
      (start_ms[i+1] >= start_ms[i] + duration_ms[i] + 500). audio_url is null when no audio exists for the
      line and Speech is not configured: show the text as a caption.
      422 {"error": "bad_request", "message"} for a bad mode/lang/club/player.
  GET /api/matches/{id}/commentary/audio/{key}.mp3[?mode&lang&club&player]
      audio/mpeg. Served from <export>/<id>/commentary/ (prewarmed, baked into the image), then from the runtime
      cache (COMMENTARY_CACHE_DIR), else synthesized with Azure AI Speech on first request. Only keys produced
      by the engine are accepted (no arbitrary text). 404 unknown key, 503 speech_unavailable,
      429 rate_limited (Retry-After), 502 speech_failed.

No LLM, no simulator: timelines are pure functions of the export (cached in memory per segment).
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, JSONResponse

from app.commentary.data import League, MatchData, find_league, load_match
from app.commentary.engine import Line, Segment, build_timeline, line_key
from app.commentary.speech import AudioCache, SpeechError, SpeechSettings

KEY = re.compile(r"^[0-9a-f]{24}$")
PREWARM_DIR = "commentary"


def default_cache_dir() -> Path:
    return Path(os.environ.get("COMMENTARY_CACHE_DIR") or Path(tempfile.gettempdir()) / "sliding-doors-commentary")


class CommentaryService:
    def __init__(self, export_root: Path, league_paths: list[Path], audio: AudioCache | None = None) -> None:
        self.root = export_root
        self.league_paths = league_paths
        self.audio = audio or AudioCache(default_cache_dir(), SpeechSettings.from_env())
        self._league: League | None | bool = False  # False = not looked up yet
        self._matches: dict[str, tuple[float, MatchData]] = {}
        self._timelines: dict[tuple[str, str, float], list[Line]] = {}
        self._keys: dict[str, dict[str, tuple[Line, str]]] = {}  # match -> key -> (line, lang)
        self._lock = threading.Lock()

    def league(self, match_id: str) -> League | None:
        if self._league is False:
            self._league = find_league([self.root / match_id / "league.json", *self.league_paths])
        return self._league if isinstance(self._league, League) else None

    def match(self, match_id: str) -> tuple[float, MatchData]:
        folder = self.root / match_id
        mtime = max((folder / f).stat().st_mtime for f in ("match.json", "events.json") if (folder / f).exists())
        hit = self._matches.get(match_id)
        if hit is None or hit[0] != mtime:
            hit = self._matches[match_id] = (mtime, load_match(folder, self.league(match_id)))
        return hit

    def timeline(self, match_id: str, mode: str, lang: str, club: str | None, player: str | None) -> tuple[Segment, list[Line]]:
        with self._lock:
            mtime, md = self.match(match_id)
            seg = Segment.make(md, mode, lang, club, player)  # ValueError on bad input
            cache_key = (match_id, seg.id, mtime)
            lines = self._timelines.get(cache_key)
            if lines is None:
                lines = self._timelines[cache_key] = build_timeline(md, seg)
                keys = self._keys.setdefault(match_id, {})
                for ln in lines:
                    keys[line_key(ln, lang)] = (ln, lang)
            return seg, lines

    def prewarmed(self, match_id: str, key: str) -> Path:
        return self.root / match_id / PREWARM_DIR / f"{key}.mp3"

    def payload(self, match_id: str, mode: str, lang: str, club: str | None, player: str | None) -> dict[str, Any]:
        seg, lines = self.timeline(match_id, mode, lang, club, player)
        query = urlencode({k: v for k, v in (("mode", seg.mode), ("lang", seg.lang), ("club", seg.club), ("player", seg.player)) if v})
        out = []
        for ln in lines:
            key = line_key(ln, lang)
            has_audio = self.audio.configured or self.prewarmed(match_id, key).is_file() or self.audio.path(match_id, key).is_file()
            out.append({"id": ln.id, "start_ms": ln.start_ms, "duration_ms": ln.duration_ms, "text": ln.text, "kind": ln.kind,
                        "priority": ln.priority,
                        "audio_url": f"/api/matches/{match_id}/commentary/audio/{key}.mp3?{query}" if has_audio else None})
        return {"match_id": match_id, "segment": seg.id, "mode": seg.mode, "lang": seg.lang, "club": seg.club,
                "player": seg.player, "speech": self.audio.configured, "lines": out}

    def audio_file(self, match_id: str, key: str, params: dict[str, str | None]) -> Path:
        if not KEY.match(key):
            raise SpeechError(404, "unknown_line", "Unknown commentary line.")
        for path in (self.prewarmed(match_id, key), self.audio.path(match_id, key)):
            if path.is_file():
                return path
        known = self._keys.get(match_id, {}).get(key)
        if known is None and params.get("mode"):
            try:  # after a restart: rebuild the segment the URL came from
                self.timeline(match_id, params["mode"] or "", params.get("lang") or "en", params.get("club"), params.get("player"))
            except ValueError:
                pass
            known = self._keys.get(match_id, {}).get(key)
        if known is None:
            raise SpeechError(404, "unknown_line", "Unknown commentary line.")
        line, lang = known
        return self.audio.get(match_id, key, line.text, lang, line.rate, line.pitch)


def _error(e: SpeechError) -> JSONResponse:
    headers = {"Retry-After": str(e.retry_after_s)} if e.retry_after_s else None
    body: dict[str, Any] = {"error": e.error, "message": e.message}
    if e.retry_after_s:
        body["retry_after_s"] = e.retry_after_s
    return JSONResponse(body, status_code=e.status, headers=headers)


def commentary_router(service: CommentaryService, known_match: Callable[[str], Any]) -> APIRouter:
    router = APIRouter()

    @router.get("/api/matches/{match_id}/commentary")
    async def commentary(match_id: str, mode: str = Query("casual"), lang: str = Query("en"), club: str | None = None,
                         player: str | None = None) -> Any:
        known_match(match_id)
        try:
            return await asyncio.to_thread(service.payload, match_id, mode, lang, club, player)
        except ValueError as e:
            return JSONResponse({"error": "bad_request", "message": str(e)}, status_code=422)

    @router.get("/api/matches/{match_id}/commentary/audio/{file}")
    async def commentary_audio(match_id: str, file: str, mode: str | None = None, lang: str | None = None,
                               club: str | None = None, player: str | None = None) -> Any:
        known_match(match_id)
        key = file.removesuffix(".mp3") if file.endswith(".mp3") else ""
        try:
            path = await asyncio.to_thread(service.audio_file, match_id, key,
                                           {"mode": mode, "lang": lang, "club": club, "player": player})
        except SpeechError as e:
            return _error(e)
        return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400, immutable"})

    return router
