import logging
import json
from types import SimpleNamespace
from typing import Dict, Any, Tuple
from django.utils import timezone

logger = logging.getLogger(__name__)

# Testo utente inviato insieme all'immagine del referto (condiviso tra i provider vivi).
OCR_USER_TEXT = "Estrai i dati da questo referto fotografato. Rispondi solo con il JSON."

# Prompt di sistema hardened v2 (per-field confidence + null preference + ambiguity channel).
# Usato da GeminiVisionProvider: schema OCR v2 in output.
OCR_SYSTEM_PROMPT_V2 = """
        Sei un esperto di analisi di referti di partite di pallanuoto (FIN - GUG). 
        Riceverai la FOTO di un referto ufficiale. Segui queste istruzioni spaziali:
        
        1. SQUADRE E PUNTEGGIO:
           - In alto a sinistra (Tabella 1): Squadra CASA (es. POL. DELTA). 'Risultato finale' è il numero in fondo a questa casella.
           - In basso a sinistra (Tabella 2): Squadra OSPITE (es. VILLA YORK). 'Risultato finale' è il numero in fondo a questa casella.
           - Punteggi parziali: Nella tabella 'Risultati parziali' al centro.
        
        2. ROSTER (GIOCATORI):
           - Sotto il nome di ogni squadra c'è l'elenco 'Giocatori'. Estrai 'N.' (numero calottina) e 'Cognome e Nome'.
           - Un roster tipico ha tra 7 e 15 giocatori per squadra.
        
        3. EVENTI (CRONOLOGIA):
           - TABELLE A DESTRA ('STORIA CRONOMETRICA'): Elenca tutti gli eventi.
           - Colonne: Tempo (Minuto), N. Calottina (chi fa l'azione), Evento (GOL, ET per Esclusione 20", TR per Rigore, ecc.).
           - Importante: Trascrivi i gol (GOL) e le espulsioni (ET come EXCLUSION_20).
           - PERIODO DI OGNI EVENTO ("quarter"): la 'STORIA CRONOMETRICA' è divisa in
             sezioni o blocchi, uno per periodo (1°, 2°, 3°, 4° tempo). Ricava il campo
             "quarter" di ogni evento dalla SEZIONE in cui l'evento è scritto, non dal
             minuto e non dai punteggi parziali.
           - Se non riesci a stabilire con certezza in quale sezione/periodo cade un
             evento, scrivi null in "quarter": è un valore ammesso e preferibile.
             NON dedurre il periodo dal minuto e NON distribuire gli eventi fra i
             periodi per farli tornare con i punteggi parziali.

        REGOLE CRITICHE:
        - Se un dato è ILLEGGIBILE, PARZIALE o AMBIGUO: usa null. NON INDOVINARE MAI.
        - Se un nome è parzialmente leggibile, trascrivi solo le lettere chiare e aggiungi "?" (es. "ROSS?" o "M?RETTI").
        - Se un numero è ambiguo (es. potrebbe essere 3 o 8), usa null e segnalalo in extraction_warnings.
        - Se il punteggio di un quarto non è leggibile, usa null per quel quarto.
        
        FORMATO JSON RICHIESTO:
        {
            "metadata": {
                "schema_version": "2.0",
                "confidence": <0.0-1.0 fiducia complessiva>,
                "confidence_fields": {
                    "home_team": <0.0-1.0>,
                    "away_team": <0.0-1.0>,
                    "final_score": <0.0-1.0>,
                    "quarters": <0.0-1.0>,
                    "home_roster": <0.0-1.0>,
                    "away_roster": <0.0-1.0>,
                    "events": <0.0-1.0>,
                    "officials": <0.0-1.0>
                },
                "extraction_warnings": [
                    "<stringa che descrive ogni campo ambiguo o parzialmente leggibile>"
                ]
            },
            "match_info": {
                "home_team": "<nome squadra o null>",
                "away_team": "<nome squadra o null>",
                "competition": "<nome campionato o null>",
                "date": "<YYYY-MM-DD o null se illeggibile>",
                "city": "<città o null>",
                "venue": "<nome impianto specifico (es: Piscina Comunale) o null>",
                "round": "<giornata/fase (es: Giornata 5, Finale) o null>",
                "group": "<girone (es: Girone A) o null>"
            },
            "officials": {
                "confidence": <0.0-1.0 fiducia sulla lettura degli ufficiali>,
                "referees": [
                    {"name": "<COGNOME NOME o null>", "role": "1st|2nd|null"}
                ],
                "timekeeper": "<nome segnapunti o null>"
            },
            "scores": {
                "final_score": "<X-Y o null>",
                "quarters": {
                    "1": [<home, away> o null],
                    "2": [<home, away> o null],
                    "3": [<home, away> or null],
                    "4": [<home, away> o null]
                }
            },
            "teams": {
                "home": {
                    "name": "<nome>",
                    "coach": "<nome allenatore o null>",
                    "confidence": <0.0-1.0 fiducia sulla lettura del roster>,
                    "players": [{"number": <int o null>, "name": "<cognome nome>"}]
                },
                "away": {
                    "name": "<nome>",
                    "coach": "<nome allenatore o null>",
                    "confidence": <0.0-1.0 fiducia sulla lettura del roster>,
                    "players": [{"number": <int o null>, "name": "<cognome nome>"}]
                }
            },
            "events": [
                {
                    "type": "GOAL|EXCLUSION_20|YELLOW_CARD|RED_CARD|TIMEOUT|OTHER",
                    "player_name": "<nome giocatore o null (null per timeout squadra)>",
                    "team": "home|away",
                    "minute": <int o null>,
                    "quarter": <int o null>,
                    "sanction_duration": <null o intero secondi (es: 20 per esclusione 20 secondi)>
                }
            ]
        }
        
        Rispondi SOLO con il JSON. Non aggiungere testo, commenti o markdown.
        """

