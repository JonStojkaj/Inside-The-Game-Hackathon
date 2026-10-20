"""Spike B: how fast is the rollout engine, and do counterfactuals give sensible answers?

Run from repo root:  backend/.venv/bin/python spikes/rollout_benchmark.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.models import Intervention  # noqa: E402
from app.rollout.engine import RolloutEngine  # noqa: E402
from app.rollout.scenarios import final_third_attack  # noqa: E402

engine = RolloutEngine()
state = final_third_attack()
engine.run(state, n=50)  # warm-up

print("== Throughput (15 s horizon, dt 0.4 s) ==")
for n in (100, 500, 1000, 2000):
    r = engine.run(state, n=n, seed=0)
    print(f"n={n:5d}  {r.elapsed_ms:7.1f} ms  ->  {n / r.elapsed_ms * 1000:8.0f} rollouts/s")

print("\n== Counterfactuals from the same moment (n=1000, 3 seeds) ==")
cases = {
    "baseline (engine decides)": None,
    "H7 shoots from 33 m": Intervention(kind="swap_action", params={"action": "shoot"}),
    "H7 passes to H9 (striker)": Intervention(kind="swap_action", params={"action": "pass", "target_id": "H9"}),
    "H7 passes back to H3": Intervention(kind="swap_action", params={"action": "pass", "target_id": "H3"}),
    "A8 marks H7 tightly": Intervention(kind="move_player", params={"player_id": "A8", "dx": -4.0, "dy": -5.5}),
    "A4 (centre back) removed": Intervention(kind="remove_player", params={"player_id": "A4"}),
}
print(f"{'case':30s} {'P(goal)':>8s} {'P(conc.)':>8s} {'P(lose)':>8s} {'chaos':>6s}   spread over seeds")
for label, iv in cases.items():
    runs = [engine.run(state, n=1000, seed=s, intervention=iv) for s in (11, 12, 13)]
    goals = [r.p_goal_for for r in runs]
    avg = lambda attr: sum(getattr(r, attr) for r in runs) / len(runs)  # noqa: E731
    print(
        f"{label:30s} {avg('p_goal_for'):8.3f} {avg('p_goal_against'):8.3f} "
        f"{avg('p_turnover'):8.3f} {avg('outcome_entropy'):6.2f}   ±{(max(goals) - min(goals)) / 2:.3f}"
    )
