"""Stages c-e for the demo match: key moments -> verified insights -> overlays per viewer segment.

Writes into the output dir:
  insights.json        [Insight]                      (explain team, once per match)
  overlays.json        {segment_id: [Overlay]}        (production team + scheduler, once per segment)
  segments.json        {segment_id: Segment}          (profile + rules each segment was produced with)
  production_log.json  [AgentStep] + stats            (control-room panel: who decided what)

Run from repo root (offline, deterministic):
  LLM_PROVIDER=fake backend/.venv/bin/python spikes/produce_demo.py
With Azure OpenAI for the agents (needs .env + az login):
  LLM_PROVIDER=azure backend/.venv/bin/python spikes/produce_demo.py --out data/production/full-34-azure
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.explain import ExplainTeam, fake_explain_llm  # noqa: E402
from app.agents.llm import CachedLLM, FakeLLM, llm_from_env  # noqa: E402
from app.agents.production import fake_production_llm  # noqa: E402
from app.models import Insight  # noqa: E402
from app.overlay.cues import context_from_grf  # noqa: E402
from app.overlay.pipeline import produce  # noqa: E402
from app.personalization.i18n import minute  # noqa: E402
from app.personalization.segments import demo_segments  # noqa: E402
from app.source.events import derive_events  # noqa: E402
from app.source.grf import load_grf_match  # noqa: E402
from app.stats.moments import detect_moments  # noqa: E402

DEFAULT_MATCH = ROOT / "spikes" / "grf" / "out" / "matches" / "full-34"


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("match", nargs="?", type=Path, default=DEFAULT_MATCH)
    ap.add_argument("--out", type=Path, default=None, help="default: data/production/<match_id>")
    ap.add_argument("--insights", type=Path, default=None, help="reuse an existing insights.json instead of explaining")
    ap.add_argument("--fake-explain", action="store_true", help="explain team on the fake LLM even if LLM_PROVIDER=azure")
    args = ap.parse_args()
    load_env()

    t0 = time.time()
    match = load_grf_match(args.match)
    events = derive_events(match)
    moments = detect_moments(events, match.clock_s)
    out = args.out or ROOT / "data" / "production" / match.match_id
    out.mkdir(parents=True, exist_ok=True)
    fake = FakeLLM({**fake_explain_llm().handlers, **fake_production_llm().handlers})
    llm = llm_from_env(fake)
    print(f"{match.home.name} vs {match.away.name} ({match.match_id}): {len(events)} events, {len(moments)} key moments, "
          f"LLM {llm.name}")

    if args.insights:
        insights = [Insight.model_validate(i) for i in json.loads(args.insights.read_text())]
    else:
        team = ExplainTeam(llm_from_env(fake_explain_llm()) if args.fake_explain else llm)
        insights = [team.explain(match, m, events) for m in moments]
    (out / "insights.json").write_text(json.dumps([i.model_dump(mode="json") for i in insights], ensure_ascii=False))
    print(f"explain: {len(insights)} insights in {time.time() - t0:.1f}s")

    t1 = time.time()
    ctx = context_from_grf(match)
    frames = [match.frame_state(f) for f in range(match.n_frames)]
    segments = demo_segments()
    result = produce(ctx, frames, events, moments, insights, segments, llm)
    (out / "overlays.json").write_text(json.dumps(
        {sid: [o.model_dump(mode="json") for o in ovs] for sid, ovs in result.overlays.items()}, ensure_ascii=False))
    (out / "segments.json").write_text(json.dumps({s.id: s.model_dump(mode="json") for s in segments}, ensure_ascii=False, indent=1))
    (out / "production_log.json").write_text(json.dumps(
        {"stats": result.stats, "steps": [s.model_dump(mode="json") for s in result.log]}, ensure_ascii=False, indent=1))
    print(f"production: {len(segments)} segments in {time.time() - t1:.1f}s -> {out}")
    if isinstance(llm, CachedLLM):
        print(f"LLM cache: {llm.hits} hits, {llm.misses} calls")
    print(f"\n{'segment':28s} {'shown':>5s} {'dropped':>7s} {'insights':>8s} {'llm':>4s}")
    for sid, s in result.stats.items():
        if sid != "*":
            print(f"{sid:28s} {s['shown']:5d} {s['dropped']:7d} {s['insights_shown']:4d}/{s['insights_produced']:<3d} {s['llm_calls']:4d}")
    print(f"'show every event' baseline: {result.stats['*']['show_every_event_baseline']} graphics per segment")

    # what each segment sees around the first goal
    first_goal = next((e for e in events if e.type == "goal"), None)
    if first_goal:
        lo, hi = first_goal.t_ms - 2_000, first_goal.t_ms + 12_000
        print(f"\nAround the first goal ({minute(ctx.clock_of(first_goal.t_ms))}'):")
        for sid, ovs in result.overlays.items():
            print(f"  [{sid}]")
            for o in ovs:
                if lo <= o.start_ms <= hi and o.slot not in ("scorebug", "side_panel"):
                    print(f"    {o.start_ms / 1000:6.1f}s {o.type:13s} {o.headline} | {o.body}")


if __name__ == "__main__":
    main()