# Prompt sperimentale v3 (Macro 8, giro 2026-07-22): V2 più tre modifiche mirate
# alle classi di errore misurate dalla baseline §8.9 del syllabus 8:
#   (a) anti-riconciliazione sulla griglia parziali (l'errore compensativo:
#       parziali ricostruiti per far tornare la somma col finale estratto);
#   (b) trascrizione letterale dei nomi (allucinazione plausibile, es.
#       FRUSINO -> FROSINONE);
#   (c) data trascritta cifra per cifra, con confidence dedicata
#       (confidence_fields.date) e trascrizione grezza (match_info.date_digits).
# Le aggiunte allo schema JSON sono additive e retrocompatibili:
# _normalize_response tollera sia l'assenza sia la presenza dei nuovi campi.
# NON è il default di produzione: si seleziona via settings.OCR_PROMPT_VERSION
# o dal bench (ocr_bench --prompt-version v3). La promozione a default è una
# decisione di prodotto sui numeri del bench, non un fatto tecnico.
OCR_SYSTEM_PROMPT_V3 = """
        Sei un esperto di analisi di referti di partite di pallanuoto (FIN - GUG).
        Riceverai la FOTO di un referto ufficiale. Segui queste istruzioni spaziali:

        1. SQUADRE E PUNTEGGIO:
           - In alto a sinistra (Tabella 1): Squadra CASA (es. POL. DELTA). 'Risultato finale' è il numero in fondo a questa casella.
           - In basso a sinistra (Tabella 2): Squadra OSPITE (es. VILLA YORK). 'Risultato finale' è il numero in fondo a questa casella.
           - Punteggi parziali: Nella tabella 'Risultati parziali' al centro.
           - GRIGLIA 'Risultati parziali': trascrivi le 8 celle ESATTAMENTE come
             le vedi, cella per cella. Ogni cella è una LETTURA, mai un calcolo:
             NON ricavare nessuna cella da altre celle né dal risultato finale.
           - Il 'Risultato finale' di ciascuna squadra è una trascrizione
             INDIPENDENTE del numero scritto in fondo alla sua casella: NON è la
             somma dei parziali e NON va ricavato né corretto a partire da essi.
           - Se la somma dei parziali NON torna col risultato finale trascritto,
             NON aggiustare niente: riporta i valori discordi esattamente come
             sono scritti e segnala la discordanza in extraction_warnings.
             La discordanza è un esito ammesso e prezioso, non un errore da
             nascondere.

        2. ROSTER (GIOCATORI):
           - Sotto il nome di ogni squadra c'è l'elenco 'Giocatori'. Estrai 'N.' (numero calottina) e 'Cognome e Nome'.
           - Un roster tipico ha tra 7 e 15 giocatori per squadra.

        3. EVENTI (CRONOLOGIA):
           - TABELLE A DESTRA ('STORIA CRONOMETRICA'): Elenca tutti gli eventi.
           - Colonne: Tempo (Minuto), N. Calottina (chi fa l'azione), Evento (GOL, ET per Esclusione 20", TR per Rigore, ecc.).
           - Importante: Trascrivi i gol (GOL) e le espulsioni (ET come EXCLUSION_20).
           - USA SOLO i tipi dell'enum "type" qui sotto. NON inventare MAI tipi
             fuori enum (es. NON usare "PENALTY_GOAL", "TR", "RIGORE" come "type"):
             il rigore si esprime col flag "is_penalty", non con un tipo nuovo.
           - RIGORI (flag "is_penalty", default false):
             * Il GOL segnato su rigore va trascritto come "type": "GOAL" con
               "is_penalty": true (il "team"/calottina sono di chi SEGNA).
             * L'ESPULSIONE che comporta un rigore per gli avversari va trascritta
               come "type": "EXCLUSION_20" con "is_penalty": true (la calottina è di
               chi COMMETTE il fallo, non di chi tira).
             * Un rigore parato o sbagliato NON produce un GOAL: resta solo
               l'espulsione con "is_penalty": true, senza gol corrispondente.
             * Per ogni altro evento "is_penalty" è false (o omesso).
           - PERIODO DI OGNI EVENTO ("quarter"): la 'STORIA CRONOMETRICA' è divisa in
             sezioni o blocchi, uno per periodo (1°, 2°, 3°, 4° tempo). Ricava il campo
             "quarter" di ogni evento dalla SEZIONE in cui l'evento è scritto, non dal
             minuto e non dai punteggi parziali.
           - Se non riesci a stabilire con certezza in quale sezione/periodo cade un
             evento, scrivi null in "quarter": è un valore ammesso e preferibile.
             NON dedurre il periodo dal minuto e NON distribuire gli eventi fra i
             periodi per farli tornare con i punteggi parziali.

        4. DATA DELLA GARA:
           - Leggila cifra per cifra come scritta sul foglio, senza dedurla dal
             contesto (stagione, campionato, altre scritte sul foglio).
           - Riporta in "date_digits" la trascrizione esatta come scritta
             (es. "11/04/2026") e in "date" la stessa data in formato YYYY-MM-DD.
           - Se anche una sola cifra è incerta, usa null in "date" e segnala il
             dubbio in extraction_warnings.
           - Dichiara la fiducia sulla lettura della data in confidence_fields.date.

        REGOLE CRITICHE:
        - Se un dato è ILLEGGIBILE, PARZIALE o AMBIGUO: usa null. NON INDOVINARE MAI.
        - NOMI (squadre e giocatori): trascrivi ESATTAMENTE le lettere scritte,
          anche se il nome sembra insolito, raro o "sbagliato" (es. se sul foglio
          c'è scritto FRUSINO, trascrivi FRUSINO: NON correggerlo in FROSINONE).
          NON normalizzare MAI verso nomi di città, di società note o forme più
          comuni: la mappatura ai nomi ufficiali avviene a valle, non è compito tuo.
        - Se un nome è parzialmente leggibile, trascrivi solo le lettere chiare e aggiungi "?" (es. "ROSS?" o "M?RETTI").
        - Se un numero è ambiguo (es. potrebbe essere 3 o 8), usa null e segnalalo in extraction_warnings.
        - Se il punteggio di un quarto non è leggibile, usa null per quel quarto.

        FORMATO JSON RICHIESTO:
        {
            "metadata": {
                "schema_version": "2.0",
                "confidence": <0.0-1.0 fiducia complessiva>,
                "confidence_fields": {
                    "home_team": <0.0-1.0>,
                    "away_team": <0.0-1.0>,
                    "final_score": <0.0-1.0>,
                    "quarters": <0.0-1.0>,
                    "date": <0.0-1.0>,
                    "home_roster": <0.0-1.0>,
                    "away_roster": <0.0-1.0>,
                    "events": <0.0-1.0>,
                    "officials": <0.0-1.0>
                },
                "extraction_warnings": [
                    "<stringa che descrive ogni campo ambiguo o parzialmente leggibile, incluse le discordanze somma parziali/finale>"
                ]
            },
            "match_info": {
                "home_team": "<nome squadra o null>",
                "away_team": "<nome squadra o null>",
                "competition": "<nome campionato o null>",
                "date": "<YYYY-MM-DD o null se illeggibile>",
                "date_digits": "<data trascritta cifra per cifra come scritta sul foglio (es. '11/04/2026') o null>",
                "city": "<città o null>",
                "venue": "<nome impianto specifico (es: Piscina Comunale) o null>",
                "round": "<giornata/fase (es: Giornata 5, Finale) o null>",
                "group": "<girone (es: Girone A) o null>"
            },
            "officials": {
                "confidence": <0.0-1.0 fiducia sulla lettura degli ufficiali>,
                "referees": [
                    {"name": "<COGNOME NOME o null>", "role": "1st|2nd|null"}
                ],
                "timekeeper": "<nome segnapunti o null>"
            },
            "scores": {
                "final_score": "<X-Y o null>",
                "quarters": {
                    "1": [<home, away> o null],
                    "2": [<home, away> o null],
                    "3": [<home, away> or null],
                    "4": [<home, away> o null]
                }
            },
            "teams": {
                "home": {
                    "name": "<nome>",
                    "coach": "<nome allenatore o null>",
                    "confidence": <0.0-1.0 fiducia sulla lettura del roster>,
                    "players": [{"number": <int o null>, "name": "<cognome nome>"}]
                },
                "away": {
                    "name": "<nome>",
                    "coach": "<nome allenatore o null>",
                    "confidence": <0.0-1.0 fiducia sulla lettura del roster>,
                    "players": [{"number": <int o null>, "name": "<cognome nome>"}]
                }
            },
            "events": [
                {
                    "type": "GOAL|EXCLUSION_20|YELLOW_CARD|RED_CARD|TIMEOUT|OTHER",
                    "player_name": "<nome giocatore o null (null per timeout squadra)>",
                    "team": "home|away",
                    "minute": <int o null>,
                    "quarter": <int o null>,
                    "is_penalty": <true|false: true se GOAL segnato su rigore o EXCLUSION_20 che ha comportato un rigore; altrimenti false>,
                    "sanction_duration": <null o intero secondi (es: 20 per esclusione 20 secondi)>
                }
            ]
        }

        Rispondi SOLO con il JSON. Non aggiungere testo, commenti o markdown.
        """

