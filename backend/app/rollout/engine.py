"""M5 rollout engine: vectorised Monte-Carlo "world model".

Simulates N possible futures from one FrameState in parallel with numpy.
Every future is a possession-level simulation: in each time step the ball
holder shoots, passes or carries; off-ball players drift (attackers forward,
defenders compact, the nearest defender presses). Probabilities come from
simple, documented heuristics (xG from distance + goal angle, pass success
from distance + openness + pressure, tackles from defender proximity).

Outcomes are valued per possession, like possession-value models:
  GOAL_FOR      the attacking team scores before it loses the ball
  GOAL_AGAINST  after losing it, the opponent scores before it is won back
  LOST          the ball is lost and won back without a goal
  RETAINED      the attacking team still has the ball at the horizon
                (or lost it and the opponent still has it: counted as LOST)

It is deliberately simple and fast. The engine sits behind `run()` so it can
be replaced by a model calibrated on real data without touching the agents.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from app.models import (
    PITCH_LENGTH,
    PITCH_WIDTH,
    FrameState,
    Intervention,
    RolloutResult,
)

GOAL_Y = PITCH_WIDTH / 2
GOAL_HALF_WIDTH = 7.32 / 2
MAX_SPEED = 7.0  # m/s, off-ball movement
CARRY_SPEED = 5.0  # m/s, ball carrier

GOAL_FOR, GOAL_AGAINST, RETAINED, LOST = range(4)
ACTION_SHOOT, ACTION_PASS, ACTION_CARRY = range(3)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def expected_goals(pos: np.ndarray, attacks_right: np.ndarray, pressure: np.ndarray) -> np.ndarray:
    """xG for shots from `pos` (n, 2), reduced under defensive pressure (0..1)."""
    goal_x = np.where(attacks_right, PITCH_LENGTH, 0.0)
    post_a = np.stack([goal_x, np.full_like(goal_x, GOAL_Y - GOAL_HALF_WIDTH)], axis=1) - pos
    post_b = np.stack([goal_x, np.full_like(goal_x, GOAL_Y + GOAL_HALF_WIDTH)], axis=1) - pos
    cos = (post_a * post_b).sum(1) / (
        np.linalg.norm(post_a, axis=1) * np.linalg.norm(post_b, axis=1) + 1e-9
    )
    angle = np.arccos(np.clip(cos, -1.0, 1.0))
    dist = np.hypot(goal_x - pos[:, 0], GOAL_Y - pos[:, 1])
    return _sigmoid(-1.0 + 1.6 * angle - 0.09 * dist) * (1.0 - 0.5 * pressure)


def _lane_clearance(start: np.ndarray, end: np.ndarray, pos: np.ndarray, opponents: np.ndarray) -> np.ndarray:
    """Distance from the closest opponent to each pass lane start -> end (m, 2) given pos (m, P, 2)."""
    seg = end - start
    rel = pos - start[:, None, :]
    t = np.clip((rel * seg[:, None, :]).sum(2) / ((seg**2).sum(1)[:, None] + 1e-9), 0.0, 1.0)
    closest = start[:, None, :] + t[..., None] * seg[:, None, :]
    return np.where(opponents, np.linalg.norm(pos - closest, axis=2), np.inf).min(1)


def _nearest_opponent(opp_matrix: np.ndarray, pair: np.ndarray, sims: np.ndarray, of: np.ndarray) -> np.ndarray:
    """Index of the opponent closest to player `of[i]` in simulation `sims[i]`."""
    return np.where(opp_matrix[of], pair[sims, of], np.inf).argmin(1)


@dataclass(frozen=True)
class EngineParams:
    """Behaviour knobs, tuned by app/rollout/calibration.py against recorded GRF matches.

    Calibrated 2026-10-22 on 150 real GRF states (6 matches, 15 s horizon):
      turnover  engine 0.89 vs GRF 0.77 (final third 0.90 vs 0.82)
      goal      engine 0.071 vs GRF 0.060
    The engine still over-predicts turnovers, so Sliding Doors only makes comparative claims.
    """

    shoot_base: float = 0.6  # per-step shot probability near goal
    pass_base: float = 0.03  # per-step pass probability when free
    pass_pressure: float = 0.1  # extra pass probability when pressed
    pass_distance_scale: float = 600.0  # m; pass success decays with exp(-d / scale)
    lane_block: float = 0.15  # max success reduction from an opponent in the lane
    tackle_base: float = 0.02  # per-step tackle probability with a defender on top of the carrier


class RolloutEngine:
    def __init__(self, dt: float = 0.4, params: EngineParams | None = None) -> None:
        self.dt = dt
        self.params = params or EngineParams()

    def run(
        self,
        state: FrameState,
        n: int = 500,
        horizon_s: float = 15.0,
        seed: int = 0,
        intervention: Intervention | None = None,
        n_paths: int = 50,
    ) -> RolloutResult:
        started = time.perf_counter()
        rng = np.random.default_rng(seed)
        prm = self.params
        dt = self.dt

        ids = [p.id for p in state.players]
        index = {pid: i for i, pid in enumerate(ids)}
        if state.ball.owner_id is None or state.ball.owner_id not in index:
            raise ValueError("rollouts need a ball owner")

        team = np.array([0 if p.team == "home" else 1 for p in state.players])
        is_gk = np.array([p.role == "gk" for p in state.players])
        present = np.ones(len(ids), dtype=bool)
        base = np.array([[p.x, p.y] for p in state.players], dtype=float)
        forced_action: int | None = None
        forced_target: int | None = None

        if intervention is not None:
            params = intervention.params
            if intervention.kind == "move_player":
                i = index[params["player_id"]]
                base[i] += (float(params.get("dx", 0.0)), float(params.get("dy", 0.0)))
            elif intervention.kind == "remove_player":
                present[index[params["player_id"]]] = False
            elif intervention.kind == "swap_action":
                forced_action = {"shoot": ACTION_SHOOT, "pass": ACTION_PASS, "carry": ACTION_CARRY}[
                    params["action"]
                ]
                if forced_action == ACTION_PASS:
                    forced_target = index[params["target_id"]]

        base[:, 0] = np.clip(base[:, 0], 0.0, PITCH_LENGTH)
        base[:, 1] = np.clip(base[:, 1], 0.0, PITCH_WIDTH)

        pos = np.repeat(base[None], n, axis=0)  # (n, P, 2)
        owner = np.full(n, index[state.ball.owner_id])
        ball0 = base[owner[0]].copy()
        init_team = team[owner[0]]
        keeper_of: dict[int, int | None] = {}
        for t in (0, 1):
            keepers = np.flatnonzero(is_gk & (team == t) & present)
            keeper_of[t] = int(keepers[0]) if keepers.size else None

        outcome = np.full(n, -1)
        ever_lost = np.zeros(n, dtype=bool)
        rows = np.arange(n)
        opp_matrix = (team[:, None] != team[None, :]) & present[None, :]  # (P, P)
        steps = max(1, int(round(horizon_s / dt)))
        k = min(n_paths, n)
        paths = np.empty((steps + 1, k, 2))
        paths[0] = pos[rows[:k], owner[:k]]

        for step in range(steps):
            active = outcome < 0
            if not active.any():
                paths[step + 1 :] = paths[step]
                break

            hteam = team[owner]
            attacks_right = hteam == 0
            direction = np.where(attacks_right, 1.0, -1.0)
            hpos = pos[rows, owner]

            pair = np.linalg.norm(pos[:, :, None, :] - pos[:, None, :, :], axis=3)  # (n, P, P)
            nearest_opp = np.where(opp_matrix[None], pair, np.inf).min(axis=2)  # (n, P)
            d_press = nearest_opp[rows, owner]
            pressure = np.exp(-d_press / 3.0)

            goal_x = np.where(attacks_right, PITCH_LENGTH, 0.0)
            d_goal = np.hypot(goal_x - hpos[:, 0], GOAL_Y - hpos[:, 1])

            # --- choose action -------------------------------------------------
            p_shoot = np.where(d_goal < 35.0, prm.shoot_base * np.exp(-np.maximum(d_goal - 8.0, 0.0) / 7.0), 0.0)
            p_pass = prm.pass_base + prm.pass_pressure * pressure
            u = rng.random(n)
            action = np.where(
                u < p_shoot, ACTION_SHOOT, np.where(u < p_shoot + p_pass, ACTION_PASS, ACTION_CARRY)
            )
            action[is_gk[owner]] = ACTION_PASS  # keepers distribute, they don't dribble
            if step == 0 and forced_action is not None:
                action[:] = forced_action

            # --- shots ---------------------------------------------------------
            shoot = active & (action == ACTION_SHOOT)
            if shoot.any():
                shooters = np.flatnonzero(shoot)
                xg = expected_goals(hpos[shooters], attacks_right[shooters], pressure[shooters])
                scored = rng.random(shooters.size) < xg
                for_init = hteam[shooters] == init_team
                outcome[shooters[scored & for_init]] = GOAL_FOR
                outcome[shooters[scored & ~for_init]] = GOAL_AGAINST
                missed = shooters[~scored]
                for t in (0, 1):
                    sel = missed[hteam[missed] == t]
                    keeper = keeper_of[1 - t]
                    if keeper is not None:
                        owner[sel] = keeper
                    elif sel.size:
                        owner[sel] = _nearest_opponent(opp_matrix, pair, sel, owner[sel])

            # --- passes --------------------------------------------------------
            passing = active & (action == ACTION_PASS)
            if passing.any():
                rp = np.flatnonzero(passing)
                m = np.arange(rp.size)
                mates = (team[None, :] == hteam[rp, None]) & present[None, :]
                mates[m, owner[rp]] = False
                dist = pair[rp, owner[rp]]  # (m, P)
                progress = direction[rp, None] * (pos[rp, :, 0] - hpos[rp, None, 0])
                openness = nearest_opp[rp]
                weight = np.exp(0.04 * progress) * (1 - np.exp(-openness / 4.0)) * np.exp(-dist / 25.0)
                weight = np.where(mates, weight, 0.0)
                weight /= weight.sum(1, keepdims=True) + 1e-12
                target = np.minimum((weight.cumsum(1) < rng.random((rp.size, 1))).sum(1), len(ids) - 1)
                if step == 0 and forced_target is not None:
                    target[:] = forced_target
                t_dist = dist[m, target]
                t_open = openness[m, target]
                lane = _lane_clearance(hpos[rp], pos[rp, target], pos[rp], opp_matrix[owner[rp]])
                p_success = (
                    0.99
                    * np.exp(-t_dist / prm.pass_distance_scale)
                    * (1 - 0.4 * np.exp(-t_open / 2.0))
                    * (1 - prm.lane_block * np.exp(-lane / 1.5))
                    * (1 - 0.15 * pressure[rp])
                )
                p_success = np.where(is_gk[owner[rp]], 0.85, p_success)
                ok = rng.random(rp.size) < p_success
                owner[rp[ok]] = target[ok]
                failed = rp[~ok]
                if failed.size:
                    owner[failed] = _nearest_opponent(opp_matrix, pair, failed, target[~ok])

            # --- carries + tackles --------------------------------------------
            carry = active & (action == ACTION_CARRY)
            if carry.any():
                rc = np.flatnonzero(carry)
                to_goal = np.stack([goal_x[rc] - hpos[rc, 0], GOAL_Y - hpos[rc, 1]], axis=1)
                to_goal /= np.linalg.norm(to_goal, axis=1, keepdims=True) + 1e-9
                heading = 0.6 * to_goal + 0.4 * np.stack([direction[rc], np.zeros(rc.size)], axis=1)
                heading /= np.linalg.norm(heading, axis=1, keepdims=True) + 1e-9
                pos[rc, owner[rc]] += heading * CARRY_SPEED * dt + rng.normal(0, 0.4, (rc.size, 2))
                p_tackle = prm.tackle_base * np.exp(-d_press[rc] / 1.0)
                tackled = rc[rng.random(rc.size) < p_tackle]
                if tackled.size:
                    owner[tackled] = _nearest_opponent(opp_matrix, pair, tackled, owner[tackled])

            regained = active & ever_lost & (team[owner] == init_team) & (outcome < 0)
            outcome[regained] = LOST
            ever_lost |= active & (team[owner] != init_team)

            # --- off-ball movement --------------------------------------------
            # Players keep their shape: each one is anchored to its starting position,
            # shifted with the ball (attackers further and a little forward, defenders
            # less and towards the goal they protect).
            ball = pos[rows, owner]
            att_team = team[owner]
            attacking = team[None, :] == att_team[:, None]  # (n, P)
            att_dir = np.where(att_team == 0, 1.0, -1.0)
            shift = (ball - ball0)[:, None, :]
            forward = base[None] + 0.6 * shift
            forward[..., 0] += att_dir[:, None] * 2.0
            protected_goal_x = np.where(att_team == 0, PITCH_LENGTH, 0.0)
            compact = base[None] + 0.45 * shift
            compact[..., 0] += 0.1 * (protected_goal_x[:, None] - compact[..., 0])
            target_pos = np.where(attacking[..., None], forward, compact)
            d_ball = np.where(
                ~attacking & present[None, :], np.linalg.norm(pos - ball[:, None, :], axis=2), np.inf
            )
            # nearest defender presses, closing to ~1.5 m rather than standing on the ball
            presser = d_ball.argmin(1)
            away = pos[rows, presser] - ball
            away /= np.linalg.norm(away, axis=1, keepdims=True) + 1e-9
            target_pos[rows, presser] = ball + 1.5 * away
            target_pos[:, is_gk] = pos[:, is_gk]
            step_vec = target_pos - pos
            step_len = np.linalg.norm(step_vec, axis=2, keepdims=True)
            step_vec *= np.minimum(1.0, MAX_SPEED * dt / (step_len + 1e-9))
            moving = (np.arange(len(ids))[None, :] != owner[:, None]) & present[None, :] & active[:, None]
            pos += np.where(moving[..., None], step_vec + rng.normal(0, 0.3, pos.shape), 0.0)
            pos[..., 0].clip(0.0, PITCH_LENGTH, out=pos[..., 0])
            pos[..., 1].clip(0.0, PITCH_WIDTH, out=pos[..., 1])

            paths[step + 1] = pos[rows[:k], owner[:k]]

        unresolved = outcome < 0
        outcome[unresolved] = np.where(team[owner[unresolved]] == init_team, RETAINED, LOST)

        counts = np.bincount(outcome, minlength=4) / n
        nonzero = counts[counts > 0]
        entropy = float(-(nonzero * np.log(nonzero)).sum() / np.log(4))

        return RolloutResult(
            n=n,
            seed=seed,
            horizon_s=horizon_s,
            attacking_team="home" if init_team == 0 else "away",
            p_goal_for=float(counts[GOAL_FOR]),
            p_goal_against=float(counts[GOAL_AGAINST]),
            p_turnover=float(ever_lost.mean()),
            p_retained=float(counts[RETAINED]),
            outcome_entropy=entropy,
            sample_paths=[[(float(x), float(y)) for x, y in paths[:, j]] for j in range(k)],
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )
