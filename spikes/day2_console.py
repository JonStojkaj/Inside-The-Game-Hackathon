"""Day 2 end-to-end check: recorded match -> events -> live replay over the bus -> stats.

Run from repo root:
  backend/.venv/bin/python spikes/day2_console.py spikes/grf/out/matches/grf-1 --speed 60
  backend/.venv/bin/python spikes/day2_console.py --summary          # compare all recordings
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.bus.memory import InMemoryBus  # noqa: E402
from app.source.events import derive_events  # noqa: E402
from app.source.grf import load_grf_match  # noqa: E402
from app.source.replayer import EVENTS, FRAMES, replay  # noqa: E402
from app.stats.engine import StatsEngine  # noqa: E402

MATCHES = Path(__file__).resolve().parent / "grf" / "out" / "matches"
SHOWN = {"goal", "shot", "kickoff", "tackle", "interception"}


def clock(seconds: float) -> str:
    return f"{int(seconds // 60):2d}'"


def summary() -> None:
    for d in sorted(MATCHES.iterdir()):
        if not (d / "raw.jsonl").exists():
            continue
        m = load_grf_match(d)
        ev = derive_events(m)
        c = Counter(e.type for e in ev)
        shots = [e for e in ev if e.type == "shot"]
        goals = [round(m.clock_s(e.frame) / 60) for e in ev if e.type == "goal"]
        print(f"{d.name:14s} {m.score[-1].tolist()}  frames {m.n_frames:6d}  passes {c['pass']:4d}  shots {len(shots):3d}  goals at {goals}")


async def live(path: Path, speed: float) -> None:
    match = load_grf_match(path)
    events = derive_events(match)
    names = {p.id: f"{p.name} ({p.number})" for p in match.players}
    clubs = {"home": match.home.short, "away": match.away.short}
    stats = StatsEngine(match.match_id)
    bus = InMemoryBus()
    frames_sub, events_sub = bus.subscribe(FRAMES), bus.subscribe(EVENTS)

    async def on_frames() -> None:
        next_report = 15 * 60
        async for frame in frames_sub:
            stats.on_frame(frame, clock_s=match.clock_s(frame.frame))
            if match.clock_s(frame.frame) >= next_report:
                report(stats)
                next_report += 15 * 60

    async def on_events() -> None:
        async for e in events_sub:
            stats.on_event(e)
            if e.type not in SHOWN:
                continue
            who = names.get(e.player_id or "", clubs.get(e.team or "", ""))
            extra = ""
            if e.type == "shot":
                extra = f"{e.outcome}, {e.meta.get('distance_m')} m, {e.meta.get('shot_speed_kmh')} km/h"
            elif e.type == "goal":
                extra = f"score {e.meta['score'][0]}-{e.meta['score'][1]}"
            elif e.target_id:
                extra = f"from {names[e.target_id]}"
            print(f"{clock(match.clock_s(e.frame))} {clubs.get(e.team or '', '   ')} {e.type:12s} {who:28s} {extra}")

    print(f"{match.home.name} vs {match.away.name}  ({match.match_id}, {match.n_frames} frames, x{speed})\n")
    await asyncio.gather(on_frames(), on_events(), replay(match, events, bus, speed=speed))
    report(stats, final=True)


def report(stats: StatsEngine, final: bool = False) -> None:
    s = stats.snapshot()
    h, a = s.teams["home"], s.teams["away"]
    title = "FULL TIME" if final else f"{clock(s.clock_s)} STATS"
    print(f"\n  -- {title} --  score {s.score[0]}-{s.score[1]}")
    for label, fn in [
        ("possession", lambda t: f"{t.possession:.0%}"),
        ("passes (acc.)", lambda t: f"{t.passes} ({t.pass_accuracy or 0:.0%})"),
        ("avg pass m", lambda t: f"{t.avg_pass_distance_m or 0:.1f}"),
        ("shots (on t.)", lambda t: f"{t.shots} ({t.shots_on_target})"),
        ("max shot km/h", lambda t: f"{t.max_shot_speed_kmh:.0f}"),
        ("tackles/interc.", lambda t: f"{t.tackles}/{t.interceptions}"),
        ("distance km", lambda t: f"{t.distance_km:.1f}"),
    ]:
        print(f"  {label:16s} {fn(h):>10s} {fn(a):>10s}")
    fastest = max(s.players.values(), key=lambda p: p.top_speed_kmh)
    runner = max(s.players.values(), key=lambda p: p.distance_m)
    print(f"  fastest: {fastest.name} {fastest.top_speed_kmh:.1f} km/h | most distance: {runner.name} {runner.distance_m / 1000:.2f} km\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("match", nargs="?", default=str(MATCHES / "grf-1"))
    parser.add_argument("--speed", type=float, default=60.0)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    if args.summary:
        summary()
    else:
        asyncio.run(live(Path(args.match), args.speed))


if __name__ == "__main__":
    main()