# V3.2 — variante sperimentale di V3.1 con DUE sole modifiche additive alla
# sezione EVENTI (giro §8.x, 22/07):
#   (a) campo "clock" (cronometro a scalare mm:ss) accanto a "minute", con
#       l'istruzione esplicita che gli stessi valori di clock si ripetono nei
#       quattro periodi (il clock NON identifica il periodo);
#   (b) ancoraggio di periodo rinforzato per gli EVENTI ISOLATI: un evento
#       appartiene al periodo della SEZIONE in cui è scritto anche quando è
#       l'unico evento di una squadra in quella sezione; se la sezione non è
#       certa, quarter=null è preferibile a un periodo indovinato.
# Costruita per SOSTITUZIONE MIRATA su V3 così che ogni altra zona (punteggi,
# nomi, data, rigori) resti IDENTICA byte-per-byte a V3.1: qualunque scarto sui
# punteggi tra V3.1 e V3.2 è varianza di campionamento, non effetto del prompt.
# NON è il default di produzione: si seleziona via settings.OCR_PROMPT_VERSION
# o dal bench (ocr_bench --prompt-version v3_2). La promozione a default è una
# decisione di prodotto sui numeri del bench, non un fatto tecnico.
OCR_SYSTEM_PROMPT_V3_2 = (
    OCR_SYSTEM_PROMPT_V3
    # (a) CLOCK COMPLETO: cronometro a scalare mm:ss accanto al minuto.
    .replace(
        "           - Importante: Trascrivi i gol (GOL) e le espulsioni (ET come EXCLUSION_20).\n",
        "           - Importante: Trascrivi i gol (GOL) e le espulsioni (ET come EXCLUSION_20).\n"
        "           - TEMPO (\"clock\"): la colonna Tempo è un CRONOMETRO A SCALARE dentro il\n"
        "             periodo, in formato mm:ss: parte da circa 7:55 a inizio periodo e SCENDE\n"
        "             fino a 0:00. Trascrivilo ESATTAMENTE come scritto nella stringa \"clock\"\n"
        "             (es. \"4:44\", \"0:58\", \"0:09\"), oltre al campo \"minute\". NON arrotondare.\n"
        "             Gli STESSI valori di clock si ripetono in tutti e quattro i periodi:\n"
        "             il clock NON identifica il periodo, indica solo l'ordine dentro la sezione.\n",
    )
    # (b) ANCORAGGIO DI PERIODO: rinforzo esplicito per gli eventi isolati.
    .replace(
        "           - PERIODO DI OGNI EVENTO (\"quarter\"): la 'STORIA CRONOMETRICA' è divisa in\n"
        "             sezioni o blocchi, uno per periodo (1°, 2°, 3°, 4° tempo). Ricava il campo\n"
        "             \"quarter\" di ogni evento dalla SEZIONE in cui l'evento è scritto, non dal\n"
        "             minuto e non dai punteggi parziali.\n"
        "           - Se non riesci a stabilire con certezza in quale sezione/periodo cade un\n"
        "             evento, scrivi null in \"quarter\": è un valore ammesso e preferibile.\n"
        "             NON dedurre il periodo dal minuto e NON distribuire gli eventi fra i\n"
        "             periodi per farli tornare con i punteggi parziali.\n",
        "           - PERIODO DI OGNI EVENTO (\"quarter\"): la 'STORIA CRONOMETRICA' è divisa in\n"
        "             sezioni o blocchi, uno per periodo (1°, 2°, 3°, 4° tempo). Ricava il campo\n"
        "             \"quarter\" di ogni evento dalla SEZIONE in cui l'evento è scritto, non dal\n"
        "             minuto, non dal clock e non dai punteggi parziali.\n"
        "           - Questo vale ANCHE quando un evento è l'UNICO evento di una squadra in una\n"
        "             sezione: l'evento appartiene comunque al periodo della SEZIONE in cui è\n"
        "             scritto sul foglio. NON spostare un evento isolato in un'altra sezione\n"
        "             perché \"sembra\" appartenerci o per farlo coincidere con eventi di un altro\n"
        "             periodo: la posizione sul foglio decide, non la plausibilità.\n"
        "           - Se non riesci a stabilire con certezza in quale sezione/periodo cade un\n"
        "             evento — isolato o no — scrivi null in \"quarter\": è un valore ammesso e\n"
        "             preferibile a un periodo indovinato. NON dedurre il periodo dal minuto o\n"
        "             dal clock e NON distribuire gli eventi fra i periodi per farli tornare con\n"
        "             i punteggi parziali.\n",
    )
    # (a) schema: campo "clock" additivo accanto a "minute" nell'oggetto evento.
    .replace(
        "                    \"minute\": <int o null>,\n"
        "                    \"quarter\": <int o null>,\n",
        "                    \"minute\": <int o null>,\n"
        "                    \"clock\": \"<cronometro a scalare mm:ss come scritto sul foglio, es. '4:44', o null>\",\n"
        "                    \"quarter\": <int o null>,\n",
    )
)

