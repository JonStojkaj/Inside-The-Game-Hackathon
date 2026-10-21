"""Per-segment rendering: a live cue or a produced insight becomes a scheduler Candidate.

Live cards are localised templates (instant, free); insights carry the Narrator's text.
Depth decides how much of the payload a segment gets (analysts get distributions and
hypotheses, light segments one line).
"""

from __future__ import annotations

from typing import Any

from app.agents.production import Narrated, Recap, insight_metric
from app.models import Insight, Moment
from app.overlay.cues import Cue, MatchContext
from app.overlay.scheduler import Candidate
from app.personalization.i18n import minute, num, pct, surname, t
from app.personalization.segments import Segment, cue_priority, side

ANALYSIS_LATENCY_MS = 2_000  # rollouts + agent loop, measured 2-4 s
INSIGHT_STALE_MS = 45_000  # an unshown insight older than this (~13 broadcast minutes) is dropped
GOAL_INSIGHT_STALE_MS = 60_000
RECAP_MS = 30_000

# (slot, duration, min duration, timing, max delay)
_LAYOUT: dict[str, tuple[str, int, int, str, int]] = {
    "goal": ("lower_third", 6_000, 4_000, "live", 3_000),
    "shot": ("lower_third", 5_000, 3_000, "live", 2_000),
    "turnover": ("lower_third", 4_000, 2_500, "live", 1_500),
    "key_pass": ("lower_third", 4_000, 2_500, "live", 1_500),
    "sprint": ("ticker", 4_000, 2_500, "live", 2_000),
    "milestone": ("ticker", 5_000, 3_000, "live", 4_000),
    "player_tag": ("pitch", 3_000, 2_000, "live", 1_000),
    "stat": ("ticker", 6_000, 4_000, "calm", 10_000),
    "momentum": ("scorebug", 10_000, 0, "persistent", 0),
    "metric_card": ("side_panel", 15_000, 0, "persistent", 0),
    "player_card": ("side_panel", 15_000, 0, "persistent", 0),
}
_TYPE = {"goal": "event_card", "shot": "event_card", "turnover": "event_card", "key_pass": "event_card",
         "sprint": "alert", "milestone": "alert", "player_tag": "player_tag", "stat": "stat_card",
         "momentum": "momentum", "metric_card": "stat_card", "player_card": "stat_card"}


def _who(ctx: MatchContext, pid: str | None) -> str:
    return ctx.name(pid)


def _team_values(values: dict[str, float], fmt, ctx: MatchContext) -> dict[str, Any]:
    return {ctx.clubs[k]: fmt(v) for k, v in values.items()}


