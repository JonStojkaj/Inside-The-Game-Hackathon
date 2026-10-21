"""Export a recorded match to the web player format (data/export/<match_id>/).

Run from repo root:
  backend/.venv/bin/python spikes/export_demo.py spikes/grf/out/matches/full-34 data/export
  backend/.venv/bin/python spikes/export_demo.py <match_dir> <out_root> --insights insights.json --overlays overlays.json
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.export.exporter import export_from_dir  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("match_dir", help="recording folder with raw.jsonl (and optionally video.mp4)")
    parser.add_argument("out_root", help="export root; files go to <out_root>/<match_id>/")
    parser.add_argument("--match-id")
    parser.add_argument("--insights", help="list[Insight] JSON from the explain team")
    parser.add_argument("--overlays", help="{segment_id: [Overlay]} or [Overlay] JSON from the production team")
    parser.add_argument("--video", help="video.mp4 (default: <match_dir>/video.mp4 if present)")
    args = parser.parse_args()

    t0 = time.perf_counter()
    out, sizes = export_from_dir(
        args.match_dir, args.out_root, match_id=args.match_id,
        insights_path=args.insights, overlays_path=args.overlays, video_path=args.video,
    )
    print(f"exported to {out} in {time.perf_counter() - t0:.1f} s")
    for name, size in sizes.items():
        print(f"  {name:14s} {size / 1024:9.1f} KB")
    print(f"  {'total':14s} {sum(sizes.values()) / 1024:9.1f} KB")


if __name__ == "__main__":
    main()