# V3.3 — variante CLOCK-ONLY di V3.1 (giro §8.17, 23/07): isola il guadagno
# reale e indipendente misurato in V3.2 (§8.16) — il campo clock mm:ss — e
# SCARTA l'ancoraggio di periodo per gli eventi isolati, che in V3.2 ha prodotto
# zero movimento sul residuo e ha aggiunto peso/rumore alla sezione EVENTI.
# UNA sola modifica additiva a V3.1, in due punti coordinati della sezione EVENTI:
#   (a) istruzione "clock" (cronometro a scalare mm:ss) accanto a "minute", con
#       la nota che gli stessi valori si ripetono nei quattro periodi (il clock
#       NON identifica il periodo);
#   (a') schema: campo "clock" additivo accanto a "minute" nell'oggetto evento.
# Costruita per SOSTITUZIONE MIRATA su V3 con le stesse DUE .replace() del clock
# di V3.2 (byte-identiche), OMESSA la terza .replace() dell'ancoraggio: così ogni
# altra zona (punteggi, nomi, data, rigori, ancoraggio di periodo) resta IDENTICA
# byte-per-byte a V3.1, e V3.3 differisce da V3.2 ESATTAMENTE per il solo blocco
# di ancoraggio. Qualunque scarto misurato tra V3.1/V3.2 e V3.3 sulle zone
# invariate è varianza di campionamento, non effetto del prompt.
# NON è il default di produzione: si seleziona via settings.OCR_PROMPT_VERSION
# o dal bench (ocr_bench --prompt-version v3_3). La promozione a default è una
# decisione di prodotto sui numeri del bench, non un fatto tecnico.
OCR_SYSTEM_PROMPT_V3_3 = (
    OCR_SYSTEM_PROMPT_V3
    # (a) CLOCK COMPLETO: cronometro a scalare mm:ss accanto al minuto.
    # Byte-identica alla (a) di V3.2.
    .replace(
        "           - Importante: Trascrivi i gol (GOL) e le espulsioni (ET come EXCLUSION_20).\n",
        "           - Importante: Trascrivi i gol (GOL) e le espulsioni (ET come EXCLUSION_20).\n"
        "           - TEMPO (\"clock\"): la colonna Tempo è un CRONOMETRO A SCALARE dentro il\n"
        "             periodo, in formato mm:ss: parte da circa 7:55 a inizio periodo e SCENDE\n"
        "             fino a 0:00. Trascrivilo ESATTAMENTE come scritto nella stringa \"clock\"\n"
        "             (es. \"4:44\", \"0:58\", \"0:09\"), oltre al campo \"minute\". NON arrotondare.\n"
        "             Gli STESSI valori di clock si ripetono in tutti e quattro i periodi:\n"
        "             il clock NON identifica il periodo, indica solo l'ordine dentro la sezione.\n",
    )
    # (a') schema: campo "clock" additivo accanto a "minute" nell'oggetto evento.
    # Byte-identica alla (a) schema di V3.2.
    .replace(
        "                    \"minute\": <int o null>,\n"
        "                    \"quarter\": <int o null>,\n",
        "                    \"minute\": <int o null>,\n"
        "                    \"clock\": \"<cronometro a scalare mm:ss come scritto sul foglio, es. '4:44', o null>\",\n"
        "                    \"quarter\": <int o null>,\n",
    )
)

