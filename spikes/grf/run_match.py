"""Spike A: can GRF give us a bot-vs-bot match with per-frame state + video?

Runs inside the gfootball:spike container:
  docker run --rm --platform linux/amd64 -v "$PWD/spikes/grf:/spike" gfootball:spike \
    xvfb-run -a -s "-screen 0 1280x720x24" python3 /spike/run_match.py

Writes to /spike/out:
  frames.jsonl     one line per step (positions in GRF coords: x -1..1, y -0.42..0.42)
  video/           rendered dump (only with RENDER=1)
  timing.json      steps/s headless and rendered, scenario-reset cost
"""

from __future__ import annotations

import json
import os
import time

import gfootball.env as football_env
from gfootball.env import football_action_set

OUT = "/spike/out"
# GRF only returns observations for controlled players, so we control one and
# hand it back to the built-in AI: effectively bot vs bot, with full raw state.
BOT = [football_action_set.action_builtin_ai]
STEPS = int(os.environ.get("STEPS", "600"))  # 10 steps = 1 s of game time
RENDER = os.environ.get("RENDER", "1") == "1"


def make(render: bool, logdir: str | None = None):
    return football_env.create_environment(
        env_name="11_vs_11_stochastic",
        representation="raw",
        number_of_left_players_agent_controls=1,
        number_of_right_players_agent_controls=0,
        other_config_options={"action_set": "full"},
        render=render,
        write_video=render,
        write_full_episode_dumps=render,
        logdir=logdir or "",
    )


def snapshot(obs: dict, step: int) -> dict:
    return {
        "step": step,
        "ball": [round(float(v), 4) for v in obs["ball"]],
        "ball_owned_team": int(obs["ball_owned_team"]),
        "ball_owned_player": int(obs["ball_owned_player"]),
        "left_team": [[round(float(x), 4), round(float(y), 4)] for x, y in obs["left_team"]],
        "right_team": [[round(float(x), 4), round(float(y), 4)] for x, y in obs["right_team"]],
        "game_mode": int(obs["game_mode"]),
        "score": [int(s) for s in obs["score"]],
    }


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    timing: dict[str, float] = {}

    # 1) headless speed + state dump
    env = make(render=False)
    obs = env.reset()
    started = time.perf_counter()
    with open(f"{OUT}/frames.jsonl", "w") as f:
        for step in range(STEPS):
            obs, _, done, _ = env.step(BOT)
            f.write(json.dumps(snapshot(obs[0] if isinstance(obs, list) else obs, step)) + "\n")
            if done:
                break
    timing["headless_steps_per_s"] = STEPS / (time.perf_counter() - started)

    started = time.perf_counter()
    for _ in range(5):
        env.reset()
    timing["reset_s"] = (time.perf_counter() - started) / 5
    env.close()

    # 2) rendered video
    if RENDER:
        env = make(render=True, logdir=f"{OUT}/video")
        env.reset()
        started = time.perf_counter()
        n = min(STEPS, 300)
        for _ in range(n):
            _, _, done, _ = env.step(BOT)
            if done:
                break
        timing["rendered_steps_per_s"] = n / (time.perf_counter() - started)
        env.close()

    with open(f"{OUT}/timing.json", "w") as f:
        json.dump(timing, f, indent=2)
    print(json.dumps(timing, indent=2))


if __name__ == "__main__":
    main()
