"""M5 rollout engine: vectorised Monte-Carlo "world model".

Simulates N possible futures from one FrameState in parallel with numpy.
Every future is a possession-level simulation: in each time step the ball
holder shoots, passes or carries; off-ball players drift (attackers forward,
defenders compact, the nearest defender presses, the keeper comes off his line).
Probabilities come from simple, documented heuristics (xG from distance, goal
angle and keeper position; pass success from distance + openness + pressure;
dispossession from defender density and closeness to goal).

Interventions: move_player / remove_player change the start state; swap_action forces
the first decision. move/remove accept params["then_action"] (same shape as swap_action
params) to replay the actual decision, so such a counterfactual differs from the baseline
only in the moved player (with equal seeds a 0 m move reproduces the baseline exactly).

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
KEEPER_REACH = 1.5  # m; half the width a keeper covers
KEEPER_RUSH_DIST = 25.0  # m; the keeper leaves his line when the ball is this close to his goal
KEEPER_MAX_OUT = 7.0  # m off the goal line at most
TACKLE_GOAL_SCALE = 15.0  # m; how fast the extra near-goal dispossession risk fades
CARRY_SPEED = 5.0  # m/s, ball carrier (default for EngineParams.carry_speed)

GOAL_FOR, GOAL_AGAINST, RETAINED, LOST = range(4)
ACTION_SHOOT, ACTION_PASS, ACTION_CARRY = range(3)
ACTIONS = {"shoot": ACTION_SHOOT, "pass": ACTION_PASS, "carry": ACTION_CARRY}


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def _keeper_factor(pos: np.ndarray, goal_x: np.ndarray, angle: np.ndarray, keeper: np.ndarray, weight: float) -> np.ndarray:
    """How much of the goal the keeper leaves open, relative to a keeper standing on his line.

    A keeper covers about 2*atan(reach / distance) of the shooter's view of the goal; coming off
    the line towards the shooter (1v1) covers more, so the base xG (keeper on the line) shrinks.
    """
    d_line = np.abs(goal_x - pos[:, 0]) + 1.0
    d_keeper = np.linalg.norm(keeper - pos, axis=1)
    in_front = np.abs(goal_x - keeper[:, 0]) < np.abs(goal_x - pos[:, 0])
    cover_line = 2 * np.arctan(KEEPER_REACH / d_line)
    cover = np.where(in_front, 2 * np.arctan(KEEPER_REACH / np.maximum(d_keeper, 0.5)), 0.0)
    open_line = np.maximum(angle - cover_line, 1e-3)
    return np.clip((angle - cover) / open_line, 0.05, 1.5) ** weight


def expected_goals(
    pos: np.ndarray,
    attacks_right: np.ndarray,
    pressure: np.ndarray,
    keeper: np.ndarray | None = None,
    keeper_weight: float = 1.0,
) -> np.ndarray:
    """xG for shots from `pos` (n, 2), reduced under defensive pressure (0..1).

    The distance/angle curve assumes a keeper on his line; pass `keeper` (n, 2) to account for
    where he actually stands (a keeper rushing out narrows the angle); `keeper_weight` (0..1)
    damps that correction.
    """
    goal_x = np.where(attacks_right, PITCH_LENGTH, 0.0)
    post_a = np.stack([goal_x, np.full_like(goal_x, GOAL_Y - GOAL_HALF_WIDTH)], axis=1) - pos
    post_b = np.stack([goal_x, np.full_like(goal_x, GOAL_Y + GOAL_HALF_WIDTH)], axis=1) - pos
    cos = (post_a * post_b).sum(1) / (
        np.linalg.norm(post_a, axis=1) * np.linalg.norm(post_b, axis=1) + 1e-9
    )
    angle = np.arccos(np.clip(cos, -1.0, 1.0))
    dist = np.hypot(goal_x - pos[:, 0], GOAL_Y - pos[:, 1])
    xg = _sigmoid(-1.0 + 1.6 * angle - 0.09 * dist) * (1.0 - 0.5 * pressure)
    if keeper is not None:
        xg = np.clip(xg * _keeper_factor(pos, goal_x, angle, keeper, keeper_weight), 0.0, 0.95)
    return xg


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

    Calibrated 2026-10-21 on 150 real GRF states (grf-1..6, 15 s horizon, n=100 per state), with the
    decision-ranking gate (shoot beats carry at all 6 scenario spots within 12 m of goal):
                         engine   GRF     (before this calibration)
      turnover           0.875    0.773   (0.887)
      turnover, final 3rd 0.902   0.824   (0.905)
      goal               0.060    0.060   (0.073)
      tackles / 15 s     0.67     0.70    (0.04)
      shots / 15 s       0.46     0.29    (1.12)
      passes / 15 s      3.59     3.12    (3.92), completion 0.79 vs 0.71
      penalty spot (94, 34): shoot 0.24 vs carry 0.17   (before: 0.275 vs 0.350)
    The old engine hit the outcome rates for the wrong reason: almost no tackles, and players ran
    at goal and shot (dribbling beat shooting everywhere, review R1). Now dispossession grows with
    defender density and closeness to goal, and the keeper comes out and narrows the angle.
    Turnovers are still over-predicted, so Sliding Doors only makes comparative claims.
    """

    shoot_base: float = 0.2  # per-step shot probability within 8 m of goal
    shoot_range: float = 3.0  # m; shot probability decays with exp(-(d_goal - 8) / range)
    pass_base: float = 0.03  # per-step pass probability when free
    pass_pressure: float = 0.1  # extra pass probability when pressed
    pass_distance_scale: float = 600.0  # m; pass success decays with exp(-d / scale)
    lane_block: float = 0.15  # max success reduction from an opponent in the lane
    tackle_base: float = 0.2  # per-step dispossession probability per defender standing on the carrier
    tackle_range: float = 1.0  # m; each defender's tackle threat decays with exp(-d / range) (density: summed)
    tackle_goal_boost: float = 2.0  # extra risk near goal: x (1 + boost * exp(-d_goal / TACKLE_GOAL_SCALE))
    keeper_advance: float = 0.5  # keeper stands this fraction of the way from goal to ball (ball inside 25 m)
    keeper_xg_weight: float = 0.3  # how strongly shot xG depends on where the keeper stands (0 = ignore)
    carry_speed: float = CARRY_SPEED  # m/s