# V3.4 — variante di V3.3 (clock-only) + DUE semantiche nuove nella sezione EVENTI
# (giro §8.18, 23/07). Isola l'effetto di due tipi di evento finora non gestiti dal
# prompt, misurati sul referto 8 (Unime vs Nautilus Roma):
#   (A) TIMEOUT: sul foglio è "T.O." con asterisco nella colonna della squadra che
#       lo chiama. Va estratto come evento con "team" e "clock", SENZA calottina
#       (il timeout è della squadra, "player_name" null).
#   (B) ESPULSIONE DEFINITIVA (EXCLUSION_DEF): riga siglata "EDCS" o equivalente, con
#       nella colonna del PUNTEGGIO il numero dell'articolo di regolamento (es. "9.13").
#       REGOLA DI PROGETTO: il prompt NON insegna la tassonomia degli articoli. Deve
#       solo (a) riconoscere che la riga è un'espulsione definitiva e NON un gol,
#       (b) estrarre l'articolo VERBATIM come stringa, (c) estrarre la sigla verbatim.
#       La mappatura articolo->tipo vive nel NOSTRO codice (matches/event_types.py,
#       DEFINITIVE_EXCLUSION_ARTICLES + classify_definitive_exclusion), non qui: un
#       articolo mai visto resta grezzo e mappabile dopo, non inventato dal modello.
#       Trappola neutralizzata esplicitamente: l'articolo sta nella colonna del punteggio
#       e ASSOMIGLIA a un punteggio, ma su una riga di espulsione definitiva è un ARTICOLO
#       e NON deve mai entrare nella progressione del punteggio.
# Costruita per SOSTITUZIONE MIRATA su V3.3 (stesso meccanismo di V3.2/V3.3): ogni
# altra zona resta IDENTICA byte-per-byte a V3.3 (che a sua volta = V3.1 + clock).
# NON è il default di produzione: si seleziona via settings.OCR_PROMPT_VERSION o dal
# bench (ocr_bench --prompt-version v3_4). La promozione a default è una decisione di
# prodotto sui numeri del bench, non un fatto tecnico. DA MISURARE: bloccata dal cap
# Gemini (nessuna chiamata reale eseguita in questo giro).
OCR_SYSTEM_PROMPT_V3_4 = (
    OCR_SYSTEM_PROMPT_V3_3
    # (A)+(B) istruzioni: timeout di squadra ed espulsione definitiva, aggiunte in
    # coda al blocco RIGORI della sezione EVENTI (anchor presente in V3.1/V3.3).
    .replace(
        '             * Per ogni altro evento "is_penalty" è false (o omesso).\n',
        '             * Per ogni altro evento "is_penalty" è false (o omesso).\n'
        '           - TIMEOUT (type "TIMEOUT"): sul foglio è siglato "T.O." con un\n'
        '             asterisco nella colonna della SQUADRA che lo ha chiamato. Estrailo\n'
        '             come evento con "team" e "clock" (e "quarter" dalla sezione), ma\n'
        '             SENZA numero di calottina: il timeout è della SQUADRA, non del\n'
        '             giocatore, quindi "player_name" è null.\n'
        '           - ESPULSIONE DEFINITIVA (type "EXCLUSION_DEF"): una riga siglata "EDCS"\n'
        '             (Espulsione Definitiva Con Sostituzione) o sigla equivalente NON è un\n'
        '             gol ed è DISTINTA dall\'esclusione di 20 secondi. Per queste righe:\n'
        '             * usa "type": "EXCLUSION_DEF" (MAI "GOAL");\n'
        '             * trascrivi la sigla ESATTAMENTE come scritta in "sanction_sigla"\n'
        '               (es. "EDCS"), senza interpretarla;\n'
        '             * accanto alla sigla, nella colonna del PUNTEGGIO, c\'è il NUMERO\n'
        '               DELL\'ARTICOLO di regolamento (es. "9.13"): trascrivilo VERBATIM come\n'
        '               stringa in "regulation_article". NON dedurre da esso il tipo di\n'
        '               sanzione e NON normalizzarlo: la mappatura avviene a valle, non è\n'
        '               compito tuo.\n'
        '             * TRAPPOLA DA EVITARE: quel numero d\'articolo sta nella colonna del\n'
        '               punteggio e ASSOMIGLIA a un punteggio, ma NON lo è. Su una riga di\n'
        '               espulsione definitiva il valore in colonna punteggio è un ARTICOLO,\n'
        '               non un punteggio: NON deve MAI entrare nella progressione del\n'
        '               punteggio né nei parziali/risultato finale.\n',
    )
    # (B) enum "type": aggiunge EXCLUSION_DEF ai tipi ammessi.
    .replace(
        '                    "type": "GOAL|EXCLUSION_20|YELLOW_CARD|RED_CARD|TIMEOUT|OTHER",\n',
        '                    "type": "GOAL|EXCLUSION_20|EXCLUSION_DEF|YELLOW_CARD|RED_CARD|TIMEOUT|OTHER",\n',
    )
    # (B) schema: due campi additivi per l'espulsione definitiva, dopo sanction_duration.
    .replace(
        '                    "sanction_duration": <null o intero secondi (es: 20 per esclusione 20 secondi)>\n',
        '                    "sanction_duration": <null o intero secondi (es: 20 per esclusione 20 secondi)>,\n'
        '                    "sanction_sigla": "<sigla verbatim della sanzione come scritta sul foglio, es. \'EDCS\', o null>",\n'
        '                    "regulation_article": "<numero d\'articolo di regolamento VERBATIM come stringa, es. \'9.13\', o null (SOLO per EXCLUSION_DEF)>"\n',
    )
)

# Registro delle versioni di prompt selezionabili. Il default di produzione
# resta "v2" (fallback tecnico); config/settings.py imposta v3 come default reale.
# V3.2, V3.3 e V3.4 sono sperimentali e NON promosse: si selezionano solo per-chiamata
# (parametro prompt_version, usato dal bench: ocr_bench --prompt-version v3_4).
# Aggiungere una versione = una costante sopra + una entry qui.
OCR_SYSTEM_PROMPTS = {
    "v2": OCR_SYSTEM_PROMPT_V2,
    "v3": OCR_SYSTEM_PROMPT_V3,
    "v3_2": OCR_SYSTEM_PROMPT_V3_2,
    "v3_3": OCR_SYSTEM_PROMPT_V3_3,
    "v3_4": OCR_SYSTEM_PROMPT_V3_4,
}