def render_cue(cue: Cue, segment: Segment, ctx: MatchContext) -> Candidate | None:
    priority = cue_priority(segment, cue.kind, cue.team, cue.player_ids, cue.data)
    if priority is None:
        return None
    lang, d, light = segment.language, cue.data, segment.depth == "light"
    mn = minute(cue.clock_s)
    s = side(segment, cue.team)
    payload: dict[str, Any] = {"minute": mn, "clock_s": cue.clock_s, "team": cue.team, "player_ids": cue.player_ids,
                               "cue": cue.kind, "persistent": cue.kind in ("momentum", "metric_card", "player_card")}
    p0 = cue.player_ids[0] if cue.player_ids else None
    headline = body = ""

    if cue.kind == "goal":
        score = f"{d['score'][0]}-{d['score'][1]}"
        key = f"goal.{s}" if segment.perspective in ("partisan", "player") and s != "neutral" else "goal"
        headline = t(f"{key}.h", lang, team=ctx.clubs[cue.team or "home"])
        body = t(f"{key}.b", lang, player=_who(ctx, p0), minute=mn, score=score, team=ctx.clubs[cue.team or "home"])
        payload["score"] = d["score"]
    elif cue.kind == "shot":
        outcome = t(f"outcome.{d['outcome']}", lang)
        headline = t("shot.h", lang, player=_who(ctx, p0))
        if light:
            body = t("shot.light.b", lang, player=surname(_who(ctx, p0)), outcome=outcome)
        else:
            body = t("shot.b", lang, outcome=outcome, distance=num(d["distance_m"], lang), speed=num(d["speed_kmh"], lang, 0),
                     xg=num(d["xg"], lang, 2))
            payload |= {"xg": d["xg"], "distance_m": d["distance_m"], "shot_speed_kmh": d["speed_kmh"]}
    elif cue.kind == "turnover":
        winner, loser = cue.player_ids
        lost = segment.perspective == "player" and segment.player == loser or segment.perspective == "partisan" and s == "against"
        if lost:
            headline = t("turnover.lost.h", lang, loser=_who(ctx, loser))
            body = t("turnover.lost.b", lang, player=_who(ctx, winner))
        else:
            headline = t("turnover.h", lang, player=_who(ctx, winner))
            body = t("turnover.b", lang, loser=_who(ctx, loser), distance=num(d["distance_m"], lang, 0))
        payload["distance_from_goal_m"] = d["distance_m"]
    elif cue.kind == "key_pass":
        headline = t("pass.h", lang, player=_who(ctx, p0))
        body = t("pass.b", lang, target=_who(ctx, cue.player_ids[1]), distance=num(d["distance_m"], lang),
                 difficulty=num(d["difficulty"], lang, 0))
        payload |= {"difficulty": d["difficulty"], "distance_m": d["distance_m"]}
    elif cue.kind == "sprint":
        headline = t("sprint.h", lang, player=_who(ctx, p0))
        body = t("sprint.b", lang, speed=num(d["speed_kmh"], lang))
        payload |= {"speed_kmh": d["speed_kmh"], "threshold_kmh": d["threshold_kmh"]}
    elif cue.kind == "milestone":
        key = {"first_goal": "first_goal", "first_on_target": "first_on_target", "fastest_shot": "fastest_shot",
               "top_speed": "top_speed"}[d["milestone"]]
        headline = t(f"ms.{key}.h", lang)
        body = t(f"ms.{key}.b", lang, player=_who(ctx, p0), minute=mn, speed=num(d.get("speed_kmh", 0.0), lang))
        payload["milestone"] = d["milestone"]
    elif cue.kind == "player_tag":
        p = ctx.players.get(p0 or "")
        headline = _who(ctx, p0)
        body = f"#{p.number} {p.position}" if p else ""
    elif cue.kind == "stat":
        keys = segment.stat_keys
        if not keys or d["key"] != keys[d["tick"] % len(keys)]:
            return None
        headline, body, payload = _stat_text(d["key"], d["values"], segment, ctx, payload)
    elif cue.kind == "momentum":
        headline, body = _momentum_text(cue, segment, ctx)
        payload |= {k: d.get(k) for k in ("chaos", "control_team", "control_share", "score", "possession")}
        if segment.depth == "deep":
            payload |= {"pressing": d.get("pressing"), "possession_changes_per_min": d.get("possession_changes_per_min")}
    elif cue.kind == "metric_card":
        if d["metric"] != segment.metric:
            return None
        headline, body, payload = _metric_text(d["metric"], d["values"], segment, ctx, payload)
    elif cue.kind == "player_card":
        if segment.player not in cue.player_ids:
            return None
        p = ctx.players[p0 or ""]
        acc = d.get("pass_accuracy")
        diff = d.get("avg_pass_difficulty")
        headline = t("card.h", lang, player=p.name, number=p.number, position=p.position)
        body = t("card.b", lang, speed=num(d["top_speed_kmh"], lang), accuracy=pct(acc, lang, 0) if acc is not None else "-",
                 difficulty=num(diff, lang, 0) if diff is not None else "-")
        payload |= {k: d.get(k) for k in ("top_speed_kmh", "speed_kmh", "pass_accuracy", "avg_pass_difficulty", "heatmap",
                                          "heatmap_bins")}

    slot, duration, min_duration, timing, max_delay = _LAYOUT[cue.kind]
    return Candidate(
        id=cue.id, type=_TYPE[cue.kind], slot=slot, ready_ms=cue.t_ms,  # type: ignore[arg-type]
        duration_ms=duration, min_duration_ms=min_duration, priority=priority, timing=timing,  # type: ignore[arg-type]
        max_delay_ms=max_delay, lang=lang, headline=headline, body=body, payload=payload, evidence=cue.evidence,
    )


def _stat_text(key: str, values: dict[str, float], segment: Segment, ctx: MatchContext, payload: dict) -> tuple[str, str, dict]:
    lang = segment.language
    fmt = {
        "possession": lambda v: pct(v, lang, 0), "pass_accuracy": lambda v: pct(v, lang, 0),
        "avg_pass_distance": lambda v: f"{num(v, lang)} m", "pass_difficulty": lambda v: f"{num(v, lang, 0)}/100",
        "pressing": lambda v: num(v, lang, 2), "max_shot_speed": lambda v: f"{num(v, lang, 0)} km/h",
    }[key]
    shown = _team_values(values, fmt, ctx)
    body = " · ".join(f"{club} {v}" for club, v in shown.items())
    if segment.club:  # partisan: our number first
        mine, theirs = ctx.clubs[segment.club], ctx.clubs["away" if segment.club == "home" else "home"]
        body = f"{mine} {shown[mine]} · {theirs} {shown[theirs]}"
    return t(f"stat.{key}", lang), body, payload | {"stat": key, "values": values}


