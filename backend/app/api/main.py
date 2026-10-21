"""REST + WebSocket API over the exported matches (data/export/<match_id>/).

  GET /api/health                           {"status": "ok", "matches": <number of exported matches>}
  GET /api/matches                          summaries of every exported match
  GET /api/matches/{id}/{file}              match.json, frames.json, ..., video.mp4 (range requests)
  WS  /api/matches/{id}/live?speed=10&step=2&start_frame=0&segment=analyst-en
  GET /export/{id}/{file}                   the export folder as static files (frontend's static mode)
  GET /                                     the built web player (frontend/dist), if present

Production contract: this API only SERVES pre-computed exports. It never calls an LLM, the
rollout engine or the stats engine at request time, and it needs no Azure OpenAI credentials.
Insights and overlays are produced offline (spikes/explain_demo.py, spikes/produce_demo.py, LLM
answers cached in data/cache/llm/), written into data/export/<match_id>/ by spikes/export_demo.py,
and that folder is baked into the container image (backend/Dockerfile, infra/README.md).
tests/test_api_production.py guards that importing this module loads no agent/LLM code.

Run from backend/:  .venv/bin/uvicorn app.api.main:app --reload
EXPORT_DIR overrides the export root (default: <repo>/data/export), FRONTEND_DIR the built
frontend (default: <repo>/frontend/dist). APPLICATIONINSIGHTS_CONNECTION_STRING turns on
Azure Monitor tracing when azure-monitor-opentelemetry is installed (the Docker image has it).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.live import ExportedMatch, live_messages
from app.export.exporter import FILES, VIDEO_FILE

REPO = Path(__file__).resolve().parents[3]
DEFAULT_EXPORT_DIR = REPO / "data" / "export"
DEFAULT_FRONTEND_DIR = REPO / "frontend" / "dist"
MATCH_ID = re.compile(r"^[A-Za-z0-9_-]+$")
SERVED = {*FILES, VIDEO_FILE}


def _configure_monitoring() -> None:
    if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ImportError:
        return
    configure_azure_monitor()


def create_app(export_dir: str | Path | None = None, frontend_dir: str | Path | None = None) -> FastAPI:
    root = Path(export_dir or os.environ.get("EXPORT_DIR") or DEFAULT_EXPORT_DIR)
    dist = Path(frontend_dir or os.environ.get("FRONTEND_DIR") or DEFAULT_FRONTEND_DIR)
    cache: dict[str, tuple[float, ExportedMatch]] = {}
    app = FastAPI(title="Sliding Doors API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def folder(match_id: str) -> Path:
        path = root / match_id
        if not MATCH_ID.match(match_id) or not (path / "match.json").is_file():
            raise HTTPException(404, f"unknown match {match_id!r}")
        return path

    def exported(match_id: str) -> ExportedMatch:
        path = folder(match_id)
        mtime = max((path / f).stat().st_mtime for f in FILES if (path / f).exists())
        hit = cache.get(match_id)
        if hit is None or hit[0] != mtime:
            hit = cache[match_id] = (mtime, ExportedMatch.load(path))
        return hit[1]

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        # liveness/readiness probe of the container; "matches" shows the exports were baked in
        return {"status": "ok", "matches": len(list(root.glob("*/match.json")))}

    @app.get("/api/matches")
    def matches() -> list[dict[str, Any]]:
        out = []
        for path in sorted(root.glob("*/match.json")):
            meta = json.loads(path.read_text(encoding="utf-8"))
            out.append({k: meta.get(k) for k in ("match_id", "home", "away", "final_score", "n_frames",
                                                  "duration_ms", "clock_scale", "video")})
        return out

    @app.get("/api/matches/{match_id}/{file}")
    def match_file(match_id: str, file: str) -> FileResponse:
        if file not in SERVED:
            raise HTTPException(404, f"unknown file {file!r}; one of {sorted(SERVED)}")
        path = folder(match_id) / file
        if not path.is_file():
            raise HTTPException(404, f"{file} not exported for {match_id}")
        return FileResponse(path)

    @app.websocket("/api/matches/{match_id}/live")
    async def live(
        websocket: WebSocket,
        match_id: str,
        speed: float = Query(10.0, gt=0, le=1000),
        step: int = Query(1, ge=1, le=50),
        start_frame: int = Query(0, ge=0),
        segment: str | None = None,
    ) -> None:
        try:
            match = exported(match_id)
        except HTTPException:
            await websocket.close(code=4404, reason="unknown match")
            return
        await websocket.accept()
        try:
            async for message in live_messages(match, speed=speed, step=step, start_frame=start_frame,
                                               segment=segment):
                await websocket.send_json(message)
            await websocket.close()
        except WebSocketDisconnect:
            pass

    # static mounts last, so they never shadow /api
    if root.is_dir():
        app.mount("/export", StaticFiles(directory=root), name="export")
    if (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


_configure_monitoring()
app = create_app()
