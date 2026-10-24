"""Phrases for the commentator's analysis lines (app.commentary.narrative): momentum, the story since a goal,
the spell summaries, the move behind a goal, season milestones and why a key moment matters.

Same rules as phrases.py: no digits in templates (numbers come from the data through fields), at most 14 words
once filled, tones n (neutral TV) / a (analyst, drier, more numbers) / us + them (club fan) / p (player focus).
"""

from __future__ import annotations

Pool = dict[str, dict[str, list[str]]]

EN: Pool = {
    "why_chance_missed": {
        "n": ["Key moment: a {xg} xG chance from {dist} metres goes begging.", "A big chance, worth {xg} xG, and no goal."],
        "a": ["Missed big chance: {xg} xG from {dist} metres. Finishing is costing {team}.", "Chance quality {xg} xG, converted zero. {team} wasteful."],
        "us": ["That's the kind of chance we have to take!", "So close! We need to be more clinical."],
        "them": ["They should have scored there. Big let-off!", "Phew! That was a real chance for them."],
        "p": ["{player} won't want to see that again, {xg} xG.", "A big chance for {player}, worth {xg} xG. Missed."],
    },
    "momentum_swing": {
        "n": ["The game has turned. {team} are on top now.", "Momentum swing! {team} have taken over this game."],
        "a": ["Momentum has flipped: {team} with {share} of the ball in this spell.",
              "Shift in control. {team} now dictate, {share} of possession since the change."],
        "us": ["We've turned it around! We're on top now!", "The tide's turning our way, come on!"],
        "them": ["They've taken over now. We need to weather this.", "Momentum's gone to them. Dig in, lads!"],
    },
    "momentum_take": {
        "n": ["{team} starting to take a grip on this game.", "{team} settling into the better rhythm."],
        "a": ["{team} establishing control: {share} of the ball in this phase.", "First clear pattern: {team} dominating territory."],
        "us": ["We're getting a grip on this now!", "This is more like it, we're on top!"],
        "them": ["They're settling better than us early on.", "They've started the stronger. Wake up!"],
    },
    "momentum_push": {
        "n": ["{team} turning the screw now.", "Wave after wave from {team}.", "{team} camped in the final third."],
        "a": ["Sustained pressure from {team}: {sh} shots in this spell.", "Peak pressure phase for {team}, the opponents can't get out."],
        "us": ["Keep pushing, they can't get out!", "We're all over them now!"],
        "them": ["We're pinned back here. Clear it!", "They're throwing everything at us. Hold on!"],
    },
    "goal_move_regain": {
        "n": ["And it all started with {starter} winning the ball, {secs} seconds earlier.",
              "Won by {starter}, in the net {secs} seconds later."],
        "a": ["Transition goal: ball won by {starter}, shot {secs} seconds later.", "Regain to goal in {secs} seconds. That is the counter-attack."],
        "us": ["And it started with {starter} winning it back! Brilliant!", "{starter} wins it, {secs} seconds later we're celebrating!"],
        "them": ["We gave it away, and {secs} seconds later it's in.", "Lost it, punished in {secs} seconds. That hurts."],
    },
    "goal_move_pass": {
        "n": ["A move of {passes}, {secs} seconds from {starter} to the finish.", "{passes}, {players} players involved. Lovely team goal."],
        "a": ["Build-up: {passes} in {secs} seconds, {players} players involved.", "Sequence: {passes}, {secs} seconds, started by {starter}."],
        "us": ["What a move! {passes} and it's in!", "{passes}, {players} players, one goal. Beautiful!"],
        "them": ["They cut right through us. {passes} and that's it.", "{passes} and we never got near them."],
    },
    "goal_move_set": {
        "n": ["And it came from a set piece.", "Set-piece goal. All that work on the training ground."],
        "a": ["Origin: set piece. Dead-ball situations decide games.", "Goal from a restart. Set-piece threat confirmed."],
        "us": ["Straight off the training ground!", "Set piece, goal. Love it!"],
        "them": ["From a set piece. That's so avoidable.", "A set piece. We have to defend that better."],
    },
    "goal_season": {
        "n": ["That's {scorer}'s {count} goal of the season.", "{scorer} now has {goals} league goals this season."],
        "a": ["Season tally for {scorer}: {goals} goals in {apps} games.", "{scorer}: {goals} goals this season, his {count} in {apps} games."],
        "us": ["{count} of the season for {scorer}! What a player!", "{scorer} again! That's {goals} this season!"],
        "them": ["His {count} of the season. We knew he was dangerous.", "{scorer}, {goals} goals this season now."],
        "p": ["{scorer}'s {count} goal of the season!", "{goals} league goals this season for {scorer} now."],
    },
    "goal_season_first": {
        "n": ["And that's {scorer}'s first goal of the season.", "His first of the season, a big moment for {scorer}."],
        "a": ["First league goal of the season for {scorer}, in his {apps} game.", "Season tally opened: {scorer}, first goal."],
        "us": ["His first of the season, and what a time to get it!", "Finally! {scorer} gets off the mark this season!"],
        "them": ["His first goal of the season, and it's against us.", "He hadn't scored all season. Typical."],
        "p": ["{scorer} is off the mark for the season!", "First goal of the season for {scorer}!"],
    },
    "since_goal_reply": {
        "n": ["Since going behind, {team} have responded: {sh} shots to {sa}.", "{team} have reacted well since the goal, {share} of the ball."],
        "a": ["Post-goal phase: {team} {sh} shots to {sa}, {share} possession.", "Game state effect: trailing {team} now dominate, {share} of the ball."],
        "us": ["We've responded well since that goal, keep going!", "Since their goal it's been all us!"],
        "them": ["Since the goal they've come at us. Stay calm.", "They've reacted. We're sitting too deep."],
    },
    "since_goal_hold": {
        "n": ["Since the goal, {team} have kept control: {share} of the ball.", "{team} managing the lead well since the goal."],
        "a": ["Post-goal phase: {team} keep {share} possession, opponents {sa} shots.", "Lead managed: {team} {share} of the ball since scoring."],
        "us": ["We've kept the ball nicely since the goal.", "Controlling it since the goal, perfect!"],
        "them": ["Since the goal we can't get the ball off them.", "We need to do more. They've controlled it since the goal."],
    },
    "spell": {
        "n": ["{minute} minutes played. {team} the better side so far.", "{minute} minutes in, and {team} are edging this."],
        "a": ["{minute} minutes: shots {sh} to {sa}, xG {xh} to {xa}.", "Last quarter-hour: {team} with {share} of the ball."],
        "us": ["{minute} minutes and we're the better side!", "{minute} minutes gone, we're running this!"],
        "them": ["{minute} minutes. They've had the better of it so far.", "{minute} minutes, and we need to improve."],
        "p": ["{minute} minutes: {player} rated {rating} so far.", "{minute} minutes in. {player} at {rating}, season average {season}."],
    },
    "spell_even": {
        "n": ["{minute} minutes played, and nothing between the sides.", "{minute} minutes, still very even."],
        "a": ["{minute} minutes: even contest. Shots {sh} to {sa}, xG {xh} to {xa}.", "{minute} minutes, balanced: {ph} to {pa} possession."],
        "us": ["{minute} minutes, tight game. One moment could decide it.", "{minute} minutes, it's even. Let's push on!"],
        "them": ["{minute} minutes, it's even. Stay switched on.", "{minute} minutes, nothing in it yet."],
        "p": ["{minute} minutes: {player} rated {rating} so far.", "{minute} minutes in. {player} at {rating}, season average {season}."],
    },
    "why_turnover": {
        "n": ["Key moment: {loser} gives it away just {dist} metres from his own goal.", "That's the danger: lost {dist} metres from goal."],
        "a": ["Key moment: turnover {dist} metres from goal. Highest-risk zone on the pitch.",
              "Why it matters: possession lost {dist} metres out, no cover behind."],
        "us": ["Big moment! {winner} wins it high up the pitch!", "{winner} steals it, right where it hurts them!"],
        "them": ["Lost it {dist} metres from our goal. Can't do that!", "Careless! {loser} loses it far too deep."],
    },
    "why_turnover_shot": {
        "n": ["Key moment: {winner} wins it, and {secs} seconds later there's a shot.", "That's why it matters: lost, and a shot within {secs} seconds."],
        "a": ["Key moment: regain to shot in {secs} seconds. Classic transition.", "Turnover {dist} metres from goal, shot after {secs} seconds."],
        "us": ["{winner} wins it and we're shooting {secs} seconds later!", "That's how you punish a mistake!"],
        "them": ["Lost it, and {secs} seconds later they're shooting. Dangerous!", "That's what happens when we give it away."],
    },
    "why_chance": {
        "n": ["That was their best chance yet, worth {xg} xG.", "Key moment: {team}'s biggest chance of the game so far."],
        "a": ["Key moment: {xg} xG, the best chance of the game so far for {team}.",
              "Highest-quality chance yet for {team}: {xg} xG from {dist} metres."],
        "us": ["That was our best chance yet! So close!", "Best chance of the game, we have to bury those!"],
        "them": ["Their best chance so far. That was a let-off.", "Phew. Their biggest chance yet, we got lucky."],
        "p": ["{player}'s chance was the best of the game so far.", "Biggest chance of the game for {player}, {xg} xG."],
    },
    "intro_context": {
        "n": ["{home} start the day {hpos}, {away} {apos}.", "Table check: {home} {hpos}, {away} {apos}."],
        "a": ["Context: {home} {hpos}, {hwins} wins from five. {away} {apos}, {awins} wins.",
              "Form guide: {home} {hwins} wins in five, {away} {awins} wins."],
    },
}