class RolloutEngine:
    def __init__(self, dt: float = 0.4, params: EngineParams | None = None) -> None:
        self.dt = dt
        self.params = params or EngineParams()
        self.last_counts: dict[str, float] = {}

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
            # swap_action forces the first decision; move/remove can replay one via "then_action",
            # so a counterfactual differs from the actual decision only in what it changes
            action_params = params if intervention.kind == "swap_action" else params.get("then_action")
            if action_params:
                forced_action = ACTIONS[action_params["action"]]
                if forced_action == ACTION_PASS:
                    forced_target = index[action_params["target_id"]]

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

        tally: dict[str, float] = {"owned_s": 0.0, "passes": 0, "passes_completed": 0, "shots": 0, "tackles": 0}
        for step in range(steps):
            active = outcome < 0
            if not active.any():
                paths[step + 1 :] = paths[step]
                break
            tally["owned_s"] += float(active.sum()) * dt

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
            p_shoot = np.where(d_goal < 35.0, prm.shoot_base * np.exp(-np.maximum(d_goal - 8.0, 0.0) / prm.shoot_range), 0.0)
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
                keeper_xy = None
                if prm.keeper_xg_weight > 0:
                    keeper_xy = hpos[shooters] + 50.0  # no keeper: far away, never "in front"
                    for t in (0, 1):
                        keeper = keeper_of[1 - t]
                        sel = hteam[shooters] == t
                        if keeper is not None and sel.any():
                            keeper_xy[sel] = pos[shooters[sel], keeper]
                xg = expected_goals(hpos[shooters], attacks_right[shooters], pressure[shooters], keeper_xy, prm.keeper_xg_weight)
                scored = rng.random(shooters.size) < xg
                tally["shots"] += int(shooters.size)
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
                tally["passes"] += int(rp.size)
                tally["passes_completed"] += int(ok.sum())
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
                pos[rc, owner[rc]] += heading * prm.carry_speed * dt + rng.normal(0, 0.4, (rc.size, 2))
                # dispossession: every defender nearby adds risk (density), and defences defend
                # deeper and more desperately close to their own goal
                d_def = np.linalg.norm(pos[rc] - pos[rc, owner[rc]][:, None, :], axis=2)  # after the carry step
                threat_sum = np.where(opp_matrix[owner[rc]], np.exp(-d_def / prm.tackle_range), 0.0).sum(1)
                near_goal = 1.0 + prm.tackle_goal_boost * np.exp(-d_goal[rc] / TACKLE_GOAL_SCALE)
                p_tackle = np.minimum(prm.tackle_base * threat_sum * near_goal, 0.95)
                tackled = rc[rng.random(rc.size) < p_tackle]
                tally["tackles"] += int(tackled.size)
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
            # the defending keeper comes off his line towards a ball inside ~25 m: narrows the angle,
            # pressures the shooter and can smother a carry (1v1 situations)
            for t in (0, 1):
                keeper = keeper_of[t]
                if keeper is None:
                    continue
                own_goal = np.array([PITCH_LENGTH if t == 1 else 0.0, GOAL_Y])
                to_ball = ball - own_goal
                d_ball_goal = np.linalg.norm(to_ball, axis=1, keepdims=True)
                out = np.minimum(prm.keeper_advance * d_ball_goal, KEEPER_MAX_OUT)
                rush = (att_team != t) & (d_ball_goal[:, 0] < KEEPER_RUSH_DIST)
                target_pos[rush, keeper] = own_goal + to_ball[rush] / (d_ball_goal[rush] + 1e-9) * out[rush]
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

        # action rates of this run (per possession-second), for calibration against GRF event rates
        self.last_counts = tally
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
