"""Commentary template pools: language -> kind -> tone -> templates.

Templates contain NO numbers: every number is a {placeholder} filled by the engine from the match data.
Tones: n = neutral TV commentator (casual), a = analyst (sober, stats first), us / them = club fan when our / their
team acts (biased: "we", "us", "they"), p = player focus when the chosen player acts; fan-only and player-only kinds
use their own tones (win/draw/loss, up/same/down). Missing tones fall back to n (see engine.TONE_FALLBACK).
Every rendered line must stay at or under 14 words (tests/test_commentary.py checks all of them).
"""

from __future__ import annotations

from app.commentary.phrases_story import STORY

Pool = dict[str, dict[str, list[str]]]

EN: Pool = {
    # ------------------------------------------------------------------------------------------- events
    "kickoff": {
        "n": ["And we're under way: {home} against {away}.", "Kick-off! {home} and {away}, here we go."],
        "a": ["Kick-off. {home} against {away}, let's see the patterns emerge."],
        "us": ["Here we go! Come on, {us}!", "We're off! Let's get after {them}."],
    },
    "goal": {
        "n": ["Goal! {scorer} scores for {team}! {score}.", "It's in! {scorer} finds the net. {score}."],
        "a": ["Goal, {team}. {scorer} finishes. {score}.", "{scorer} scores for {team}. {score}."],
        "us": ["GOAL! {scorer}! Get in! {score} to us!", "YES! {scorer} scores! What a moment! {score}!"],
        "them": ["Oh no. {scorer} scores for them. {score}.", "They've scored. {scorer}. {score}, heads up, lads."],
        "p": ["Goal! {scorer} scores! {score}!", "It's {scorer}! He finds the net! {score}."],
    },
    "goal_detail": {
        "n": ["From {dist} metres, struck at {speed} km/h.", "{dist} metres out, {speed} km/h, and a chance worth {xg} xG."],
        "a": ["Finish from {dist} metres at {speed} km/h, xG {xg}.", "Chance quality just {xg} xG, from {dist} metres."],
        "us": ["{speed} km/h from {dist} metres, what a strike!", "From {dist} metres! The keeper had no chance!"],
        "them": ["{dist} metres out, {speed} km/h. We left him too much space.", "A chance worth only {xg} xG, and they took it."],
    },
    "goal_assist": {
        "n": ["Set up by {assist}, finished from {dist} metres.", "{assist} with the assist."],
        "a": ["Assist {assist}. Finish from {dist} metres, xG {xg}."],
        "us": ["Lovely ball from {assist}, and {scorer} does the rest!"],
        "them": ["{assist} picked him out, and we didn't close it down."],
    },
    "shot_saved": {
        "n": ["{player} shoots from {dist} metres, saved by {gk}!", "Good save! {gk} keeps out {player}."],
        "a": ["Shot on target, {player} from {dist} metres, xG {xg}. Saved.", "{gk} saves a {speed} km/h effort from {player}."],
        "us": ["So close! {player} from {dist} metres, their keeper saves.", "{player} tests {gk}! Keep shooting, lads!"],
        "them": ["{player} shoots, and {gk} saves! Brilliant from our keeper!", "Big save from {gk}! That was dangerous."],
        "p": ["{player} lets fly from {dist} metres, but {gk} saves.", "Shot from {player}, {speed} km/h, kept out by {gk}."],
    },
    "shot_off": {
        "n": ["{player} shoots from {dist} metres, wide.", "{player} tries his luck, off target."],
        "a": ["{player} shoots from {dist} metres, off target. xG {xg}.", "Off target from {player}, a chance worth {xg} xG."],
        "us": ["Ooh, {player}, just wide! So close!", "{player} from {dist} metres, wide. Next one goes in!"],
        "them": ["{player} shoots for them, wide. Phew.", "Off target from {player}. Let off there."],
        "p": ["{player} goes for goal from {dist} metres, wide.", "Not this time, {player} drags it wide."],
    },
    "shot_blocked": {
        "n": ["{player} shoots, and it's blocked!", "Blocked! {player}'s effort from {dist} metres charged down."],
        "a": ["Blocked shot, {player} from {dist} metres, xG {xg}.", "{player}'s shot is blocked, a chance worth {xg} xG."],
        "us": ["{player} shoots, blocked! Keep the pressure on!", "Blocked! {player} so nearly through for us!"],
        "them": ["{player} shoots, blocked! Bodies on the line from us!", "Great block, that {player} shot was heading in."],
        "p": ["{player} shoots from {dist} metres, blocked.", "{player} pulls the trigger, but it's blocked."],
    },
    "sd_alt": {
        "n": ["Sliding Doors: had {player} {action}, {alt} instead of {actual}.",
              "Sliding Doors: {action_cap} would have given {alt}, not {actual}."],
        "a": ["Sliding Doors: {action}, {player} gets {alt} scoring chance, not {actual}.",
              "Simulated alternative: {action_noun} gives {alt}, versus {actual}."],
    },
    "sd_right": {
        "n": ["Sliding Doors: right call by {player}. {action_cap}? Only {alt}, not {actual}.",
              "Sliding Doors: {player} chose well, {actual} versus {alt} for {action_noun}."],
        "a": ["Sliding Doors: {player}'s choice gave {actual}; {action_noun} only {alt}.",
              "Simulation backs {player}: {actual}, against {alt} for {action_noun}."],
    },
    "sd_none": {
        "n": ["Sliding Doors: a {actual} chance, and no alternative was clearly better.",
              "Sliding Doors: {player}'s decision holds up, {actual} chance to score."],
        "a": ["Sliding Doors: {actual} scoring chance; no tested alternative clearly better.",
              "Simulation: {player}'s decision, {actual} chance, was reasonable."],
    },
    "sd_keep": {
        "n": ["Sliding Doors: only {keep} chance to keep the ball, whatever {player} chose.",
              "Sliding Doors: no safer option for {player}, {keep} chance to keep it."],
        "a": ["Sliding Doors: {keep} chance to keep possession; no alternative clearly safer.",
              "Simulation: none of {player}'s options clearly safer, {keep} retention."],
    },
    "tackle": {
        "n": ["{player} wins it back from {target}.", "Strong tackle from {player}.", "{player} steps in on {target}, ball won."],
        "a": ["Tackle won by {player}, that's {count} for {team}.", "{player} wins the duel with {target}."],
        "us": ["Great tackle, {player}! That's how we do it!", "{player} wins it back! Love that, {player}!"],
        "them": ["{player} robs {target}. We have to be sharper.", "Lost it. {player} wins the tackle for them."],
        "p": ["{player} wins the ball from {target}.", "Big tackle from {player}!"],
    },
    "interception": {
        "n": ["{player} reads it and intercepts.", "Cut out by {player}.", "Intercepted! {player} was waiting for that."],
        "a": ["Interception by {player}, {team}'s {count} so far.", "{player} intercepts, a turnover for {team}."],
        "us": ["{player} reads it! Ball back for us!", "Intercepted by {player}! Go on, lads!"],
        "them": ["Picked off by {player}. Careless from us.", "{player} intercepts for them. Sloppy."],
        "p": ["{player} reads it perfectly, intercepted.", "{player} steps in and cuts it out."],
    },
    "pass_chain": {
        "n": ["{team} keeping it nicely, {n} passes in a row.", "{n} passes on the bounce for {team}."],
        "a": ["{n} consecutive completed passes for {team}.", "Sequence of {n} passes for {team}, pass accuracy {acc}."],
        "us": ["{n} passes in a row! They can't get near us!", "Lovely stuff, {n} passes, keep it moving!"],
        "them": ["{n} passes for them now. We need to get tighter.", "They're passing it around us, {n} in a row."],
    },
    "decisive_pass": {
        "n": ["Brilliant ball from {player} to {target}!", "{player} opens them up, {target} in space."],
        "a": ["Line-breaking pass, {player} to {target}: threat up {gain}.", "{player} finds {target}, raising the scoring chance by {gain}."],
        "us": ["What a ball from {player}! {target} is in!", "{player} splits them open! Go on, {target}!"],
        "them": ["Dangerous ball from {player} to {target}. Watch out!", "{player} carves us open, {target} in behind."],
        "p": ["Superb pass from {player} to {target}!", "{player} sees it, finds {target}, danger!"],
    },
    "pressure": {
        "n": ["{player} closes down {target}.", "Pressure from {player}.", "{player} hunting the ball."],
        "a": ["{player} presses {target} from {dist} metres.", "Pressure on {target}, applied by {player}."],
        "us": ["{player} hunting him down! Love it!", "Get in his face, {player}!", "Pressing from {player}, no time on the ball!"],
        "them": ["They press {target}, quick, move it!", "{player} on {target}'s back, careful.", "Pressure from {player}, we need options."],
        "p": ["{player} closes {target} down.", "{player} presses, no time for {target}."],
    },
    "carry": {
        "n": ["{player} drives forward, {dist} metres with the ball.", "{player} carries it into space."],
        "a": ["Carry of {dist} metres by {player}.", "{player} progresses it {dist} metres on the ball."],
        "us": ["{player} on the charge! {dist} metres!", "Go on, {player}, run at them!"],
        "them": ["{player} running at us, {dist} metres. Stop him!", "{player} carries it for them, nobody stepping in."],
        "p": ["{player} drives forward, {dist} metres.", "{player} takes it on himself, carrying forward."],
    },
    "long_pass": {
        "n": ["Long ball from {player} to {target}.", "{player} switches it, {dist} metres to {target}."],
        "a": ["{dist}-metre pass, {player} to {target}.", "Long distribution: {player} finds {target} over {dist} metres."],
        "us": ["Lovely long ball, {player} to {target}!"],
        "them": ["Long ball for them, {player} to {target}."],
        "p": ["{player} pings it {dist} metres to {target}."],
    },
    "corner": {
        "n": ["Corner to {team}.", "{team} win a corner."],
        "a": ["Corner, {team}. Set-piece chance."],
        "us": ["Corner to us! Come on, get it in the box!", "Corner for us, big lads forward!"],
        "them": ["Corner to them. Concentrate now.", "They've got a corner. Mark up, lads."],
    },
    "free_kick": {
        "n": ["Free kick to {team}.", "{team} have a free kick."],
        "a": ["Free kick, {team}."],
        "us": ["Free kick to us! Good, let's use it.", "Free kick, our ball."],
        "them": ["Free kick to them. Stay switched on.", "They've got a free kick."],
    },
    "penalty": {
        "n": ["Penalty to {team}!"],
        "us": ["Penalty! Penalty to us!"],
        "them": ["Penalty to them. Oh no."],
    },
    "pass_ok": {"p": ["{player} finds {target}.", "Neat from {player}, on to {target}.", "{player} moves it on to {target}."]},
    "pass_bad": {"p": ["{player}'s pass doesn't find its man.", "Loose from {player}, possession lost.", "{player} tries the pass, cut out."]},
    "fulltime": {
        "n": ["Full time! {home} {score} {away}.", "That's it, full time. {score}."],
        "a": ["Full time: {score}. The numbers tell the story."],
        "win": ["Full time! We've won it! {score}!", "That's the whistle! Three points! {score}!"],
        "draw": ["Full time, {score}. A point, we'll take it.", "It finishes {score}. Honours even."],
        "loss": ["Full time. {score}. Not our day.", "It's over, {score}. We go again next week."],
    },
    "stakes_live": {
        "up": ["As it stands, we'd climb to {pos} in the table!", "If it ends like this, we go up to {pos}!"],
        "same": ["As it stands, we'd stay {pos}.", "Right now that keeps us {pos} in the table."],
        "down": ["As it stands, we'd drop to {pos}.", "If it ends like this, we slip to {pos}."],
    },
    # ------------------------------------------------------------------------------------------- fillers
    "possession": {
        "n": ["{home} {ph} of the ball, {away} {pa}.", "Possession so far: {home} {ph}, {away} {pa}."],
        "a": ["Possession: {home} {ph}, {away} {pa}.", "Ball share {ph} to {pa}, {team} on top."],
        "us": ["We've had {p} of the ball, keep it that way!", "{p} possession for us, we're running this."],
        "them": ["They've had {p} of the ball. We need it back.", "{p} possession for them, too much."],
    },
    "passing": {
        "n": ["{team} completing {acc} of their passes.", "{team} have found a teammate with {acc} of passes."],
        "a": ["{team} pass accuracy: {acc}, {done} of {total}.", "{done} of {total} passes completed by {team}, {acc}."],
        "us": ["{acc} of our passes finding a teammate. Tidy!", "We've completed {done} of {total} passes."],
        "them": ["They're completing {acc} of their passes. Close them down!"],
    },
    "shots": {
        "n": ["Shots so far: {home} {sh}, {away} {sa}.", "{home} {sh} shots, {away} {sa}."],
        "a": ["Shot count: {home} {sh}, {away} {sa}.", "Attempts {sh} to {sa}, {home} versus {away}."],
        "us": ["We've had {sh} shots, they've had {sa}. Keep shooting!", "{sh} shots for us so far!"],
        "them": ["They've had {sa} shots to our {sh}. We need more.", "{sa} shots for them, we need to respond."],
    },
    "xg": {
        "n": ["Expected goals so far: {home} {xh}, {away} {xa}."],
        "a": ["xG: {home} {xh}, {away} {xa}.", "Expected goals {xh} to {xa}, {home} against {away}."],
        "us": ["Our chances add up to {xh} expected goals, theirs {xa}."],
        "them": ["Their chances add up to {xa} expected goals, ours {xh}."],
    },
    "top_speed": {
        "n": ["Fastest so far: {player}, {speed} km/h.", "{player} has hit {speed} km/h today."],
        "a": ["Top speed so far: {player}, {speed} km/h.", "Peak sprint: {player} at {speed} km/h."],
        "us": ["{player} flying, {speed} km/h top speed!"],
    },
    "distance": {
        "n": ["{team} have covered {km} kilometres between them.", "{km} kilometres covered by {team} so far."],
        "a": ["Distance covered: {team} {km} kilometres.", "{team} total running: {km} kilometres."],
        "us": ["{km} kilometres covered by us! Working hard!"],
    },
    "control": {
        "n": ["{team} in control right now, {share} of recent possession.", "This spell belongs to {team}."],
        "a": ["Control index: {team} with {share} of recent possession.", "Recent phase: {team} holding {share} of the ball."],
        "us": ["We're on top now, {share} of the recent ball!", "This is our spell, keep pushing!"],
        "them": ["They're on top right now. We need to hang in.", "They've had {share} of the recent ball. Hold firm."],
    },
    "chaos": {
        "n": ["End to end! The ball keeps changing hands.", "Scrappy spell, {changes} turnovers a minute."],
        "a": ["High chaos: {changes} possession changes per minute.", "Unstructured phase, {changes} turnovers per minute."],
        "us": ["Bit frantic out there! Calm it down, lads."],
    },
    "tempo_up": {
        "n": ["The tempo is rising now.", "Things are speeding up, {apm} actions a minute."],
        "a": ["Rhythm rising: {apm} actions per minute.", "Tempo up, {apm} actions per minute in this window."],
    },
    "tempo_down": {
        "n": ["The game has slowed down a little.", "A calmer spell, {apm} actions a minute."],
        "a": ["Rhythm falling: {apm} actions per minute.", "Tempo dropping to {apm} actions per minute."],
    },
    "score": {
        "n": ["{minute_ord} minute here, {score}.", "Into the {minute_ord} minute, {score}."],
        "a": ["Minute {minute}: {score}.", "{minute} minutes played, {score}."],
        "lead": ["{minute} minutes gone, we're ahead, {score}!", "We lead {score}, {minute_ord} minute. Keep going!"],
        "level": ["{minute_ord} minute, {score}. Come on, let's win this!", "Still {score} after {minute} minutes. Push on!"],
        "behind": ["{minute} minutes gone, {score}. We need a goal.", "Behind {score}, {minute_ord} minute. Come on, lads!"],
    },
    "phase": {
        "n": ["{team} in possession, probing.", "Patient build-up from {team}.", "{team} knocking it around, looking for an opening."],
        "us": ["Our ball, nice and patient.", "We've got it, let's build.", "Keep it, lads, move them around."],
        "them": ["They have it, stay compact.", "Their ball, we need to win it back.", "They're knocking it about. Squeeze them!"],
    },
    "win_prob": {
        "a": ["Win probability, model estimate: {team} {win}.", "Our model gives {team} a {win} chance to win."],
        "us": ["Model says {win} we win this. Let's make it more!", "Our chance of winning right now: {win}."],
    },
    "fan_colour": {
        "us": ["Come on, {us}!", "Big shift from everyone in our shirt.", "Let's hear it for the lads!",
               "This crowd is right behind us.", "Keep the shape, keep the faith."],
    },
    "fan_stakes": {
        "us": ["Win this, and we go {win} in the table.", "Three points here would lift us to {win}."],
    },
    "fan_rival": {
        "us": ["{rival} sit {rpos}. As it stands we're {pos}.", "Remember: {rival} are {rpos}, we're {pos} right now."],
    },
    "fan_form": {
        "us": ["{wins} wins in our last five, the lads are flying.", "Form guide: {wins} wins from our last five."],
    },
    "fan_derby": {
        "us": ["It's the derby. Nothing beats beating {them}.", "Derby day against {them}. This one matters."],
    },
    "intro_fan": {
        "us": ["We start the day {pos}. Win this, and it's {win}.", "{pos} before kick-off. Three points would mean {win}."],
    },
    "intro_player": {
        "p": ["All eyes on {full}, number {num}, for {team}.", "Tonight we follow {full}, {team}'s number {num}."],
    },
    "player_passes": {"p": ["{player}: {done} of {total} passes completed.", "{player} has completed {done} of {total} passes."]},
    "player_speed": {"p": ["{player}'s top speed so far: {speed} km/h.", "{player} has clocked {speed} km/h."]},
    "player_rating": {"p": ["{player} rated {rating} so far, season average {season}.", "Live rating for {player}: {rating}. Season: {season}."]},
    "player_actions": {"p": ["{player} involved in {k} actions so far.", "{k} actions on the ball for {player} already."]},
    "player_defence": {"p": ["{player} has won the ball back {k} times.", "{k} ball recoveries for {player}."]},
    "player_quiet": {"p": ["{player} waiting for his moment.", "{player} keeping his position, staying patient."]},
}

