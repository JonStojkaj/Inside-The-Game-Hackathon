"""Export a recorded match to the web player format (data/export/<match_id>/).

The match id is the recording folder's name unless --match-id is given, so the same command
works for any recording, e.g. the deterministic demo match spikes/grf/out/matches/demo-<variant>.

Run from repo root:
  backend/.venv/bin/python spikes/export_demo.py spikes/grf/out/matches/demo-<n> data/export \\
      --insights data/insights/demo-<n>.json --overlays data/overlays/demo-<n>.json \\
      --video spikes/grf/out/matches/demo-<n>/video.mp4

  --insights  list[Insight] JSON from the explain team (spikes/explain_demo.py)
  --overlays  {segment_id: [Overlay]} or a flat [Overlay] list from the production team
  --video     TV-view video; copied to <out>/video.mp4 and announced in match.json as
              {"file": "video.mp4", "fps": 10}. Default: <match_dir>/video.mp4 if it exists.

data/export/<match_id>/ is exactly what the Docker image bakes in and the deployed API serves
(no LLM calls in production), see infra/README.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.export.exporter import export_from_dir  # noqa: E402


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a recorded match for the web player and the API.")
    parser.add_argument("match_dir", help="recording folder with raw.jsonl (and optionally video.mp4)")
    parser.add_argument("out_root", help="export root; files go to <out_root>/<match_id>/")
    parser.add_argument("--match-id", help="override the match id (default: the recording folder's name)")
    parser.add_argument("--insights", help="list[Insight] JSON from the explain team")
    parser.add_argument("--overlays", help="{segment_id: [Overlay]} or [Overlay] JSON from the production team")
    parser.add_argument("--video", help="video.mp4 (default: <match_dir>/video.mp4 if present)")
    args = parser.parse_args(argv)
    if not (Path(args.match_dir) / "raw.jsonl").is_file():
        parser.error(f"no raw.jsonl in {args.match_dir}")
    for flag in ("insights", "overlays", "video"):
        value = getattr(args, flag)
        if value is not None and not Path(value).is_file():
            parser.error(f"--{flag}: file not found: {value}")
    return args


def main(argv: Sequence[str] | None = None) -> Path:
    args = parse_args(argv)
    t0 = time.perf_counter()
    out, sizes = export_from_dir(
        args.match_dir, args.out_root, match_id=args.match_id,
        insights_path=args.insights, overlays_path=args.overlays, video_path=args.video,
    )
    insights = json.loads((out / "insights.json").read_text(encoding="utf-8"))
    overlays = json.loads((out / "overlays.json").read_text(encoding="utf-8"))
    video = json.loads((out / "match.json").read_text(encoding="utf-8"))["video"]
    print(f"exported {out.name} to {out} in {time.perf_counter() - t0:.1f} s")
    print(f"  insights: {len(insights)}, overlay segments: {sorted(overlays) or '-'}, video: {video or '-'}")
    for name, size in sizes.items():
        print(f"  {name:14s} {size / 1024:9.1f} KB")
    print(f"  {'total':14s} {sum(sizes.values()) / 1024:9.1f} KB")
    return out


if __name__ == "__main__":
    main()