DE: Pool = {
    "why_chance_missed": {
        "n": ["Schlüsselmoment: eine {xg}-xG-Chance aus {dist} Metern, vergeben.", "Eine große Chance, {xg} xG, und kein Tor."],
        "a": ["Großchance vergeben: {xg} xG aus {dist} Metern. Die Chancenverwertung kostet {team}.",
              "Chancenqualität {xg} xG, kein Tor. {team} zu verschwenderisch."],
        "us": ["So eine Chance müssen wir machen!", "So knapp! Wir müssen kaltschnäuziger werden."],
        "them": ["Da hätten die treffen müssen. Glück gehabt!", "Puh! Das war eine echte Chance für die."],
        "p": ["{player} will die Szene nicht nochmal sehen, {xg} xG.", "Große Chance für {player}, {xg} xG. Vergeben."],
    },
    "momentum_swing": {
        "n": ["Das Spiel hat sich gedreht. Jetzt ist {team} am Drücker.", "Der Wind hat gedreht! {team} übernimmt."],
        "a": ["Momentum gekippt: {team} mit {share} Ballbesitz in dieser Phase.", "Kontrollwechsel. {team} bestimmt jetzt, {share} Ballbesitz."],
        "us": ["Wir haben das Spiel gedreht! Jetzt sind wir dran!", "Es kippt in unsere Richtung, komm schon!"],
        "them": ["Die haben jetzt übernommen. Durchhalten!", "Das Momentum ist bei denen. Dagegenhalten, Jungs!"],
    },
    "momentum_take": {
        "n": ["{team} bekommt das Spiel langsam in den Griff.", "{team} findet den besseren Rhythmus."],
        "a": ["{team} etabliert Kontrolle: {share} Ballbesitz in dieser Phase.", "Erstes klares Muster: {team} dominiert das Feld."],
        "us": ["Jetzt kriegen wir das Spiel in den Griff!", "So sieht das aus, wir sind am Drücker!"],
        "them": ["Die sind besser reingekommen als wir.", "Die starten stärker. Aufwachen!"],
    },
    "momentum_push": {
        "n": ["{team} macht jetzt richtig Druck.", "Angriff auf Angriff von {team}.", "{team} schnürt den Gegner ein."],
        "a": ["Druckphase von {team}: {sh} Schüsse in dieser Phase.", "Druckmaximum für {team}, der Gegner kommt nicht raus."],
        "us": ["Weiter drücken, die kommen nicht raus!", "Wir rennen an, das muss jetzt fallen!"],
        "them": ["Wir sind hinten eingeschnürt. Klärt das Ding!", "Die werfen alles nach vorn. Halten!"],
    },
    "goal_move_regain": {
        "n": ["Und alles begann mit dem Ballgewinn von {starter}, {secs} Sekunden zuvor.", "Ballgewinn {starter}, {secs} Sekunden später im Netz."],
        "a": ["Umschaltor: Ballgewinn {starter}, Abschluss nach {secs} Sekunden.", "Vom Ballgewinn zum Tor in {secs} Sekunden. Konter wie im Lehrbuch."],
        "us": ["Und angefangen hat's mit dem Ballgewinn von {starter}! Stark!", "{starter} erobert ihn, {secs} Sekunden später jubeln wir!"],
        "them": ["Ball verloren, {secs} Sekunden später liegt er drin.", "Ballverlust, bestraft in {secs} Sekunden. Bitter."],
    },
    "goal_move_pass": {
        "n": ["Ein Angriff: {passes}, {secs} Sekunden von {starter} bis zum Abschluss.", "{passes}, {players} Spieler beteiligt. Schönes Mannschaftstor."],
        "a": ["Aufbau: {passes} in {secs} Sekunden, {players} Spieler beteiligt.", "Sequenz: {passes}, {secs} Sekunden, eingeleitet von {starter}."],
        "us": ["Was für ein Angriff! {passes} und drin!", "{passes}, {players} Spieler, ein Tor. Wunderschön!"],
        "them": ["Die haben uns komplett ausgespielt. {passes} und drin.", "{passes} und wir waren nie dran."],
    },
    "goal_move_set": {
        "n": ["Und das Tor fiel nach einem Standard.", "Standardtor. Die Arbeit vom Trainingsplatz."],
        "a": ["Ursprung: Standardsituation. Ruhende Bälle entscheiden Spiele.", "Tor nach Standard. Gefahr bei ruhenden Bällen bestätigt."],
        "us": ["Direkt vom Trainingsplatz!", "Standard, Tor. Herrlich!"],
        "them": ["Nach einem Standard. Das ist so vermeidbar.", "Ein Standard. Das müssen wir besser verteidigen."],
    },
    "goal_season": {
        "n": ["Das ist {scorer}s {count}. Saisontor.", "{scorer} steht jetzt bei {goals} Ligatoren in dieser Saison."],
        "a": ["Saisonbilanz {scorer}: {goals} Tore in {apps} Spielen.", "{scorer}: {goals} Saisontore, das {count}. in {apps} Spielen."],
        "us": ["Das {count}. Saisontor für {scorer}! Was für ein Spieler!", "{scorer} schon wieder! {goals} in dieser Saison!"],
        "them": ["Sein {count}. Saisontor. Wir wussten, dass er gefährlich ist.", "{scorer}, jetzt {goals} Saisontore."],
        "p": ["{scorer}s {count}. Saisontor!", "{goals} Ligatore in dieser Saison für {scorer}."],
    },
    "goal_season_first": {
        "n": ["Und das ist {scorer}s erstes Saisontor.", "Sein erstes Tor in dieser Saison, ein großer Moment für {scorer}."],
        "a": ["Erstes Ligator der Saison für {scorer}, in seinem {apps}. Spiel.", "Saisonkonto eröffnet: {scorer}, erstes Tor."],
        "us": ["Sein erstes Saisontor, und genau zur richtigen Zeit!", "Endlich! {scorer} trifft zum ersten Mal in dieser Saison!"],
        "them": ["Sein erstes Saisontor, und natürlich gegen uns.", "Die ganze Saison nicht getroffen. Typisch."],
        "p": ["{scorer} trifft zum ersten Mal in dieser Saison!", "Erstes Saisontor für {scorer}!"],
    },
    "since_goal_reply": {
        "n": ["Seit dem Rückstand antwortet {team}: {sh} Schüsse zu {sa}.", "{team} hat gut auf das Gegentor reagiert, {share} Ballbesitz."],
        "a": ["Phase nach dem Tor: {team} {sh} Schüsse zu {sa}, {share} Ballbesitz.",
              "Spielstand-Effekt: {team} liegt hinten und dominiert, {share} Ballbesitz."],
        "us": ["Wir haben stark auf das Gegentor reagiert, weiter so!", "Seit deren Tor sind nur noch wir am Ball!"],
        "them": ["Seit dem Tor kommen die. Ruhig bleiben.", "Die haben reagiert. Wir stehen zu tief."],
    },
    "since_goal_hold": {
        "n": ["Seit dem Tor behält {team} die Kontrolle: {share} Ballbesitz.", "{team} verwaltet die Führung bisher gut."],
        "a": ["Phase nach dem Tor: {team} {share} Ballbesitz, Gegner {sa} Schüsse.", "Führung verwaltet: {team} {share} Ballbesitz seit dem Tor."],
        "us": ["Seit dem Tor halten wir den Ball schön.", "Seit dem Tor alles unter Kontrolle, perfekt!"],
        "them": ["Seit dem Tor kriegen wir den Ball nicht mehr.", "Wir müssen mehr machen. Die kontrollieren das seit dem Tor."],
    },
    "spell": {
        "n": ["{minute} Minuten gespielt. {team} ist bisher die bessere Mannschaft.", "{minute} Minuten, und {team} hat leicht die Nase vorn."],
        "a": ["{minute} Minuten: Schüsse {sh} zu {sa}, xG {xh} zu {xa}.", "Letzte Viertelstunde: {team} mit {share} Ballbesitz."],
        "us": ["{minute} Minuten, und wir sind die bessere Mannschaft!", "{minute} Minuten gespielt, wir haben das im Griff!"],
        "them": ["{minute} Minuten. Die waren bisher besser.", "{minute} Minuten, und wir müssen uns steigern."],
        "p": ["{minute} Minuten: {player} bisher mit Note {rating}.", "{minute} Minuten. {player} bei {rating}, Saisonschnitt {season}."],
    },
    "spell_even": {
        "n": ["{minute} Minuten gespielt, und nichts trennt die Teams.", "{minute} Minuten, weiter sehr ausgeglichen."],
        "a": ["{minute} Minuten: ausgeglichen. Schüsse {sh} zu {sa}, xG {xh} zu {xa}.", "{minute} Minuten, ausgeglichen: {ph} zu {pa} Ballbesitz."],
        "us": ["{minute} Minuten, enges Spiel. Ein Moment kann's entscheiden.", "{minute} Minuten, alles offen. Weiter nach vorn!"],
        "them": ["{minute} Minuten, alles offen. Konzentriert bleiben.", "{minute} Minuten, noch nichts entschieden."],
        "p": ["{minute} Minuten: {player} bisher mit Note {rating}.", "{minute} Minuten. {player} bei {rating}, Saisonschnitt {season}."],
    },
    "why_turnover": {
        "n": ["Schlüsselmoment: {loser} verliert den Ball nur {dist} Meter vor dem eigenen Tor.",
              "Genau das ist gefährlich: Ballverlust {dist} Meter vor dem Tor."],
        "a": ["Schlüsselmoment: Ballverlust {dist} Meter vor dem Tor. Die riskanteste Zone.",
              "Warum es zählt: Ballverlust {dist} Meter vor dem Tor, keine Absicherung."],
        "us": ["Großer Moment! {winner} erobert den Ball weit vorne!", "{winner} klaut ihn, genau da wo's wehtut!"],
        "them": ["Ballverlust {dist} Meter vor unserem Tor. Das geht nicht!", "Leichtsinnig! {loser} verliert ihn viel zu tief."],
    },
    "why_turnover_shot": {
        "n": ["Schlüsselmoment: {winner} gewinnt den Ball, {secs} Sekunden später der Schuss.", "Deshalb zählt es: Ballverlust, Schuss nach {secs} Sekunden."],
        "a": ["Schlüsselmoment: vom Ballgewinn zum Schuss in {secs} Sekunden. Klassisches Umschalten.",
              "Ballverlust {dist} Meter vor dem Tor, Schuss nach {secs} Sekunden."],
        "us": ["{winner} gewinnt ihn und {secs} Sekunden später schießen wir!", "So bestraft man einen Fehler!"],
        "them": ["Ball verloren, {secs} Sekunden später schießen die. Gefährlich!", "Das passiert, wenn wir ihn herschenken."],
    },
    "why_chance": {
        "n": ["Das war ihre bisher beste Chance, {xg} xG.", "Schlüsselmoment: die größte Chance für {team} bisher."],
        "a": ["Schlüsselmoment: {xg} xG, die beste Chance für {team} bisher.", "Hochwertigste Chance bisher für {team}: {xg} xG aus {dist} Metern."],
        "us": ["Das war unsere beste Chance! So knapp!", "Die beste Chance des Spiels, die muss rein!"],
        "them": ["Ihre beste Chance bisher. Glück gehabt.", "Puh. Ihre größte Chance bisher, da hatten wir Glück."],
        "p": ["{player} hatte die beste Chance des Spiels bisher.", "Größte Chance des Spiels für {player}, {xg} xG."],
    },
    "intro_context": {
        "n": ["{home} steht vor dem Spiel auf {hpos}, {away} auf {apos}.", "Blick auf die Tabelle: {home} auf {hpos}, {away} auf {apos}."],
        "a": ["Kontext: {home} auf {hpos}, {hwins} Siege aus fünf. {away} auf {apos}, {awins} Siege.",
              "Formkurve: {home} {hwins} Siege aus fünf, {away} {awins} Siege."],
    },
}