DE: Pool = {
    "kickoff": {
        "n": ["Und los geht's: {home} gegen {away}.", "Anstoß! {home} gegen {away}, das Spiel läuft."],
        "a": ["Anstoß. {home} gegen {away}, schauen wir auf die Muster."],
        "us": ["Los geht's! Auf geht's, {us}!", "Anpfiff! Jetzt holen wir uns {them}!"],
    },
    "goal": {
        "n": ["Tor! {scorer} trifft für {team}! {score}.", "Drin! {scorer} macht es. {score}."],
        "a": ["Tor für {team}. Torschütze {scorer}. {score}.", "{scorer} trifft für {team}. {score}."],
        "us": ["TOOOR! {scorer}! Ja! {score} für uns!", "JAAA! {scorer} trifft! Was für ein Moment! {score}!"],
        "them": ["Oh nein. {scorer} trifft für die. {score}.", "Gegentor. {scorer}. {score}, Kopf hoch, Jungs."],
        "p": ["Tor! {scorer} trifft! {score}!", "Es ist {scorer}! Er trifft! {score}."],
    },
    "goal_detail": {
        "n": ["Aus {dist} Metern, mit {speed} km/h.", "{dist} Meter, {speed} km/h, eine Chance von {xg} xG."],
        "a": ["Abschluss aus {dist} Metern, {speed} km/h, xG {xg}.", "Chancenqualität nur {xg} xG, aus {dist} Metern."],
        "us": ["{speed} km/h aus {dist} Metern, was für ein Schuss!", "Aus {dist} Metern! Keine Chance für den Keeper!"],
        "them": ["{dist} Meter, {speed} km/h. Viel zu viel Platz gelassen.", "Nur {xg} xG, und die machen ihn rein."],
    },
    "goal_assist": {
        "n": ["Vorlage {assist}, Abschluss aus {dist} Metern.", "{assist} mit der Vorlage."],
        "a": ["Assist {assist}. Abschluss aus {dist} Metern, xG {xg}."],
        "us": ["Klasse Ball von {assist}, und {scorer} macht den Rest!"],
        "them": ["{assist} findet ihn, und keiner von uns geht drauf."],
    },
    "shot_saved": {
        "n": ["{player} schießt aus {dist} Metern, {gk} hält!", "Gute Parade! {gk} gegen {player}."],
        "a": ["Schuss aufs Tor, {player} aus {dist} Metern, xG {xg}. Gehalten.", "{gk} pariert {player}s Schuss mit {speed} km/h."],
        "us": ["So knapp! {player} aus {dist} Metern, deren Keeper hält.", "{player} prüft {gk}! Weiter schießen, Jungs!"],
        "them": ["{player} schießt, {gk} hält! Stark, unser Keeper!", "Riesenparade von {gk}! Das war gefährlich."],
        "p": ["{player} zieht aus {dist} Metern ab, {gk} hält.", "Schuss von {player}, {speed} km/h, {gk} pariert."],
    },
    "shot_off": {
        "n": ["{player} schießt aus {dist} Metern, vorbei.", "{player} versucht es, daneben."],
        "a": ["{player} aus {dist} Metern, neben das Tor. xG {xg}.", "Vorbei von {player}, eine Chance von {xg} xG."],
        "us": ["Uuh, {player}, knapp vorbei! So nah dran!", "{player} aus {dist} Metern, vorbei. Der nächste sitzt!"],
        "them": ["{player} schießt für die, vorbei. Puh.", "Daneben von {player}. Glück gehabt."],
        "p": ["{player} versucht es aus {dist} Metern, vorbei.", "Diesmal nicht, {player} setzt ihn daneben."],
    },
    "shot_blocked": {
        "n": ["{player} schießt, geblockt!", "Geblockt! {player}s Versuch aus {dist} Metern."],
        "a": ["Geblockter Schuss, {player} aus {dist} Metern, xG {xg}.", "{player}s Schuss geblockt, eine Chance von {xg} xG."],
        "us": ["{player} schießt, geblockt! Druck hochhalten!", "Geblockt! {player} war fast durch!"],
        "them": ["{player} schießt, geblockt! Wir werfen uns rein!", "Starker Block, der Schuss von {player} war gefährlich."],
        "p": ["{player} schießt aus {dist} Metern, geblockt.", "{player} zieht ab, aber geblockt."],
    },
    "sd_alt": {
        "n": ["Sliding Doors: Hätte {player} {action}, {alt} statt {actual}.",
              "Sliding Doors: {action_cap} hätte {alt} gebracht, nicht {actual}."],
        "a": ["Sliding Doors: Hätte {player} {action}, {alt} Torchance statt {actual}.",
              "Simulierte Alternative: {action_noun}, {alt} gegenüber {actual}."],
    },
    "sd_right": {
        "n": ["Sliding Doors: richtige Wahl von {player}. {action_cap}? Nur {alt} statt {actual}.",
              "Sliding Doors: {player} entscheidet gut. {action_cap}: nur {alt} statt {actual}."],
        "a": ["Sliding Doors: {player}s Wahl brachte {actual}; {action_noun} nur {alt}.",
              "Die Simulation stützt {player}: {actual}, {action_noun} nur {alt}."],
    },
    "sd_none": {
        "n": ["Sliding Doors: {actual} Torchance, keine Alternative klar besser.",
              "Sliding Doors: {player}s Entscheidung passt, {actual} Torchance."],
        "a": ["Sliding Doors: {actual} Torchance; keine getestete Alternative klar besser.",
              "Simulation: {player}s Entscheidung mit {actual} Torchance war vernünftig."],
    },
    "sd_keep": {
        "n": ["Sliding Doors: nur {keep} Chance auf Ballbesitz, egal was {player} wählt.",
              "Sliding Doors: keine sicherere Option für {player}, {keep} Ballsicherung."],
        "a": ["Sliding Doors: {keep} Chance, den Ball zu halten; keine Alternative klar sicherer.",
              "Simulation: keine von {player}s Optionen klar sicherer, {keep} Ballsicherung."],
    },
    "tackle": {
        "n": ["{player} erobert den Ball von {target}.", "Starkes Tackling von {player}.", "{player} geht dazwischen, Ball gewonnen."],
        "a": ["Zweikampf gewonnen von {player}, der {count}. für {team}.", "{player} gewinnt das Duell gegen {target}."],
        "us": ["Klasse Tackling, {player}! So geht das!", "{player} holt ihn sich! Stark, {player}!"],
        "them": ["{player} nimmt {target} den Ball ab. Wacher sein!", "Ball weg. {player} gewinnt den Zweikampf für die."],
        "p": ["{player} holt sich den Ball von {target}.", "Starker Zweikampf von {player}!"],
    },
    "interception": {
        "n": ["{player} liest das und fängt ab.", "Abgefangen von {player}.", "Abgefangen! {player} hat darauf gewartet."],
        "a": ["Ballgewinn durch {player}, der {count}. für {team}.", "{player} fängt ab, Ballwechsel für {team}."],
        "us": ["{player} liest das! Ball wieder bei uns!", "Abgefangen von {player}! Los, Jungs!"],
        "them": ["{player} fängt ab. Zu leichtfertig von uns.", "{player} fängt für die ab. Schlampig."],
        "p": ["{player} liest das perfekt, abgefangen.", "{player} geht dazwischen und fängt ab."],
    },
    "pass_chain": {
        "n": ["{team} lässt den Ball laufen, {n} Pässe am Stück.", "{n} Pässe in Folge für {team}."],
        "a": ["{n} angekommene Pässe in Folge für {team}.", "Passfolge von {n} für {team}, Passquote {acc}."],
        "us": ["{n} Pässe am Stück! Die kommen nicht ran!", "Schön, {n} Pässe, weiter so!"],
        "them": ["{n} Pässe für die jetzt. Enger ran!", "Die spielen um uns herum, {n} in Folge."],
    },
    "decisive_pass": {
        "n": ["Herrlicher Ball von {player} auf {target}!", "{player} öffnet die Abwehr, {target} frei."],
        "a": ["Linienbrechender Pass, {player} auf {target}: Gefahr plus {gain}.", "{player} findet {target}, Torchance plus {gain}."],
        "us": ["Was für ein Ball von {player}! {target} ist durch!", "{player} spielt sie schwindlig! Los, {target}!"],
        "them": ["Gefährlicher Ball von {player} auf {target}. Achtung!", "{player} reißt uns auf, {target} hinter der Kette."],
        "p": ["Toller Pass von {player} auf {target}!", "{player} sieht es, findet {target}, Gefahr!"],
    },
    "pressure": {
        "n": ["{player} läuft {target} an.", "Druck von {player}.", "{player} jagt den Ball."],
        "a": ["{player} presst {target} aus {dist} Metern.", "Druck auf {target}, ausgeübt von {player}."],
        "us": ["{player} jagt ihn! Herrlich!", "Drauf, {player}!", "Pressing von {player}, keine Zeit am Ball!"],
        "them": ["Die pressen {target}, schnell, weg damit!", "{player} sitzt {target} im Nacken, Vorsicht.", "Druck von {player}, wir brauchen Optionen."],
        "p": ["{player} läuft {target} an.", "{player} presst, keine Zeit für {target}."],
    },
    "carry": {
        "n": ["{player} marschiert nach vorne, {dist} Meter mit Ball.", "{player} trägt den Ball in den freien Raum."],
        "a": ["Dribbling über {dist} Meter von {player}.", "{player} gewinnt {dist} Meter am Ball."],
        "us": ["{player} geht durch! {dist} Meter!", "Los, {player}, lauf auf sie zu!"],
        "them": ["{player} läuft auf uns zu, {dist} Meter. Stoppt ihn!", "{player} trägt den Ball, keiner greift ein."],
        "p": ["{player} zieht nach vorne, {dist} Meter.", "{player} nimmt es selbst in die Hand."],
    },
    "long_pass": {
        "n": ["Langer Ball von {player} auf {target}.", "{player} verlagert, {dist} Meter auf {target}."],
        "a": ["Pass über {dist} Meter, {player} auf {target}.", "Langer Ball: {player} findet {target} über {dist} Meter."],
        "us": ["Schöner langer Ball, {player} auf {target}!"],
        "them": ["Langer Ball für die, {player} auf {target}."],
        "p": ["{player} schlägt ihn {dist} Meter auf {target}."],
    },
    "corner": {
        "n": ["Ecke für {team}.", "{team} bekommt eine Ecke."],
        "a": ["Ecke, {team}. Standardsituation."],
        "us": ["Ecke für uns! Rein damit in den Strafraum!", "Ecke für uns, die Großen nach vorne!"],
        "them": ["Ecke für die. Jetzt konzentriert.", "Ecke gegen uns. Zuordnen, Jungs."],
    },
    "free_kick": {
        "n": ["Freistoß für {team}.", "{team} hat einen Freistoß."],
        "a": ["Freistoß, {team}."],
        "us": ["Freistoß für uns! Gut, nutzen wir ihn.", "Freistoß, unser Ball."],
        "them": ["Freistoß für die. Wach bleiben.", "Freistoß gegen uns."],
    },
    "penalty": {"n": ["Elfmeter für {team}!"], "us": ["Elfmeter! Elfmeter für uns!"], "them": ["Elfmeter für die. Oh nein."]},
    "pass_ok": {"p": ["{player} findet {target}.", "Sauber von {player}, weiter auf {target}.", "{player} spielt auf {target}."]},
    "pass_bad": {"p": ["{player}s Pass kommt nicht an.", "Ungenau von {player}, Ball weg.", "{player} versucht den Pass, abgefangen."]},
    "fulltime": {
        "n": ["Abpfiff! {home} {score} {away}.", "Das war's, Schluss. {score}."],
        "a": ["Abpfiff: {score}. Die Zahlen erzählen die Geschichte."],
        "win": ["Abpfiff! Wir haben gewonnen! {score}!", "Schluss! Drei Punkte! {score}!"],
        "draw": ["Abpfiff, {score}. Ein Punkt, nehmen wir mit.", "Es endet {score}. Unentschieden."],
        "loss": ["Abpfiff. {score}. Nicht unser Tag.", "Vorbei, {score}. Nächste Woche wieder."],
    },
    "stakes_live": {
        "up": ["Stand jetzt klettern wir auf {pos}!", "Bleibt es so, geht's hoch auf {pos}!"],
        "same": ["Stand jetzt bleiben wir auf {pos}.", "Damit bleiben wir aktuell auf {pos}."],
        "down": ["Stand jetzt rutschen wir auf {pos}.", "Bleibt es so, fallen wir auf {pos}."],
    },
    "possession": {
        "n": ["{home} {ph} Ballbesitz, {away} {pa}.", "Ballbesitz bisher: {home} {ph}, {away} {pa}."],
        "a": ["Ballbesitz: {home} {ph}, {away} {pa}.", "Ballanteil {ph} zu {pa}, {team} vorne."],
        "us": ["{p} Ballbesitz für uns, so soll's sein!", "{p} Ballbesitz, wir haben das im Griff."],
        "them": ["Die hatten {p} Ballbesitz. Wir brauchen den Ball.", "{p} Ballbesitz für die, zu viel."],
    },
    "passing": {
        "n": ["{team} bringt {acc} der Pässe an.", "{team} mit {acc} angekommenen Pässen."],
        "a": ["Passquote {team}: {acc}, {done} von {total}.", "{done} von {total} Pässen angekommen bei {team}, {acc}."],
        "us": ["{acc} unserer Pässe kommen an. Sauber!", "{done} von {total} Pässen angekommen."],
        "them": ["Die bringen {acc} ihrer Pässe an. Enger ran!"],
    },
    "shots": {
        "n": ["Schüsse bisher: {home} {sh}, {away} {sa}.", "{home} {sh} Schüsse, {away} {sa}."],
        "a": ["Torschüsse: {home} {sh}, {away} {sa}.", "Abschlüsse {sh} zu {sa}, {home} gegen {away}."],
        "us": ["{sh} Schüsse für uns, {sa} für die. Weiter so!", "Schon {sh} Schüsse für uns!"],
        "them": ["Die haben {sa} Schüsse, wir {sh}. Da muss mehr kommen.", "{sa} Schüsse für die, wir müssen antworten."],
    },
    "xg": {
        "n": ["Erwartete Tore bisher: {home} {xh}, {away} {xa}."],
        "a": ["xG: {home} {xh}, {away} {xa}.", "Expected Goals {xh} zu {xa}, {home} gegen {away}."],
        "us": ["Unsere Chancen ergeben {xh} erwartete Tore, deren {xa}."],
        "them": ["Deren Chancen ergeben {xa} erwartete Tore, unsere {xh}."],
    },
    "top_speed": {
        "n": ["Am schnellsten bisher: {player}, {speed} km/h.", "{player} kam schon auf {speed} km/h."],
        "a": ["Höchstgeschwindigkeit bisher: {player}, {speed} km/h.", "Topsprint: {player} mit {speed} km/h."],
        "us": ["{player} fliegt, {speed} km/h Spitze!"],
    },
    "distance": {
        "n": ["{team} ist zusammen {km} Kilometer gelaufen.", "{km} Kilometer Laufleistung für {team} bisher."],
        "a": ["Laufleistung: {team} {km} Kilometer.", "{team} gesamt: {km} Kilometer."],
        "us": ["{km} Kilometer gelaufen! Die Jungs ackern!"],
    },
    "control": {
        "n": ["{team} hat gerade die Kontrolle, {share} Ballbesitz zuletzt.", "Diese Phase gehört {team}."],
        "a": ["Kontrolle: {team} mit {share} Ballbesitz im letzten Abschnitt.", "Aktuelle Phase: {team} hält {share} des Balls."],
        "us": ["Wir sind jetzt am Drücker, {share} Ballbesitz zuletzt!", "Das ist unsere Phase, weiter so!"],
        "them": ["Die sind gerade besser. Wir müssen dagegenhalten.", "Die hatten zuletzt {share} Ballbesitz. Standhalten."],
    },
    "chaos": {
        "n": ["Hin und her! Der Ball wechselt ständig.", "Zerfahrene Phase, {changes} Ballwechsel pro Minute."],
        "a": ["Hohes Chaos: {changes} Ballbesitzwechsel pro Minute.", "Unstrukturierte Phase, {changes} Ballverluste pro Minute."],
        "us": ["Ganz schön hektisch! Ruhe reinbringen, Jungs."],
    },
    "tempo_up": {
        "n": ["Das Tempo zieht an.", "Es wird schneller, {apm} Aktionen pro Minute."],
        "a": ["Rhythmus steigt: {apm} Aktionen pro Minute.", "Tempo hoch, {apm} Aktionen pro Minute."],
    },
    "tempo_down": {
        "n": ["Das Spiel beruhigt sich etwas.", "Ruhigere Phase, {apm} Aktionen pro Minute."],
        "a": ["Rhythmus fällt: {apm} Aktionen pro Minute.", "Tempo sinkt auf {apm} Aktionen pro Minute."],
    },
    "score": {
        "n": ["{minute}. Minute, {score}.", "Wir sind in der {minute}. Minute, {score}."],
        "a": ["Minute {minute}: {score}.", "{minute} Minuten gespielt, {score}."],
        "lead": ["{minute}. Minute, wir führen {score}!", "Führung {score}, {minute}. Minute. Weiter so!"],
        "level": ["{minute}. Minute, {score}. Los, holen wir uns das!", "Immer noch {score} nach {minute} Minuten. Weiter!"],
        "behind": ["{minute}. Minute, {score}. Wir brauchen ein Tor.", "Rückstand {score}, {minute}. Minute. Auf geht's!"],
    },
    "phase": {
        "n": ["{team} im Ballbesitz, sucht die Lücke.", "Geduldiger Aufbau von {team}.", "{team} lässt den Ball laufen."],
        "us": ["Unser Ball, schön geduldig.", "Wir haben ihn, jetzt aufbauen.", "Ball halten, Jungs, laufen lassen."],
        "them": ["Die haben den Ball, kompakt bleiben.", "Deren Ball, wir müssen ihn zurückholen.", "Die schieben ihn hin und her. Drauf!"],
    },
    "win_prob": {
        "a": ["Siegwahrscheinlichkeit laut Modell: {team} {win}.", "Unser Modell gibt {team} {win} Siegchance."],
        "us": ["Laut Modell gewinnen wir zu {win}. Da geht mehr!", "Unsere Siegchance gerade: {win}."],
    },
    "fan_colour": {
        "us": ["Auf geht's, {us}!", "Starker Einsatz von allen in unserem Trikot.", "Die Jungs geben alles!",
               "Die Kurve steht hinter uns.", "Ordnung halten, daran glauben."],
    },
    "fan_stakes": {"us": ["Gewinnen wir, geht's auf {win}.", "Drei Punkte hier, und wir stehen auf {win}."]},
    "fan_rival": {"us": ["{rival} steht auf {rpos}. Stand jetzt stehen wir auf {pos}.", "Zur Erinnerung: {rival} {rpos}, wir aktuell {pos}."]},
    "fan_form": {"us": ["{wins} Siege aus den letzten fünf, die Jungs sind in Form.", "Formkurve: {wins} Siege aus fünf."]},
    "fan_derby": {"us": ["Derby! Nichts ist schöner als ein Sieg gegen {them}.", "Derbytag gegen {them}. Das zählt doppelt."]},
    "intro_fan": {"us": ["Vor dem Spiel stehen wir auf {pos}. Mit Sieg geht's auf {win}.", "{pos} vor Anpfiff. Drei Punkte hießen {win}."]},
    "intro_player": {"p": ["Alle Augen auf {full}, die Nummer {num} von {team}.", "Heute im Fokus: {full}, Nummer {num} bei {team}."]},
    "player_passes": {"p": ["{player}: {done} von {total} Pässen angekommen.", "{player} hat {done} von {total} Pässen angebracht."]},
    "player_speed": {"p": ["{player}s Spitzentempo bisher: {speed} km/h.", "{player} kam schon auf {speed} km/h."]},
    "player_rating": {"p": ["{player} bisher mit Note {rating}, Saisonschnitt {season}.", "Live-Bewertung für {player}: {rating}. Saison: {season}."]},
    "player_actions": {"p": ["{player} war schon an {k} Aktionen beteiligt.", "{k} Aktionen am Ball für {player} bisher."]},
    "player_defence": {"p": ["{player} hat den Ball schon {k}-mal erobert.", "{k} Ballgewinne für {player}."]},
    "player_quiet": {"p": ["{player} wartet auf seinen Moment.", "{player} hält die Position, bleibt geduldig."]},
}

