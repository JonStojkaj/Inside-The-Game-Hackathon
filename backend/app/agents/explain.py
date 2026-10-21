"""Explain team (stage c): Analyst -> Experimenter -> Critic, with one retry.

  Analyst      (LLM)   picks 1-3 hypotheses, each tied to an experiment from the menu
  Experimenter (tool)  runs every chosen experiment in the rollout engine against what really happened
  Critic       (LLM)   judges each hypothesis and writes the claim; hard rules in code have the last word
                       (effect big enough and stable across seeds, every number in the claim must be ours)

Nothing reaches the screen unless it survived the Critic and the rules.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.experiments import DecisionContext, ExperimentResult, ExperimentRunner, decision_context, experiment_menu
from app.agents.llm import FakeLLM, LLMClient
from app.models import Hypothesis, Insight, MatchEvent, Moment
from app.source.grf import GrfMatch

MIN_EFFECT = 0.015  # absolute change in goal probability worth talking about
CLEAR_EFFECT = 0.04  # ... or a 2x ratio: "clearly" instead of "slightly"


# --- structured outputs ---------------------------------------------------------------------

class AnalystHypothesis(BaseModel):
    experiment_id: str = Field(description="id of one experiment from the menu")
    text: str = Field(description="the hypothesis in one sentence, e.g. 'Shooting would have been the better option'")


class AnalystPlan(BaseModel):
    hypotheses: list[AnalystHypothesis] = Field(description="1 to 3 hypotheses")


class CriticVerdict(BaseModel):
    experiment_id: str
    verdict: Literal["accepted", "rejected"]
    note: str = Field(description="one short sentence why")


class CriticReview(BaseModel):
    verdicts: list[CriticVerdict]
    claim: str = Field(description="1-2 neutral English sentences explaining why the moment mattered, "
                                   "using only accepted findings and only numbers given in the input")


ANALYST_SYSTEM = """You are the Analyst in a football broadcast's explanation team.
A key moment happened. You get the game context, what really happened (with its simulated outcome)
and a MENU of counterfactual experiments our simulator can run. Pick the 1-3 experiments most likely to
explain why this moment mattered, and state each as a short, testable hypothesis.
Only use experiment ids from the menu. Never invent numbers."""

CRITIC_SYSTEM = """You are the Critic in a football broadcast's explanation team.
You get what really happened and the simulated results of each hypothesis (500 futures x 3 seeds each).
Accept a hypothesis only if its effect on the goal probability is meaningful and stable across seeds
(the input marks which effects pass the stability rule). Then write the claim viewers will see:
1-2 neutral sentences, only about accepted findings, using only percentages that appear in the input.
If nothing was accepted, say what really happened was the reasonable choice."""


# --- rules ----------------------------------------------------------------------------------

def passes_rule(base: ExperimentResult, alt: ExperimentResult) -> bool:
    delta = alt.p_goal - base.p_goal
    noise = 2 * max(alt.seed_spread, base.seed_spread) + 0.005
    return abs(delta) >= MIN_EFFECT and abs(delta) > noise


def confidence(base: ExperimentResult, alt: ExperimentResult) -> Literal["clear", "slight"]:
    lo, hi = sorted([base.p_goal, alt.p_goal])
    delta = hi - lo
    return "clear" if delta >= CLEAR_EFFECT or (lo > 0 and hi / lo >= 2) else "slight"


def pct(p: float) -> str:
    return f"{p * 100:.1f}%"


def numbers_are_ours(claim: str, allowed: set[str]) -> bool:
    """Every percentage in the claim must be one we computed (LLMs must not invent numbers)."""
    found = re.findall(r"\d+(?:\.\d+)?\s*%", claim)
    return all(f.replace(" ", "") in allowed for f in found)


def template_claim(ctx: DecisionContext, base: ExperimentResult, accepted: list[ExperimentResult]) -> str:
    if not accepted:
        return f"{ctx.actual_label.capitalize()} was a reasonable choice: no tested alternative did clearly better ({pct(base.p_goal)} chance to score)."
    best = max(accepted, key=lambda r: abs(r.p_goal - base.p_goal))
    direction = "would have raised" if best.p_goal > base.p_goal else "would have lowered"
    return f"{best.description} {direction} the chance to score from {pct(base.p_goal)} to {pct(best.p_goal)}."


# --- the team -------------------------------------------------------------------------------

class ExplainTeam:
    def __init__(self, llm: LLMClient, runner: ExperimentRunner | None = None, max_rounds: int = 2) -> None:
        self.llm = llm
        self.runner = runner or ExperimentRunner()
        self.max_rounds = max_rounds

    def explain(self, match: GrfMatch, moment: Moment, events: list[MatchEvent]) -> Insight:
        ctx = decision_context(match, moment, events)
        menu = {e.id: e for e in experiment_menu(ctx)}
        base, base_rollout = self.runner.baseline(ctx)
        results: dict[str, ExperimentResult] = {}
        rollouts = {}
        hypotheses: list[Hypothesis] = []
        accepted: list[ExperimentResult] = []
        tried: set[str] = set()
        claim = ""

        for round_no in range(self.max_rounds):
            available = {k: v for k, v in menu.items() if k not in tried}
            if not available:
                break
            plan = self.llm.complete(ANALYST_SYSTEM, self._analyst_prompt(ctx, base, available, hypotheses), AnalystPlan, "analyst")
            chosen = [h for h in plan.hypotheses if h.experiment_id in available][:3]
            for h in chosen:
                exp = available[h.experiment_id]
                tried.add(exp.id)
                results[exp.id], rollouts[exp.id] = self.runner.run(ctx, exp.id, exp.description, exp.intervention)
                hypotheses.append(Hypothesis(text=h.text, intervention=exp.intervention, baseline_p_goal=base.p_goal,
                                             counterfactual_p_goal=results[exp.id].p_goal,
                                             seed_spread=results[exp.id].seed_spread))
            pending = [h for h in hypotheses if h.verdict == "pending"]
            if not pending:
                break
            review = self.llm.complete(CRITIC_SYSTEM, self._critic_prompt(ctx, base, results, chosen), CriticReview, "critic")
            verdicts = {v.experiment_id: v for v in review.verdicts}
            for h, exp_id in zip(pending, [c.experiment_id for c in chosen if c.experiment_id in results]):
                r = results[exp_id]
                v = verdicts.get(exp_id)
                rule_ok = passes_rule(base, r)
                if v and v.verdict == "accepted" and rule_ok:
                    h.verdict, h.critic_note = "accepted", v.note
                elif v and v.verdict == "accepted":
                    h.verdict, h.critic_note = "rejected", f"overruled by rule: effect not stable across seeds. ({v.note})"
                else:
                    h.verdict, h.critic_note = "rejected", v.note if v else "no verdict"
                if h.verdict == "accepted":
                    accepted.append(r)
            claim = review.claim
            if accepted:
                break

        allowed = {pct(base.p_goal)} | {pct(r.p_goal) for r in results.values()}
        if not claim or not numbers_are_ours(claim, allowed) or (not accepted and "%" in claim and pct(base.p_goal) not in claim):
            claim = template_claim(ctx, base, accepted)

        best = max(accepted, key=lambda r: abs(r.p_goal - base.p_goal)) if accepted else None
        numbers = {"actual_p_goal": base.p_goal, "actual_p_turnover": base.p_turnover}
        if best:
            numbers |= {"best_alt_p_goal": best.p_goal, "delta_p_goal": round(best.p_goal - base.p_goal, 4)}
        return Insight(
            id=f"{moment.id}-insight",
            moment_id=moment.id,
            claim=claim,
            evidence=[*moment.event_ids, *base.rollout_ids, *(rid for r in accepted for rid in r.rollout_ids)],
            numbers=numbers,
            verified=True,
            confidence=confidence(base, best) if best else "clear",
            hypotheses=hypotheses,
            decision_frame=ctx.frame,
            ghost_paths=base_rollout.sample_paths,
            alt_ghost_paths=rollouts[best.experiment_id].sample_paths if best else [],
            alt_label=best.description if best else "",
        )

    # --- prompts (JSON so both the model and the fake can read them) -------------------------
    def _analyst_prompt(self, ctx: DecisionContext, base: ExperimentResult, menu: dict, previous: list[Hypothesis]) -> str:
        return json.dumps({
            "moment": {"kind": ctx.moment.kind, "minute": int(ctx.moment.clock_s // 60), "team": ctx.moment.team,
                       "reason": ctx.moment.reason},
            "what_really_happened": {"decision": ctx.actual_label, "p_goal": pct(base.p_goal), "p_turnover": pct(base.p_turnover)},
            "already_rejected": [h.text for h in previous if h.verdict == "rejected"],
            "MENU": [{"id": e.id, "experiment": e.description} for e in menu.values()],
        }, indent=1)

    def _critic_prompt(self, ctx: DecisionContext, base: ExperimentResult, results: dict, chosen: list[AnalystHypothesis]) -> str:
        return json.dumps({
            "what_really_happened": {"decision": ctx.actual_label, "p_goal": pct(base.p_goal)},
            "hypotheses": [{
                "experiment_id": h.experiment_id, "hypothesis": h.text,
                "experiment": results[h.experiment_id].description,
                "p_goal": pct(results[h.experiment_id].p_goal),
                "change_vs_actual": f"{(results[h.experiment_id].p_goal - base.p_goal) * 100:+.1f} points",
                "stable_across_seeds": passes_rule(base, results[h.experiment_id]),
            } for h in chosen if h.experiment_id in results],
        }, indent=1)


def fake_explain_llm() -> FakeLLM:
    """Deterministic stand-in for tests and offline demos: picks the first two menu items, follows the rule."""

    def analyst(prompt: str) -> AnalystPlan:
        menu = json.loads(prompt)["MENU"]
        return AnalystPlan(hypotheses=[AnalystHypothesis(experiment_id=m["id"], text=f"{m['experiment']} would have changed the outcome")
                                       for m in menu[:2]])

    def critic(prompt: str) -> CriticReview:
        data = json.loads(prompt)
        verdicts = [CriticVerdict(experiment_id=h["experiment_id"],
                                  verdict="accepted" if h["stable_across_seeds"] else "rejected",
                                  note="stable effect" if h["stable_across_seeds"] else "within noise")
                    for h in data["hypotheses"]]
        return CriticReview(verdicts=verdicts, claim="")  # empty claim -> template from code

    return FakeLLM({"analyst": analyst, "critic": critic})
