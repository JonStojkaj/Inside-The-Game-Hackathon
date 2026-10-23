"""AI commentator: speak the key overlays of every segment with Azure AI Speech (neural TTS).

Reads <export>/overlays.json, writes <export>/audio/*.mp3 and <export>/audio.json:
  [{"id", "segment_id", "start_ms", "duration_ms", "file", "lang", "text"}]
The spoken text is exactly the overlay text the production team already validated (no new numbers).
Voice per language, delivery per profile (club fan faster and brighter, analyst calmer).

  backend/.venv/bin/python spikes/voice_demo.py data/export/demo-109
Needs AZURE_SPEECH_KEY + AZURE_SPEECH_REGION in .env (free tier F0: 20 requests/min, 0.5 M chars/month).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from html import escape
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

SPOKEN_TYPES = {"sliding_doors", "insight", "recap"}
VOICES = {"en": ("en-GB", "en-GB-RyanNeural"), "de": ("de-DE", "de-DE-ConradNeural"), "es": ("es-ES", "es-ES-AlvaroNeural")}
DELIVERY = {  # (rate, pitch) per profile mode
    "analyst": ("-4%", "-2%"),
    "club_fan": ("+10%", "+6%"),
    "player_focus": ("+3%", "+2%"),
    "casual": ("+5%", "+3%"),
}
MP3_KBPS = 48
REQUEST_GAP_S = 3.2  # stay under 20 requests/minute on F0


def is_goal_card(o: dict) -> bool:
    return o["type"] == "event_card" and str(o.get("payload", {}).get("event_type", o.get("headline", ""))).lower().startswith("goal")


def spoken_text(o: dict) -> str:
    text = " ".join(t for t in (o.get("headline", ""), o.get("body", "")) if t)
    text = re.sub(r"Sliding Doors\s*·\s*\d+'", "", text)  # graphic label, not commentary
    return re.sub(r"\s+", " ", text).strip(" ·|")


def ssml(text: str, lang: str, mode: str) -> str:
    locale, voice = VOICES.get(lang, VOICES["en"])
    rate, pitch = DELIVERY.get(mode, ("+0%", "+0%"))
    return (f"<speak version='1.0' xml:lang='{locale}'><voice name='{voice}'>"
            f"<prosody rate='{rate}' pitch='{pitch}'>{escape(text)}</prosody></voice></speak>")


def main() -> None:
    export = Path(sys.argv[1])
    key, region = os.environ["AZURE_SPEECH_KEY"], os.environ.get("AZURE_SPEECH_REGION", "swedencentral")
    overlays: dict[str, list[dict]] = json.loads((export / "overlays.json").read_text())
    out_dir = export / "audio"
    out_dir.mkdir(exist_ok=True)
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
               "X-Microsoft-OutputFormat": f"audio-24khz-{MP3_KBPS}kbitrate-mono-mp3", "User-Agent": "sliding-doors"}
    clips, chars, calls = [], 0, 0
    with httpx.Client(timeout=30) as client:
        for segment_id, items in overlays.items():
            mode = segment_id.split("-")[0]
            for o in items:
                if o["type"] not in SPOKEN_TYPES and not is_goal_card(o):
                    continue
                text = spoken_text(o)
                if not text:
                    continue
                lang = o.get("lang", "en")
                name = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{segment_id}__{o['id'].split(':')[-1]}")[:120] + ".mp3"
                path = out_dir / name
                if not path.exists():
                    resp = client.post(url, headers=headers, content=ssml(text, lang, mode).encode())
                    resp.raise_for_status()
                    path.write_bytes(resp.content)
                    chars += len(text)
                    calls += 1
                    time.sleep(REQUEST_GAP_S)
                duration_ms = int(path.stat().st_size * 8 / (MP3_KBPS * 1000) * 1000)
                clips.append({"id": f"{segment_id}:{o['id']}", "segment_id": segment_id, "start_ms": o["start_ms"],
                              "duration_ms": duration_ms, "file": f"audio/{name}", "lang": lang, "text": text})
    clips.sort(key=lambda c: (c["segment_id"], c["start_ms"]))
    (export / "audio.json").write_text(json.dumps(clips, ensure_ascii=False, indent=1))
    print(f"{len(clips)} clips ({calls} new TTS calls, {chars} chars) -> {export / 'audio.json'}")


if __name__ == "__main__":
    main()
