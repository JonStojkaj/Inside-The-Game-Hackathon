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
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.experiments import (
    DecisionContext,
    Experiment,
    ExperimentResult,
    ExperimentRunner,
    decision_context,
    experiment_menu,
)
from app.agents.llm import FakeLLM, LLMClient, llm_from_env
from app.models import Hypothesis, Insight, MatchEvent, Moment, RolloutResult
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
A key moment happened. You get the game context, what really happened (with its simulated outcome),
the QUESTION this kind of moment raises and a MENU of counterfactual experiments our simulator can run.
Pick the 1-3 experiments that best answer the question, each as a short, testable hypothesis.
Only use experiment ids from the menu. Never invent numbers."""

CRITIC_SYSTEM = """You are the Critic in a football broadcast's explanation team.
You get what really happened, the question, and the simulated results of each hypothesis (500 futures x 3 seeds).
Accept a hypothesis only if the input marks it as passing the rules (meaningful, stable across seeds and
football-plausible). Then write the claim viewers will see: 1-2 neutral sentences answering the question,
only about accepted findings, using only the percentages and point changes given in the input (never compute
new numbers). Use player names, never ids. If nothing was accepted, say the real decision was a reasonable one.
Speak to viewers: never mention "the input", "rules", "criteria", hypotheses or experiments."""

QUESTIONS = {
    "goal": "A goal was scored. What made it possible? If what_really_happened is the assist (the pass to the scorer), "
            "show how much better that pass was than the passer's alternatives. Otherwise show what the defending side "
            "could have done to prevent it. Never suggest the scorer should not have shot.",
    "big_chance": "A big chance did not go in. Was taking the shot the right decision, or was there a better option?",
    "decisive_pass": "A pass sharply raised the scoring chance. How much better was it than the alternatives?",
    "dangerous_turnover": "The ball was lost close to the team's own goal. What would have kept it safe? Only an alternative "
                          "with a HIGHER chance to keep the ball answers this; never present the lost pass as the safe option.",
}


# --- rules ----------------------------------------------------------------------------------

# which outcome a moment is judged on: scoring for attacking moments, keeping the ball for turnovers
METRIC = {"goal": "p_goal", "big_chance": "p_goal", "decisive_pass": "p_goal", "dangerous_turnover": "p_keep"}
METRIC_LABEL = {"p_goal": "chance to score", "p_keep": "chance to keep the ball"}


def value(r: ExperimentResult, key: str = "p_goal") -> float:
    return float(getattr(r, key))


def spread(r: ExperimentResult, key: str = "p_goal") -> float:
    return r.seed_spread if key == "p_goal" else r.keep_spread


def passes_rule(base: ExperimentResult, alt: ExperimentResult, key: str = "p_goal") -> bool:
    delta = value(alt, key) - value(base, key)
    noise = 2 * max(spread(alt, key), spread(base, key)) + 0.005
    return abs(delta) >= MIN_EFFECT and abs(delta) > noise


def plausible(alt: ExperimentResult, base: ExperimentResult, expected_sign: int | None, key: str = "p_goal") -> bool:
    """Football prior: e.g. tighter marking must not help the team on the ball. Violations are simulator artifacts."""
    if expected_sign is None:
        return True
    return (value(alt, key) - value(base, key)) * expected_sign > 0


def points(base: ExperimentResult, alt: ExperimentResult, key: str = "p_goal") -> str:
    return f"{abs(value(alt, key) - value(base, key)) * 100:.1f}"


def confidence(base: ExperimentResult, alt: ExperimentResult, key: str = "p_goal") -> Literal["clear", "slight"]:
    lo, hi = sorted([value(base, key), value(alt, key)])
    delta = hi - lo
    return "clear" if delta >= CLEAR_EFFECT or (lo > 0 and hi / lo >= 2) else "slight"


def pct(p: float) -> str:
    return f"{p * 100:.1f}%"


PLAYER_ID = re.compile(r"\b[HA]\d{1,2}\b")  # internal ids must never reach the screen
NUMBER_WORDS = frozenset(
    "two three four five six seven eight nine ten eleven twelve fifteen twenty thirty forty fifty hundred "
    "twice thrice double doubled triple tripled quadruple half halved quarter dozen".split()
)


def integers_in(*texts: str) -> set[str]:
    """Plain integers that appear in texts we generated (minutes, "5 m closer", shirt numbers)."""
    return {n for t in texts for n in re.findall(r"(?<![\d.])\d+(?![\d.])", t)}


def numbers_are_ours(
    claim: str,
    allowed_pct: set[str],
    allowed_points: set[str] | frozenset[str] = frozenset(),
    allowed_plain: set[str] | frozenset[str] = frozenset(),
) -> bool:
    """Every number in the claim must be one we computed (LLMs must not invent or compute numbers).

    Percentages must be one of our probabilities, "N points" / "N percentage points" one of our deltas,
    plain integers one of `allowed_plain` (taken from code-generated texts), any other decimal is
    rejected outright, and so are number words ("three times", "doubled", "half").
    """
    for value, unit in re.findall(r"[+-]?(\d+(?:\.\d+)?)\s*(%|-?\s*(?:percentage[- ])?points?)?", claim):
        if not unit:
            if "." in value or value not in allowed_plain:
                return False
            continue
        if unit.strip() == "%":
            if f"{value}%" not in allowed_pct:
                return False
        elif value not in allowed_points:
            return False
    words = set(re.findall(r"[a-z]+", claim.lower()))
    return not (words & NUMBER_WORDS)


def claimable(base: ExperimentResult, accepted: list[ExperimentResult], key: str = "p_goal") -> list[ExperimentResult]:
    """Accepted findings worth telling viewers.

    For a lost ball only a *safer* alternative is an insight: "passing elsewhere would have been even
    riskier" than a pass that was intercepted reads as if the intercepted pass were the safe choice.
    """
    if key == "p_keep":
        return [r for r in accepted if value(r, key) > value(base, key)]
    return accepted


def headline(base: ExperimentResult, accepted: list[ExperimentResult], key: str = "p_goal") -> ExperimentResult | None:
    """The finding the claim is about: the best better option if there is one, else the clearest worse one."""
    usable = claimable(base, accepted, key)
    better = [r for r in usable if value(r, key) > value(base, key)]
    if better:
        return max(better, key=lambda r: value(r, key))
    return max(usable, key=lambda r: abs(value(r, key) - value(base, key))) if usable else None


def template_claim(ctx: DecisionContext, base: ExperimentResult, accepted: list[ExperimentResult], key: str = "p_goal") -> str:
    label = METRIC_LABEL[key]
    best = headline(base, accepted, key)
    if best is None:
        now = f"{pct(value(base, key))} {label}"
        if key == "p_keep":
            return f"{ctx.actual_label} — none of the tested alternatives would clearly have kept the ball safer ({now})."
        if ctx.moment.kind == "goal" and not ctx.assist:
            return f"{ctx.actual_label} — none of the tested defensive changes would clearly have prevented it ({now})."
        return f"{ctx.actual_label} — a reasonable decision: no tested alternative did clearly better ({now})."
    direction = "risen" if value(best, key) > value(base, key) else "fallen"
    return f"If {best.description}, the {label} would have {direction} from {pct(value(base, key))} to {pct(value(best, key))}."


# --- the team -------------------------------------------------------------------------------

@dataclass
class Episode:
    """The explain team's working state for one moment; the steps below (and the framework workflow's executors)
    read and update it, so both runtimes share every guard."""

    ctx: DecisionContext
    key: str
    menu: dict[str, Experiment]
    base: ExperimentResult
    base_rollout: RolloutResult
    events: list[MatchEvent] = field(default_factory=list)
    results: dict[str, ExperimentResult] = field(default_factory=dict)
    rollouts: dict[str, RolloutResult] = field(default_factory=dict)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    accepted: list[ExperimentResult] = field(default_factory=list)
    tried: set[str] = field(default_factory=set)
    chosen: list[AnalystHypothesis] = field(default_factory=list)
    claim: str = ""
    round_no: int = 0
    probes: dict[str, tuple[ExperimentResult, RolloutResult]] = field(default_factory=dict)  # run by the tool
    path: list[str] = field(default_factory=list)  # agent hand-offs, for logs


class ExplainTeam:
    def __init__(self, llm: LLMClient, runner: ExperimentRunner | None = None, max_rounds: int = 2) -> None:
        self.llm = llm
        self.runner = runner or ExperimentRunner()
        self.max_rounds = max_rounds

    def explain(self, match: GrfMatch, moment: Moment, events: list[MatchEvent]) -> Insight:
        """Hand-written orchestration (AGENT_RUNTIME=sdk). app.agents.workflow runs the same steps as a
        Microsoft Agent Framework workflow."""
        ep = self.start(match, moment, events)
        for _ in range(self.max_rounds):
            if not self.available(ep):
                break
            ep.round_no += 1
            self.choose(ep, self.llm.complete(self.analyst_system(), self.analyst_prompt(ep), AnalystPlan, "analyst"))
            self.experiment(ep)
            if not self.pending(ep):
                break
            self.judge(ep, self.llm.complete(self.critic_system(), self.critic_prompt(ep), CriticReview, "critic"))
            if claimable(ep.base, ep.accepted, ep.key):
                break
        return self.finalize(ep)

    # --- steps --------------------------------------------------------------------------------
    def start(self, match: GrfMatch, moment: Moment, events: list[MatchEvent]) -> Episode:
        ctx = decision_context(match, moment, events)
        base, base_rollout = self.runner.baseline(ctx)
        return Episode(ctx=ctx, key=METRIC[moment.kind], menu={e.id: e for e in experiment_menu(ctx)}, base=base,
                       base_rollout=base_rollout, events=events)

    @staticmethod
    def available(ep: Episode) -> dict[str, Experiment]:
        """The menu minus what was already tried: the only experiments the Analyst may pick (or run)."""
        return {k: v for k, v in ep.menu.items() if k not in ep.tried}

    def analyst_system(self) -> str:
        return ANALYST_SYSTEM

    def critic_system(self) -> str:
        return CRITIC_SYSTEM

    def analyst_prompt(self, ep: Episode) -> str:
        return self._analyst_prompt(ep.ctx, ep.base, self.available(ep), ep.hypotheses, ep.key)

    def choose(self, ep: Episode, plan: AnalystPlan) -> None:
        """Menu restriction: ids not on the (remaining) menu are dropped, duplicates collapsed, at most 3."""
        available = self.available(ep)
        ep.chosen = list({h.experiment_id: h for h in plan.hypotheses if h.experiment_id in available}.values())[:3]

    def run_experiment(self, ep: Episode, exp_id: str) -> tuple[ExperimentResult, RolloutResult]:
        """The Experimenter: the rollout engine, never an LLM. Results the Analyst already probed are reused."""
        if exp_id not in ep.probes:
            exp = ep.menu[exp_id]
            ep.probes[exp_id] = self.runner.run(ep.ctx, exp.id, exp.description, exp.intervention)
        return ep.probes[exp_id]

    def experiment(self, ep: Episode) -> None:
        key, base = ep.key, ep.base
        for h in ep.chosen:
            exp = ep.menu[h.experiment_id]
            ep.tried.add(exp.id)
            ep.results[exp.id], ep.rollouts[exp.id] = self.run_experiment(ep, exp.id)
            # the control room shows this text: it may only use the baseline it was shown
            text = h.text if self._clean(h.text, {pct(value(base, key))}, set(), ep.ctx, exp.description) else f"If {exp.description}."
            ep.hypotheses.append(Hypothesis(text=text, intervention=exp.intervention, metric=key,
                                            baseline_p_goal=value(base, key),
                                            counterfactual_p_goal=value(ep.results[exp.id], key),
                                            seed_spread=spread(ep.results[exp.id], key)))

    @staticmethod
    def pending(ep: Episode) -> list[Hypothesis]:
        return [h for h in ep.hypotheses if h.verdict == "pending"]

    def critic_prompt(self, ep: Episode) -> str:
        return self._critic_prompt(ep.ctx, ep.base, ep.results, ep.chosen, ep.menu, ep.key)

    def judge(self, ep: Episode, review: CriticReview) -> None:
        """The Critic proposes, the rules decide: an 'accepted' verdict on an unstable or implausible effect is overruled."""
        key, base, menu, results = ep.key, ep.base, ep.menu, ep.results
        verdicts = {v.experiment_id: v for v in review.verdicts}
        for hyp, exp_id in zip(self.pending(ep), [c.experiment_id for c in ep.chosen if c.experiment_id in results]):
            r = results[exp_id]
            v = verdicts.get(exp_id)
            stable = passes_rule(base, r, key)
            sane = plausible(r, base, menu[exp_id].expected_sign, key)
            note = v.note if v else "no verdict"
            if not self._clean(note, {pct(value(base, key)), pct(value(r, key))}, {points(base, r, key)}, ep.ctx, r.description):
                note = "(critic note withheld: it used numbers the simulator did not produce)"
            if v and v.verdict == "accepted" and stable and sane:
                hyp.verdict, hyp.critic_note = "accepted", note
            elif v and v.verdict == "accepted":
                why = "effect not stable across seeds" if not stable else "football-implausible direction (simulator artifact)"
                hyp.verdict, hyp.critic_note = "rejected", f"overruled by rule: {why}. ({note})"
            else:
                hyp.verdict, hyp.critic_note = "rejected", note
            if hyp.verdict == "accepted":
                ep.accepted.append(r)
        ep.claim = review.claim

    def wants_retry(self, ep: Episode) -> bool:
        """Critic gate: another Analyst round only if nothing claimable survived and rounds/menu are left."""
        return ep.round_no < self.max_rounds and not claimable(ep.base, ep.accepted, ep.key) and bool(self.available(ep))

    def finalize(self, ep: Episode) -> Insight:
        ctx, key, base, accepted, moment = ep.ctx, ep.key, ep.base, ep.accepted, ep.ctx.moment
        claim = ep.claim
        # only the baseline and ACCEPTED (claimable) findings may be stated as fact; plain integers must
        # come from texts we generated (decision label, accepted experiment descriptions, the minute)
        usable = claimable(base, accepted, key)
        minute = str(int(moment.clock_s // 60))
        allowed = {pct(value(base, key))} | {pct(value(r, key)) for r in usable}
        allowed_points = {points(base, r, key) for r in usable}
        plain = integers_in(ctx.actual_label, minute, *(r.description for r in usable))
        if not claim or not numbers_are_ours(claim, allowed, allowed_points, plain) or PLAYER_ID.search(claim):
            claim = template_claim(ctx, base, accepted, key)

        best = headline(base, accepted, key)
        numbers = {"actual_p_goal": base.p_goal, "actual_p_keep": base.p_keep, f"actual_{key}": value(base, key)}
        if best:
            numbers |= {f"best_alt_{key}": value(best, key), f"delta_{key}": round(value(best, key) - value(base, key), 4)}
        return Insight(
            id=f"{moment.id}-insight",
            moment_id=moment.id,
            claim=claim,
            evidence=[*moment.event_ids, *base.rollout_ids, *(rid for r in accepted for rid in r.rollout_ids)],
            numbers=numbers,
            verified=True,
            confidence=confidence(base, best, key) if best else "clear",
            metric=key,
            hypotheses=ep.hypotheses,
            decision_frame=ctx.frame,
            ghost_paths=ep.base_rollout.sample_paths,
            alt_ghost_paths=ep.rollouts[best.experiment_id].sample_paths if best else [],
            alt_label=best.description if best else "",
        )

    @staticmethod
    def _clean(text: str, allowed_pct: set[str], allowed_points: set[str], ctx: DecisionContext, description: str) -> bool:
        """LLM text shown anywhere (claim, hypothesis, critic note) may only use numbers we produced."""
        plain = integers_in(ctx.actual_label, description, str(int(ctx.moment.clock_s // 60)))
        return numbers_are_ours(text, allowed_pct, allowed_points, plain) and not PLAYER_ID.search(text)

    # --- prompts (JSON so both the model and the fake can read them) -------------------------
    def _analyst_prompt(self, ctx: DecisionContext, base: ExperimentResult, menu: dict, previous: list[Hypothesis], key: str) -> str:
        return json.dumps({
            "moment": {"kind": ctx.moment.kind, "minute": int(ctx.moment.clock_s // 60), "team": ctx.moment.team,
                       "reason": ctx.moment.reason},
            "QUESTION": QUESTIONS[ctx.moment.kind],
            "judged_on": METRIC_LABEL[key],
            "what_really_happened": {"decision": ctx.actual_label, METRIC_LABEL[key]: pct(value(base, key))},
            "already_rejected": [h.text for h in previous if h.verdict == "rejected"],
            "MENU": [{"id": e.id, "experiment": "if " + e.description} for e in menu.values()],
        }, indent=1)

    def _critic_prompt(self, ctx: DecisionContext, base: ExperimentResult, results: dict, chosen: list[AnalystHypothesis],
                       menu: dict, key: str) -> str:
        label = METRIC_LABEL[key]

        def rules(exp_id: str) -> bool:
            r = results[exp_id]
            return passes_rule(base, r, key) and plausible(r, base, menu[exp_id].expected_sign, key)

        return json.dumps({
            "QUESTION": QUESTIONS[ctx.moment.kind],
            "judged_on": label,
            "what_really_happened": {"decision": ctx.actual_label, label: pct(value(base, key))},
            "hypotheses": [{
                "experiment_id": h.experiment_id, "hypothesis": h.text,
                "experiment": "if " + results[h.experiment_id].description,
                label: pct(value(results[h.experiment_id], key)),
                "change_vs_actual": f"{'+' if value(results[h.experiment_id], key) >= value(base, key) else '-'}"
                                    f"{points(base, results[h.experiment_id], key)} points",
                "passes_rules": rules(h.experiment_id),
            } for h in chosen if h.experiment_id in results],
        }, indent=1)


def explain_team_from_env(fake: FakeLLM | None = None, runner: ExperimentRunner | None = None) -> ExplainTeam:
    """AGENT_RUNTIME=framework: agents + workflow on the Microsoft Agent Framework; sdk: the loop above."""
    llm = llm_from_env(fake if fake is not None else fake_explain_llm())
    if type(llm).__name__ == "FrameworkLLM":
        from app.agents.framework import FrameworkLLM
        from app.agents.workflow import FrameworkExplainTeam

        assert isinstance(llm, FrameworkLLM)
        return FrameworkExplainTeam(llm, runner)
    return ExplainTeam(llm, runner)


def fake_explain_llm() -> FakeLLM:
    """Deterministic stand-in for tests and offline demos: picks the first two menu items, follows the rule."""

    def analyst(prompt: str) -> AnalystPlan:
        menu = json.loads(prompt)["MENU"]
        return AnalystPlan(hypotheses=[AnalystHypothesis(experiment_id=m["id"], text=f"{m['experiment']} would have changed the outcome")
                                       for m in menu[:2]])

    def critic(prompt: str) -> CriticReview:
        data = json.loads(prompt)
        verdicts = [CriticVerdict(experiment_id=h["experiment_id"],
                                  verdict="accepted" if h["passes_rules"] else "rejected",
                                  note="stable, plausible effect" if h["passes_rules"] else "within noise or implausible")
                    for h in data["hypotheses"]]
        return CriticReview(verdicts=verdicts, claim="")  # empty claim -> template from code

    return FakeLLM({"analyst": analyst, "critic": critic})
