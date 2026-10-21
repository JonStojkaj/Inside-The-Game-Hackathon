"""Production team (stage e): runs once per *segment*, never per viewer.

  Producer  (LLM + rules)  decides whether a verified insight goes on air for a segment, how important
                           it is and the angle to take. Rules decide relevance first (no LLM call for
                           irrelevant moments) and clamp the LLM's priority to a band around the rule's.
  Narrator  (LLM)          writes headline + body in the segment's language, tone and perspective. It may
                           only use the Insight's verified claim and the numbers we hand it: every number
                           in its text must be one of ours, else the localised template is used instead.
  Recap     (LLM)          full-time summary per segment, same number rule, template fallback.

Numbers never come from an LLM; the templates in app.personalization.i18n are the safety net.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.llm import FakeLLM, LLMClient
from app.models import Hypothesis, Insight, Moment
from app.overlay.cues import MatchContext
from app.personalization.i18n import minute, num, pct, surname, t
from app.personalization.segments import Segment, insight_priority, moment_relevance, side

PRIORITY_BAND = 15
HEADLINE_MAX = 70
BODY_MAX = {"light": 160, "medium": 240, "deep": 320}
RECAP_BODY_MAX = 600
RECAP_BULLET_MAX = 140

# --- number validation --------------------------------------------------------------------------

_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def numbers_in(text: str) -> list[str]:
    """All numbers in a text, normalised ("14,8" -> "14.8", "15.0" -> "15")."""
    out = []
    for raw in _NUM.findall(text):
        value = raw.replace(",", ".")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        out.append(value)
    return out


def allowed_numbers(facts: Iterable[Any]) -> set[str]:
    """Numbers a writer may use: every number in our facts, plus its whole-number rounding."""
    allowed: set[str] = set()
    for fact in facts:
        for value in numbers_in(str(fact)):
            allowed.add(value)
            allowed.add(str(math.floor(float(value) + 0.5)))
    return allowed


def numbers_are_ours(text: str, allowed: set[str]) -> bool:
    return all(n in allowed for n in numbers_in(text))


# --- structured outputs -------------------------------------------------------------------------

class ProducerDecision(BaseModel):
    show: bool = Field(description="put this insight on air for this segment?")
    priority: int = Field(description="0-100, how prominent; stay near base_priority")
    angle: str = Field(description="one short English line: what this audience should take away")


class NarratorDraft(BaseModel):
    headline: str = Field(description="max ~50 characters, in the target language")
    body: str = Field(description="1-2 sentences in the target language, only numbers from FACTS")


class RecapDraft(BaseModel):
    headline: str
    body: str = Field(description="3-5 sentences in the target language, only numbers from FACTS")
    bullets: list[str] = Field(description="2-4 short lines, only numbers from FACTS")


class Narrated(BaseModel):
    headline: str
    body: str
    source: Literal["llm", "template"]
    note: str = ""  # why the template was used


class Recap(BaseModel):
    headline: str
    body: str
    bullets: list[str]
    source: Literal["llm", "template"]
    note: str = ""


PRODUCER_SYSTEM = """You are the Producer of a personalised football broadcast. One viewer segment
(mode, club, followed player, language) at a time, you decide whether a VERIFIED insight about a key
moment goes on air for that segment, how prominent it is (priority 0-100, stay within the allowed
range) and the angle: one short English line on what this audience should take away.
Analysts want tactics and numbers, club fans want their team's story, player-focus fans want their
player's decisions, casual viewers want only the big moments. Never invent facts."""

NARRATOR_SYSTEM = """You are the Narrator of a personalised football broadcast graphic.
Write a headline and a short body in the TARGET LANGUAGE, in the segment's tone and perspective,
from the verified claim and the plain template. Rules:
- Only use numbers that appear in FACTS, written exactly as given there (localised). No other numbers,
  no ratios or sums you computed yourself, no spelled-out numbers.
- Only state what the verified claim says; you may rephrase, shorten and add emotion, not new facts.
- Perspective 'partisan': first person plural for the viewer's club. 'player': from the followed
  player's side. 'neutral': no side.
- Respect the length limits."""

RECAP_SYSTEM = """You are the full-time Recap writer of a personalised football broadcast.
Write a headline, a 3-5 sentence body and 2-4 bullets in the TARGET LANGUAGE for one viewer segment,
in its tone and perspective, using only the facts and verified insights given. Only use numbers that
appear in FACTS, written exactly as given. No other numbers, no spelled-out numbers, nothing invented."""