ES: Pool = {
    "kickoff": {
        "n": ["Arranca el partido: {home} contra {away}.", "¡Saque inicial! {home} y {away}, empezamos."],
        "a": ["Saque inicial. {home} contra {away}, veamos los patrones."],
        "us": ["¡Vamos allá! ¡Arriba, {us}!", "¡Empezamos! ¡A por {them}!"],
    },
    "goal": {
        "n": ["¡Gol! ¡{scorer} marca para {team}! {score}.", "¡Adentro! {scorer} la mete. {score}."],
        "a": ["Gol de {team}. Marca {scorer}. {score}.", "{scorer} marca para {team}. {score}."],
        "us": ["¡GOOOL! ¡{scorer}! ¡Sí! ¡{score} para nosotros!", "¡SÍ! ¡Marca {scorer}! ¡Qué momento! ¡{score}!"],
        "them": ["Vaya. {scorer} marca para ellos. {score}.", "Nos marcan. {scorer}. {score}, cabeza arriba."],
        "p": ["¡Gol! ¡Marca {scorer}! ¡{score}!", "¡Es {scorer}! ¡La mete! {score}."],
    },
    "goal_detail": {
        "n": ["Desde {dist} metros, a {speed} km/h.", "{dist} metros, {speed} km/h, una ocasión de {xg} xG."],
        "a": ["Remate desde {dist} metros a {speed} km/h, xG {xg}.", "Calidad de ocasión de solo {xg} xG, desde {dist} metros."],
        "us": ["¡{speed} km/h desde {dist} metros, qué disparo!", "¡Desde {dist} metros! ¡El portero no tuvo opción!"],
        "them": ["{dist} metros, {speed} km/h. Le dejamos demasiado espacio.", "Una ocasión de solo {xg} xG, y la metieron."],
    },
    "goal_assist": {
        "n": ["Asistencia de {assist}, remate desde {dist} metros.", "{assist} con la asistencia."],
        "a": ["Asistencia {assist}. Remate desde {dist} metros, xG {xg}."],
        "us": ["¡Qué pase de {assist}, y {scorer} hace el resto!"],
        "them": ["{assist} lo encontró, y nadie salió a cerrar."],
    },
    "shot_saved": {
        "n": ["{player} dispara desde {dist} metros, ¡para {gk}!", "¡Paradón! {gk} le gana a {player}."],
        "a": ["Tiro a puerta, {player} desde {dist} metros, xG {xg}. Parado.", "{gk} detiene un disparo de {player} a {speed} km/h."],
        "us": ["¡Uy! {player} desde {dist} metros, para su portero.", "¡{player} pone a prueba a {gk}! ¡Seguid tirando!"],
        "them": ["¡{player} dispara y para {gk}! ¡Enorme nuestro portero!", "¡Paradón de {gk}! Eso era peligroso."],
        "p": ["{player} dispara desde {dist} metros, pero para {gk}.", "Disparo de {player}, {speed} km/h, lo detiene {gk}."],
    },
    "shot_off": {
        "n": ["{player} dispara desde {dist} metros, fuera.", "{player} lo intenta, desviado."],
        "a": ["{player} desde {dist} metros, fuera. xG {xg}.", "Disparo fuera de {player}, una ocasión de {xg} xG."],
        "us": ["¡Uy, {player}, por poco! ¡Casi!", "{player} desde {dist} metros, fuera. ¡La próxima entra!"],
        "them": ["{player} dispara para ellos, fuera. Uf.", "Disparo fuera de {player}. Nos salvamos."],
        "p": ["{player} busca la portería desde {dist} metros, fuera.", "Esta vez no, {player} la manda fuera."],
    },
    "shot_blocked": {
        "n": ["{player} dispara, ¡y bloqueado!", "¡Bloqueado! El disparo de {player} desde {dist} metros."],
        "a": ["Disparo bloqueado, {player} desde {dist} metros, xG {xg}.", "Bloquean a {player}, una ocasión de {xg} xG."],
        "us": ["¡{player} dispara, bloqueado! ¡Seguid apretando!", "¡Bloqueado! ¡{player} casi se escapa!"],
        "them": ["¡{player} dispara, bloqueado! ¡Nos tiramos al suelo!", "Gran bloqueo, el disparo de {player} iba dentro."],
        "p": ["{player} dispara desde {dist} metros, bloqueado.", "{player} aprieta el gatillo, pero lo bloquean."],
    },
    "sd_alt": {
        "n": ["Sliding Doors: si {player} hubiera {action}, {alt} en vez de {actual}.",
              "Sliding Doors: {action_cap} habría dado {alt}, no {actual}."],
        "a": ["Sliding Doors: si {player} hubiera {action}, {alt} de ocasión, no {actual}.",
              "Alternativa simulada: {action_noun}, {alt} frente a {actual}."],
    },
    "sd_right": {
        "n": ["Sliding Doors: buena decisión de {player}. ¿{action_cap}? Solo {alt}, no {actual}.",
              "Sliding Doors: {player} eligió bien. {action_cap}: solo {alt}, no {actual}."],
        "a": ["Sliding Doors: la opción de {player} dio {actual}; {action_noun}, solo {alt}.",
              "La simulación respalda a {player}: {actual}; {action_noun}, solo {alt}."],
    },
    "sd_none": {
        "n": ["Sliding Doors: ocasión del {actual}, ninguna alternativa claramente mejor.",
              "Sliding Doors: la decisión de {player} se sostiene, {actual} de ocasión."],
        "a": ["Sliding Doors: {actual} de ocasión; ninguna alternativa probada claramente mejor.",
              "Simulación: la decisión de {player}, {actual} de ocasión, fue razonable."],
    },
    "sd_keep": {
        "n": ["Sliding Doors: solo {keep} de conservar el balón, eligiera lo que eligiera {player}.",
              "Sliding Doors: ninguna opción más segura para {player}, {keep} de conservarlo."],
        "a": ["Sliding Doors: {keep} de conservar la posesión; ninguna alternativa claramente más segura.",
              "Simulación: ninguna opción de {player} claramente más segura, {keep} de retención."],
    },
    "tackle": {
        "n": ["{player} le roba el balón a {target}.", "Buena entrada de {player}.", "{player} se impone a {target}, balón recuperado."],
        "a": ["Entrada ganada por {player}, la número {count} de {team}.", "{player} gana el duelo a {target}."],
        "us": ["¡Gran entrada, {player}! ¡Así se hace!", "¡{player} la recupera! ¡Me encanta, {player}!"],
        "them": ["{player} le roba a {target}. Hay que estar más atentos.", "La perdimos. {player} gana la entrada para ellos."],
        "p": ["{player} le quita el balón a {target}.", "¡Entradón de {player}!"],
    },
    "interception": {
        "n": ["{player} lo lee e intercepta.", "Cortado por {player}.", "¡Interceptado! {player} lo estaba esperando."],
        "a": ["Intercepción de {player}, la número {count} de {team}.", "{player} intercepta, pérdida para el rival."],
        "us": ["¡{player} lo lee! ¡Balón nuestro!", "¡Interceptado por {player}! ¡Vamos!"],
        "them": ["{player} la corta. Demasiado descuidados.", "{player} intercepta para ellos. Qué despiste."],
        "p": ["{player} lo lee perfecto, interceptado.", "{player} se anticipa y corta el pase."],
    },
    "pass_chain": {
        "n": ["{team} mueve bien el balón, {n} pases seguidos.", "{n} pases seguidos para {team}."],
        "a": ["{n} pases completados consecutivos para {team}.", "Secuencia de {n} pases de {team}, precisión {acc}."],
        "us": ["¡{n} pases seguidos! ¡No la huelen!", "Qué bonito, {n} pases, ¡seguid así!"],
        "them": ["{n} pases para ellos ya. Hay que apretar.", "Nos la mueven, {n} seguidos."],
    },
    "decisive_pass": {
        "n": ["¡Pase brillante de {player} para {target}!", "{player} los abre, {target} solo."],
        "a": ["Pase entre líneas, {player} para {target}: peligro más {gain}.", "{player} encuentra a {target}, ocasión más {gain}."],
        "us": ["¡Qué pase de {player}! ¡{target} se va solo!", "¡{player} los parte! ¡Vamos, {target}!"],
        "them": ["Pase peligroso de {player} a {target}. ¡Cuidado!", "{player} nos abre, {target} a la espalda."],
        "p": ["¡Pasazo de {player} para {target}!", "{player} lo ve, encuentra a {target}, ¡peligro!"],
    },
    "pressure": {
        "n": ["{player} presiona a {target}.", "Presión de {player}.", "{player} va a por el balón."],
        "a": ["{player} presiona a {target} a {dist} metros.", "Presión sobre {target}, de {player}."],
        "us": ["¡{player} va a por él! ¡Así!", "¡Encima, {player}!", "¡Presión de {player}, sin tiempo para pensar!"],
        "them": ["Presionan a {target}, ¡rápido, suéltala!", "{player} encima de {target}, cuidado.", "Presión de {player}, necesitamos opciones."],
        "p": ["{player} presiona a {target}.", "{player} aprieta, sin tiempo para {target}."],
    },
    "carry": {
        "n": ["{player} avanza, {dist} metros con el balón.", "{player} conduce hacia el espacio."],
        "a": ["Conducción de {dist} metros de {player}.", "{player} progresa {dist} metros con balón."],
        "us": ["¡{player} lanzado! ¡{dist} metros!", "¡Vamos, {player}, encáralos!"],
        "them": ["{player} viene hacia nosotros, {dist} metros. ¡Paradlo!", "{player} conduce para ellos, nadie sale."],
        "p": ["{player} avanza, {dist} metros.", "{player} se la echa al hombro y conduce."],
    },
    "long_pass": {
        "n": ["Balón largo de {player} para {target}.", "{player} cambia de banda, {dist} metros para {target}."],
        "a": ["Pase de {dist} metros, {player} para {target}.", "Envío largo: {player} encuentra a {target} a {dist} metros."],
        "us": ["¡Qué balón largo, {player} para {target}!"],
        "them": ["Balón largo para ellos, {player} a {target}."],
        "p": ["{player} la manda {dist} metros a {target}."],
    },
    "corner": {
        "n": ["Córner para {team}.", "{team} saca de esquina."],
        "a": ["Córner, {team}. Balón parado."],
        "us": ["¡Córner a favor! ¡Métela al área!", "Córner para nosotros, ¡los altos arriba!"],
        "them": ["Córner para ellos. Concentración.", "Córner en contra. Marcad, chicos."],
    },
    "free_kick": {
        "n": ["Falta a favor de {team}.", "{team} tiene un tiro libre."],
        "a": ["Tiro libre, {team}."],
        "us": ["¡Falta a favor! Hay que aprovecharla.", "Tiro libre, balón nuestro."],
        "them": ["Falta para ellos. Atentos.", "Tiro libre en contra."],
    },
    "penalty": {"n": ["¡Penalti para {team}!"], "us": ["¡Penalti! ¡Penalti a favor!"], "them": ["Penalti para ellos. Vaya."]},
    "pass_ok": {"p": ["{player} encuentra a {target}.", "Limpio de {player}, para {target}.", "{player} se la da a {target}."]},
    "pass_bad": {"p": ["El pase de {player} no llega.", "Impreciso {player}, balón perdido.", "{player} intenta el pase, cortado."]},
    "fulltime": {
        "n": ["¡Final! {home} {score} {away}.", "Se acabó, final del partido. {score}."],
        "a": ["Final: {score}. Los números cuentan la historia."],
        "win": ["¡Final! ¡Hemos ganado! ¡{score}!", "¡Pitido final! ¡Tres puntos! ¡{score}!"],
        "draw": ["Final, {score}. Un punto, lo aceptamos.", "Termina {score}. Reparto de puntos."],
        "loss": ["Final. {score}. No era nuestro día.", "Se acabó, {score}. La semana que viene, otra vez."],
    },
    "stakes_live": {
        "up": ["Tal como va, ¡subimos al puesto {pos}!", "Si acaba así, ¡escalamos al puesto {pos}!"],
        "same": ["Tal como va, seguimos en el puesto {pos}.", "Ahora mismo nos mantiene en el puesto {pos}."],
        "down": ["Tal como va, caemos al puesto {pos}.", "Si acaba así, bajamos al puesto {pos}."],
    },
    "possession": {
        "n": ["{home} con el {ph} del balón, {away} {pa}.", "Posesión: {home} {ph}, {away} {pa}."],
        "a": ["Posesión: {home} {ph}, {away} {pa}.", "Reparto del balón {ph} a {pa}, domina {team}."],
        "us": ["Tenemos el {p} del balón, ¡así!", "{p} de posesión para nosotros, mandamos."],
        "them": ["Ellos han tenido el {p} del balón. Hay que recuperarlo.", "{p} de posesión para ellos, demasiado."],
    },
    "passing": {
        "n": ["{team} completa el {acc} de sus pases.", "{team} acierta el {acc} de los pases."],
        "a": ["Precisión de pase de {team}: {acc}, {done} de {total}.", "{done} de {total} pases completados por {team}, {acc}."],
        "us": ["El {acc} de nuestros pases llega. ¡Limpio!", "Hemos completado {done} de {total} pases."],
        "them": ["Completan el {acc} de sus pases. ¡Hay que apretar!"],
    },
    "shots": {
        "n": ["Disparos: {home} {sh}, {away} {sa}.", "{home} {sh} disparos, {away} {sa}."],
        "a": ["Remates: {home} {sh}, {away} {sa}.", "Disparos {sh} a {sa}, {home} contra {away}."],
        "us": ["{sh} disparos nuestros, {sa} de ellos. ¡Seguid tirando!", "¡Ya llevamos {sh} disparos!"],
        "them": ["Ellos llevan {sa} disparos, nosotros {sh}. Hace falta más.", "{sa} disparos de ellos, hay que responder."],
    },
    "xg": {
        "n": ["Goles esperados: {home} {xh}, {away} {xa}."],
        "a": ["xG: {home} {xh}, {away} {xa}.", "Goles esperados {xh} a {xa}, {home} contra {away}."],
        "us": ["Nuestras ocasiones suman {xh} goles esperados, las suyas {xa}."],
        "them": ["Sus ocasiones suman {xa} goles esperados, las nuestras {xh}."],
    },
    "top_speed": {
        "n": ["El más rápido: {player}, {speed} km/h.", "{player} ya ha llegado a {speed} km/h."],
        "a": ["Velocidad máxima: {player}, {speed} km/h.", "Sprint máximo: {player} a {speed} km/h."],
        "us": ["¡{player} vuela, {speed} km/h de punta!"],
    },
    "distance": {
        "n": ["{team} ha recorrido {km} kilómetros en total.", "{km} kilómetros recorridos por {team}."],
        "a": ["Distancia recorrida: {team} {km} kilómetros.", "{team} en total: {km} kilómetros."],
        "us": ["¡{km} kilómetros recorridos! ¡Cómo trabajan!"],
    },
    "control": {
        "n": ["{team} controla ahora, {share} de la posesión reciente.", "Este tramo es de {team}."],
        "a": ["Control: {team} con el {share} de la posesión reciente.", "Fase actual: {team} con el {share} del balón."],
        "us": ["¡Ahora mandamos, {share} del balón reciente!", "¡Es nuestro momento, seguid apretando!"],
        "them": ["Ahora dominan ellos. Hay que aguantar.", "Han tenido el {share} del balón reciente. Firmes."],
    },
    "chaos": {
        "n": ["¡Ida y vuelta! El balón cambia de manos sin parar.", "Fase desordenada, {changes} pérdidas por minuto."],
        "a": ["Caos alto: {changes} cambios de posesión por minuto.", "Fase sin estructura, {changes} pérdidas por minuto."],
        "us": ["¡Mucho lío ahí fuera! Calma, chicos."],
    },
    "tempo_up": {
        "n": ["Sube el ritmo.", "Esto se acelera, {apm} acciones por minuto."],
        "a": ["Ritmo al alza: {apm} acciones por minuto.", "Tempo arriba, {apm} acciones por minuto."],
    },
    "tempo_down": {
        "n": ["El partido se calma un poco.", "Fase tranquila, {apm} acciones por minuto."],
        "a": ["Ritmo a la baja: {apm} acciones por minuto.", "El tempo baja a {apm} acciones por minuto."],
    },
    "score": {
        "n": ["Minuto {minute}, {score}.", "Estamos en el minuto {minute}, {score}."],
        "a": ["Minuto {minute}: {score}.", "{minute} minutos jugados, {score}."],
        "lead": ["Minuto {minute}, ¡ganamos {score}!", "Vamos {score}, minuto {minute}. ¡Seguid!"],
        "level": ["Minuto {minute}, {score}. ¡Vamos a ganarlo!", "Sigue {score} tras {minute} minutos. ¡Arriba!"],
        "behind": ["Minuto {minute}, {score}. Necesitamos un gol.", "Perdemos {score}, minuto {minute}. ¡Vamos, chicos!"],
    },
    "phase": {
        "n": ["{team} tiene el balón, busca el hueco.", "Construcción paciente de {team}.", "{team} mueve el balón, buscando espacio."],
        "us": ["Balón nuestro, con paciencia.", "La tenemos, a construir.", "Tocad, chicos, que corran ellos."],
        "them": ["La tienen ellos, juntos atrás.", "Balón suyo, hay que recuperarlo.", "Nos la mueven. ¡Apretad!"],
    },
    "win_prob": {
        "a": ["Probabilidad de victoria según el modelo: {team} {win}.", "Nuestro modelo da a {team} un {win} de ganar."],
        "us": ["El modelo dice {win} de ganar. ¡Hay que subirlo!", "Probabilidad de ganar ahora mismo: {win}."],
    },
    "fan_colour": {
        "us": ["¡Vamos, {us}!", "Qué esfuerzo de todos los nuestros.", "¡Arriba esos chicos!",
               "La grada está con nosotros.", "Orden y fe, chicos."],
    },
    "fan_stakes": {"us": ["Si ganamos, subimos al puesto {win}.", "Tres puntos aquí nos ponen en el puesto {win}."]},
    "fan_rival": {"us": ["{rival} está en el puesto {rpos}. Ahora vamos en el puesto {pos}.", "Ojo: {rival} va en el puesto {rpos}, nosotros en el {pos}."]},
    "fan_form": {"us": ["{wins} victorias en los últimos cinco, estamos en racha.", "Racha: {wins} victorias de cinco."]},
    "fan_derby": {"us": ["Es el derbi. Nada como ganarle a {them}.", "Día de derbi contra {them}. Este cuenta doble."]},
    "intro_fan": {"us": ["Empezamos el día en el puesto {pos}. Si ganamos, el {win}.", "Puesto {pos} antes del inicio. Tres puntos nos subirían al {win}."]},
    "intro_player": {"p": ["Todos los ojos en {full}, el número {num} de {team}.", "Hoy seguimos a {full}, el {num} de {team}."]},
    "player_passes": {"p": ["{player}: {done} de {total} pases completados.", "{player} ha completado {done} de {total} pases."]},
    "player_speed": {"p": ["Velocidad máxima de {player}: {speed} km/h.", "{player} ya ha llegado a {speed} km/h."]},
    "player_rating": {"p": ["{player} lleva un {rating}, media de la temporada {season}.", "Nota en directo de {player}: {rating}. Temporada: {season}."]},
    "player_actions": {"p": ["{player} ya ha participado en {k} acciones.", "{k} acciones con balón para {player}."]},
    "player_defence": {"p": ["{player} ha recuperado el balón {k} veces.", "{k} recuperaciones para {player}."]},
    "player_quiet": {"p": ["{player} espera su momento.", "{player} mantiene la posición, con paciencia."]},
}

PHRASES: dict[str, Pool] = {"en": EN, "de": DE, "es": ES}
for _lang, _pool in STORY.items():  # the analysis lines (narrative.py)
    PHRASES[_lang].update(_pool)

# Sliding Doors alternatives, per language: (verb phrase for "had he ...", noun phrase for "a ... would give")
ACTIONS: dict[str, dict[str, tuple[str, str]]] = {
    "en": {"carry": ("carried it forward", "carrying on"), "shoot": ("shot", "a shot"), "pass": ("passed to {target}", "a pass to {target}")},
    "de": {"carry": ("den Ball weitergetragen", "ein Dribbling"), "shoot": ("geschossen", "ein Schuss"),
           "pass": ("zu {target} gepasst", "ein Pass zu {target}")},
    "es": {"carry": ("conducido", "conducir"), "shoot": ("disparado", "un disparo"), "pass": ("pasado a {target}", "un pase a {target}")},
}

NUMBER_WORDS = {
    "en": ["nil", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"],
    "de": ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn"],
    "es": ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez"],
}
