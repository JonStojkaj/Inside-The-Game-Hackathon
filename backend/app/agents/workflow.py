"""The explain team as a Microsoft Agent Framework workflow (AGENT_RUNTIME=framework).

    analyst ──> experimenter ──> critic ──(nothing claimable, rounds left)──> analyst     (one retry loop)
       │              │             └──────(done)──────────────────────────> finalize ──> Insight
       └──(menu used up)──> finalize      └──(no hypothesis)──> finalize

  analyst       framework Agent with two function tools: get_match_stats() and run_experiment(experiment_id),
                restricted to the remaining menu and to a probe budget; returns an AnalystPlan (structured)
  experimenter  code: runs every chosen experiment in the rollout engine (reusing what the Analyst probed)
  critic        framework Agent, returns a CriticReview; the rules (passes_rule, plausible) overrule it
  finalize      code: the claim must pass numbers_are_ours / the player-id check, else the template claim

Every step calls the same ExplainTeam methods as the hand-written path, so the guards are shared, not copied.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal

import numpy as np
from agent_framework import Executor, FunctionTool, WorkflowBuilder, WorkflowContext, handler, tool
from pydantic import Field
from typing_extensions import Never

from app.agents.experiments import ExperimentRunner
from app.agents.explain import (
    METRIC_LABEL,
    AnalystPlan,
    CriticReview,
    Episode,
    ExplainTeam,
    passes_rule,
    pct,
    plausible,
    points,
    value,
)
from app.agents.framework import FrameworkLLM, run_sync
from app.models import Insight, MatchEvent, Moment
from app.source.grf import GrfMatch
from app.stats.metrics import pressure_index

PROBE_BUDGET = 4  # run_experiment calls per Analyst round

ANALYST_TOOLS = """
You have two tools. get_match_stats() returns the score, shots, passes and the pressure on the player on
the ball at the decision moment. run_experiment(experiment_id) runs one MENU experiment in our simulator and
returns its result against what really happened (you may run up to 4 per round). Use them to pick the
hypotheses that answer the question best; every hypothesis you return must still use a MENU id."""


def match_stats(ep: Episode) -> dict[str, Any]:
    """Facts computed by code for the get_match_stats tool (events up to the decision frame)."""
    ctx = ep.ctx
    so_far = [e for e in ep.events if e.frame <= ctx.frame]
    stats: dict[str, Any] = {"minute": int(ctx.moment.clock_s // 60), "score": {"home": ctx.state.score[0], "away": ctx.state.score[1]}}
    for team in ("home", "away"):
        passes = [e for e in so_far if e.type == "pass" and e.team == team]
        stats[team] = {
            "shots": sum(1 for e in so_far if e.type == "shot" and e.team == team),
            "passes": len(passes),
            "passes_completed": sum(1 for e in passes if e.outcome == "complete"),
        }
    me = next((p for p in ctx.state.players if p.id == ctx.decider), None)
    if me is not None:
        rivals = np.array([(p.x, p.y) for p in ctx.state.players if p.team != me.team]).reshape(-1, 2)
        stats["player_on_ball"] = {"name": me.name, "position": me.position, "team": me.team,
                                   "pressure_index": round(pressure_index((me.x, me.y), rivals), 2)}
    return stats


def analyst_tools(team: ExplainTeam, ep: Episode) -> list[FunctionTool]:
    """Function tools bound to this moment. The simulator is a tool; the menu restriction lives in the tool."""
    budget = {"left": PROBE_BUDGET}

    def get_match_stats() -> str:
        """Match context at the decision moment: minute, score, shots and passes per team, pressure on the player on the ball."""
        return json.dumps(match_stats(ep))

    def run_experiment(experiment_id: Annotated[str, Field(description="an id from the MENU")]) -> str:
        """Run one counterfactual experiment from the MENU in the simulator (500 futures x 3 seeds)."""
        available = team.available(ep)
        if experiment_id not in available:
            return json.dumps({"error": f"'{experiment_id}' is not on the menu", "menu": sorted(available)})
        if experiment_id not in ep.probes:
            if budget["left"] <= 0:
                return json.dumps({"error": "experiment budget for this round used up; decide now"})
            budget["left"] -= 1
        r, _ = team.run_experiment(ep, experiment_id)
        key, base, label = ep.key, ep.base, METRIC_LABEL[ep.key]
        return json.dumps({
            "experiment_id": experiment_id, "experiment": "if " + r.description,
            label: pct(value(r, key)), "what_really_happened": pct(value(base, key)),
            "change_vs_actual": f"{'+' if value(r, key) >= value(base, key) else '-'}{points(base, r, key)} points",
            "passes_rules": passes_rule(base, r, key) and plausible(r, base, ep.menu[experiment_id].expected_sign, key),
        })

    return [tool(get_match_stats, name="get_match_stats"), tool(run_experiment, name="run_experiment")]


# --- executors ------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Handoff:
    """One explicit agent-to-agent hand-off. The route is fixed when the message is sent: the Episode itself is
    shared, mutable state, so edge conditions must never be evaluated against it."""

    ep: Episode
    to: Literal["analyst", "experimenter", "critic", "finalize"]


class AnalystExecutor(Executor):
    def __init__(self, team: FrameworkExplainTeam) -> None:
        super().__init__(id="analyst")
        self.team = team

    @handler
    async def plan(self, msg: Handoff, ctx: WorkflowContext[Handoff]) -> None:
        ep = msg.ep
        if not self.team.available(ep):  # menu used up
            await ctx.send_message(Handoff(ep, "finalize"))
            return
        ep.round_no += 1
        ep.path.append("analyst")
        plan = await self.team.runtime.arun("analyst", self.team.analyst_system() + ANALYST_TOOLS, self.team.analyst_prompt(ep), AnalystPlan,
                                            tools=analyst_tools(self.team, ep))
        self.team.choose(ep, plan)
        await ctx.send_message(Handoff(ep, "experimenter"))


class ExperimenterExecutor(Executor):
    def __init__(self, team: FrameworkExplainTeam) -> None:
        super().__init__(id="experimenter")
        self.team = team

    @handler
    async def run(self, msg: Handoff, ctx: WorkflowContext[Handoff]) -> None:
        ep = msg.ep
        ep.path.append("experimenter")
        self.team.experiment(ep)
        await ctx.send_message(Handoff(ep, "critic" if self.team.pending(ep) else "finalize"))


class CriticExecutor(Executor):
    def __init__(self, team: FrameworkExplainTeam) -> None:
        super().__init__(id="critic")
        self.team = team

    @handler
    async def review(self, msg: Handoff, ctx: WorkflowContext[Handoff]) -> None:
        ep = msg.ep
        ep.path.append("critic")
        review = await self.team.runtime.arun("critic", self.team.critic_system(), self.team.critic_prompt(ep), CriticReview)
        self.team.judge(ep, review)
        await ctx.send_message(Handoff(ep, "analyst" if self.team.wants_retry(ep) else "finalize"))


class FinalizeExecutor(Executor):
    def __init__(self, team: FrameworkExplainTeam) -> None:
        super().__init__(id="finalize")
        self.team = team

    @handler
    async def finish(self, msg: Handoff, ctx: WorkflowContext[Never, Insight]) -> None:
        msg.ep.path.append("finalize")
        await ctx.yield_output(self.team.finalize(msg.ep))


def _to(target: str) -> Callable[[Any], bool]:
    return lambda msg: isinstance(msg, Handoff) and msg.to == target


# --- the team -------------------------------------------------------------------------------------------

class FrameworkExplainTeam(ExplainTeam):
    """ExplainTeam whose orchestration is an Agent Framework workflow and whose agents are framework Agents."""

    def __init__(self, runtime: FrameworkLLM, runner: ExperimentRunner | None = None, max_rounds: int = 2) -> None:
        super().__init__(runtime, runner, max_rounds)
        self.runtime = runtime
        self.last_path: list[str] = []

    def build_workflow(self) -> Any:
        analyst, experimenter, critic, finalize = (AnalystExecutor(self), ExperimenterExecutor(self), CriticExecutor(self),
                                                   FinalizeExecutor(self))
        return (
            WorkflowBuilder(start_executor=analyst, name="explain-team",
                            description="Analyst -> Experimenter -> Critic with one retry; rules and claim checks in code")
            .add_edge(analyst, experimenter, condition=_to("experimenter"))
            .add_edge(analyst, finalize, condition=_to("finalize"))
            .add_edge(experimenter, critic, condition=_to("critic"))
            .add_edge(experimenter, finalize, condition=_to("finalize"))
            .add_edge(critic, analyst, condition=_to("analyst"))  # the Critic gate's retry loop
            .add_edge(critic, finalize, condition=_to("finalize"))
            .build()
        )

    async def aexplain(self, match: GrfMatch, moment: Moment, events: list[MatchEvent]) -> Insight:
        ep = self.start(match, moment, events)
        result = await self.build_workflow().run(Handoff(ep, "analyst"))
        self.last_path = list(ep.path)
        outputs = [o for o in result.get_outputs() if isinstance(o, Insight)]
        if len(outputs) != 1:
            raise RuntimeError(f"explain workflow produced {len(outputs)} insights (path: {ep.path})")
        return outputs[0]

    def explain(self, match: GrfMatch, moment: Moment, events: list[MatchEvent]) -> Insight:
        return run_sync(self.aexplain(match, moment, events))
