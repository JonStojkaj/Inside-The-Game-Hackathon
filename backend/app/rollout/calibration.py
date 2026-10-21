"""Calibrate the rollout engine against recorded GRF matches (PLAN.md §7).

Idea: start the engine from *real* GRF game states and compare what it predicts with what
actually happened next in GRF:
  - turnover rate: did the team in possession lose the ball within the horizon?
  - goal rate:     did it score before losing the ball?
A small grid search then picks the EngineParams whose predictions match best.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace

import numpy as np

from app.models import FrameState
from app.rollout.engine import EngineParams, RolloutEngine
from app.source.grf import STEP_S, GrfMatch


@dataclass
class Sample:
    state: FrameState
    lost: bool  # GRF: possession lost within the horizon
    scored: bool  # GRF: possession team scored before losing it
    final_third: bool


def sample_states(matches: list[GrfMatch], horizon_s: float = 15.0, every: int = 25, limit: int | None = None) -> list[Sample]:
    horizon = int(horizon_s / STEP_S)
    out: list[Sample] = []
    for m in matches:
        for f in range(0, m.n_frames - horizon, every):
            owner = int(m.owner_idx[f])
            if owner < 0 or m.game_mode[f] != 0 or m.jump[f : f + 2].any():
                continue
            team = 0 if owner < 11 else 1
            window = m.owner_team[f : f + horizon]
            lost_at = np.flatnonzero(window == 1 - team)
            first_loss = int(lost_at[0]) if lost_at.size else horizon
            goals_before = m.score[f + first_loss - 1, team] - m.score[f, team] if first_loss > 0 else 0
            x = m.pos[f, owner, 0]
            out.append(
                Sample(
                    state=m.frame_state(f),
                    lost=bool(lost_at.size),
                    scored=bool(goals_before > 0),
                    final_third=bool(x > 70 if team == 0 else x < 35),
                )
            )
    if limit is not None and len(out) > limit:
        idx = np.linspace(0, len(out) - 1, limit).astype(int)
        out = [out[i] for i in idx]
    return out


@dataclass
class Fit:
    params: EngineParams
    engine_turnover: float
    grf_turnover: float
    engine_goal: float
    grf_goal: float
    engine_turnover_final_third: float
    grf_turnover_final_third: float

    @property
    def error(self) -> float:
        return (
            (self.engine_turnover - self.grf_turnover) ** 2
            + (self.engine_turnover_final_third - self.grf_turnover_final_third) ** 2
            + 4 * (self.engine_goal - self.grf_goal) ** 2
        )


def evaluate(params: EngineParams, samples: list[Sample], n: int = 100, horizon_s: float = 15.0) -> Fit:
    engine = RolloutEngine(params=params)
    results = [engine.run(s.state, n=n, horizon_s=horizon_s, seed=i, n_paths=0) for i, s in enumerate(samples)]
    final = [i for i, s in enumerate(samples) if s.final_third] or list(range(len(samples)))
    return Fit(
        params=params,
        engine_turnover=float(np.mean([r.p_turnover for r in results])),
        grf_turnover=float(np.mean([s.lost for s in samples])),
        engine_goal=float(np.mean([r.p_goal_for for r in results])),
        grf_goal=float(np.mean([s.scored for s in samples])),
        engine_turnover_final_third=float(np.mean([results[i].p_turnover for i in final])),
        grf_turnover_final_third=float(np.mean([samples[i].lost for i in final])),
    )


def grid_search(samples: list[Sample], grid: dict[str, list[float]], base: EngineParams | None = None, n: int = 100) -> list[Fit]:
    base = base or EngineParams()
    keys = list(grid)
    fits = [evaluate(replace(base, **dict(zip(keys, values))), samples, n=n) for values in itertools.product(*grid.values())]
    return sorted(fits, key=lambda f: f.error)
