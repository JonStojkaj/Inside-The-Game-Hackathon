"""Azure AI Speech (neural TTS, REST) for commentary lines: SSML, rate limit, disk cache.

Voices: Dragon HD per mode and language (engine.VOICES). Prosody per mode comes from the engine
(club fan faster/brighter, analyst calmer). Free tier F0 allows 20 requests/minute: the limiter keeps the
process under TTS_PER_MINUTE (default 18) and the caller turns a refusal into 429 + Retry-After.
Files are content-addressed (engine.audio_key) and written atomically, so concurrent requests never see
half-written audio and the same line is synthesized once per process (per-key lock).
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from app.commentary.engine import LOCALES, voice_for

MP3_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
MP3_KBPS = 48


class SpeechError(Exception):
    def __init__(self, status: int, error: str, message: str, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.status, self.error, self.message, self.retry_after_s = status, error, message, retry_after_s


def ssml(text: str, lang: str, rate: int, pitch: int, voice: str = "") -> str:
    locale, voice = LOCALES[lang], voice or voice_for(lang, "casual")
    return (f"<speak version='1.0' xml:lang='{locale}'><voice name='{voice}'>"
            f"<prosody rate='{rate:+d}%' pitch='{pitch:+d}%'>{escape(text)}</prosody></voice></speak>")


def mp3_duration_ms(path: Path) -> int:
    return int(path.stat().st_size * 8 / (MP3_KBPS * 1000) * 1000)


@dataclass
class RateLimit:
    per_minute: int
    clock: Callable[[], float] = time.monotonic
    starts: deque[float] = field(default_factory=deque)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def acquire(self) -> None:
        with self.lock:
            now = self.clock()
            while self.starts and now - self.starts[0] >= 60:
                self.starts.popleft()
            if len(self.starts) >= self.per_minute:
                raise SpeechError(429, "rate_limited", "Commentary voice is busy, captions only for a moment.",
                                  retry_after_s=int(60 - (now - self.starts[0])) + 1)
            self.starts.append(now)


@dataclass
class SpeechSettings:
    key: str = ""
    region: str = "swedencentral"
    per_minute: int = 18
    timeout_s: float = 10.0

    @property
    def configured(self) -> bool:
        return bool(self.key)

    @classmethod
    def from_env(cls) -> SpeechSettings:
        return cls(key=os.environ.get("AZURE_SPEECH_KEY", "").strip(),
                   region=os.environ.get("AZURE_SPEECH_REGION", "").strip() or "swedencentral",
                   per_minute=int(os.environ.get("COMMENTARY_TTS_PER_MINUTE", "18")),
                   timeout_s=float(os.environ.get("COMMENTARY_TTS_TIMEOUT_S", "10")))


Synthesize = Callable[[str], bytes]  # SSML -> mp3 bytes (raises SpeechError)


def azure_synthesizer(settings: SpeechSettings) -> Synthesize:
    import httpx  # lazy: only when a line is actually synthesized

    url = f"https://{settings.region}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {"Ocp-Apim-Subscription-Key": settings.key, "Content-Type": "application/ssml+xml",
               "X-Microsoft-OutputFormat": MP3_FORMAT, "User-Agent": "sliding-doors-commentary"}

    def synthesize(body: str) -> bytes:
        try:
            resp = httpx.post(url, headers=headers, content=body.encode(), timeout=settings.timeout_s)
        except httpx.HTTPError as e:
            raise SpeechError(502, "speech_failed", f"Speech service unreachable ({type(e).__name__}).") from e
        if resp.status_code == 429:
            raise SpeechError(429, "rate_limited", "Speech service rate limit.", retry_after_s=int(resp.headers.get("retry-after", "5") or 5))
        if resp.status_code != 200 or not resp.content:
            raise SpeechError(502, "speech_failed", f"Speech service answered {resp.status_code}.")
        return resp.content

    return synthesize


class AudioCache:
    """mp3 per audio key in `root`; synthesizes missing ones (one at a time per key, rate-limited)."""

    def __init__(self, root: Path, settings: SpeechSettings, synthesize: Synthesize | None = None) -> None:
        self.root = root
        self.settings = settings
        self.limit = RateLimit(settings.per_minute)
        self._synthesize = synthesize
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    @property
    def configured(self) -> bool:
        return self.settings.configured or self._synthesize is not None

    def path(self, match_id: str, key: str) -> Path:
        return self.root / match_id / f"{key}.mp3"

    def get(self, match_id: str, key: str, text: str, lang: str, rate: int, pitch: int, voice: str = "") -> Path:
        path = self.path(match_id, key)
        if path.is_file():
            return path
        if not self.configured:
            raise SpeechError(503, "speech_unavailable", "No commentary voice configured; captions only.")
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            if path.is_file():  # a concurrent request made it meanwhile
                return path
            self.limit.acquire()
            if self._synthesize is None:
                self._synthesize = azure_synthesizer(self.settings)
            audio = self._synthesize(ssml(text, lang, rate, pitch, voice))
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
            tmp.write_bytes(audio)
            os.replace(tmp, path)
        with self._guard:
            self._locks.pop(key, None)
        return path