# Prompt "solo zona" per il SECONDO passaggio della doppia estrazione
# (Macro 8, giro 2026-07-22). Non è un prompt di produzione a sé: è la seconda
# lettura, indipendente dalla prima, ristretta alle tre zone in cui vivono gli
# errori stabili misurati sul gold — griglia 'Risultati parziali' (8 celle),
# 'Risultato finale' di ciascuna squadra, data della gara. Output JSON minimale
# (solo quei campi + confidence + warnings). Eredita da V3 le due regole che
# contano su queste zone: anti-riconciliazione (parziali = letture, mai calcoli;
# finale trascritto indipendentemente, discordanza somma/finale segnalata e MAI
# aggiustata) e trascrizione letterale cifra-per-cifra (la data non si deduce dal
# contesto). Non estrae nomi/roster/eventi: quelli restano al primo passaggio.
# La seconda chiamata NON deve MAI ricevere il risultato della prima: l'indipendenza
# è il punto dell'esperimento (secondo atto di lettura, non confronto guidato).
OCR_SYSTEM_PROMPT_ZONE = """
        Sei un esperto di analisi di referti di partite di pallanuoto (FIN - GUG).
        Riceverai la FOTO di un referto ufficiale. Questo è un SECONDO atto di
        lettura, indipendente: leggi SOLO tre zone del foglio e ignora tutto il
        resto (roster, eventi, ufficiali, campionato). Non hai memoria di alcuna
        lettura precedente: trascrivi ciò che vedi ORA sul foglio, mai ciò che
        "ti aspetteresti" di leggere.

        Le tre zone da leggere, e SOLO queste:

        1. GRIGLIA 'Risultati parziali' (le 8 celle al centro del foglio):
           - Trascrivi le 8 celle ESATTAMENTE come le vedi, cella per cella. Ogni
             cella è una LETTURA, mai un calcolo: NON ricavare nessuna cella da
             altre celle né dal risultato finale.
           - Se il punteggio di un quarto non è leggibile, usa null per quel quarto.

        2. 'Risultato finale' di ciascuna squadra (il numero in fondo alla casella
           di ogni squadra: casa in alto a sinistra, ospite in basso a sinistra):
           - È una trascrizione INDIPENDENTE del numero scritto: NON è la somma dei
             parziali e NON va ricavato né corretto a partire da essi.
           - Se la somma dei parziali NON torna col risultato finale trascritto,
             NON aggiustare niente: riporta i valori discordi esattamente come
             sono scritti e segnala la discordanza in extraction_warnings. La
             discordanza è un esito ammesso e prezioso, non un errore da nascondere.

        3. DATA della gara:
           - Leggila cifra per cifra come scritta sul foglio, senza dedurla dal
             contesto (stagione, campionato, altre scritte sul foglio).
           - Riporta in "date_digits" la trascrizione esatta come scritta
             (es. "11/04/2026") e in "date" la stessa data in formato YYYY-MM-DD.
           - Se anche una sola cifra è incerta, usa null in "date" e segnala il
             dubbio in extraction_warnings.

        REGOLE CRITICHE:
        - Se un dato è ILLEGGIBILE, PARZIALE o AMBIGUO: usa null. NON INDOVINARE MAI.
        - NON normalizzare, NON dedurre, NON correggere verso valori "attesi":
          trascrivi esattamente le cifre scritte, anche se il risultato sembra
          insolito o la somma non torna.

        FORMATO JSON RICHIESTO (SOLO questi campi, niente altro):
        {
            "metadata": {
                "schema_version": "zone-1.0",
                "confidence": <0.0-1.0 fiducia complessiva sulle tre zone>,
                "confidence_fields": {
                    "final_score": <0.0-1.0>,
                    "quarters": <0.0-1.0>,
                    "date": <0.0-1.0>
                },
                "extraction_warnings": [
                    "<ogni ambiguità o discordanza somma parziali/finale>"
                ]
            },
            "match_info": {
                "date": "<YYYY-MM-DD o null se illeggibile>",
                "date_digits": "<data trascritta cifra per cifra come scritta, o null>"
            },
            "scores": {
                "final_score": "<X-Y o null>",
                "quarters": {
                    "1": [<home, away> o null],
                    "2": [<home, away> o null],
                    "3": [<home, away> o null],
                    "4": [<home, away> o null]
                }
            }
        }

        Rispondi SOLO con il JSON. Non aggiungere testo, commenti o markdown.
        """

# Registro dei prompt del secondo passaggio (doppia estrazione). Tenuto SEPARATO
# da OCR_SYSTEM_PROMPTS: "zone" non è una versione di prompt di produzione (non
# estrae roster/eventi), non va mai usata come OCR_PROMPT_VERSION di default.
OCR_SECOND_PASS_PROMPTS = {
    "zone": OCR_SYSTEM_PROMPT_ZONE,
}

# Vista unificata usata dalla risoluzione del prompt (extract_data) e dal bench:
# accetta sia le versioni di produzione sia i prompt del secondo passaggio.
OCR_ALL_PROMPTS = {**OCR_SYSTEM_PROMPTS, **OCR_SECOND_PASS_PROMPTS}