# --- facts + templates for one insight ----------------------------------------------------------

def best_hypothesis(insight: Insight) -> Hypothesis | None:
    best = insight.numbers.get("best_alt_p_goal")
    accepted = [h for h in insight.hypotheses if h.verdict == "accepted" and h.counterfactual_p_goal is not None]
    if best is None or not accepted:
        return None
    return min(accepted, key=lambda h: abs((h.counterfactual_p_goal or 0.0) - best))


def alternative_phrase(h: Hypothesis | None, ctx: MatchContext, lang: str) -> tuple[str, dict[str, str]]:
    """The best alternative in the target language (code-made, so DE/ES never see English labels)."""
    if h is None or h.intervention is None:
        return "", {}
    iv = h.intervention
    if iv.kind == "swap_action" and iv.params.get("action") == "pass":
        return t("alt.pass", lang, target=surname(ctx.name(iv.params.get("target_id")))), {}
    if iv.kind == "swap_action":
        return t(f"alt.{iv.params.get('action', 'carry')}", lang), {}
    if iv.kind == "move_player":
        metres = str(round(math.hypot(iv.params.get("dx", 0.0), iv.params.get("dy", 0.0))))
        return t("alt.move", lang, player=surname(ctx.name(iv.params.get("player_id"))), metres=metres), {"metres": metres}
    return "", {}


def insight_facts(segment: Segment, moment: Moment, insight: Insight, ctx: MatchContext) -> dict[str, str]:
    lang = segment.language
    n = insight.numbers
    facts = {"minute": str(minute(moment.clock_s)), "actual_chance_to_score": pct(n["actual_p_goal"], lang)}
    if "best_alt_p_goal" in n:
        lo, hi = sorted([n["actual_p_goal"], n["best_alt_p_goal"]])
        facts["best_alternative_chance_to_score"] = pct(n["best_alt_p_goal"], lang)
        facts["difference_in_points"] = num(abs(n["best_alt_p_goal"] - n["actual_p_goal"]) * 100, lang)
        if lo > 0:
            facts["times_better"] = num(hi / lo, lang)
    facts.update(alternative_phrase(best_hypothesis(insight), ctx, lang)[1])
    return facts


def insight_template(segment: Segment, moment: Moment, insight: Insight, ctx: MatchContext) -> tuple[str, str]:
    lang = segment.language
    facts = insight_facts(segment, moment, insight, ctx)
    m = facts["minute"]
    s = side(segment, moment.team)
    if segment.perspective == "player" and segment.player:
        headline = t("sd.h.player", lang, player=surname(ctx.name(segment.player)), minute=m)
    elif segment.perspective == "partisan" and s != "neutral":
        headline = t(f"sd.h.{s}", lang, minute=m)
    else:
        headline = t("sd.h.neutral", lang, minute=m)
    alt, _ = alternative_phrase(best_hypothesis(insight), ctx, lang)
    if alt and "best_alternative_chance_to_score" in facts:
        if insight.numbers["best_alt_p_goal"] > insight.numbers["actual_p_goal"]:
            key = "sd.better"
        else:  # what really happened was the better option ("right call", unless the ball was lost anyway)
            key = "sd.worse.plain" if moment.kind == "dangerous_turnover" else "sd.worse"
        body = t(key, lang, alt=alt, actual=facts["actual_chance_to_score"], best=facts["best_alternative_chance_to_score"])
        if lang == "en" and key in ("sd.better", "sd.worse.plain"):
            body = body[0].upper() + body[1:]
    else:
        body = t("sd.none", lang, actual=facts["actual_chance_to_score"])
    return headline, body


def _segment_brief(segment: Segment, ctx: MatchContext) -> dict[str, Any]:
    return {
        "mode": segment.mode, "language": segment.language, "depth": segment.depth, "perspective": segment.perspective,
        "tone": segment.tone,
        "viewer_club": ctx.clubs.get(segment.club or segment.player_team or "", None),
        "followed_player": ctx.name(segment.player) if segment.player else None,
    }


