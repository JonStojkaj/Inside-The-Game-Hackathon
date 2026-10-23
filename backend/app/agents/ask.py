"""Ask Sliding Doors: a fan's free-text "What if ...?" answered live by the explain team.

  pick_moment   the key moment nearest the paused frame (or the next pass/shot of the ball carrier)
  Analyst       maps the fan's question onto the experiment MENU (never invents one; nothing fits -> says so)
  Experimenter  the rollout engine, as in the offline pipeline
  Critic        answers the fan's question; the rules and numbers_are_ours still have the last word
  translator    optional: the verified English claim in German/Spanish, accepted only if its numbers are identical

Same team, same guards as the offline pipeline (AskTeam subclasses ExplainTeam / FrameworkExplainTeam and only
adds the question to the prompts and progress callbacks). Nothing here talks to the network unless the LLM does.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agents.experiments import (
    HORIZON_S,
    DecisionContext,
    Experiment,
    ExperimentResult,
    ExperimentRunner,
    decision_context,
    experiment_menu,
)
from app.agents.explain import (
    CRITIC_SYSTEM,
    METRIC_LABEL,
    PLAYER_ID,
    AnalystPlan,
    CriticReview,
    Episode,
    ExplainTeam,
    claimable,
    fake_explain_llm,
    pct,
    template_claim,
    value,
)
from app.agents.llm import FakeLLM, LLMClient
from app.models import Insight, MatchEvent, Moment, RolloutResult
from app.source.grf import GrfMatch

MOMENT_WINDOW = 120  # frames (12 s): a key moment this close to the paused frame is "the moment"
CARRIER_BEFORE, CARRIER_AFTER = 50, 100  # frames to look for the ball carrier's own pass/shot otherwise
LANGS = ("en", "de", "es")

ASK_ANALYST_SYSTEM = """You are the Analyst in a football broadcast's explanation team.
A fan watching the match paused at a moment and asked FAN_QUESTION (in English, German or Spanish; players may be
named by first or last name). You get the game context, what really happened (with its simulated outcome) and a
MENU of counterfactual experiments our simulator can run for this moment.
Pick the 1-3 MENU experiments that test exactly what the fan asks (e.g. "what if he had shot" -> the shoot
experiment; "what if the defender had been closer" -> the matching 'stood ... closer' experiments).
If no MENU experiment tests the fan's question, return an EMPTY list of hypotheses: never pick unrelated
experiments and never invent new ones. Only use experiment ids from the menu. Never invent numbers."""

ASK_CRITIC_EXTRA = """
A fan asked FAN_QUESTION. Your claim answers it directly in 1-2 sentences (start with the answer, then why)."""

TRANSLATOR_SYSTEM = """Translate a football broadcast caption into the target language (de = German, es = Spanish).
Keep every number exactly as written (you may write a decimal comma), keep player names, add nothing."""


class Translation(BaseModel):
    text: str = Field(description="the caption in the target language")


Step = dict[str, Any]
OnStep = Callable[[Step], None]


# --- the moment ------------------------------------------------------------------------------------------

def _moment_for_event(match: GrfMatch, e: MatchEvent) -> Moment:
    kind = ("goal" if e.outcome == "goal" else "big_chance") if e.type == "shot" else "decisive_pass"
    return Moment(id=f"{match.match_id}-ask{e.frame:05d}-{kind}", match_id=match.match_id, frame=e.frame, t_ms=e.t_ms,
                  clock_s=round(match.clock_s(e.frame), 1), kind=kind, score=0.0, team=e.team or "home",  # type: ignore[arg-type]
                  player_ids=[p for p in (e.player_id, e.target_id) if p], event_ids=[e.id],
                  reason=f"{e.type} picked by a viewer question")


def pick_moment(match: GrfMatch, events: list[MatchEvent], moments: list[Moment], frame: int,
                moment_id: str | None = None) -> Moment | None:
    """The moment a question at `frame` is about: an explicit key moment, else the nearest key moment within
    MOMENT_WINDOW, else the nearest own pass/shot of a player around the frame (an ad-hoc moment)."""
    if moment_id:
        return next((m for m in moments if m.id == moment_id), None)
    near = [m for m in moments if abs(m.frame - frame) <= MOMENT_WINDOW]
    if near:
        return min(near, key=lambda m: (abs(m.frame - frame), -m.frame))
    actions = [e for e in events if e.type in ("shot", "pass") and e.team and e.player_id
               and (e.type == "shot" or e.outcome == "complete") and -CARRIER_BEFORE <= e.frame - frame <= CARRIER_AFTER]
    if not actions:
        return None
    # prefer what the player on the ball does next (the decision the fan is looking at), then the latest before
    return _moment_for_event(match, min(actions, key=lambda e: (e.frame < frame, abs(e.frame - frame))))


def suggestion(exp: Experiment, ctx: DecisionContext) -> dict[str, Any]:
    """A menu item as structured data the frontend can phrase in the viewer's language."""
    names = {p.id: p.name for p in ctx.state.players}
    player = names.get(ctx.decider, ctx.decider)
    iv = exp.intervention
    out: dict[str, Any] = {"experiment_id": exp.id, "player": player, "question": f"What if {exp.description}?"}
    if iv.kind == "move_player":
        m = re.search(r"(\d+) m closer", exp.description)
        out |= {"kind": "tight", "defender": names.get(iv.params["player_id"], ""), "meters": int(m.group(1)) if m else 5}
    elif iv.params.get("action") == "pass":
        out |= {"kind": "pass", "target": names.get(iv.params.get("target_id", ""), "")}
    else:
        out |= {"kind": str(iv.params.get("action", "carry"))}
    return out


