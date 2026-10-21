"""Record full bot-vs-bot GRF matches (raw state per step) for the replayer.

Runs inside the gfootball:spike container (headless, no Xvfb needed):
  docker run --rm --platform linux/amd64 -v "$PWD/spikes/grf:/spike" gfootball:spike \
    python3 /spike/record_match.py --seeds 1 2 3

Full-length, balanced matches with our own scenario:
  docker run --rm --platform linux/amd64 -v "$PWD/spikes/grf:/spike" \
    -v "$PWD/spikes/grf/scenarios/sliding_doors_full.py:/usr/local/lib/python3.8/dist-packages/gfootball/scenarios/sliding_doors_full.py" \
    -e GRF_DURATION=54000 gfootball:spike python3 /spike/record_match.py --scenario sliding_doors_full --seeds 11

Writes /spike/out/matches/grf-<seed>/raw.jsonl (one line per step, GRF coordinates:
x -1..1, y -0.42..0.42) and meta.json.
"""

from __future__ import annotations

import argparse
import json
import os
import time

import gfootball.env as football_env
from gfootball.env import football_action_set

OUT = "/spike/out/matches"
# GRF only returns observations for controlled players: control one and hand it to the built-in AI.
BOT = [football_action_set.action_builtin_ai]


def _pairs(arr) -> list[list[float]]:
    return [[round(float(a), 5), round(float(b), 5)] for a, b in arr]


def snapshot(obs: dict, step: int) -> dict:
    return {
        "step": step,
        "steps_left": int(obs["steps_left"]),
        "ball": [round(float(v), 5) for v in obs["ball"]],
        "ball_direction": [round(float(v), 5) for v in obs["ball_direction"]],
        "ball_owned_team": int(obs["ball_owned_team"]),
        "ball_owned_player": int(obs["ball_owned_player"]),
        "left_team": _pairs(obs["left_team"]),
        "right_team": _pairs(obs["right_team"]),
        "left_team_direction": _pairs(obs["left_team_direction"]),
        "right_team_direction": _pairs(obs["right_team_direction"]),
        "left_team_roles": [int(r) for r in obs["left_team_roles"]],
        "right_team_roles": [int(r) for r in obs["right_team_roles"]],
        "game_mode": int(obs["game_mode"]),
        "score": [int(s) for s in obs["score"]],
    }


def record(seed: int, scenario: str) -> dict:
    match_id = f"grf-{seed}" if scenario == "11_vs_11_stochastic" else f"full-{seed}"
    out_dir = f"{OUT}/{match_id}"
    os.makedirs(out_dir, exist_ok=True)
    env = football_env.create_environment(
        env_name=scenario,
        representation="raw",
        number_of_left_players_agent_controls=1,
        number_of_right_players_agent_controls=0,
        other_config_options={"action_set": "full", "game_engine_random_seed": seed},
        write_full_episode_dumps=True,
        logdir=out_dir,
    )
    obs = env.reset()
    started = time.perf_counter()
    steps = 0
    with open(f"{out_dir}/raw.jsonl", "w") as f:
        f.write(json.dumps(snapshot(obs[0], 0)) + "\n")
        done = False
        while not done:
            obs, _, done, _ = env.step(BOT)
            steps += 1
            f.write(json.dumps(snapshot(obs[0], steps)) + "\n")
    env.close()
    meta = {
        "match_id": match_id,
        "seed": seed,
        "steps": steps,
        "final_score": [int(s) for s in obs[0]["score"]],
        "record_seconds": round(time.perf_counter() - started, 1),
    }
    with open(f"{out_dir}/meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[1])
    # 11_vs_11_stochastic = GRF default (5 min of play, clock scaled to 90');
    # sliding_doors_full = our scenario (length + balance via GRF_* env vars, see scenarios/)
    parser.add_argument("--scenario", default="11_vs_11_stochastic")
    args = parser.parse_args()
    for seed in args.seeds:
        print(json.dumps(record(seed, args.scenario)), flush=True)


if __name__ == "__main__":
    main()
