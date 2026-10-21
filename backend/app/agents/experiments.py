"""Experiment menu + runner: the tools the explain team uses (Sliding Doors).

For a key moment we rebuild the game state at the decision frame and offer a fixed menu of
counterfactual experiments. The Analyst picks from the menu (it cannot invent physics), the
runner executes them in the rollout engine against the *actual* decision, over several seeds.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel

from app.models import FrameState, Intervention, MatchEvent, Moment, RolloutResult
from app.rollout.engine import RolloutEngine
from app.source.grf import GrfMatch
from app.stats.metrics import threat

SEEDS = (101, 202, 303)
N_ROLLOUTS = 500
HORIZON_S = 15.0


class Experiment(BaseModel):
    id: str
    description: str
    intervention: Intervention


class ExperimentResult(BaseModel):
    experiment_id: str
    description: str
    p_goal: float  # mean over seeds, team in possession scores in this possession
    p_turnover: float
    p_conceded: float
    seed_spread: float  # half-range of p_goal over seeds
    rollout_ids: list[str]


@dataclass
class DecisionContext:
    """The game state right before the decision that the moment is about."""

    moment: Moment
    frame: int
    state: FrameState
    decider: str  # player who had the ball
    actual: Intervention  # what really happened, expressed as an intervention
    actual_label: str


def decision_context(match: GrfMatch, moment: Moment, events: list[MatchEvent]) -> DecisionContext:
    by_id = {e.id: e for e in events}
    trigger = by_id[moment.event_ids[0]]
    if trigger.type == "shot":
        frame, decider = trigger.frame, trigger.player_id
        actual, label = Intervention(kind="swap_action", params={"action": "shoot"}), "shoot"
    elif trigger.type == "pass":
        frame, decider = trigger.frame, trigger.player_id
        actual = Intervention(kind="swap_action", params={"action": "pass", "target_id": trigger.target_id})
        label = f"pass to {trigger.target_id}"
    else:  # turnover: look at the loser's last frame on the ball
        loser = trigger.target_id
        idx = next(i for i, p in enumerate(match.players) if p.id == loser)
        frame = next((f for f in range(trigger.frame, max(trigger.frame - 30, 0), -1) if match.owner_idx[f] == idx), trigger.frame - 1)
        lost_pass = by_id.get(moment.event_ids[1]) if len(moment.event_ids) > 1 else None
        decider = loser
        if lost_pass is not None and lost_pass.meta.get("intended_receiver"):
            frame = lost_pass.frame
            actual = Intervention(kind="swap_action", params={"action": "pass", "target_id": lost_pass.meta["intended_receiver"]})
            label = f"pass to {lost_pass.meta['intended_receiver']} (intercepted)"
        else:
            actual, label = Intervention(kind="swap_action", params={"action": "carry"}), "carry (tackled)"
    state = match.frame_state(frame)
    state.ball.owner_id = decider
    return DecisionContext(moment, frame, state, decider or "", actual, label)


def experiment_menu(ctx: DecisionContext, max_passes: int = 3, max_defenders: int = 3) -> list[Experiment]:
    s = ctx.state
    me = next(p for p in s.players if p.id == ctx.decider)
    attacks_right = me.team == "home"
    mates = [p for p in s.players if p.team == me.team and p.id != me.id and p.role != "gk"]
    rivals = [p for p in s.players if p.team != me.team and p.role != "gk"]
    menu: list[Experiment] = []

    def add(eid: str, text: str, iv: Intervention) -> None:
        if iv != ctx.actual:
            menu.append(Experiment(id=eid, description=text, intervention=iv))

    add("shoot", f"{me.name} shoots instead", Intervention(kind="swap_action", params={"action": "shoot"}))
    add("carry", f"{me.name} carries the ball forward instead", Intervention(kind="swap_action", params={"action": "carry"}))
    for p in sorted(mates, key=lambda p: -threat(p.x, p.y, attacks_right))[:max_passes]:
        add(f"pass_{p.id}", f"{me.name} passes to {p.name} ({p.position}) instead",
            Intervention(kind="swap_action", params={"action": "pass", "target_id": p.id}))
    # defenders closest to the ball: what if they had been 5 m tighter / goal-side?
    for p in sorted(rivals, key=lambda p: np.hypot(p.x - me.x, p.y - me.y))[:max_defenders]:
        dx, dy = me.x - p.x, me.y - p.y
        dist = max(np.hypot(dx, dy), 1e-6)
        step = min(5.0, dist - 1.0)
        if step > 0.5:
            add(f"tight_{p.id}", f"{p.name} ({p.position}, {me.team == 'home' and 'away' or 'home'}) stands {step:.0f} m closer to {me.name}",
                Intervention(kind="move_player", params={"player_id": p.id, "dx": dx / dist * step, "dy": dy / dist * step}))
    return menu


class ExperimentRunner:
    def __init__(self, engine: RolloutEngine | None = None, n: int = N_ROLLOUTS, seeds: tuple[int, ...] = SEEDS) -> None:
        self.engine = engine or RolloutEngine()
        self.n = n
        self.seeds = seeds

    def run(self, ctx: DecisionContext, exp_id: str, description: str, iv: Intervention) -> tuple[ExperimentResult, RolloutResult]:
        results = [self.engine.run(ctx.state, n=self.n, horizon_s=HORIZON_S, seed=s, intervention=iv, n_paths=30) for s in self.seeds]
        goals = [r.p_goal_for for r in results]
        summary = ExperimentResult(
            experiment_id=exp_id,
            description=description,
            p_goal=round(float(np.mean(goals)), 4),
            p_turnover=round(float(np.mean([r.p_turnover for r in results])), 4),
            p_conceded=round(float(np.mean([r.p_goal_against for r in results])), 4),
            seed_spread=round((max(goals) - min(goals)) / 2, 4),
            rollout_ids=[f"rollout:{ctx.moment.id}:{exp_id}:{s}" for s in self.seeds],
        )
        return summary, results[0]

    def baseline(self, ctx: DecisionContext) -> tuple[ExperimentResult, RolloutResult]:
        return self.run(ctx, "actual", f"what really happened: {ctx.actual_label}", ctx.actual)
