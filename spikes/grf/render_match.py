"""Render a match to video AND record its raw state in the same pass (video and data match by construction).

Runs inside the gfootball:spike container with a virtual display (do not use xvfb-run, it hangs).
SDL_VIDEODRIVER=x11 is required since the macOS 27 / OrbStack update, otherwise SDL fails with
"Video subsystem has not been initialized":
  docker run --rm --cpus=2 --platform linux/amd64 -v "$PWD/spikes/grf:/spike" \
    -v "$PWD/spikes/grf/scenarios/sliding_doors_full.py:/usr/local/lib/python3.8/dist-packages/gfootball/scenarios/sliding_doors_full.py" \
    -e GRF_DURATION=3000 -e SDL_VIDEODRIVER=x11 -e XDG_RUNTIME_DIR=/tmp -w /spike gfootball:spike \
    sh -c 'Xvfb :99 -screen 0 1280x720x24 >/dev/null 2>&1 & sleep 4; DISPLAY=:99 python3 /spike/render_match.py --seed 34 --match-id demo-34'

Writes /spike/out/matches/<match-id>/raw.jsonl, video.mp4 (1280x720, 10 fps = real time) and meta.json.
"""

from __future__ import annotations

import argparse
import json
import os
import time

import cv2
import gfootball.env as football_env
from gfootball.env import football_action_set

from record_match import OUT, snapshot

BOT = [football_action_set.action_builtin_ai]
FPS = 10  # one GRF step = 0.1 s


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--match-id", required=True)
    parser.add_argument("--scenario", default="sliding_doors_full")
    args = parser.parse_args()

    out_dir = f"{OUT}/{args.match_id}"
    os.makedirs(out_dir, exist_ok=True)
    # Creating a headless engine first is what makes SDL video init succeed under amd64 emulation
    # (a rendering engine created first fails with "Video subsystem has not been initialized").
    warmup = football_env.create_environment(env_name=args.scenario, representation="raw")
    warmup.reset()
    warmup.close()
    env = football_env.create_environment(
        env_name=args.scenario,
        representation="raw",
        number_of_left_players_agent_controls=1,
        number_of_right_players_agent_controls=0,
        render=True,
        other_config_options={
            "action_set": "full",
            "game_engine_random_seed": args.seed,
            "render_resolution_x": 1280,
            "display_game_stats": False,
        },
    )
    obs = env.reset()
    frame = env.render(mode="rgb_array")
    height, width = frame.shape[:2]
    writer = cv2.VideoWriter(f"{out_dir}/video.mp4", cv2.VideoWriter_fourcc(*"mp4v"), FPS, (width, height))

    started = time.perf_counter()
    steps = 0
    with open(f"{out_dir}/raw.jsonl", "w") as f:
        f.write(json.dumps(snapshot(obs[0], 0)) + "\n")
        writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        done = False
        while not done:
            obs, _, done, _ = env.step(BOT)
            steps += 1
            f.write(json.dumps(snapshot(obs[0], steps)) + "\n")
            writer.write(cv2.cvtColor(env.render(mode="rgb_array"), cv2.COLOR_RGB2BGR))
            if steps % 500 == 0:
                print(f"step {steps} ({steps / (time.perf_counter() - started):.1f} steps/s)", flush=True)
    writer.release()
    env.close()
    meta = {
        "match_id": args.match_id,
        "seed": args.seed,
        "scenario": args.scenario,
        "steps": steps,
        "final_score": [int(s) for s in obs[0]["score"]],
        "video": {"file": "video.mp4", "fps": FPS, "width": width, "height": height},
        "record_seconds": round(time.perf_counter() - started, 1),
    }
    with open(f"{out_dir}/meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(json.dumps(meta), flush=True)


if __name__ == "__main__":
    main()
