"""Commentary engine: one exported match + a viewer segment -> a timeline of short, non-overlapping spoken lines.

Pipeline (deterministic for a given match and segment, so audio caches always hit):
  1. candidates   every derived event worth a word (goals, shots, saves, tackles, interceptions, pass chains,
                  decisive passes, pressure, carries, set pieces), the Sliding Doors one-liner of every key moment
                  (numbers from the verified insight), kick-off / full time and mode intros (table stakes, focus player)
  2. placement    by priority (5 = goal ... 1 = colour), each at the time the event is *known* (never earlier:
                  no spoilers), delayed at most a little to avoid overlaps, otherwise dropped
  3. fillers      gaps are filled every few seconds (rhythm per mode) with live facts computed at that time:
                  possession, pass accuracy, shots, xG, top speed, distance, control/chaos, tempo, win probability,
                  table stakes and rivals (club fan), the chosen player's numbers and live rating (player focus)
Text comes from phrases.py (no numbers in templates); every number here is computed from the export.
Spacing rule: next start >= previous start + estimated duration + GAP_MS. No template repeats within REPEAT_MS.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
import string
from dataclasses import dataclass, field
from typing import Any

from app.commentary.data import Event, MatchData, Player, other
from app.commentary.phrases import ACTIONS, NUMBER_WORDS, PHRASES

MODES = ("analyst", "club_fan", "player_focus", "casual")
LANGS = ("en", "de", "es")
CLUBS = ("home", "away")
GAP_MS = 500  # silence between two lines, at least
REPEAT_MS = 60_000  # the same template never twice within a minute
MAX_WORDS = 14

# start-to-start rhythm of filler lines (ms) and the minimum silence before a filler, per mode
RHYTHM: dict[str, tuple[int, int, int]] = {
    "club_fan": (3800, 5600, 700),
    "casual": (4600, 7200, 1100),
    "player_focus": (4600, 7200, 1100),
    "analyst": (5000, 7800, 1300),
}
FILLERS: dict[str, list[str]] = {
    "casual": ["phase", "possession", "score", "shots", "top_speed", "control", "passing", "chaos", "tempo", "distance"],
    "analyst": ["possession", "passing", "shots", "xg", "top_speed", "control", "win_prob", "distance", "chaos", "tempo", "score"],
    "club_fan": ["fan_colour", "phase", "possession", "fan_stakes", "shots", "score", "fan_rival", "control", "win_prob",
                 "fan_derby", "fan_form", "top_speed", "passing", "xg"],
    "player_focus": ["player_passes", "phase", "player_rating", "player_speed", "possession", "player_actions",
                     "player_defence", "score", "player_quiet", "shots"],
}
FILLER_MAX_USES = {"fan_derby": 2, "fan_form": 1}
FILLER_MIN_MS = {"fan_colour": 25_000, "phase": 20_000, "player_quiet": 30_000}  # others: REPEAT_MS per kind

# delivery per mode: (rate %, pitch %); goals for "us" are delivered even brighter
DELIVERY = {"analyst": (-4, -2), "club_fan": (10, 6), "player_focus": (3, 2), "casual": (5, 3)}
EXCITED = {"goal", "goal_detail"}
CHARS_PER_S = {"en": 14.0, "de": 14.5, "es": 15.0}  # at rate +0 %, after expanding numbers and units (calibrated)


@dataclass(frozen=True)
class Segment:
    mode: str
    lang: str
    club: str | None = None  # club_fan only
    player: str | None = None  # player_focus only

    @property
    def id(self) -> str:
        extra = self.club if self.mode == "club_fan" else self.player if self.mode == "player_focus" else None
        return "-".join(x for x in (self.mode, extra, self.lang) if x)

    @classmethod
    def make(cls, md: MatchData, mode: str, lang: str = "en", club: str | None = None, player: str | None = None) -> Segment:
        """Validate and normalise viewer parameters (ValueError on bad input)."""
        if mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")
        if lang not in LANGS:
            raise ValueError(f"lang must be one of {', '.join(LANGS)}")
        if mode == "club_fan":
            club = club or "home"
            if club not in CLUBS:
                raise ValueError("club must be home or away")
            return cls(mode, lang, club=club)
        if mode == "player_focus":
            player = player or default_player(md)
            if player not in md.players:
                raise ValueError(f"unknown player {player!r}")
            return cls(mode, lang, player=player)
        return cls(mode, lang)


@dataclass
class Line:
    id: str
    start_ms: int
    duration_ms: int
    text: str
    kind: str
    priority: int
    tone: str
    template: str = field(repr=False)
    event_ms: int = field(default=0, repr=False)
    rate: int = 0
    pitch: int = 0

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms


@dataclass
class Candidate:
    t_ms: int  # desired start (when the event is known + reaction)
    prio: int
    kind: str
    fields: dict[str, str]
    team: str | None = None  # acting team (club fan tone)
    involves: bool = False  # player focus: the chosen player acts
    tones: list[str] | None = None  # explicit tone chain (fan-only / player-only kinds)
    max_delay: int = 3000
    must: bool = False  # allow template repetition rather than dropping it
    event_ms: int = 0


def default_player(md: MatchData) -> str:
    """The most involved player of the match (most derived events)."""
    counts: dict[str, int] = {}
    for e in md.events:
        if e.player_id:
            counts[e.player_id] = counts.get(e.player_id, 0) + 1
    return max(sorted(counts), key=lambda p: counts[p]) if counts else next(iter(md.players))


# ------------------------------------------------------------------------------------------------ formatting


def num(x: float, lang: str, digits: int = 0) -> str:
    s = f"{x:.{digits}f}" if digits else str(int(round(x)))
    return s.replace(".", ",") if lang in ("de", "es") else s


def pct(p: float, lang: str, digits: int = 0) -> str:
    v = num(p * 100, lang, digits)
    return f"{v}%" if lang == "en" else f"{v} %"


def ordinal(n: int, lang: str) -> str:
    if lang == "de":
        return f"Platz {n}"
    if lang == "es":
        return str(n)
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def minute_ord(n: int, lang: str) -> str:
    if lang == "en":
        return ordinal(n, "en")
    return f"{n}." if lang == "de" else str(n)


def score_words(score: tuple[int, int], lang: str) -> str:
    words = NUMBER_WORDS[lang]

    def w(n: int) -> str:
        return words[n] if 0 <= n < len(words) else str(n)

    h, a = score
    if lang == "en":
        return f"{w(h)}-all" if h == a and h > 0 else f"{w(h)}-{w(a)}"
    if lang == "de":
        return f"{w(h)} zu {w(a)}"
    return f"{w(h)} a {w(a)}"


_UNIT_WORDS = {
    "en": {"km/h": "kilometres per hour", "%": " percent", "xG": "ex gee"},
    "de": {"km/h": "Kilometer pro Stunde", "%": " Prozent", "xG": "ix geh"},
    "es": {"km/h": "kilómetros por hora", "%": " por ciento", "xG": "equis ge"},
}
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def spoken_length(text: str, lang: str) -> int:
    """Characters as spoken: numbers and units are much longer read aloud than written."""
    s = text
    for unit, words in _UNIT_WORDS[lang].items():
        s = s.replace(unit, words)

    def expand(m: re.Match[str]) -> str:
        whole, _, frac = m.group(0).replace(",", ".").partition(".")
        n = int(whole)
        size = 4 if n < 13 else 8 if n < 100 else 16 if n < 1000 else 20
        return "x" * (size + (6 + 5 * len(frac) if frac else 0))

    return len(_NUM.sub(expand, s))


def estimate_ms(text: str, lang: str, rate: int) -> int:
    cps = CHARS_PER_S[lang] * (1 + rate / 100)
    return int(round(450 + spoken_length(text, lang) / cps * 1000, -1))


def delivery(mode: str, kind: str, tone: str) -> tuple[int, int]:
    rate, pitch = DELIVERY[mode]
    if kind in EXCITED and tone in ("us", "p") or (kind == "goal" and mode == "casual"):
        rate, pitch = rate + 4, pitch + 6
    return rate, pitch


def word_count(text: str) -> int:
    return len([w for w in text.split() if any(c.isalnum() for c in w)])


def template_fields(template: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(template) if f}


def _de_genitive(template: str, fields: dict[str, str]) -> str:
    """German genitive of names ending in s/x/z: "Reyes' Pass", not "Reyess Pass"."""
    for name, value in fields.items():
        if value and value[-1] in "sxzß":
            template = template.replace("{" + name + "}s ", "{" + name + "}' ")
    return template


# ------------------------------------------------------------------------------------------------ engine


class _Builder:
    def __init__(self, md: MatchData, seg: Segment) -> None:
        self.md, self.seg, self.lang = md, seg, seg.lang
        self.lines: list[Line] = []
        self.used: dict[str, list[int]] = {}  # template id -> start times
        self.home = md.clubs["home"]["short"]
        self.away = md.clubs["away"]["short"]

    # --- names -----------------------------------------------------------------------------------------------
    def player(self, pid: str | None) -> str:
        p = self.md.players.get(pid or "")
        return p.surname if p else ""

    def team_name(self, team: str | None) -> str:
        return self.md.club_name(team) if team in ("home", "away") else ""

    def involves(self, *pids: str | None) -> bool:
        return self.seg.mode == "player_focus" and self.seg.player in pids

    # --- rendering -------------------------------------------------------------------------------------------
    def tone_chain(self, c: Candidate) -> list[str]:
        if c.tones is not None:
            return c.tones
        mode = self.seg.mode
        if mode == "analyst":
            return ["a", "n"]
        if mode == "club_fan" and c.team in ("home", "away"):
            return ["us" if c.team == self.seg.club else "them", "n"]
        if mode == "player_focus" and c.involves:
            return ["p", "n"]
        return ["n"]

    def recent(self, template_id: str, t_ms: int) -> bool:
        return any(abs(t - t_ms) < REPEAT_MS for t in self.used.get(template_id, ()))

    def render(self, c: Candidate, t_ms: int) -> tuple[str, str, str] | None:
        """(text, template id, tone) for the candidate at time t_ms, or None if nothing fits."""
        pool = PHRASES[self.lang].get(c.kind, {})
        fallback: tuple[str, str, str] | None = None
        rng = random.Random(f"{self.md.match_id}|{self.seg.id}|{c.kind}|{c.t_ms}")
        for tone in self.tone_chain(c):
            options = [(i, t) for i, t in enumerate(pool.get(tone, [])) if template_fields(t) <= c.fields.keys()]
            if not options:
                continue
            fresh = [(i, t) for i, t in options if not self.recent(f"{c.kind}.{tone}.{i}", t_ms)]
            if fresh:
                i, template = rng.choice(fresh)
                return self.fill(template, c.fields), f"{c.kind}.{tone}.{i}", tone
            if c.must and fallback is None:
                i, template = rng.choice(options)
                fallback = (self.fill(template, c.fields), f"{c.kind}.{tone}.{i}", tone)
        return fallback

    def fill(self, template: str, fields: dict[str, str]) -> str:
        if self.lang == "de":
            template = _de_genitive(template, fields)
        text = re.sub(r"\s+", " ", template.format(**fields)).strip()
        # sentence starts are capitalised even when they begin with a value ("... finds the net. One-all.")
        return re.sub(r"(^|[.!?]\s+)([¡¿]?)([a-zà-ÿ])", lambda m: m.group(1) + m.group(2) + m.group(3).upper(), text)

    # --- placement -------------------------------------------------------------------------------------------
    def free(self, start: int, dur: int) -> bool:
        return all(start >= ln.end_ms + GAP_MS or ln.start_ms >= start + dur + GAP_MS for ln in self.lines)

    def place(self, c: Candidate, limit_ms: int) -> Line | None:
        rendered = self.render(c, c.t_ms)
        if rendered is None:
            return None
        text, template, tone = rendered
        rate, pitch = delivery(self.seg.mode, c.kind, tone)
        dur = estimate_ms(text, self.lang, rate)
        starts = sorted({c.t_ms, *(ln.end_ms + GAP_MS for ln in self.lines if c.t_ms < ln.end_ms + GAP_MS <= c.t_ms + c.max_delay)})
        for s in starts:
            if s + dur > limit_ms:
                break
            # never talk about an earlier event after the goal line of a later one
            if any(ln.priority == 5 and ln.event_ms > c.event_ms and ln.start_ms < s and ln.kind == "goal" for ln in self.lines):
                continue
            if self.free(s, dur):
                return self.add(Line(f"{c.kind}-{s}", s, dur, text, c.kind, c.prio, tone, template, c.event_ms, rate, pitch))
        return None

    def add(self, line: Line) -> Line:
        self.lines.append(line)
        self.lines.sort(key=lambda ln: ln.start_ms)
        self.used.setdefault(line.template, []).append(line.start_ms)
        return line


def build_timeline(md: MatchData, seg: Segment) -> list[Line]:
    b = _Builder(md, seg)
    end_ms = md.duration_ms or (md.events[-1].known_ms + 5000 if md.events else 60_000)
    cands = event_candidates(b) + moment_candidates(b) + frame_candidates(b, end_ms)
    for c in sorted(cands, key=lambda c: (-c.prio, c.t_ms, c.kind)):
        b.place(c, end_ms)
    fill_gaps(b, end_ms)
    return b.lines


# ------------------------------------------------------------------------------------------------ candidates


def _shot_fields(b: _Builder, e: Event) -> dict[str, str]:
    lang = b.lang
    f = {"player": b.player(e.player_id), "team": b.team_name(e.team)}
    if "distance_m" in e.meta:
        f["dist"] = num(float(e.meta["distance_m"]), lang)
    if e.meta.get("shot_speed_kmh"):
        f["speed"] = num(float(e.meta["shot_speed_kmh"]), lang)
    if "xg" in e.meta:
        f["xg"] = num(float(e.meta["xg"]), lang, 2)
    return f


def event_candidates(b: _Builder) -> list[Candidate]:
    md, seg, lang = b.md, b.seg, b.lang
    out: list[Candidate] = []
    by_id = {e.id: e for e in md.events}
    turnover_ids = {i for m in md.moments if m.get("kind") == "dangerous_turnover" for i in m.get("event_ids", [])}
    decisive_ids = {i for m in md.moments if m.get("kind") == "decisive_pass" for i in m.get("event_ids", [])}
    chain_team: str | None = None
    chain_n = 0
    counts: dict[tuple[str, str], int] = {}
    fan = seg.mode == "club_fan"
    focus = seg.mode == "player_focus"

    for i, e in enumerate(md.events):
        t = e.known_ms + 300
        involved = b.involves(e.player_id)
        if e.type == "pass" and e.outcome == "complete":
            if e.team == chain_team:
                chain_n += 1
            else:
                chain_team, chain_n = e.team, 1
        elif e.type in ("pass", "interception", "tackle", "shot", "goal", "out_of_play", "set_piece", "kickoff"):
            chain_team, chain_n = None, 0
        if e.team and e.type in ("tackle", "interception"):
            counts[(e.team, e.type)] = counts.get((e.team, e.type), 0) + 1

        if e.type == "goal" and e.team:
            shot = by_id.get(str(e.meta.get("shot_id", "")))
            score = (int(e.meta["score"][0]), int(e.meta["score"][1])) if "score" in e.meta else md.score_at(e.known_ms)
            scorer = e.player_id or (shot.player_id if shot else None)
            f = {"scorer": b.player(scorer), "team": b.team_name(e.team), "score": score_words(score, lang)}
            if not f["scorer"]:
                f.pop("scorer")
            out.append(Candidate(e.known_ms + 200, 5, "goal", f, team=e.team, involves=b.involves(scorer), max_delay=1500,
                                 must=True, event_ms=e.known_ms))
            if shot is not None:
                detail = {**_shot_fields(b, shot), "scorer": b.player(scorer)}
                assist = next((p for p in reversed(md.events[:i]) if p.type == "pass" and p.outcome == "complete"
                               and p.target_id == scorer and 0 <= shot.t_ms - p.t_ms <= 6000), None)
                kind = "goal_detail"
                if assist is not None:
                    detail["assist"] = b.player(assist.player_id)
                    kind = "goal_assist" if (focus and b.involves(assist.player_id)) or seg.mode != "analyst" and i % 2 else kind
                out.append(Candidate(e.known_ms + 3800, 4, kind, detail, team=e.team,
                                     involves=b.involves(scorer) or (assist is not None and b.involves(assist.player_id)),
                                     max_delay=4000, must=True, event_ms=e.known_ms))
            if fan and md.league is not None:
                short = md.clubs[seg.club or "home"]["short"]
                before = md.league.position(short, b.home, b.away, None)
                now = md.league.position(short, b.home, b.away, score)
                tone = "up" if now < before else "down" if now > before else "same"
                out.append(Candidate(e.known_ms + 9000, 4, "stakes_live", {"pos": ordinal(now, lang)}, tones=[tone],
                                     max_delay=7000, event_ms=e.known_ms))
        elif e.type == "shot" and e.outcome != "goal" and e.team:
            kind = {"saved": "shot_saved", "off_target": "shot_off"}.get(e.outcome or "", "shot_blocked")
            f = _shot_fields(b, e)
            gk = md.goalkeeper(other(e.team))
            if gk:
                f["gk"] = gk.surname
            out.append(Candidate(t, 5 if involved else 4, kind, f, team=e.team, involves=involved, max_delay=2500,
                                 must=True, event_ms=e.known_ms))
        elif e.type in ("tackle", "interception") and e.team:
            prio = 4 if involved else 3 if e.id in turnover_ids else 2
            if focus and not involved and e.id not in turnover_ids:
                prio = 1
            f = {"player": b.player(e.player_id), "target": b.player(e.target_id), "team": b.team_name(e.team),
                 "count": ordinal_count(counts[(e.team, e.type)], lang)}
            out.append(Candidate(e.known_ms + 300, prio, e.type, f, team=e.team, involves=involved, max_delay=2500,
                                 event_ms=e.known_ms))
        elif e.type == "pass" and e.team:
            dist = float(e.meta.get("distance_m", 0.0))
            f = {"player": b.player(e.player_id), "target": b.player(e.target_id), "team": b.team_name(e.team),
                 "dist": num(dist, lang)}
            if e.outcome == "complete" and e.id in decisive_ids:
                f["gain"] = pct(float(e.meta.get("threat_gain", 0.0)), lang)
                out.append(Candidate(t, 4 if involved else 3, "decisive_pass", f, team=e.team, involves=involved,
                                     max_delay=2000, event_ms=e.known_ms))
            elif e.outcome == "complete" and dist >= 30:
                out.append(Candidate(t, 3 if involved else 1, "long_pass", f, team=e.team, involves=involved,
                                     max_delay=2000, event_ms=e.known_ms))
            elif involved:
                out.append(Candidate(t, 2, "pass_ok" if e.outcome == "complete" else "pass_bad", f, tones=["p"],
                                     max_delay=2500, event_ms=e.known_ms))
            if e.outcome == "complete" and chain_n >= 4 and chain_n in (4, 7, 10, 13, 16):
                acc = pass_accuracy(md, e.team, e.known_ms)
                cf = {"team": b.team_name(e.team), "n": num(chain_n, lang)}
                if acc is not None:
                    cf["acc"] = pct(acc[0], lang)
                out.append(Candidate(t + 200, 2, "pass_chain", cf, team=e.team, max_delay=3000, event_ms=e.known_ms))
        elif e.type == "pressure" and e.team:
            dist = float(e.meta.get("distance_m", 0.0))
            prio = 3 if involved else 0 if focus else 1
            if prio and not (seg.mode == "analyst" and i % 3):  # the analyst mentions only some pressing
                f = {"player": b.player(e.player_id), "target": b.player(e.target_id), "dist": num(dist, lang)}
                out.append(Candidate(t, prio, "pressure", f, team=e.team, involves=involved, max_delay=1500, event_ms=e.known_ms))
        elif e.type == "carry" and e.team:
            dist = float(e.meta.get("distance_m", 0.0))
            prio = 3 if involved and dist >= 8 else 2 if dist >= 25 else 1 if dist >= 15 else 0
            if focus and not involved:
                prio = min(prio, 1)
            if prio:
                f = {"player": b.player(e.player_id), "dist": num(dist, lang)}
                out.append(Candidate(t, prio, "carry", f, team=e.team, involves=involved, max_delay=2000, event_ms=e.known_ms))
        elif e.type == "set_piece":
            mode = str(e.meta.get("mode", ""))
            kind = {"corner": "corner", "free_kick": "free_kick", "penalty": "penalty"}.get(mode)
            team = next((x.team for x in md.events[i + 1:] if x.team and x.type != "set_piece" and x.known_ms - e.known_ms <= 6000), None)
            if kind and team:
                out.append(Candidate(e.known_ms + 400, 4 if kind == "penalty" else 2, kind, {"team": b.team_name(team)},
                                     team=team, max_delay=2500, event_ms=e.known_ms))
    return out


def ordinal_count(n: int, lang: str) -> str:
    if lang == "en":
        return ordinal(n, "en")
    if lang == "de":
        return str(n)  # template: "der {count}. für ..."
    return str(n)


def pass_accuracy(md: MatchData, team: str | None, t_ms: int) -> tuple[float, int, int] | None:
    done = total = 0
    for e in md.events:
        if e.known_ms > t_ms:
            break
        if e.type == "pass" and e.team == team:
            total += 1
            done += e.outcome == "complete"
    return (done / total, done, total) if total >= 5 else None


def _decider(md: MatchData, insight: dict[str, Any], moment: dict[str, Any]) -> str | None:
    """Who made the decision the insight is about: the player who lost the ball (turnover) or acted at the decision frame."""
    pids = [p for p in moment.get("player_ids", []) if p in md.players]
    if moment.get("kind") == "dangerous_turnover" and pids:
        return pids[0]
    frame = insight.get("decision_frame", moment.get("frame"))
    e = next((e for e in md.events if e.frame == frame and e.player_id and e.type in ("pass", "shot", "carry")), None)
    return e.player_id if e else pids[0] if pids else None


def sliding_doors_fields(b: _Builder, insight: dict[str, Any], decider: str | None) -> tuple[str, dict[str, str]] | None:
    """Kind + fields of the Sliding Doors one-liner, numbers straight from the verified insight."""
    lang = b.lang
    nums = insight.get("numbers") or {}
    f = {"player": b.player(decider)} if decider else {}
    actual = nums.get("actual_p_goal")
    alt = nums.get("best_alt_p_goal")
    if insight.get("metric") == "p_keep" and nums.get("actual_p_keep") is not None:
        return "sd_keep", {**f, "keep": pct(float(nums["actual_p_keep"]), lang, 1)}
    if actual is None:
        return None
    f["actual"] = pct(float(actual), lang, 1)
    hyp = next((h for h in insight.get("hypotheses", []) if alt is not None and h.get("verdict") == "accepted"
                and abs(float(h.get("counterfactual_p_goal", -1)) - float(alt)) < 1e-6), None)
    if alt is None or hyp is None:
        return "sd_none", f
    params = (hyp.get("intervention") or {}).get("params") or {}
    action = params.get("action")
    if (hyp.get("intervention") or {}).get("kind") != "swap_action" or action not in ACTIONS[lang]:
        return "sd_none", f
    target = b.player(params.get("target_id"))
    verb, noun = (s.replace("{target}", target) for s in ACTIONS[lang][action])
    f.update(alt=pct(float(alt), lang, 1), action=verb, action_noun=noun, action_cap=noun[:1].upper() + noun[1:])
    return ("sd_alt" if float(alt) > float(actual) else "sd_right"), f


def moment_candidates(b: _Builder) -> list[Candidate]:
    md = b.md
    out = []
    for m in md.moments:
        insight = md.insights.get(m.get("id", ""))
        if insight is None:
            continue
        refs = [e for e in md.events if e.id in m.get("event_ids", [])]
        anchor = max((e.known_ms for e in refs), default=int(m.get("t_ms", 0)))
        if m.get("kind") == "goal":  # after the goal line and its detail
            goal = next((e for e in md.events if e.type == "goal" and e.known_ms >= anchor - 100), None)
            anchor = (goal.known_ms if goal else anchor) + 4000
        decider = _decider(md, insight, m)
        sd = sliding_doors_fields(b, insight, decider)
        if sd is None:
            continue
        kind, f = sd
        involved = b.involves(decider)
        out.append(Candidate(anchor + 3000, 4, kind, f, involves=involved, max_delay=7000, must=True, event_ms=anchor))
    return out


def frame_candidates(b: _Builder, end_ms: int) -> list[Candidate]:
    """Kick-off, mode intros and full time."""
    md, seg, lang = b.md, b.seg, b.lang
    home, away = md.club_name("home"), md.club_name("away")
    out = []
    fan_tones = ["us", "n"] if seg.mode == "club_fan" else None
    ko = {"home": home, "away": away}
    if seg.mode == "club_fan":
        ko |= {"us": md.club_name(seg.club or "home"), "them": md.club_name(other(seg.club or "home"))}
    out.append(Candidate(300, 5, "kickoff", ko, tones=fan_tones or (["a", "n"] if seg.mode == "analyst" else ["n"]),
                         max_delay=1000, must=True))
    if seg.mode == "club_fan" and md.league is not None:
        short = md.clubs[seg.club or "home"]["short"]
        pos = md.league.position(short, b.home, b.away, None)
        win = md.league.stakes(seg.club or "home", b.home, b.away, (0, 0))["win"]
        out.append(Candidate(3500, 4, "intro_fan", {"pos": ordinal(pos, lang), "win": ordinal(win, lang)}, tones=["us"],
                             max_delay=6000))
    if seg.mode == "player_focus" and seg.player:
        p = md.players[seg.player]
        out.append(Candidate(3500, 4, "intro_player", {"full": p.name, "num": str(p.number), "team": md.club_name(p.team)},
                             tones=["p"], max_delay=6000))
    final = md.final_score
    if seg.mode == "club_fan":
        us, them = final if seg.club == "home" else (final[1], final[0])
        tones = ["win" if us > them else "draw" if us == them else "loss"]
    else:
        tones = ["a", "n"] if seg.mode == "analyst" else ["n"]
    f = {"home": home, "away": away, "score": score_words(final, lang)}
    rendered_guess = 4200
    out.append(Candidate(max(0, end_ms - rendered_guess), 5, "fulltime", f, tones=tones, max_delay=rendered_guess - 1500, must=True,
                         event_ms=end_ms))
    return out


# ------------------------------------------------------------------------------------------------ fillers


def win_probability(md: MatchData, team: str, t_ms: int) -> float:
    """Same model as the web player (frontend/src/lib/models.ts): Poisson goals for the remaining minutes, rate
    blending a prior (1.35 per 90, home x1.08 / away x0.92) with the observed xG rate (weight minute/90, max 60 %)."""
    minute = min(90.0, t_ms / 1000 * md.clock_scale / 60)
    rem = max(0.0, 90 - minute)
    xg = xg_so_far(md, t_ms)
    score = md.score_at(t_ms)

    def lam(tm: str) -> float:
        prior = (1.35 / 90) * (1.08 if tm == "home" else 0.92)
        observed = xg[tm] / max(minute, 15)
        w = min(0.6, minute / 90)
        return ((1 - w) * prior + w * observed) * rem

    def pois(lmb: float) -> list[float]:
        p, v = [], math.exp(-lmb)
        for k in range(11):
            p.append(v)
            v = v * lmb / (k + 1)
        return p

    pu, pt = pois(lam(team)), pois(lam(other(team)))
    diff = score[0] - score[1] if team == "home" else score[1] - score[0]
    win = sum(pu[a] * pt[c] for a in range(11) for c in range(11) if diff + a - c > 0)
    return win / max(1e-9, sum(pu) * sum(pt))


def xg_so_far(md: MatchData, t_ms: int) -> dict[str, float]:
    out = {"home": 0.0, "away": 0.0}
    for e in md.events:
        if e.known_ms > t_ms:
            break
        if e.type == "shot" and e.team and "xg" in e.meta:
            out[e.team] += float(e.meta["xg"])
    return out


def shots_so_far(md: MatchData, t_ms: int) -> dict[str, int]:
    out = {"home": 0, "away": 0}
    for e in md.events:
        if e.known_ms > t_ms:
            break
        if e.type == "shot" and e.team:
            out[e.team] += 1
    return out


def player_rating(md: MatchData, pid: str, t_ms: int) -> float:
    """Live rating 1..10, same formula as the web player: 6 + 3.5 tanh(sum of action values / 3)."""
    team = md.players[pid].team
    total = 0.0
    events = [e for e in md.events if e.known_ms <= t_ms]
    for i, e in enumerate(events):
        if e.player_id != pid:
            continue
        if e.type == "pass":
            total += 0.05 + 0.1 * float(e.meta.get("difficulty", 0)) / 100 if e.outcome == "complete" else -0.12
        elif e.type == "shot":
            total += 0.15 + 2 * float(e.meta.get("xg", 0))
        elif e.type == "goal":
            total += 1.2
        elif e.type == "interception" or (e.type == "tackle" and e.outcome == "won"):
            total += 0.3
        elif e.type == "pressure" and any(x.frame - e.frame <= 30 and x.team == team and x.type in ("interception", "tackle")
                                          for x in events[i + 1:]):
            total += 0.15
    return max(1.0, min(10.0, 6 + 3.5 * math.tanh(total / 3)))


def possession_team(md: MatchData, t_ms: int) -> str | None:
    last = None
    for e in md.events:
        if e.known_ms > t_ms:
            break
        if t_ms - e.known_ms > 6000 or not e.team:
            continue
        if e.type in ("pass", "carry") and e.outcome != "incomplete":
            last = e.team
        elif e.type in ("tackle", "interception"):
            last = e.team
        elif e.type == "pressure":
            last = other(e.team)
        elif e.type in ("shot", "goal", "out_of_play", "set_piece"):
            last = None
    return last


def filler(b: _Builder, kind: str, t_ms: int) -> Candidate | None:
    """A live fact at t_ms (fields from the data known at that time) or None if it does not apply yet."""
    md, seg, lang = b.md, b.seg, b.lang
    s = md.stats_at(t_ms) or {}
    teams = s.get("teams", {})
    club = seg.club or "home"
    home, away = md.club_name("home"), md.club_name("away")
    fan = seg.mode == "club_fan"
    played_s = t_ms / 1000

    def cand(fields: dict[str, str], team: str | None = None, tones: list[str] | None = None, involves: bool = False) -> Candidate:
        return Candidate(t_ms, 0, kind, fields, team=team, tones=tones, involves=involves, max_delay=0)

    if kind == "phase":
        team = possession_team(md, t_ms)
        return cand({"team": b.team_name(team)}, team=team) if team else None
    if kind == "possession":
        if played_s < 25 or not teams:
            return None
        ph, pa = float(teams["home"]["possession"]), float(teams["away"]["possession"])
        lead = "home" if ph >= pa else "away"
        mine = ph if club == "home" else pa
        f = {"home": home, "away": away, "ph": pct(ph, lang), "pa": pct(pa, lang), "team": b.team_name(lead)}
        if fan:
            f["p"] = pct(mine if mine >= 0.5 else 1 - mine, lang)
            return cand(f, tones=["us" if mine >= 0.5 else "them", "n"])
        return cand(f, team=lead)
    if kind == "passing":
        team = club if fan else ("home" if (t_ms // 1000) % 2 == 0 else "away")
        acc = pass_accuracy(md, team, t_ms)
        if acc is None:
            return None
        return cand({"team": b.team_name(team), "acc": pct(acc[0], lang), "done": str(acc[1]), "total": str(acc[2])}, team=team)
    if kind == "shots":
        sh = shots_so_far(md, t_ms)
        if sh["home"] + sh["away"] == 0:
            return None
        f = {"home": home, "away": away, "sh": str(sh["home"]), "sa": str(sh["away"])}
        if fan:
            us, them = (sh["home"], sh["away"]) if club == "home" else (sh["away"], sh["home"])
            f["sh"], f["sa"] = str(us), str(them)
            return cand(f, tones=["us" if us >= them else "them", "n"]) if us + them else None
        return cand(f)
    if kind == "xg":
        xg = xg_so_far(md, t_ms)
        if xg["home"] + xg["away"] < 0.05:
            return None
        f = {"home": home, "away": away, "xh": num(xg["home"], lang, 2), "xa": num(xg["away"], lang, 2)}
        if fan:
            us, them = (xg["home"], xg["away"]) if club == "home" else (xg["away"], xg["home"])
            f["xh"], f["xa"] = num(us, lang, 2), num(them, lang, 2)
            return cand(f, tones=["us" if us >= them else "them"])
        return cand(f)
    if kind == "top_speed":
        players = s.get("players", {})
        pool = [p for p in players.values() if not fan or p.get("team") == club]
        if played_s < 20 or not pool:
            return None
        top = max(pool, key=lambda p: (float(p.get("top_speed_kmh", 0)), p["id"]))
        if float(top.get("top_speed_kmh", 0)) < 15:
            return None
        return cand({"player": b.player(top["id"]), "speed": num(float(top["top_speed_kmh"]), lang)}, team=top.get("team"))
    if kind == "distance":
        team = club if fan else ("away" if (t_ms // 1000) % 2 == 0 else "home")
        km = float(teams.get(team, {}).get("distance_km", 0))
        return cand({"team": b.team_name(team), "km": num(km, lang, 1)}, team=team) if km >= 1 else None
    if kind == "control":
        ctl = s.get("control") or {}
        team, share = ctl.get("control_team"), ctl.get("control_share")
        if played_s < 30 or team not in ("home", "away") or share is None or float(share) < 0.6:
            return None
        return cand({"team": b.team_name(team), "share": pct(float(share), lang)}, team=team)
    if kind == "chaos":
        ctl = s.get("control") or {}
        if played_s < 30 or float(ctl.get("chaos", 0)) < 0.55:
            return None
        return cand({"changes": num(float(ctl.get("possession_changes_per_min", 0)), lang)}, team=None)
    if kind == "tempo":
        rh = s.get("rhythm") or {}
        trend = rh.get("trend")
        if played_s < 80 or trend not in ("rising", "falling"):
            return None
        return Candidate(t_ms, 0, "tempo_up" if trend == "rising" else "tempo_down", {"apm": num(float(rh.get("actions_per_min", 0)), lang)},
                         max_delay=0)
    if kind == "score":
        if played_s < 40:
            return None
        score = md.score_at(t_ms)
        minute = md.minute(t_ms)
        f = {"minute": str(minute), "minute_ord": minute_ord(minute, lang), "score": score_words(score, lang)}
        if fan:
            us, them = score if club == "home" else (score[1], score[0])
            return cand(f, tones=["lead" if us > them else "level" if us == them else "behind"])
        return cand(f)
    if kind == "win_prob":
        if played_s < 60:
            return None
        if fan:
            return cand({"team": b.team_name(club), "win": pct(win_probability(md, club, t_ms), lang)}, tones=["us"])
        ph, pa = win_probability(md, "home", t_ms), win_probability(md, "away", t_ms)
        team = "home" if ph >= pa else "away"
        return cand({"team": b.team_name(team), "win": pct(max(ph, pa), lang)}, tones=["a"])
    if kind == "fan_colour":
        return cand({"us": md.club_name(club)}, tones=["us"])
    if kind in ("fan_stakes", "fan_rival", "fan_form", "fan_derby"):
        lg = md.league
        mine = md.clubs[club]["short"]
        opp = md.clubs[other(club)]["short"]
        entry = lg.club(mine) if lg else None
        if lg is None or entry is None:
            return None
        score = md.score_at(t_ms)
        if kind == "fan_stakes":
            return cand({"win": ordinal(lg.stakes(club, b.home, b.away, score)["win"], lang)}, tones=["us"])
        if kind == "fan_form":
            wins = str(entry.get("form", "")).count("W")
            return cand({"wins": str(wins)}, tones=["us"]) if wins >= 3 else None
        if kind == "fan_derby":
            return cand({"them": md.club_name(other(club))}, tones=["us"]) if opp in entry.get("rivals", []) else None
        rivals = [r for r in entry.get("rivals", []) if r != opp and lg.club(r)]
        if not rivals:
            return None
        rival = rivals[(t_ms // 60_000) % len(rivals)]
        table = {r["short"]: r for r in lg.table(b.home, b.away, score)}
        return cand({"rival": str(lg.club(rival)["name"]), "rpos": ordinal(table[rival]["pos"], lang),  # type: ignore[index]
                     "pos": ordinal(table[mine]["pos"], lang)}, tones=["us"])
    # player focus
    pid = seg.player
    if pid is None or pid not in md.players:
        return None
    player: Player = md.players[pid]
    pf = {"player": player.surname}
    mine_events = [e for e in md.events if e.known_ms <= t_ms and e.player_id == pid]
    if kind == "player_passes":
        passes = [e for e in mine_events if e.type == "pass"]
        if len(passes) < 2:
            return None
        return cand({**pf, "done": str(sum(e.outcome == "complete" for e in passes)), "total": str(len(passes))}, tones=["p"])
    if kind == "player_speed":
        top = float((s.get("players", {}).get(pid) or {}).get("top_speed_kmh", 0))
        return cand({**pf, "speed": num(top, lang)}, tones=["p"]) if played_s >= 20 and top >= 12 else None
    if kind == "player_rating":
        if len(mine_events) < 2:
            return None
        season = md.league.season_ratings.get(player.name, md.league.default_rating) if md.league else None
        if season is None:
            return None
        return cand({**pf, "rating": num(player_rating(md, pid, t_ms), lang, 1), "season": num(float(season), lang, 1)}, tones=["p"])
    if kind == "player_actions":
        k = len([e for e in mine_events if e.type != "kickoff"])
        return cand({**pf, "k": str(k)}, tones=["p"]) if k >= 3 else None
    if kind == "player_defence":
        k = len([e for e in mine_events if e.type in ("tackle", "interception")])
        return cand({**pf, "k": str(k)}, tones=["p"]) if k >= 1 else None
    if kind == "player_quiet":
        recent = [e for e in mine_events if t_ms - e.known_ms < 30_000]
        return cand(pf, tones=["p"]) if not recent and played_s > 20 else None
    return None


def fill_gaps(b: _Builder, end_ms: int) -> None:
    lo, hi, min_silence = RHYTHM[b.seg.mode]
    kinds = FILLERS[b.seg.mode]
    last_kind_ms: dict[str, int] = {}
    uses: dict[str, int] = {}
    rng = random.Random(f"{b.md.match_id}|{b.seg.id}|fill")
    anchors = list(b.lines)
    prev_start, prev_end = 0, 0
    for nxt in anchors + [None]:
        stop = nxt.start_ms if nxt is not None else end_ms
        while True:
            start = max(prev_start + rng.randint(lo, hi), prev_end + min_silence)
            if start + 1500 + GAP_MS > stop:
                break
            line = _pick_filler(b, kinds, start, stop, last_kind_ms, uses)
            if line is None:
                prev_start, prev_end = start, start  # nothing fits here: try a bit later
                continue
            prev_start, prev_end = line.start_ms, line.end_ms
        if nxt is not None:
            prev_start, prev_end = nxt.start_ms, nxt.end_ms


def _pick_filler(b: _Builder, kinds: list[str], start: int, stop: int, last_kind_ms: dict[str, int], uses: dict[str, int]) -> Line | None:
    ranked = sorted(kinds, key=lambda k: (last_kind_ms.get(k, -10**9), kinds.index(k)))
    if b.seg.mode == "player_focus":  # two of three fillers about the chosen player
        ranked.sort(key=lambda k: (not k.startswith("player_")) if len([1 for k2, t in last_kind_ms.items()
                                                                         if k2.startswith("player_") and start - t < 15_000]) < 2 else 0)
    for kind in ranked:
        if uses.get(kind, 0) >= FILLER_MAX_USES.get(kind, 10**6):
            continue
        if start - last_kind_ms.get(kind, -10**9) < FILLER_MIN_MS.get(kind, REPEAT_MS):
            continue
        c = filler(b, kind, start)
        if c is None:
            continue
        c.prio = 1
        rendered = b.render(c, start)
        if rendered is None:
            continue
        text, template, tone = rendered
        rate, pitch = delivery(b.seg.mode, c.kind, tone)
        dur = estimate_ms(text, b.lang, rate)
        if start + dur + GAP_MS > stop or not b.free(start, dur):
            continue
        last_kind_ms[kind] = start
        uses[kind] = uses.get(kind, 0) + 1
        return b.add(Line(f"{c.kind}-{start}", start, dur, text, c.kind, 1, tone, template, start, rate, pitch))
    return None


# ------------------------------------------------------------------------------------------------ audio keys

VOICES = {"en": ("en-GB", "en-GB-RyanNeural"), "de": ("de-DE", "de-DE-ConradNeural"), "es": ("es-ES", "es-ES-AlvaroNeural")}


def audio_key(lang: str, rate: int, pitch: int, text: str) -> str:
    """Content address of a spoken line: same voice, prosody and text -> same audio file."""
    voice = VOICES[lang][1]
    return hashlib.sha256(f"{voice}|{rate:+d}%|{pitch:+d}%|{text}".encode()).hexdigest()[:24]


def line_key(line: Line, lang: str) -> str:
    return audio_key(lang, line.rate, line.pitch, line.text)

