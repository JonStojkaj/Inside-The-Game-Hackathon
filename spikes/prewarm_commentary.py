"""Prewarm the live commentator's audio for one exported match (baked into the image, so the demo never waits on Speech).

    AZURE_SPEECH_KEY=... backend/.venv/bin/python spikes/prewarm_commentary.py data/export/demo-109 [--players H8 A20] [--langs en de]

Synthesizes every line of casual / analyst / club_fan (home + away) / player_focus (default player + --players) into
<export>/commentary/<key>.mp3, skipping keys that already exist. Waits out the F0 rate limit instead of failing.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.api.commentary import PREWARM_DIR
from app.commentary.data import League, find_league, load_match
from app.commentary.engine import (
    LANGS,
    Segment,
    build_timeline,
    default_player,
    line_key,
)
from app.commentary.speech import AudioCache, SpeechError, SpeechSettings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("export", type=Path)
    ap.add_argument("--players", nargs="*", default=[])
    ap.add_argument("--langs", nargs="*", default=list(LANGS))
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    league: League | None = find_league([args.export / "league.json", root / "frontend/public/league.json"])
    md = load_match(args.export, league)
    settings = SpeechSettings.from_env()
    if not settings.configured:
        sys.exit("AZURE_SPEECH_KEY is not set")
    # AudioCache writes <root>/<match_id>/<key>.mp3; point it so that lands in <export>/commentary/
    out = args.export / PREWARM_DIR
    cache = AudioCache(out.parent.parent / "_prewarm", settings)
    cache.path = lambda _m, key: out / f"{key}.mp3"  # type: ignore[method-assign]

    players = [default_player(md), *args.players]
    todo: dict[str, tuple[str, str, int, int]] = {}
    for lang in args.langs:
        segs = [Segment.make(md, "casual", lang), Segment.make(md, "analyst", lang),
                *(Segment.make(md, "club_fan", lang, club=c) for c in ("home", "away")),
                *(Segment.make(md, "player_focus", lang, player=p) for p in dict.fromkeys(players))]
        for seg in segs:
            for ln in build_timeline(md, seg):
                todo.setdefault(line_key(ln, lang), (ln.text, lang, ln.rate, ln.pitch))
    missing = {k: v for k, v in todo.items() if not (out / f"{k}.mp3").is_file()}
    print(f"{len(todo)} lines, {len(missing)} to synthesize -> {out}", flush=True)
    for i, (key, (text, lang, rate, pitch)) in enumerate(missing.items(), 1):
        while True:
            try:
                cache.get(md.match_id, key, text, lang, rate, pitch)
                break
            except SpeechError as e:
                if e.status != 429:
                    raise
                time.sleep(e.retry_after_s or 5)
        if i % 25 == 0 or i == len(missing):
            print(f"  {i}/{len(missing)}", flush=True)


if __name__ == "__main__":
    main()