ES: Pool = {
    "why_chance_missed": {
        "n": ["Momento clave: una ocasión de {xg} xG desde {dist} metros, fallada.", "Una gran ocasión, {xg} xG, y sin gol."],
        "a": ["Ocasión clara fallada: {xg} xG desde {dist} metros. La definición le cuesta a {team}.",
              "Calidad de ocasión {xg} xG, cero goles. {team} perdona."],
        "us": ["¡Esa hay que meterla!", "¡Por poco! Tenemos que ser más certeros."],
        "them": ["Ahí tenían que marcar. ¡Nos salvamos!", "¡Uf! Esa era una ocasión de verdad para ellos."],
        "p": ["{player} no querrá volver a verla, {xg} xG.", "Gran ocasión para {player}, {xg} xG. Fallada."],
    },
    "momentum_swing": {
        "n": ["El partido ha cambiado. Ahora manda {team}.", "¡Cambio de inercia! {team} toma el control."],
        "a": ["La inercia ha girado: {team} con {share} del balón en esta fase.", "Cambio de control. {team} dicta ahora, {share} de posesión."],
        "us": ["¡Le hemos dado la vuelta! ¡Ahora mandamos nosotros!", "¡La marea cambia a nuestro favor, vamos!"],
        "them": ["Ahora mandan ellos. Hay que aguantar.", "La inercia es suya. ¡A apretar los dientes!"],
    },
    "momentum_take": {
        "n": ["{team} empieza a hacerse con el partido.", "{team} encuentra el mejor ritmo."],
        "a": ["{team} establece el control: {share} del balón en esta fase.", "Primer patrón claro: {team} domina el territorio."],
        "us": ["¡Ya nos estamos haciendo con el partido!", "¡Así sí, ahora mandamos!"],
        "them": ["Ellos han entrado mejor al partido.", "Han empezado más fuertes. ¡Despertad!"],
    },
    "momentum_push": {
        "n": ["{team} aprieta de verdad ahora.", "Oleada tras oleada de {team}.", "{team} encierra al rival."],
        "a": ["Fase de presión de {team}: {sh} tiros en este tramo.", "Máxima presión de {team}, el rival no puede salir."],
        "us": ["¡Seguid apretando, no pueden salir!", "¡Les estamos encerrando!"],
        "them": ["Estamos encerrados atrás. ¡Despejad!", "Lo están intentando todo. ¡Aguantad!"],
    },
    "goal_move_regain": {
        "n": ["Y todo empezó con el robo de {starter}, {secs} segundos antes.", "Robo de {starter}, gol {secs} segundos después."],
        "a": ["Gol de transición: robo de {starter}, disparo a los {secs} segundos.", "Del robo al gol en {secs} segundos. Contragolpe de manual."],
        "us": ["¡Y empezó con el robo de {starter}! ¡Brillante!", "¡{starter} la roba y {secs} segundos después celebramos!"],
        "them": ["La perdimos y {secs} segundos después está dentro.", "Pérdida castigada en {secs} segundos. Duele."],
    },
    "goal_move_pass": {
        "n": ["Una jugada de {passes}, {secs} segundos de {starter} al remate.", "{passes}, {players} jugadores implicados. Gran gol colectivo."],
        "a": ["Construcción: {passes} en {secs} segundos, {players} jugadores implicados.", "Secuencia: {passes}, {secs} segundos, iniciada por {starter}."],
        "us": ["¡Qué jugada! ¡{passes} y dentro!", "¡{passes}, {players} jugadores, un gol. Precioso!"],
        "them": ["Nos han atravesado. {passes} y gol.", "{passes} y nunca llegamos."],
    },
    "goal_move_set": {
        "n": ["Y llegó a balón parado.", "Gol a balón parado. El trabajo del entrenamiento."],
        "a": ["Origen: balón parado. Las acciones a balón parado deciden partidos.", "Gol tras jugada de estrategia. Peligro confirmado."],
        "us": ["¡Directo del campo de entrenamiento!", "¡Balón parado, gol. Me encanta!"],
        "them": ["A balón parado. Era evitable.", "Balón parado. Tenemos que defenderlo mejor."],
    },
    "goal_season": {
        "n": ["Es el gol número {count} de {scorer} esta temporada.", "{scorer} suma ya {goals} goles de liga esta temporada."],
        "a": ["Balance de {scorer}: {goals} goles en {apps} partidos.", "{scorer}: {goals} goles esta temporada en {apps} partidos."],
        "us": ["¡El gol {count} de la temporada para {scorer}! ¡Qué jugador!", "¡{scorer} otra vez! ¡Ya van {goals} esta temporada!"],
        "them": ["Su gol número {count} de la temporada. Sabíamos que era peligroso.", "{scorer}, ya {goals} goles esta temporada."],
        "p": ["¡El gol número {count} de la temporada para {scorer}!", "{goals} goles de liga esta temporada para {scorer}."],
    },
    "goal_season_first": {
        "n": ["Y es el primer gol de la temporada para {scorer}.", "Su primer gol del curso, un gran momento para {scorer}."],
        "a": ["Primer gol de liga de {scorer} esta temporada, en su partido {apps}.", "Cuenta abierta: {scorer}, primer gol del curso."],
        "us": ["¡Su primer gol de la temporada, y en el mejor momento!", "¡Por fin! ¡{scorer} se estrena esta temporada!"],
        "them": ["Su primer gol de la temporada, y tenía que ser contra nosotros.", "No había marcado en todo el año. Típico."],
        "p": ["¡{scorer} se estrena esta temporada!", "¡Primer gol del curso para {scorer}!"],
    },
    "since_goal_reply": {
        "n": ["Desde que va perdiendo, {team} ha respondido: {sh} tiros a {sa}.", "{team} ha reaccionado bien al gol, {share} del balón."],
        "a": ["Tras el gol: {team} {sh} tiros a {sa}, {share} de posesión.", "Efecto marcador: {team} va perdiendo y domina, {share} del balón."],
        "us": ["¡Hemos reaccionado bien al gol, seguid así!", "¡Desde su gol, solo jugamos nosotros!"],
        "them": ["Desde el gol vienen a por nosotros. Calma.", "Han reaccionado. Estamos demasiado atrás."],
    },
    "since_goal_hold": {
        "n": ["Desde el gol, {team} mantiene el control: {share} del balón.", "{team} gestiona bien la ventaja."],
        "a": ["Tras el gol: {team} {share} de posesión, el rival {sa} tiros.", "Ventaja gestionada: {team} {share} del balón desde el gol."],
        "us": ["Desde el gol tenemos bien el balón.", "¡Todo controlado desde el gol, perfecto!"],
        "them": ["Desde el gol no les quitamos el balón.", "Hay que hacer más. Controlan desde el gol."],
    },
    "spell": {
        "n": ["Minuto {minute}. {team} es mejor hasta ahora.", "Minuto {minute}, y {team} va un poco por delante."],
        "a": ["Minuto {minute}: tiros {sh} a {sa}, xG {xh} a {xa}.", "Último cuarto de hora: {team} con {share} del balón."],
        "us": ["¡Minuto {minute} y somos mejores!", "¡Minuto {minute}, mandamos nosotros!"],
        "them": ["Minuto {minute}. Ellos han sido mejores.", "Minuto {minute}, y tenemos que mejorar."],
        "p": ["Minuto {minute}: {player} con un {rating} por ahora.", "Minuto {minute}. {player} en {rating}, media de la temporada {season}."],
    },
    "spell_even": {
        "n": ["Minuto {minute}, y nada separa a los equipos.", "Minuto {minute}, todo muy igualado."],
        "a": ["Minuto {minute}: igualado. Tiros {sh} a {sa}, xG {xh} a {xa}.", "Minuto {minute}, equilibrio: {ph} a {pa} de posesión."],
        "us": ["Minuto {minute}, partido cerrado. Un detalle lo decide.", "Minuto {minute}, todo abierto. ¡Adelante!"],
        "them": ["Minuto {minute}, todo abierto. Concentración.", "Minuto {minute}, nada decidido aún."],
        "p": ["Minuto {minute}: {player} con un {rating} por ahora.", "Minuto {minute}. {player} en {rating}, media de la temporada {season}."],
    },
    "why_turnover": {
        "n": ["Momento clave: {loser} pierde el balón a solo {dist} metros de su portería.", "Ese es el peligro: pérdida a {dist} metros de la portería."],
        "a": ["Momento clave: pérdida a {dist} metros de portería. La zona de más riesgo.",
              "Por qué importa: balón perdido a {dist} metros, sin cobertura."],
        "us": ["¡Gran momento! ¡{winner} la roba muy arriba!", "¡{winner} la roba donde más duele!"],
        "them": ["Perdida a {dist} metros de nuestra portería. ¡No se puede!", "¡Qué descuido! {loser} la pierde demasiado atrás."],
    },
    "why_turnover_shot": {
        "n": ["Momento clave: {winner} roba y {secs} segundos después hay disparo.", "Por eso importa: pérdida y disparo en {secs} segundos."],
        "a": ["Momento clave: del robo al disparo en {secs} segundos. Transición clásica.",
              "Pérdida a {dist} metros de portería, disparo a los {secs} segundos."],
        "us": ["¡{winner} la roba y {secs} segundos después disparamos!", "¡Así se castiga un error!"],
        "them": ["La perdemos y {secs} segundos después disparan. ¡Peligro!", "Esto pasa cuando la regalamos."],
    },
    "why_chance": {
        "n": ["Fue su mejor ocasión hasta ahora, {xg} xG.", "Momento clave: la mayor ocasión de {team} hasta ahora."],
        "a": ["Momento clave: {xg} xG, la mejor ocasión de {team} hasta ahora.", "Ocasión de más calidad para {team}: {xg} xG desde {dist} metros."],
        "us": ["¡Nuestra mejor ocasión! ¡Por poco!", "¡La mejor ocasión del partido, hay que meterla!"],
        "them": ["Su mejor ocasión. Nos hemos salvado.", "Uf. Su mayor ocasión, hemos tenido suerte."],
        "p": ["{player} tuvo la mejor ocasión del partido hasta ahora.", "La mayor ocasión del partido para {player}, {xg} xG."],
    },
    "intro_context": {
        "n": ["{home} llega {hpos}º en la tabla, {away} {apos}º.", "Mirada a la tabla: {home} {hpos}º, {away} {apos}º."],
        "a": ["Contexto: {home} {hpos}º, {hwins} victorias en cinco. {away} {apos}º, {awins} victorias.",
              "Forma: {home} {hwins} victorias en cinco, {away} {awins} victorias."],
    },
}

STORY: dict[str, Pool] = {"en": EN, "de": DE, "es": ES}