def suggestions(ctx: DecisionContext, limit: int = 3) -> list[dict[str, Any]]:
    """2-3 questions from this moment's menu: one per kind (shoot, pass, defender, carry) first."""
    items = [suggestion(e, ctx) for e in experiment_menu(ctx)]
    picked: list[dict[str, Any]] = []
    for kind in ("shoot", "pass", "tight", "carry"):
        picked += [s for s in items if s["kind"] == kind][:1]
    picked += [s for s in items if s not in picked]
    return picked[:limit]


def moment_info(ctx: DecisionContext) -> dict[str, Any]:
    m = ctx.moment
    return {"id": m.id, "kind": m.kind, "frame": m.frame, "decision_frame": ctx.frame, "minute": int(m.clock_s // 60),
            "team": m.team, "label": ctx.actual_label, "key_moment": "-ask" not in m.id}


# --- the team --------------------------------------------------------------------------------------------

class AskMixin:
    """Adds the fan's question to the Analyst and Critic prompts and reports every step through `on_step`."""

    question: str = ""
    on_step: OnStep | None = None
    unmatched: bool = False
    started: float = 0.0

    def emit(self, code: str, text: str, **params: Any) -> None:
        if self.on_step is not None:
            self.on_step({"code": code, "text": text, "t_ms": int((time.perf_counter() - self.started) * 1000), **params})

    def start(self, match: GrfMatch, moment: Moment, events: list[MatchEvent]) -> Episode:
        self.emit("baseline", "Replaying what really happened 1,500 times…", n=1500)
        ep: Episode = super().start(match, moment, events)  # type: ignore[misc]
        self.emit("baseline_done", f"What really happened: {pct(value(ep.base, ep.key))} {METRIC_LABEL[ep.key]}",
                  value=pct(value(ep.base, ep.key)), metric=ep.key)
        return ep

    def analyst_system(self) -> str:
        return ASK_ANALYST_SYSTEM

    def critic_system(self) -> str:
        return CRITIC_SYSTEM + ASK_CRITIC_EXTRA

    def analyst_prompt(self, ep: Episode) -> str:
        self.emit("analyst", "Analyst is forming a hypothesis…")
        data = json.loads(super().analyst_prompt(ep))  # type: ignore[misc]
        return json.dumps({"FAN_QUESTION": self.question, **data}, indent=1, ensure_ascii=False)

    def choose(self, ep: Episode, plan: AnalystPlan) -> None:
        super().choose(ep, plan)  # type: ignore[misc]   # the menu restriction
        if not ep.chosen:
            self.unmatched = True
            self.emit("no_match", "None of our experiments tests that question for this moment.")
        else:
            items = [ep.menu[h.experiment_id].description for h in ep.chosen]
            self.emit("hypotheses", f"Analyst will test: {'; '.join('if ' + i for i in items)}", items=items)

    def run_experiment(self, ep: Episode, exp_id: str) -> tuple[ExperimentResult, RolloutResult]:
        fresh = exp_id not in ep.probes
        desc = ep.menu[exp_id].description
        if fresh:
            self.emit("simulating", f"Running 1,500 simulations: if {desc}…", experiment=desc, n=1500)
        r, rollout = super().run_experiment(ep, exp_id)  # type: ignore[misc]
        if fresh:
            self.emit("simulated", f"If {desc}: {pct(value(r, ep.key))}", experiment=desc, value=pct(value(r, ep.key)))
        return r, rollout

    def critic_prompt(self, ep: Episode) -> str:
        self.emit("critic", "Critic is checking the evidence…")
        data = json.loads(super().critic_prompt(ep))  # type: ignore[misc]
        return json.dumps({"FAN_QUESTION": self.question, **data}, indent=1, ensure_ascii=False)

    def judge(self, ep: Episode, review: CriticReview) -> None:
        super().judge(ep, review)  # type: ignore[misc]
        judged = [h for h in ep.hypotheses if h.verdict != "pending"]
        accepted = sum(h.verdict == "accepted" for h in judged)
        self.emit("verdicts", f"Critic: {accepted} confirmed, {len(judged) - accepted} rejected", accepted=accepted,
                  rejected=len(judged) - accepted)

    def finalize(self, ep: Episode) -> Insight:
        self.emit("finalize", "Checking every number against the simulator…")
        insight: Insight = super().finalize(ep)  # type: ignore[misc]
        tested = [ep.results[h.experiment_id] for h in ep.chosen if h.experiment_id in ep.results]
        if tested and not claimable(ep.base, ep.accepted, ep.key) and insight.claim == template_claim(ep.ctx, ep.base, ep.accepted, ep.key):
            insight.claim = no_clear_difference(ep, tested[0])
        return insight


def no_clear_difference(ep: Episode, r: ExperimentResult) -> str:
    """The fan's alternative was tested but did not clearly change anything: say so with our numbers."""
    label = METRIC_LABEL[ep.key]
    return (f"If {r.description}, the {label} would have been {pct(value(r, ep.key))} instead of {pct(value(ep.base, ep.key))}: "
            f"no clear difference, so {ep.ctx.actual_label} was a reasonable choice.")


class AskTeam(AskMixin, ExplainTeam):
    """AGENT_RUNTIME=sdk"""


def ask_team(llm: LLMClient, runner: ExperimentRunner | None, question: str, on_step: OnStep | None) -> ExplainTeam:
    """One team per question (cheap); the LLM runtime and the runner are shared. One Analyst round: the fan asked
    one thing, a retry would test something they did not ask."""
    team: ExplainTeam
    if type(llm).__name__ == "FrameworkLLM":
        from app.agents.framework import FrameworkLLM
        from app.agents.workflow import FrameworkExplainTeam

        class AskFrameworkTeam(AskMixin, FrameworkExplainTeam):
            pass

        assert isinstance(llm, FrameworkLLM)
        team = AskFrameworkTeam(llm, runner, max_rounds=1)
    else:
        team = AskTeam(llm, runner, max_rounds=1)
    team.question, team.on_step, team.started = question, on_step, time.perf_counter()  # type: ignore[attr-defined]
    return team


# --- translation -----------------------------------------------------------------------------------------

def _numbers(text: str) -> list[str]:
    return sorted(re.findall(r"\d+(?:\.\d+)?", re.sub(r"(\d),(\d)", r"\1.\2", text)))


def translate(llm: LLMClient, claim: str, lang: str) -> str | None:
    """The verified claim in `lang`, or None if the translation changed, added or dropped a number."""
    if lang == "en":
        return claim
    try:
        out = llm.complete(TRANSLATOR_SYSTEM, json.dumps({"lang": lang, "text": claim}, ensure_ascii=False), Translation, "translator")
    except Exception:  # noqa: BLE001 - the English claim is still a correct answer
        return None
    text = out.text.strip()
    if not text or _numbers(text) != _numbers(claim) or PLAYER_ID.search(text):
        return None
    return text


# --- one question ----------------------------------------------------------------------------------------

@dataclass
class SimMatch:
    """Everything the simulator needs for one match, derived by code from raw.jsonl."""

    match: GrfMatch
    events: list[MatchEvent]
    moments: list[Moment]


def load_sim_match(raw_dir: Path) -> SimMatch:
    from app.source.events import derive_events
    from app.source.grf import load_grf_match
    from app.stats.moments import detect_moments

    match = load_grf_match(raw_dir)
    events = derive_events(match)
    return SimMatch(match, events, detect_moments(events, match.clock_s))


def answer(sim: SimMatch, moment: Moment, question: str, lang: str, llm: LLMClient, runner: ExperimentRunner | None = None,
           on_step: OnStep | None = None) -> dict[str, Any]:
    """Run the explain team on `moment` for the fan's question; returns the API result (without steps)."""
    started = time.perf_counter()
    team = ask_team(llm, runner, question, on_step)
    ctx = decision_context(sim.match, moment, sim.events)
    insight = team.explain(sim.match, moment, sim.events)
    runner_ = team.runner
    insight.numbers |= {"n_rollouts": float(runner_.n), "n_seeds": float(len(runner_.seeds))}
    explained = time.perf_counter()
    result: dict[str, Any] = {
        "answered": not team.unmatched,  # type: ignore[attr-defined]
        "question": question,
        "moment": moment_info(ctx),
        "metric": insight.metric,
        "numbers": insight.numbers,
        "confidence": insight.confidence,
        "hypotheses": [h.model_dump(mode="json") for h in insight.hypotheses],
        "ghost_paths": insight.ghost_paths,
        "alt_ghost_paths": insight.alt_ghost_paths,
        "alt_label": insight.alt_label,
        "decision_frame": insight.decision_frame,
        "horizon_s": HORIZON_S,
        "runtime": getattr(llm, "name", "?"),
        "workflow": list(getattr(team, "last_path", [])),
    }
    if team.unmatched:  # type: ignore[attr-defined]
        result["reason"] = "no_matching_experiment"
        result["suggestions"] = suggestions(ctx)
        claim = ("We can't test that for this moment. Try: "
                 + " ".join(s["question"] for s in result["suggestions"]))
        result |= {"claim": claim, "claim_en": claim, "claim_lang": "en", "insight": None}
    else:
        claim_lang = lang
        translated = translate(llm, insight.claim, lang)
        if translated is None:
            translated, claim_lang = insight.claim, "en"
        result |= {"claim": translated, "claim_en": insight.claim, "claim_lang": claim_lang,
                   "insight": insight.model_dump(mode="json")}
    done = time.perf_counter()
    result["timings"] = {"explain_ms": int((explained - started) * 1000), "translate_ms": int((done - explained) * 1000),
                         "total_ms": int((done - started) * 1000)}
    if on_step is not None:
        on_step({"code": "done", "text": "Done.", "t_ms": result["timings"]["total_ms"]})
    return result


# --- LLM for the live path -------------------------------------------------------------------------------

def ask_cache_dir() -> Path:
    """Writable in the container (the image is read-only for the app user): a temp dir unless ASK_CACHE_DIR."""
    return Path(os.environ.get("ASK_CACHE_DIR") or Path(tempfile.gettempdir()) / "sliding-doors-llm")


def ask_llm_from_env() -> LLMClient:
    """LLM_PROVIDER, else azure when AZURE_OPENAI_ENDPOINT is set; AGENT_RUNTIME as everywhere; LLM_CACHE into
    ask_cache_dir() (identical questions on the same moment are answered from the cache)."""
    from app.agents.llm import AzureLLM, CachedLLM, agent_runtime

    provider = os.environ.get("LLM_PROVIDER") or ("azure" if os.environ.get("AZURE_OPENAI_ENDPOINT") else "fake")
    mode = os.environ.get("LLM_CACHE", "readwrite")
    fake = fake_ask_llm()
    if agent_runtime() == "framework":
        from app.agents.framework import FrameworkLLM

        return FrameworkLLM(provider=provider, cache_mode=mode, fake=fake, cache_dir=ask_cache_dir())
    inner: LLMClient = AzureLLM() if provider == "azure" else fake
    return inner if mode == "off" else CachedLLM(inner, mode, ask_cache_dir())


KEYWORDS = {
    "shoot": ("shot", "shoot", "schuss", "geschossen", "schießen", "tor geschossen", "disparo", "disparad", "disparar", "tiro", "chut"),
    "carry": ("carr", "dribbl", "run ", "ran ", "dribbel", "gelaufen", "conduc", "regate", "avanz"),
    "pass": ("pass", "gepasst", "abgespielt", "zuspiel", "pase", "pasad", "pasar"),
    "tight": ("defend", "closer", "mark", "verteidig", "näher", "naher", "defens", "cerca", "marca"),
}


def fake_ask_llm() -> FakeLLM:
    """Offline stand-in: keyword match of the fan's question onto the menu (EN/DE/ES); the Critic follows the rules."""
    base = fake_explain_llm()

    def analyst(prompt: str) -> AnalystPlan:
        data = json.loads(prompt)
        q = data.get("FAN_QUESTION", "").lower() + " "
        kinds = [k for k, words in KEYWORDS.items() if any(w in q for w in words)]
        picked = []
        for m in data["MENU"]:
            kind = m["id"].split("_")[0] if m["id"].startswith(("pass_", "tight_")) else m["id"]
            if kind in kinds:
                named = re.findall(r"\b[A-Z][a-zà-ÿ]+", m["experiment"])
                picked.append((sum(w.lower() in q for w in named), m["id"], m["experiment"]))
        picked.sort(key=lambda t: -t[0])  # a named target/defender first
        from app.agents.explain import AnalystHypothesis

        return AnalystPlan(hypotheses=[AnalystHypothesis(experiment_id=i, text=f"{e} would have changed the outcome") for _, i, e in picked[:2]])

    return FakeLLM({**base.handlers, "analyst": analyst, "translator": lambda p: Translation(text=json.loads(p)["text"])})
