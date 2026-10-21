"""Stages d + e end to end: verified insights + match data -> timed overlays per segment.

    cues      once per match     (code: events, alerts, milestones, stats)
    timeline  once per match     (code: attacks + dead-ball windows)
    Producer  per segment x relevant moment   (LLM + rules)
    Narrator  per segment x produced insight  (LLM, numbers validated, template fallback)
    scheduler per segment        (rules)
    Recap     per segment        (LLM, full time)

LLM calls scale with segments x key moments, never with viewers.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from app.agents.llm import LLMClient
from app.agents.production import Narrator, Producer, RecapAgent
from app.models import FrameState, Insight, MatchEvent, Moment, Overlay
from app.overlay.cards import insight_candidate, recap_candidate, render_cue
from app.overlay.cues import GRF_SPRINT_KMH, Cue, MatchContext, build_cues
from app.overlay.scheduler import POST_MATCH_MS, Candidate, Timeline, build_timeline, schedule
from app.personalization.i18n import minute
from app.personalization.segments import Segment


class AgentStep(BaseModel):
    """One production decision, for the control-room panel."""

    segment_id: str
    agent: str  # producer | narrator | recap | rules | scheduler
    moment_id: str | None = None
    decision: str
    detail: dict[str, Any] = Field(default_factory=dict)


class Production(BaseModel):
    overlays: dict[str, list[Overlay]]
    log: list[AgentStep]
    stats: dict[str, dict[str, int]]  # per segment: candidates, shown, dropped, llm calls


def _final_stats(cues: list[Cue], player: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for c in cues:
        if c.kind == "stat" and c.data["key"] in ("possession", "pass_accuracy"):
            out[c.data["key"]] = c.data["values"]
        if c.kind == "player_card" and player in c.player_ids:
            out["player"] = c.data
    return out


def produce(
    ctx: MatchContext,
    frames: Sequence[FrameState],
    events: list[MatchEvent],
    moments: list[Moment],
    insights: list[Insight],
    segments: list[Segment],
    llm: LLMClient,
    recap_llm: LLMClient | None = None,
    sprint_kmh: float = GRF_SPRINT_KMH,
) -> Production:
    focus = sorted({s.player for s in segments if s.player})
    cues = build_cues(frames, events, ctx, focus_players=focus, sprint_kmh=sprint_kmh)
    timeline: Timeline = build_timeline(frames, events)
    by_moment = {i.moment_id: i for i in insights if i.verified}
    producer, narrator, recapper = Producer(llm), Narrator(llm), RecapAgent(recap_llm or llm)
    goals: list[tuple[int, str, str]] = [(minute(float(e.meta.get("clock_s", ctx.clock_of(e.t_ms)))), e.player_id or "", e.team or "")
             for e in events if e.type == "goal"]

    overlays: dict[str, list[Overlay]] = {}
    log: list[AgentStep] = []
    stats: dict[str, dict[str, int]] = {}
    for seg in segments:
        candidates: list[Candidate] = [c for c in (render_cue(cue, seg, ctx) for cue in cues) if c is not None]
        llm_calls = 0
        produced: dict[str, tuple[Moment, Insight]] = {}
        for moment in moments:
            insight = by_moment.get(moment.id)
            if insight is None:
                continue
            decision = producer.decide(seg, moment, insight, ctx)
            if decision is None:
                log.append(AgentStep(segment_id=seg.id, agent="rules", moment_id=moment.id, decision="not relevant"))
                continue
            llm_calls += 1
            log.append(AgentStep(segment_id=seg.id, agent="producer", moment_id=moment.id,
                                 decision="show" if decision.show else "skip",
                                 detail={"priority": decision.priority, "angle": decision.angle}))
            if not decision.show:
                continue
            text = narrator.write(seg, moment, insight, ctx, decision.angle)
            llm_calls += 1
            log.append(AgentStep(segment_id=seg.id, agent="narrator", moment_id=moment.id, decision=text.source,
                                 detail={"headline": text.headline, "note": text.note}))
            candidates.append(insight_candidate(seg, moment, insight, text, decision.priority, decision.angle))
            produced[insight.id] = (moment, insight)

        result = schedule(candidates, timeline, seg.id, ctx.match_id)
        shown_ids = {o.id.split(":", 1)[1] for o in result.overlays}
        shown = [produced[i] for i in produced if i in shown_ids]
        for i in produced:
            if i not in shown_ids:
                log.append(AgentStep(segment_id=seg.id, agent="scheduler", moment_id=produced[i][0].id,
                                     decision="dropped", detail={"reason": "no dead-ball window before it went stale"}))

        recap = recapper.write(seg, ctx, goals, _final_stats(cues, seg.player), shown)
        llm_calls += 1
        log.append(AgentStep(segment_id=seg.id, agent="recap", decision=recap.source, detail={"note": recap.note}))
        popups_end = max((o.start_ms + o.duration_ms for o in result.overlays if o.slot not in ("scorebug", "side_panel")),
                         default=0)
        at = max(timeline.end_ms + POST_MATCH_MS, popups_end)
        evidence = [e for _, i in shown for e in i.evidence[:1]] + [e.id for e in events if e.type == "goal"]
        rc = recap_candidate(seg, recap, at, evidence, {"final_score": list(ctx.final_score)})
        result.overlays.append(Overlay(
            id=f"{seg.id}:{rc.id}", match_id=ctx.match_id, segment_id=seg.id, start_ms=rc.ready_ms,
            duration_ms=rc.duration_ms, slot=rc.slot, type=rc.type, priority=rc.priority, lang=rc.lang,
            headline=rc.headline, body=rc.body, payload=rc.payload, evidence=rc.evidence,
        ))
        overlays[seg.id] = result.overlays
        stats[seg.id] = {"candidates": len(candidates) + 1, "shown": len(result.overlays), "dropped": len(result.dropped),
                         "insights_produced": len(produced), "insights_shown": len(shown), "llm_calls": llm_calls}
    stats["*"] = {"cues": len(cues), "show_every_event_baseline": sum(c.kind not in ("momentum", "metric_card", "player_card")
                                                                     for c in cues) + len(by_moment)}
    return Production(overlays=overlays, log=log, stats=stats)