def _moment_brief(segment: Segment, moment: Moment, ctx: MatchContext) -> dict[str, Any]:
    return {
        "kind": moment.kind, "minute": minute(moment.clock_s), "team": ctx.clubs.get(moment.team),
        "for_or_against_viewer": side(segment, moment.team), "players": [ctx.name(p) for p in moment.player_ids],
        "trigger": moment.reason,
    }


# --- agents -------------------------------------------------------------------------------------

class Producer:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def decide(self, segment: Segment, moment: Moment, insight: Insight, ctx: MatchContext) -> ProducerDecision | None:
        """None = the rules say this segment never sees the moment (and no LLM call is made)."""
        if not insight.verified:
            return None
        relevance = moment_relevance(segment, moment)
        if relevance is None:
            return None
        base = insight_priority(relevance)
        lo, hi = max(base - PRIORITY_BAND, 0), min(base + PRIORITY_BAND, 100)
        prompt = json.dumps({
            "segment": _segment_brief(segment, ctx),
            "moment": _moment_brief(segment, moment, ctx),
            "insight": {"claim": insight.claim, "confidence": insight.confidence},
            "rules": {"relevance": relevance, "base_priority": base, "allowed_priority_range": [lo, hi]},
        }, indent=1, ensure_ascii=False)
        d = self.llm.complete(PRODUCER_SYSTEM, prompt, ProducerDecision, "producer")
        return ProducerDecision(show=d.show or moment.kind == "goal", priority=min(max(d.priority, lo), hi), angle=d.angle[:160])


class Narrator:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def write(self, segment: Segment, moment: Moment, insight: Insight, ctx: MatchContext, angle: str = "") -> Narrated:
        facts = insight_facts(segment, moment, insight, ctx)
        headline, body = insight_template(segment, moment, insight, ctx)
        body_max = BODY_MAX[segment.depth]
        prompt = json.dumps({
            "target_language": segment.language,
            "segment": _segment_brief(segment, ctx),
            "moment": _moment_brief(segment, moment, ctx),
            "producer_angle": angle,
            "verified_claim_en": insight.claim,
            "confidence": "clearly" if insight.confidence == "clear" else "slightly",
            "FACTS": facts,
            "plain_template": {"headline": headline, "body": body},
            "limits": {"headline_chars": HEADLINE_MAX, "body_chars": body_max},
        }, indent=1, ensure_ascii=False)
        draft = self.llm.complete(NARRATOR_SYSTEM, prompt, NarratorDraft, "narrator")
        allowed = allowed_numbers(facts.values())
        problem = check_text([draft.headline, draft.body], allowed, [HEADLINE_MAX, body_max])
        if problem:
            return Narrated(headline=headline, body=body, source="template", note=problem)
        return Narrated(headline=draft.headline.strip(), body=draft.body.strip(), source="llm")


def check_text(texts: list[str], allowed: set[str], limits: list[int]) -> str:
    """'' if the texts are fine, else the reason they are not."""
    for text, limit in zip(texts, limits):
        if not text.strip():
            return "empty text"
        if len(text) > limit:
            return f"too long ({len(text)} > {limit})"
        if not numbers_are_ours(text, allowed):
            bad = [n for n in numbers_in(text) if n not in allowed]
            return f"numbers not in our facts: {bad}"
    return ""


class RecapAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def write(self, segment: Segment, ctx: MatchContext, goals: list[tuple[int, str, str]],
              final_stats: dict[str, Any], shown: list[tuple[Moment, Insight]]) -> Recap:
        """goals: (minute, scorer id, team). final_stats: possession / pass_accuracy {team: share},
        player: {top_speed_kmh, pass_accuracy}. shown: insights this segment actually saw."""
        lang = segment.language
        home, away = ctx.clubs["home"], ctx.clubs["away"]
        score = f"{ctx.final_score[0]}-{ctx.final_score[1]}"
        facts: dict[str, Any] = {"final_score": score, "goals": [f"{surname(ctx.name(p))} {m}'" for m, p, _ in goals]}
        poss = final_stats.get("possession")
        if poss:
            facts["possession"] = {home: pct(poss["home"], lang, 0), away: pct(poss["away"], lang, 0)}
        acc = final_stats.get("pass_accuracy")
        if acc:
            facts["pass_accuracy"] = {home: pct(acc["home"], lang, 0), away: pct(acc["away"], lang, 0)}
        player = final_stats.get("player")
        if segment.player and player:
            facts["followed_player"] = {
                "name": ctx.name(segment.player),
                "top_speed_kmh": num(player["top_speed_kmh"], lang),
                "pass_accuracy": pct(player["pass_accuracy"], lang, 0) if player.get("pass_accuracy") is not None else None,
                "goals": [g for g, (_, p, _) in zip(facts["goals"], goals) if p == segment.player],
            }
        insights = []
        for moment, insight in shown[:3]:
            insight_numbers = insight_facts(segment, moment, insight, ctx)
            facts.setdefault("insight_numbers", []).append(insight_numbers)
            insights.append({"minute": minute(moment.clock_s), "kind": moment.kind, "verified_claim_en": insight.claim,
                             "localised": insight_template(segment, moment, insight, ctx)[1]})
        template = self._template(segment, ctx, goals, facts)
        prompt = json.dumps({
            "target_language": lang, "segment": _segment_brief(segment, ctx),
            "match": {"home": home, "away": away, "final_score": score},
            "FACTS": facts, "verified_insights": insights,
            "plain_template": template.model_dump(include={"headline", "body", "bullets"}),
            "limits": {"headline_chars": HEADLINE_MAX, "body_chars": RECAP_BODY_MAX, "bullet_chars": RECAP_BULLET_MAX,
                       "bullets": 4},
        }, indent=1, ensure_ascii=False)
        draft = self.llm.complete(RECAP_SYSTEM, prompt, RecapDraft, "recap")
        allowed = allowed_numbers([json.dumps(facts, ensure_ascii=False)])
        bullets = draft.bullets[:4]
        problem = check_text([draft.headline, draft.body, *bullets], allowed,
                             [HEADLINE_MAX, RECAP_BODY_MAX, *[RECAP_BULLET_MAX] * len(bullets)])
        if problem or not bullets:
            return template.model_copy(update={"note": problem or "no bullets"})
        return Recap(headline=draft.headline.strip(), body=draft.body.strip(), bullets=[b.strip() for b in bullets], source="llm")

    @staticmethod
    def _template(segment: Segment, ctx: MatchContext, goals: list[tuple[int, str, str]], facts: dict[str, Any]) -> Recap:
        lang = segment.language
        home, away = ctx.clubs["home"], ctx.clubs["away"]
        score = facts["final_score"]
        h, a = ctx.final_score
        if segment.perspective == "player" and segment.player:
            headline = t("recap.h.player", lang, player=surname(ctx.name(segment.player)))
        elif segment.perspective == "partisan" and segment.club and h != a:
            won = (h > a) == (segment.club == "home")
            headline = t("recap.h.for" if won else "recap.h.against", lang, score=score)
        else:
            headline = t("recap.h", lang, home=home, away=away, score=score)
        body = t("recap.goals", lang, goals=", ".join(facts["goals"]) or "-")
        bullets = []
        if "possession" in facts:
            bullets.append(t("recap.possession", lang, home=home, away=away, hp=facts["possession"][home], ap=facts["possession"][away]))
        if "followed_player" in facts:
            fp = facts["followed_player"]
            bullets.append(t("recap.player", lang, player=surname(fp["name"]), speed=fp["top_speed_kmh"], accuracy=fp["pass_accuracy"] or "-"))
        return Recap(headline=headline, body=body, bullets=bullets, source="template")


# --- fakes for tests and offline demos ----------------------------------------------------------

def fake_production_llm() -> FakeLLM:
    """Deterministic stand-ins: the Producer follows the rules, the writers return the plain template."""

    def producer(prompt: str) -> ProducerDecision:
        data = json.loads(prompt)
        side_ = data["moment"]["for_or_against_viewer"]
        angle = {"for": "our moment", "against": "what went wrong for us"}.get(side_, "why it mattered")
        return ProducerDecision(show=True, priority=data["rules"]["base_priority"], angle=angle)

    def narrator(prompt: str) -> NarratorDraft:
        return NarratorDraft(**json.loads(prompt)["plain_template"])

    def recap(prompt: str) -> RecapDraft:
        tpl = json.loads(prompt)["plain_template"]
        return RecapDraft(headline=tpl["headline"], body=tpl["body"], bullets=tpl["bullets"] or [tpl["body"]])

    return FakeLLM({"producer": producer, "narrator": narrator, "recap": recap})
