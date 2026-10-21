"""Templates for every language we broadcast in (EN, DE, ES).

Live graphics (event cards, stat cards, alerts, momentum, player card) are cheap templates filled with
numbers from code: they must appear instantly and cost nothing per segment. The same templates are the
fallback whenever an agent's text fails validation, so a segment never goes without a graphic.
"""

from __future__ import annotations

LANGUAGES = ("en", "de", "es")


def lang_of(lang: str) -> str:
    return lang if lang in LANGUAGES else "en"


def num(value: float, lang: str, decimals: int = 1) -> str:
    text = f"{value:.{decimals}f}"
    return text.replace(".", ",") if lang_of(lang) in ("de", "es") else text


def pct(p: float, lang: str, decimals: int = 1) -> str:
    """Share 0..1 as a localised percentage: 14.8% / 14,8 % / 14,8 %."""
    value = num(p * 100, lang, decimals)
    return f"{value}%" if lang_of(lang) == "en" else f"{value} %"


def minute(clock_s: float) -> int:
    """Football minute shown on the broadcast clock (0:00-0:59 is the 1st minute)."""
    return int(clock_s // 60) + 1


def surname(name: str) -> str:
    return name.split()[-1] if name else name


S: dict[str, dict[str, str]] = {
    # --- event cards ---------------------------------------------------------------------
    "goal.h": {"en": "GOAL! {team}", "de": "TOR! {team}", "es": "¡GOL! {team}"},
    "goal.b": {"en": "{player} scores · {minute}' · {score}", "de": "{player} trifft · {minute}' · {score}",
               "es": "{player} marca · {minute}' · {score}"},
    "goal.for.h": {"en": "GOAL! {team}!", "de": "TOOOR! {team}!", "es": "¡GOOOL! ¡{team}!"},
    "goal.for.b": {"en": "{player} scores for us · {minute}' · {score}", "de": "{player} trifft für uns · {minute}' · {score}",
                   "es": "{player} marca para nosotros · {minute}' · {score}"},
    "goal.against.h": {"en": "Goal against", "de": "Gegentor", "es": "Gol en contra"},
    "goal.against.b": {"en": "{player} scores for {team} · {minute}' · {score}",
                       "de": "{player} trifft für {team} · {minute}' · {score}",
                       "es": "{player} marca para {team} · {minute}' · {score}"},
    "shot.h": {"en": "Shot · {player}", "de": "Abschluss · {player}", "es": "Disparo · {player}"},
    "shot.b": {"en": "{outcome} · {distance} m · {speed} km/h · xG {xg}", "de": "{outcome} · {distance} m · {speed} km/h · xG {xg}",
               "es": "{outcome} · {distance} m · {speed} km/h · xG {xg}"},
    "shot.light.b": {"en": "{player} goes for goal: {outcome}", "de": "{player} versucht es: {outcome}",
                     "es": "{player} lo intenta: {outcome}"},
    "outcome.goal": {"en": "goal", "de": "Tor", "es": "gol"},
    "outcome.saved": {"en": "saved", "de": "gehalten", "es": "parada"},
    "outcome.off_target": {"en": "off target", "de": "vorbei", "es": "fuera"},
    "outcome.blocked": {"en": "blocked", "de": "geblockt", "es": "bloqueado"},
    "turnover.h": {"en": "Ball won · {player}", "de": "Ballgewinn · {player}", "es": "Recuperación · {player}"},
    "turnover.b": {"en": "from {loser}, {distance} m from goal", "de": "gegen {loser}, {distance} m vor dem Tor",
                   "es": "ante {loser}, a {distance} m de la portería"},
    "turnover.lost.h": {"en": "Ball lost · {loser}", "de": "Ballverlust · {loser}", "es": "Pérdida · {loser}"},
    "turnover.lost.b": {"en": "{player} wins it back", "de": "{player} erobert den Ball", "es": "{player} roba el balón"},
    "pass.h": {"en": "Key pass · {player}", "de": "Schlüsselpass · {player}", "es": "Pase clave · {player}"},
    "pass.b": {"en": "to {target} · {distance} m · difficulty {difficulty}/100",
               "de": "auf {target} · {distance} m · Schwierigkeit {difficulty}/100",
               "es": "a {target} · {distance} m · dificultad {difficulty}/100"},
    # --- alerts + milestones ------------------------------------------------------------
    "sprint.h": {"en": "SPRINT · {player}", "de": "SPRINT · {player}", "es": "SPRINT · {player}"},
    "sprint.b": {"en": "{speed} km/h", "de": "{speed} km/h", "es": "{speed} km/h"},
    "ms.first_goal.h": {"en": "First goal of the match", "de": "Erstes Tor des Spiels", "es": "Primer gol del partido"},
    "ms.first_goal.b": {"en": "{player} · {minute}'", "de": "{player} · {minute}'", "es": "{player} · {minute}'"},
    "ms.fastest_shot.h": {"en": "Fastest shot so far", "de": "Härtester Schuss bisher", "es": "Disparo más potente"},
    "ms.fastest_shot.b": {"en": "{player} · {speed} km/h", "de": "{player} · {speed} km/h", "es": "{player} · {speed} km/h"},
    "ms.first_on_target.h": {"en": "First shot on target", "de": "Erster Schuss aufs Tor", "es": "Primer disparo a puerta"},
    "ms.first_on_target.b": {"en": "{player} · {minute}'", "de": "{player} · {minute}'", "es": "{player} · {minute}'"},
    "ms.top_speed.h": {"en": "Top speed of the match", "de": "Topspeed des Spiels", "es": "Velocidad máxima del partido"},
    "ms.top_speed.b": {"en": "{player} · {speed} km/h", "de": "{player} · {speed} km/h", "es": "{player} · {speed} km/h"},
    # --- stats ------------------------------------------------------------------------
    "stat.possession": {"en": "Possession", "de": "Ballbesitz", "es": "Posesión"},
    "stat.pass_accuracy": {"en": "Pass accuracy", "de": "Passquote", "es": "Precisión de pase"},
    "stat.avg_pass_distance": {"en": "Average pass length", "de": "Durchschnittliche Passlänge", "es": "Longitud media de pase"},
    "stat.pass_difficulty": {"en": "Pass difficulty", "de": "Passschwierigkeit", "es": "Dificultad de pase"},
    "stat.pressing": {"en": "Pressing intensity", "de": "Pressingintensität", "es": "Intensidad de presión"},
    "stat.max_shot_speed": {"en": "Hardest shot", "de": "Härtester Schuss", "es": "Disparo más potente"},
    "stat.pressure_index": {"en": "Pressure on the ball", "de": "Druck auf den Ball", "es": "Presión sobre el balón"},
    "stat.top_speed": {"en": "Top speed", "de": "Topspeed", "es": "Velocidad punta"},
    "stat.chaos": {"en": "Control vs chaos", "de": "Kontrolle vs. Chaos", "es": "Control vs. caos"},
    "explain.pass_difficulty": {"en": "0 = simple, 100 = very hard: distance, open lane, marked receiver, pressure",
                                "de": "0 = einfach, 100 = sehr schwer: Distanz, freie Passlinie, Deckung, Druck",
                                "es": "0 = fácil, 100 = muy difícil: distancia, línea libre, marcaje, presión"},
    "explain.pressure_index": {"en": "Opponents within 5 m of the ball carrier, closer counts more; above 1 = swarmed",
                               "de": "Gegner im 5-m-Radius um den Ballführenden, näher zählt mehr; über 1 = umzingelt",
                               "es": "Rivales a menos de 5 m del poseedor, más cerca cuenta más; más de 1 = rodeado"},
    "explain.possession": {"en": "Share of time on the ball", "de": "Anteil der Zeit am Ball", "es": "Porcentaje del tiempo con el balón"},
    "explain.pass_accuracy": {"en": "Completed passes / attempted passes", "de": "Angekommene / gespielte Pässe",
                              "es": "Pases completados / intentados"},
    "explain.top_speed": {"en": "Fastest sprint so far", "de": "Schnellster Sprint bisher", "es": "Sprint más rápido hasta ahora"},
    "explain.chaos": {"en": "0 = one team dictates, 1 = end-to-end chaos", "de": "0 = ein Team diktiert, 1 = wildes Hin und Her",
                      "es": "0 = un equipo manda, 1 = ida y vuelta caótico"},
    # --- momentum (persistent scorebug) -------------------------------------------------
    "mom.control.h": {"en": "{team} in control", "de": "{team} hat die Kontrolle", "es": "{team} controla"},
    "mom.chaos.h": {"en": "Open, chaotic game", "de": "Offenes, wildes Spiel", "es": "Partido abierto y caótico"},
    "mom.b": {"en": "{share} of completed passes · chaos {chaos}", "de": "{share} der angekommenen Pässe · Chaos {chaos}",
              "es": "{share} de los pases completados · caos {chaos}"},
    "mom.for.h": {"en": "We're in control", "de": "Wir haben das Spiel im Griff", "es": "Controlamos el partido"},
    "mom.against.h": {"en": "We're under pressure", "de": "Wir stehen unter Druck", "es": "Estamos bajo presión"},
    "mom.light.b": {"en": "{score}", "de": "{score}", "es": "{score}"},
    # --- player card --------------------------------------------------------------------
    "card.h": {"en": "{player} · #{number} {position}", "de": "{player} · #{number} {position}", "es": "{player} · #{number} {position}"},
    "card.b": {"en": "Top speed {speed} km/h · passes {accuracy} · difficulty {difficulty}",
               "de": "Topspeed {speed} km/h · Passquote {accuracy} · Schwierigkeit {difficulty}",
               "es": "Velocidad punta {speed} km/h · pases {accuracy} · dificultad {difficulty}"},
    # --- Sliding Doors fallback (when the Narrator's text fails validation) ------------
    "sd.h.neutral": {"en": "Sliding Doors · {minute}'", "de": "Sliding Doors · {minute}'", "es": "Sliding Doors · {minute}'"},
    "sd.h.for": {"en": "What if… our {minute}' moment", "de": "Was wäre wenn… unser Moment ({minute}')",
                 "es": "¿Y si…? Nuestro momento ({minute}')"},
    "sd.h.against": {"en": "What if… {minute}'", "de": "Was wäre wenn… {minute}'", "es": "¿Y si…? {minute}'"},
    "sd.h.player": {"en": "{player}'s decision · {minute}'", "de": "{player}s Entscheidung · {minute}'",
                    "es": "La decisión de {player} · {minute}'"},
    "sd.better": {"en": "{alt} would have raised the {measure} from {actual} to {best}.",
                  "de": "Mit {alt} wäre die {measure} von {actual} auf {best} gestiegen.",
                  "es": "Con {alt}, la {measure} habría subido del {actual} al {best}."},
    "sd.worse": {"en": "Right call: {alt} would have cut the {measure} from {actual} to {best}.",
                 "de": "Richtige Wahl: Mit {alt} wäre die {measure} von {actual} auf {best} gefallen.",
                 "es": "Buena decisión: con {alt}, la {measure} habría bajado del {actual} al {best}."},
    "sd.worse.plain": {"en": "{alt} would have cut the {measure} from {actual} to {best}.",
                       "de": "Mit {alt} wäre die {measure} von {actual} auf {best} gefallen.",
                       "es": "Con {alt}, la {measure} habría bajado del {actual} al {best}."},
    "sd.none": {"en": "No tested alternative did clearly better ({measure}: {actual}).",
                "de": "Keine getestete Alternative war klar besser ({measure}: {actual}).",
                "es": "Ninguna alternativa probada fue claramente mejor ({measure}: {actual})."},
    "measure.p_goal": {"en": "chance to score", "de": "Torchance", "es": "probabilidad de gol"},
    "measure.p_keep": {"en": "chance to keep the ball", "de": "Chance, den Ball zu behalten",
                       "es": "probabilidad de conservar el balón"},
    "alt.shoot": {"en": "shooting", "de": "einem Schuss", "es": "un disparo"},
    "alt.carry": {"en": "carrying the ball on", "de": "einem Dribbling", "es": "una conducción"},
    "alt.pass": {"en": "a pass to {target}", "de": "einem Pass auf {target}", "es": "un pase a {target}"},
    "alt.move": {"en": "{player} standing {metres} m tighter", "de": "{player} {metres} m enger am Mann",
                 "es": "{player} {metres} m más cerca"},
    # --- recap fallback -----------------------------------------------------------------
    "recap.h": {"en": "Full time: {home} {score} {away}", "de": "Abpfiff: {home} {score} {away}", "es": "Final: {home} {score} {away}"},
    "recap.h.for": {"en": "Full time: we won {score}!", "de": "Abpfiff: Sieg, {score}!", "es": "Final: ¡ganamos {score}!"},
    "recap.h.against": {"en": "Full time: {score}, not our day", "de": "Abpfiff: {score}, nicht unser Tag",
                        "es": "Final: {score}, no fue nuestro día"},
    "recap.h.player": {"en": "{player}'s match", "de": "{player}s Spiel", "es": "El partido de {player}"},
    "recap.goals": {"en": "Goals: {goals}", "de": "Tore: {goals}", "es": "Goles: {goals}"},
    "recap.possession": {"en": "Possession {home} {hp}, {away} {ap}", "de": "Ballbesitz {home} {hp}, {away} {ap}",
                         "es": "Posesión {home} {hp}, {away} {ap}"},
    "recap.player": {"en": "{player}: top speed {speed} km/h, passes {accuracy}",
                     "de": "{player}: Topspeed {speed} km/h, Passquote {accuracy}",
                     "es": "{player}: velocidad punta {speed} km/h, pases {accuracy}"},
}


def t(key: str, lang: str, **values: object) -> str:
    return S[key][lang_of(lang)].format(**values)
