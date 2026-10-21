"""Calibrate the rollout engine against recorded GRF matches (PLAN.md §7).

Idea: start the engine from *real* GRF game states and compare what it predicts with what
actually happened next in GRF:
  - turnover rate: did the team in possession lose the ball within the horizon?
  - goal rate:     did it score before losing the ball?
  - action rates:  passes, pass completion, tackles and shots per 15 s of play, from the events
                   derived from the same matches (an engine can hit the outcome rates for the
                   wrong reasons, e.g. by running at goal and shooting instead of passing)
plus a football sanity gate on *decisions*, not just aggregates:
  - decision ranking: inside 12 m of goal, shooting must beat carrying the ball on (a dribble
                      into a packed box is not the better option than the shot)
A small grid search then picks the EngineParams whose predictions match best.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field, replace

import numpy as np

from app.models import FrameState, Intervention
from app.rollout.engine import EngineParams, RolloutEngine
from app.rollout.scenarios import final_third_attack
from app.source.grf import STEP_S, GrfMatch

RATE_WINDOW_S = 15.0
# ball-carrier spots within 12 m of goal in the scenario state (attacking right, goal at x=105)
RANKING_SPOTS: tuple[tuple[float, float], ...] = ((99.0, 34.0), (96.0, 34.0), (94.0, 34.0), (95.0, 28.0), (95.0, 40.0), (93.5, 34.0))


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


def grf_action_rates(matches: list[GrfMatch]) -> dict[str, float]:
    """Passes, tackles and shots per 15 s of open play, and pass completion, from derived events."""
    from app.source.events import derive_events  # local import: events depends on stats, keep this module light

    in_play_s = 0.0
    passes = completed = tackles = shots = 0
    for m in matches:
        in_play_s += float((m.game_mode == 0).sum()) * STEP_S
        for e in derive_events(m):
            passes += e.type == "pass"
            completed += e.type == "pass" and e.outcome == "complete"
            tackles += e.type == "tackle"
            shots += e.type == "shot"
    return _rates(in_play_s, passes, completed, tackles, shots)


def _rates(seconds: float, passes: float, completed: float, tackles: float, shots: float) -> dict[str, float]:
    per = RATE_WINDOW_S / max(seconds, 1e-9)
    return {
        "passes": passes * per,
        "pass_completion": completed / passes if passes else 0.0,
        "tackles": tackles * per,
        "shots": shots * per,
    }


def decision_ranking(params: EngineParams, n: int = 2000, seed: int = 1) -> list[tuple[tuple[float, float], float, float]]:
    """(spot, p_goal if he shoots, p_goal if he carries on) for every spot within 12 m of goal."""
    engine = RolloutEngine(params=params)
    out = []
    for xy in RANKING_SPOTS:
        state = final_third_attack("H9", xy)
        p = {
            a: engine.run(state, n=n, seed=seed, n_paths=0, intervention=Intervention(kind="swap_action", params={"action": a})).p_goal_for
            for a in ("shoot", "carry")
        }
        out.append((xy, p["shoot"], p["carry"]))
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
    engine_rates: dict[str, float] = field(default_factory=dict)
    grf_rates: dict[str, float] = field(default_factory=dict)
    ranking: list[tuple[tuple[float, float], float, float]] = field(default_factory=list)

    @property
    def ranking_ok(self) -> bool:
        """Shoot beats carry at every spot within 12 m (vacuously true if not checked)."""
        return all(shoot > carry for _, shoot, carry in self.ranking)

    @property
    def error(self) -> float:
        err = (
            (self.engine_turnover - self.grf_turnover) ** 2
            + (self.engine_turnover_final_third - self.grf_turnover_final_third) ** 2
            + 4 * (self.engine_goal - self.grf_goal) ** 2
        )
        # relative error on action rates, small weight: they shape *how* outcomes come about
        for key, grf in self.grf_rates.items():
            if grf > 0 and key in self.engine_rates:
                err += 0.01 * ((self.engine_rates[key] - grf) / grf) ** 2
        return err + (0.0 if self.ranking_ok else 1.0)


def evaluate(
    params: EngineParams,
    samples: list[Sample],
    n: int = 100,
    horizon_s: float = 15.0,
    grf_rates: dict[str, float] | None = None,
    check_ranking: bool = False,
) -> Fit:
    engine = RolloutEngine(params=params)
    results = []
    totals = dict.fromkeys(("owned_s", "passes", "passes_completed", "tackles", "shots"), 0.0)
    for i, s in enumerate(samples):
        results.append(engine.run(s.state, n=n, horizon_s=horizon_s, seed=i, n_paths=0))
        for k in totals:
            totals[k] += engine.last_counts.get(k, 0.0)
    final = [i for i, s in enumerate(samples) if s.final_third] or list(range(len(samples)))
    return Fit(
        params=params,
        engine_turnover=float(np.mean([r.p_turnover for r in results])),
        grf_turnover=float(np.mean([s.lost for s in samples])),
        engine_goal=float(np.mean([r.p_goal_for for r in results])),
        grf_goal=float(np.mean([s.scored for s in samples])),
        engine_turnover_final_third=float(np.mean([results[i].p_turnover for i in final])),
        grf_turnover_final_third=float(np.mean([samples[i].lost for i in final])),
        engine_rates=_rates(totals["owned_s"], totals["passes"], totals["passes_completed"], totals["tackles"], totals["shots"]),
        grf_rates=grf_rates or {},
        ranking=decision_ranking(params) if check_ranking else [],
    )


def grid_search(
    samples: list[Sample],
    grid: dict[str, list[float]],
    base: EngineParams | None = None,
    n: int = 100,
    grf_rates: dict[str, float] | None = None,
    check_ranking: bool = True,
) -> list[Fit]:
    """All grid points, best first. Points that fail the decision-ranking gate sort last."""
    base = base or EngineParams()
    keys = list(grid)
    fits = [
        evaluate(replace(base, **dict(zip(keys, values))), samples, n=n, grf_rates=grf_rates, check_ranking=check_ranking)
        for values in itertools.product(*grid.values())
    ]
    return sorted(fits, key=lambda f: f.error)


def main(argv: list[str] | None = None) -> None:
    """Evaluate the default EngineParams against recorded matches:

    backend/.venv/bin/python -m app.rollout.calibration spikes/grf/out/matches/grf-{1..6}
    """
    import sys

    from app.source.grf import load_grf_match

    dirs = argv if argv is not None else sys.argv[1:]
    matches = [load_grf_match(d) for d in dirs]
    fit = evaluate(EngineParams(), sample_states(matches, limit=150), grf_rates=grf_action_rates(matches), check_ranking=True)
    print(f"turnover   engine {fit.engine_turnover:.3f}  GRF {fit.grf_turnover:.3f}")
    print(f"  final 3rd engine {fit.engine_turnover_final_third:.3f}  GRF {fit.grf_turnover_final_third:.3f}")
    print(f"goal       engine {fit.engine_goal:.3f}  GRF {fit.grf_goal:.3f}")
    for key, grf in fit.grf_rates.items():
        print(f"{key:15s} engine {fit.engine_rates[key]:.2f}  GRF {grf:.2f}")
    for xy, shoot, carry in fit.ranking:
        print(f"ranking {xy}: shoot {shoot:.3f} vs carry {carry:.3f}")
    print(f"ranking gate {'ok' if fit.ranking_ok else 'FAILED'}, error {fit.error:.4f}")


if __name__ == "__main__":
    main()