class BaseVisionProvider:
    """
    Interfaccia base per i provider OCR/Vision.
    Ogni nuovo provider (es. Google Vision, AWS Textract)
    deve ereditare da questa classe e implementare extract_data.
    """
    def extract_data(self, match_report) -> Tuple[Dict[str, Any], str]:
        raise NotImplementedError("Il metodo extract_data deve essere implementato dal provider.")

    @staticmethod
    def _normalize_response(data: Dict[str, Any], processed_path: str, original_path: str,
                            model: str = "gemini-2.5-pro", usage=None,
                            provider: str = "GeminiVisionProvider-v1") -> Dict[str, Any]:
        """
        Normalize a vision-provider response into the OCR v2 schema.
        Fills in missing optional sections with safe defaults.
        Trims whitespace from string fields. Passare `provider` per marcare la
        provenienza. `usage`, se fornito, espone .prompt_tokens / .completion_tokens.
        """
        # Ensure metadata structure
        if "metadata" not in data:
            data["metadata"] = {}
        meta = data["metadata"]
        meta.setdefault("schema_version", "2.0")
        meta.setdefault("confidence", 0.5)
        meta.setdefault("confidence_fields", {})
        meta.setdefault("extraction_warnings", [])
        meta.update({
            "provider": provider,
            "extracted_at": timezone.now().isoformat(),
            "model": model,
            "preprocessed": processed_path != original_path
        })
        if usage is not None:
            meta["token_usage"] = {
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
            }

        # Ensure match_info
        data.setdefault("match_info", {})
        info = data["match_info"]
        info.setdefault("home_team", None)
        info.setdefault("away_team", None)
        info.setdefault("date", None)
        # v2 optional fields
        info.setdefault("venue", None)
        info.setdefault("round", None)
        info.setdefault("group", None)
        # Trim whitespace from string fields
        for k in ["home_team", "away_team", "competition", "city", "venue", "round", "group"]:
            if isinstance(info.get(k), str):
                info[k] = info[k].strip()

        # Ensure officials structure (v2 — opzionale)
        data.setdefault("officials", {
            "confidence": None,
            "referees": [],
            "timekeeper": None,
        })
        officials = data["officials"]
        if isinstance(officials, dict):
            officials.setdefault("confidence", None)
            officials.setdefault("referees", [])
            officials.setdefault("timekeeper", None)
            # Trim referee names
            for ref in officials.get("referees", []):
                if isinstance(ref, dict) and isinstance(ref.get("name"), str):
                    ref["name"] = ref["name"].strip()

        # Ensure scores structure
        data.setdefault("scores", {})
        scores = data["scores"]
        if isinstance(scores.get("final_score"), str):
            scores["final_score"] = scores["final_score"].strip()
        scores.setdefault("quarters", {})

        # Ensure teams structure
        data.setdefault("teams", {"home": {"name": None, "players": []}, "away": {"name": None, "players": []}})
        for side in ["home", "away"]:
            team = data["teams"].setdefault(side, {"name": None, "players": []})
            team.setdefault("players", [])
            # v2 optional team fields
            team.setdefault("coach", None)
            team.setdefault("confidence", None)
            # Trim player names
            for p in team.get("players", []):
                if isinstance(p.get("name"), str):
                    p["name"] = p["name"].strip()

        # Ensure events structure. `is_penalty` è additivo e retrocompatibile:
        # un'estrazione che non lo emette (V2, mock, prompt più vecchi) lo riceve
        # a false qui, così il percorso a valle può leggerlo sempre come booleano.
        data.setdefault("events", [])
        if isinstance(data["events"], list):
            for ev in data["events"]:
                if isinstance(ev, dict):
                    ev["is_penalty"] = bool(ev.get("is_penalty", False))

        return data

class MockVisionProvider(BaseVisionProvider):
    """
    Provider Mock che simula un'estrazione OCR perfetta usando i dati del database.
    Usato per test e sviluppo senza chiamate a servizi esterni.
    """
    def extract_data(self, match_report) -> Tuple[Dict[str, Any], str]:
        match = match_report.match
        
        logger.info(f"[MockVisionProvider] Simulo estrazione per report {match_report.id}")

        data = {
            "metadata": {
                "schema_version": "2.0",
                "provider": "MockVisionProvider-v1",
                "extracted_at": timezone.now().isoformat(),
                "confidence": 0.98,
                "confidence_fields": {
                    "home_team": 0.99,
                    "away_team": 0.99,
                    "final_score": 0.99,
                    "quarters": 0.95,
                    "home_roster": 0.90,
                    "away_roster": 0.90,
                    "events": 0.85,
                    "officials": 0.80,
                },
                "extraction_warnings": []
            },
            "match_info": {
                "home_team": match.home_team.society.name if match.home_team else "Unknown Home",
                "away_team": match.away_team.society.name if match.away_team else "Unknown Away",
                "competition": match.league.name if match.league else "Unknown Competition",
                "date": match.match_date.strftime("%Y-%m-%d") if match.match_date else None,
                "city": match.location or "Not specified",
                "venue": None,
                "round": None,
                "group": None,
            },
            "officials": {
                "confidence": 0.80,
                "referees": [
                    {"name": "Arbitro Mock Primo", "role": "1st"},
                    {"name": "Arbitro Mock Secondo", "role": "2nd"},
                ],
                "timekeeper": "Segnapunti Mock",
            },
            "teams": {
                "home": {
                    "name": match.home_team.society.name if match.home_team else "Home",
                    "coach": "Allenatore Mock Casa",
                    "confidence": 0.90,
                    "players": [
                        {"number": 1, "name": "Portiere Mock"},
                        {"number": 10, "name": "Capitano Mock"}
                    ]
                },
                "away": {
                    "name": match.away_team.society.name if match.away_team else "Away",
                    "coach": "Allenatore Mock Ospite",
                    "confidence": 0.90,
                    "players": [
                        {"number": 1, "name": "Opponente Mock"},
                        {"number": 5, "name": "Difensore Mock"}
                    ]
                }
            },
            "scores": {
                "final_score": f"{match.home_score or 0}-{match.away_score or 0}",
                "quarters": match.quarter_scores or {}
            },
            "events": [
                {"type": "GOAL", "player_name": "Capitano Mock", "minute": 5, "team": "home", "quarter": 1},
                {"type": "EXCLUSION_20", "player_name": "Difensore Mock", "minute": 15, "team": "away", "quarter": 2},
                {"type": "TIMEOUT", "player_name": None, "minute": 18, "team": "home", "quarter": 2, "sanction_duration": None},
            ],
            "notes": "Estrazione simulata dal MockVisionProvider v2."
        }
        
        raw_content = json.dumps(data, indent=4, ensure_ascii=False)
        return data, raw_content


def _gemini_finish_reason(response):
    """
    Estrae il finish_reason del primo candidate se l'SDK google-genai lo espone
    (es. 'MAX_TOKENS' quando l'output viene troncato). Ritorna una stringa o None.
    Difensivo: qualunque forma inattesa della response non deve far esplodere il parse.
    """
    try:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return None
        fr = getattr(candidates[0], "finish_reason", None)
        if fr is None:
            return None
        # google-genai espone un enum: preferisci .name, fallback a str().
        return getattr(fr, "name", None) or str(fr)
    except Exception:
        return None