def _metric_text(metric: str, values: dict[str, Any], segment: Segment, ctx: MatchContext, payload: dict) -> tuple[str, str, dict]:
    lang = segment.language
    if metric == "top_speed":
        value = f"{num(values['value'], lang)} km/h · {ctx.name(values['player_id'])}"
    elif metric == "chaos":
        value = num(values["value"] or 0.0, lang, 2)
    else:
        fmt = {"possession": lambda v: pct(v, lang, 0), "pass_accuracy": lambda v: pct(v, lang, 0),
               "pass_difficulty": lambda v: f"{num(v, lang, 0)}/100", "pressure_index": lambda v: num(v, lang, 2)}[metric]
        value = " · ".join(f"{club} {v}" for club, v in _team_values(values, fmt, ctx).items())
    return (t(f"stat.{metric}", lang), f"{value}\n{t(f'explain.{metric}', lang)}",
            payload | {"metric": metric, "values": values, "my_metric": True})


def _momentum_text(cue: Cue, segment: Segment, ctx: MatchContext) -> tuple[str, str]:
    lang, d = segment.language, cue.data
    score = f"{ctx.clubs['home']} {d['score'][0]}-{d['score'][1]} {ctx.clubs['away']}"
    team = d.get("control_team")
    chaotic = (d.get("chaos") or 0.0) >= 0.6 or team is None
    s = side(segment, team)
    if segment.perspective in ("partisan", "player") and s != "neutral" and not chaotic:
        headline = t(f"mom.{s}.h", lang)
    elif chaotic:
        headline = t("mom.chaos.h", lang)
    else:
        headline = t("mom.control.h", lang, team=ctx.clubs[str(team)])
    if segment.depth == "light" or team is None:
        return headline, t("mom.light.b", lang, score=score)
    return headline, t("mom.b", lang, share=pct(d.get("control_share") or 0.0, lang, 0), chaos=num(d.get("chaos") or 0.0, lang, 2))


def insight_candidate(segment: Segment, moment: Moment, insight: Insight, text: Narrated, priority: int,
                      angle: str) -> Candidate:
    """Analyst / player focus: the full Sliding Doors view (ghost futures on the pitch). Others: a one-line
    caption over the pitch. Either way the pitch slot, so it never fights the event card in the lower third."""
    full = segment.sliding_doors_view == "full"
    metric = insight_metric(insight, moment)
    payload: dict[str, Any] = {
        "moment_id": moment.id, "moment_kind": moment.kind, "minute": minute(moment.clock_s), "team": moment.team,
        "player_ids": moment.player_ids, "confidence": insight.confidence, "narration": text.source, "angle": angle,
        "view": "full" if full else "one_line",
        "metric": metric,
        "numbers": {k: insight.numbers[k] for k in (f"actual_{metric}", f"best_alt_{metric}") if k in insight.numbers},
    }
    if full:
        payload |= {"decision_frame": insight.decision_frame, "ghost_paths": insight.ghost_paths,
                    "alt_ghost_paths": insight.alt_ghost_paths, "alt_label": insight.alt_label}
    if segment.depth == "deep":
        payload["numbers"] = dict(insight.numbers)
        # counterfactual_p_goal holds the value of the insight's metric (p_keep for turnovers); "p_goal" kept for old readers
        payload["hypotheses"] = [{"text": h.text, "verdict": h.verdict, "metric": metric, "value": h.counterfactual_p_goal,
                                  "p_goal": h.counterfactual_p_goal, "seed_spread": h.seed_spread, "note": h.critic_note}
                                 for h in insight.hypotheses]
    stale = GOAL_INSIGHT_STALE_MS if moment.kind == "goal" else INSIGHT_STALE_MS
    return Candidate(
        id=insight.id, type="sliding_doors" if full else "insight", slot="pitch",
        ready_ms=moment.t_ms + ANALYSIS_LATENCY_MS, duration_ms=9_000 if full else 6_000,
        min_duration_ms=4_000 if full else 3_500, priority=priority, timing="stoppage", max_delay_ms=stale,
        lang=segment.language, headline=text.headline, body=text.body, payload=payload, evidence=insight.evidence,
    )


def recap_candidate(segment: Segment, recap: Recap, at_ms: int, evidence: list[str], extra: dict[str, Any]) -> Candidate:
    return Candidate(
        id="recap-full-time", type="recap", slot="fullscreen", ready_ms=at_ms, duration_ms=RECAP_MS, min_duration_ms=RECAP_MS,
        priority=100, timing="live", max_delay_ms=0, lang=segment.language, headline=recap.headline, body=recap.body,
        payload={"bullets": recap.bullets, "narration": recap.source, **extra}, evidence=evidence,
    )
