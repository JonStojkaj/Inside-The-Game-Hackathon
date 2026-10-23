"""Ask Sliding Doors over HTTP: the only API path that runs agents and the simulator at request time.

  GET  /api/matches/{id}/ask?frame=N            {enabled, moment, suggestions}  (no LLM, no rollouts)
  POST /api/matches/{id}/ask[?stream=false]     body {frame, question, lang?, moment_id?}
       stream (default): application/x-ndjson, one JSON object per line:
         {"type": "step", "code": "analyst", "text": "...", "t_ms": 812, ...}   progress, as the agents work
         {"type": "result", ...}                                                   the verified answer
         {"type": "error", "error": "timeout" | "failed", "message": "..."}
       stream=false: the result object as JSON.
  Errors before any work starts are plain JSON with a status code and {"error": code, "message": ...}:
    503 disabled | unavailable (no raw.jsonl baked in)   404 unknown match   422 bad_request | no_moment
    429 busy (one question at a time) | rate_limited (ASK_MAX_PER_MINUTE), with "retry_after_s"

Feature flag ASK_ENABLED (default: on only when AZURE_OPENAI_ENDPOINT is set). Agent code is imported on the first
enabled request, never at startup, so the serving path stays as light as before (tests/test_api_production.py).
The simulator reads <export>/<id>/raw.jsonl (copied there by the exporter). Identical questions on the same moment
are answered from an in-memory cache (and the LLM cache), without counting against the rate limit.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from collections import OrderedDict, deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger("sliding_doors.ask")
LANGS = ("en", "de", "es")


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None or raw == "" else raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class AskSettings:
    enabled: bool = False
    max_per_minute: int = 6
    timeout_s: float = 90.0
    cache_size: int = 64

    @classmethod
    def from_env(cls) -> AskSettings:
        return cls(
            enabled=_flag("ASK_ENABLED", bool(os.environ.get("AZURE_OPENAI_ENDPOINT"))),
            max_per_minute=int(os.environ.get("ASK_MAX_PER_MINUTE", "6")),
            timeout_s=float(os.environ.get("ASK_TIMEOUT_S", "90")),
        )


class AskRequest(BaseModel):
    frame: int = Field(ge=0)
    question: str = Field(min_length=3, max_length=200)
    lang: str = "en"
    moment_id: str | None = Field(default=None, max_length=80)


class AskError(Exception):
    def __init__(self, status: int, error: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status, self.error, self.message, self.extra = status, error, message, extra

    def response(self) -> JSONResponse:
        return JSONResponse({"error": self.error, "message": self.message, **self.extra}, status_code=self.status)


@dataclass
class Limiter:
    """One run at a time and at most `per_minute` runs per sliding minute (process-wide: one replica)."""

    per_minute: int
    clock: Callable[[], float] = time.monotonic
    busy: bool = False
    starts: deque[float] = field(default_factory=deque)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def acquire(self) -> None:
        with self.lock:
            now = self.clock()
            while self.starts and now - self.starts[0] >= 60:
                self.starts.popleft()
            if self.busy:
                raise AskError(429, "busy", "The agents are answering another question. Try again in a few seconds.", retry_after_s=10)
            if len(self.starts) >= self.per_minute:
                wait = int(60 - (now - self.starts[0])) + 1
                raise AskError(429, "rate_limited", "Too many questions right now. Try again shortly.", retry_after_s=wait)
            self.busy = True
            self.starts.append(now)

    def release(self) -> None:
        with self.lock:
            self.busy = False


class AskService:
    """Lazy: agents, the rollout engine and the match are loaded on first use."""

    def __init__(self, settings: AskSettings, raw_dir: Callable[[str], Path], *, llm: Any = None, runner: Any = None,
                 loader: Callable[[Path], Any] | None = None) -> None:
        self.settings = settings
        self.raw_dir = raw_dir
        self.limiter = Limiter(settings.max_per_minute)
        self._llm, self._runner, self._loader = llm, runner, loader
        self._sims: dict[str, Any] = {}
        self._answers: OrderedDict[tuple[str, str, str, str], dict[str, Any]] = OrderedDict()
        self._load_lock = threading.Lock()

    # --- lazy parts --------------------------------------------------------------------------------------
    def llm(self) -> Any:
        if self._llm is None:
            from app.agents.ask import ask_llm_from_env

            self._llm = ask_llm_from_env()
        return self._llm

    def sim(self, match_id: str) -> Any:
        with self._load_lock:
            if match_id not in self._sims:
                folder = self.raw_dir(match_id)
                if not (folder / "raw.jsonl").is_file():
                    raise AskError(503, "unavailable", "Live questions are not available for this match (no simulation data).")
                if self._loader is None:
                    from app.agents.ask import load_sim_match

                    self._loader = load_sim_match
                self._sims[match_id] = self._loader(folder)
            return self._sims[match_id]

    def check_enabled(self) -> None:
        if not self.settings.enabled:
            raise AskError(503, "disabled", "Live questions are switched off for this deployment.")

    def moment(self, match_id: str, frame: int, moment_id: str | None) -> tuple[Any, Any]:
        from app.agents.ask import pick_moment

        sim = self.sim(match_id)
        if frame >= sim.match.n_frames:
            raise AskError(422, "bad_request", f"frame must be below {sim.match.n_frames}")
        moment = pick_moment(sim.match, sim.events, sim.moments, frame, moment_id)
        if moment is None:
            raise AskError(422, "no_moment", "No decision to analyse near this moment. Pause just before a pass or a shot.")
        return sim, moment

    # --- endpoints -------------------------------------------------------------------------------------------
    def menu(self, match_id: str, frame: int) -> dict[str, Any]:
        from app.agents.ask import moment_info, suggestions
        from app.agents.experiments import decision_context

        self.check_enabled()
        sim, moment = self.moment(match_id, frame, None)
        ctx = decision_context(sim.match, moment, sim.events)
        return {"enabled": True, "moment": moment_info(ctx), "suggestions": suggestions(ctx)}

    def cache_key(self, match_id: str, moment_id: str, req: AskRequest) -> tuple[str, str, str, str]:
        return match_id, moment_id, " ".join(req.question.lower().split()).rstrip("?!. "), req.lang

    def prepare(self, match_id: str, req: AskRequest) -> tuple[Any, Any, dict[str, Any] | None]:
        """Everything that can fail fast (before streaming starts). Returns (sim, moment, cached result or None)."""
        self.check_enabled()
        if req.lang not in LANGS:
            raise AskError(422, "bad_request", f"lang must be one of {', '.join(LANGS)}")
        sim, moment = self.moment(match_id, req.frame, req.moment_id)
        cached = self._answers.get(self.cache_key(match_id, moment.id, req))
        if cached is None:
            self.limiter.acquire()
        return sim, moment, cached

    def run(self, match_id: str, sim: Any, moment: Any, req: AskRequest, on_step: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        """Blocking; runs in a worker thread. Releases the limiter when the agents are really done (even after a
        timeout was already reported), so there is never more than one run."""
        from app.agents.ask import answer

        try:
            result = answer(sim, moment, req.question.strip(), req.lang, self.llm(), self._runner, on_step)
            result["cached"] = False
            self._answers[self.cache_key(match_id, moment.id, req)] = result
            while len(self._answers) > self.settings.cache_size:
                self._answers.popitem(last=False)
            return result
        finally:
            self.limiter.release()


def _line(obj: dict[str, Any]) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode()


def ask_router(service: AskService, known_match: Callable[[str], Any]) -> APIRouter:
    router = APIRouter()

    @router.get("/api/matches/{match_id}/ask")
    async def ask_menu(match_id: str, frame: int = Query(0, ge=0)) -> Any:
        known_match(match_id)
        if not service.settings.enabled:
            return {"enabled": False}
        try:
            return await asyncio.to_thread(service.menu, match_id, frame)
        except AskError as e:
            return e.response()

    @router.post("/api/matches/{match_id}/ask")
    async def ask(match_id: str, body: dict[str, Any], stream: bool = True) -> Any:
        known_match(match_id)
        try:
            req = AskRequest.model_validate(body)
        except ValidationError as e:
            return AskError(422, "bad_request", "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())).response()
        try:
            sim, moment, cached = await asyncio.to_thread(service.prepare, match_id, req)
        except AskError as e:
            return e.response()

        if cached is not None:
            result = {**cached, "cached": True}
            if not stream:
                return result
            return StreamingResponse(iter([_line({"type": "step", "code": "cached", "text": "Answered before: from the cache.", "t_ms": 0}),
                                           _line({"type": "result", **result})]), media_type="application/x-ndjson")

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        def on_step(step: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "step", **step})

        task = asyncio.ensure_future(asyncio.to_thread(service.run, match_id, sim, moment, req, on_step))

        if not stream:
            try:
                return await asyncio.wait_for(asyncio.shield(task), service.settings.timeout_s)
            except TimeoutError:
                return AskError(504, "timeout", "The agents took too long. Please try again.").response()
            except Exception as e:  # noqa: BLE001
                log.exception("ask failed")
                return AskError(500, "failed", f"The agents could not answer ({type(e).__name__}).").response()

        async def events() -> AsyncIterator[bytes]:
            deadline = loop.time() + service.settings.timeout_s
            yield _line({"type": "step", "code": "moment", "text": "Looking at the moment…", "t_ms": 0,
                         "moment_id": moment.id, "frame": moment.frame})
            while True:
                getter = asyncio.ensure_future(queue.get())
                done, _ = await asyncio.wait({getter, task}, timeout=max(deadline - loop.time(), 0), return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    yield _line(getter.result())
                    continue
                getter.cancel()
                if task in done:
                    while not queue.empty():
                        yield _line(queue.get_nowait())
                    try:
                        yield _line({"type": "result", **task.result()})
                    except Exception as e:  # noqa: BLE001
                        log.exception("ask failed")
                        yield _line({"type": "error", "error": "failed", "message": f"The agents could not answer ({type(e).__name__})."})
                    return
                yield _line({"type": "error", "error": "timeout", "message": "The agents took too long. Please try again."})
                return

        return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return router