class GeminiVisionProvider(BaseVisionProvider):
    """
    Provider reale che utilizza Google Gemini (SDK google-genai) per estrarre
    dati dal referto. Interfaccia extract_data: parametri
    model/preprocess/sent_image_callback/prompt_version, schema OCR v2 in
    output, prompt di sistema selezionato da OCR_SYSTEM_PROMPTS (default
    OCR_SYSTEM_PROMPT_V2). Il modello di default è letto da
    settings.GEMINI_MODEL con fallback a 'gemini-2.5-pro'; --models nel bench
    può passare qualsiasi model string.
    """
    def __init__(self):
        from django.conf import settings
        from google import genai
        self.client = genai.Client(api_key=getattr(settings, "GEMINI_API_KEY", ""))

    def extract_data(self, match_report, model: str = None, preprocess: bool = True,
                     sent_image_callback=None,
                     prompt_version: str = None) -> Tuple[Dict[str, Any], str]:
        """
        preprocess=False bypassa ImagePreprocessor e invia i byte grezzi;
        sent_image_callback, se fornita, riceve il path del file effettivamente
        inviato al modello, prima della chiamata API. prompt_version seleziona
        il prompt di sistema fra OCR_SYSTEM_PROMPTS (override per-chiamata >
        settings.OCR_PROMPT_VERSION > "v2": il default di produzione resta V2).
        Ritorna (data, raw_content).
        """
        import mimetypes
        import os
        from django.conf import settings
        from google.genai import types

        # Modello: override per-chiamata > settings.GEMINI_MODEL > default
        model = model or getattr(settings, "GEMINI_MODEL", "gemini-2.5-pro")

        # Prompt: override per-chiamata > settings.OCR_PROMPT_VERSION > v2.
        # Risoluzione su OCR_ALL_PROMPTS: include sia le versioni di produzione
        # (v2/v3) sia i prompt del secondo passaggio (zone), così il bench può
        # richiedere "zone" per-chiamata senza che questo diventi una versione
        # di produzione (OCR_PROMPT_VERSION resta v2 salvo decisione esplicita).
        prompt_version = prompt_version or getattr(settings, "OCR_PROMPT_VERSION", "v2")
        if prompt_version not in OCR_ALL_PROMPTS:
            raise ValueError(
                f"Prompt version sconosciuta: {prompt_version!r} "
                f"(disponibili: {', '.join(sorted(OCR_ALL_PROMPTS))})"
            )
        system_prompt = OCR_ALL_PROMPTS[prompt_version]

        logger.info(f"[GeminiVisionProvider] Avvio preprocessing per report {match_report.id} (model={model}, prompt={prompt_version})...")

        if not match_report.file:
            raise ValueError("Il referto non ha alcun file associato. Impossibile eseguire OCR.")

        # Preprocessing (bypassabile per debug).
        # Import lazy: nel path raw (preprocess=False) non tocchiamo cv2.
        original_path = match_report.file.path
        if preprocess:
            from .image_preprocessor import ImagePreprocessor
            processed_path = ImagePreprocessor.process(original_path)
            mime_type = "image/jpeg"
        else:
            logger.info(f"[GeminiVisionProvider] Preprocessing bypassato per report {match_report.id}: invio immagine grezza.")
            processed_path = original_path
            mime_type = mimetypes.guess_type(processed_path)[0] or "image/jpeg"

        logger.info(f"[GeminiVisionProvider] Invio report a Gemini: {processed_path}")

        if sent_image_callback:
            sent_image_callback(processed_path)

        with open(processed_path, "rb") as f:
            image_bytes = f.read()

        # Limite di output token: i referti densi (molti eventi + due roster) troncano
        # facilmente a 4000, producendo JSON incompleto. Default alto ma entro il massimo
        # supportato dai modelli Gemini candidati (2.5-flash: 65k; 3.x pro-preview: ampio).
        # Configurabile via settings.OCR_MAX_OUTPUT_TOKENS senza toccare il codice.
        max_output_tokens = getattr(settings, "OCR_MAX_OUTPUT_TOKENS", 32000)

        try:
            response = self.client.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    OCR_USER_TEXT,
                ],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    max_output_tokens=max_output_tokens,
                ),
            )

            content = response.text
            logger.info(f"[GeminiVisionProvider] Risposta Gemini ricevuta (lunghezza: {len(content) if content else 0})")

            finish_reason = _gemini_finish_reason(response)

            if not content:
                suffix = f" (finish_reason={finish_reason})" if finish_reason else ""
                raise Exception(f"Gemini ha restituito un contenuto vuoto{suffix}.")

            # Parse difensivo: un output troncato per limite token arriva come JSON
            # incompleto (es. 'Unterminated string'). Trasformalo in un messaggio chiaro
            # con il motivo del troncamento, così il bench lo marca come fallito e
            # leggibile invece di propagare un JSONDecodeError grezzo.
            try:
                data = json.loads(content)
            except (ValueError, json.JSONDecodeError) as je:
                if finish_reason and "MAX_TOKENS" in finish_reason.upper():
                    hint = (
                        f" (output troncato per limite token, finish_reason={finish_reason}; "
                        f"alza OCR_MAX_OUTPUT_TOKENS oltre {max_output_tokens})"
                    )
                elif finish_reason:
                    hint = f" (finish_reason={finish_reason})"
                else:
                    hint = ""
                raise Exception(f"JSON troncato/invalido dalla risposta{hint}: {je}")

            # token_usage per il confronto costi (N/A se l'SDK non lo espone)
            usage = None
            usage_meta = getattr(response, "usage_metadata", None)
            if usage_meta is not None:
                usage = SimpleNamespace(
                    prompt_tokens=getattr(usage_meta, "prompt_token_count", None),
                    completion_tokens=getattr(usage_meta, "candidates_token_count", None),
                )

            data = self._normalize_response(
                data, processed_path, original_path,
                model=model,
                usage=usage,
                provider="GeminiVisionProvider-v1",
            )

            return data, content

        except Exception as e:
            logger.error(f"Errore Gemini: {str(e)}")
            raise Exception(f"Errore durante la chiamata a Gemini: {str(e)}")
