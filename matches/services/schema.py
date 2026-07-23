from typing import Dict, Any, Tuple, List

# -- Schema version --
SCHEMA_VERSION = "2.0"

# --- Esiti del confronto eventi-gol / parziale, per periodo (§8.5(b)-1) -------
#: Conteggio eventi-gol del periodo uguale al parziale del periodo.
PERIOD_OK = "ok"
#: Piu' eventi-gol del parziale: impossibile per costruzione (D1).
PERIOD_EXCESS = "excess"
#: Meno eventi-gol del parziale: puo' essere semplice mancata rilevazione (D2/D3).
PERIOD_DEFICIT = "deficit"
#: Confronto non eseguibile su quel periodo (parziale illeggibile o malformato).
PERIOD_NOT_APPLICABLE = "not_applicable"

#: Prefisso dei messaggi che `assess_publish_readiness` promuove a blocker.
PERIOD_BLOCKER_PREFIX = "Incoerenza per-periodo"
#: Prefisso dei messaggi puramente informativi (mai blocker, in nessun punto).
PERIOD_EVIDENCE_PREFIX = "Evidenza per-periodo"

# --- Livelli di pubblicazione (Opzione A) ------------------------------------
# Stringhe, non l'enum di `MatchReport`, per tenere questo modulo privo di
# import di modelli (come `result_visibility`). Coincidono con
# `MatchReport.PublicationLevel`.
LEVEL_FULL = "FULL"
LEVEL_SCORE_ONLY = "SCORE_ONLY"

#: Marcatore anteposto a un blocker EVENT-SCOPED quando viene declassato a
#: warning sul livello SCORE_ONLY (il referto dichiara "eventi non disponibili").
OUT_OF_LEVEL_PREFIX = "[fuori livello]"

#: Blocker che dipendono dagli EVENTI (roster, eventi-gol, riconciliazione,
#: coerenza eventi/per-periodo). Sul livello SCORE_ONLY questi NON bloccano —
#: sono declassati a warning marcati `OUT_OF_LEVEL_PREFIX`. Sul livello FULL
#: restano blocker, invariati byte per byte: il declassamento e' attivo SOLO su
#: SCORE_ONLY. Match per sottostringa sul testo del blocker.
_EVENT_SCOPED_BLOCKER_MARKERS = (
    "Entrambi i roster sono vuoti",
    "Incoerenza eventi",
    PERIOD_BLOCKER_PREFIX,          # "Incoerenza per-periodo"
    "Zero Eventi",
    "Riconciliazione incompleta",
)

class OCRSchemaValidator:
    """
    Validatore nativo e strutturato per il payload OCR (normalized_data).
    Agisce come contratto di garanzia tra l'engine OCR, l'edit manuale via admin, e il PublishingService.
    Evita l'uso di dipendenze esterne come jsonschema o pydantic per l'MVP.
    """

    @staticmethod
    def validate(data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Valida il payload JSON.
        Ritorna: (success: bool, error_message: str)
        """
        if not isinstance(data, dict):
            return False, "Il payload deve essere un oggetto JSON."

        # 1. Verifica chiavi principali
        required_roots = ["metadata", "match_info", "scores", "teams", "events"]
        missing = [r for r in required_roots if r not in data]
        if missing:
            return False, f"Chiavi root mancanti: {', '.join(missing)}"

        # 2. Verifica Metadata
        meta = data.get("metadata", {})
        if not isinstance(meta, dict) or "confidence" not in meta:
            return False, "Sezione 'metadata': deve contenere 'confidence' (numero)."
        if not isinstance(meta["confidence"], (int, float)):
            return False, "Sezione 'metadata': 'confidence' deve essere un numero."

        # 3. Verifica Match Info
        info = data.get("match_info", {})
        if not isinstance(info, dict):
            return False, "Sezione 'match_info': deve essere un oggetto."
        if "home_team" not in info or "away_team" not in info:
            return False, "Sezione 'match_info': mancano 'home_team' o 'away_team'."

        # 4. Verifica Scores
        scores = data.get("scores", {})
        if not isinstance(scores, dict):
            return False, "Sezione 'scores': deve essere un oggetto."
        # Validiamo final_score (opzionale ma se c'è deve essere corretto)
        if "final_score" in scores and scores["final_score"] is not None:
            fs = scores["final_score"]
            if not isinstance(fs, str) or "-" not in fs:
                return False, "Sezione 'scores': 'final_score' deve essere nel formato 'X-Y'."
            # Robustezza extra: verifica che siano numeri
            try:
                parts = [p.strip() for p in fs.split("-")]
                if len(parts) != 2 or not all(p.isdigit() for p in parts):
                    return False, "Sezione 'scores': 'final_score' deve contenere due numeri separati da '-'."
            except Exception:
                return False, "Sezione 'scores': errore nel parsing del formato 'final_score'."

        # 5. Verifica Teams
        teams = data.get("teams", {})
        if not isinstance(teams, dict):
            return False, "Sezione 'teams': deve essere un oggetto."

        # 6. Verifica Events
        events = data.get("events", [])
        if not isinstance(events, list):
            return False, "Sezione 'events': deve essere una lista."
        for e in events:
            if not isinstance(e, dict) or "type" not in e:
                return False, "Gli elementi in 'events' devono essere oggetti con almeno il campo 'type'."

        # 7. Verifica Officials (opzionale, struttura soft)
        officials = data.get("officials")
        if officials is not None:
            if not isinstance(officials, dict):
                return False, "Sezione 'officials': se presente deve essere un oggetto."
            referees = officials.get("referees")
            if referees is not None and not isinstance(referees, list):
                return False, "Sezione 'officials.referees': se presente deve essere una lista."
            if isinstance(referees, list):
                for ref in referees:
                    if not isinstance(ref, dict):
                        return False, "Ogni arbitro in 'officials.referees' deve essere un oggetto."

        # 8. Verifica teams.coach (opzionale, struttura soft)
        for side in ["home", "away"]:
            team = teams.get(side, {})
            if isinstance(team, dict):
                coach = team.get("coach")
                if coach is not None and not isinstance(coach, str):
                    return False, f"teams.{side}.coach: se presente deve essere una stringa o null."
                team_conf = team.get("confidence")
                if team_conf is not None and not isinstance(team_conf, (int, float)):
                    return False, f"teams.{side}.confidence: se presente deve essere un numero."

        return True, "Validazione passata."

    @staticmethod
    def check_goal_events_per_period(data: Dict[str, Any]) -> Dict[str, Any]:
        """Confronta, periodo per periodo, gli eventi-gol estratti con il parziale.

        Gemello per-periodo del check aggregato (eventi-gol totali contro
        punteggio finale) che vive nel punto 4 di ``validate_coherence``. E'
        strettamente piu' informativo di quello: un eccesso locale puo' esistere
        anche quando i totali tornano.

        Opera ESCLUSIVAMENTE su ``normalized_data``. Non deve mai leggere
        ``MatchEvent``: alla proiezione a DB il periodo mancante viene forzato a 1
        (``quarter or 1`` in ``publishing_service``), quindi un gol senza periodo
        diventa indistinguibile da un gol del primo tempo e il confronto darebbe
        un risultato inventato.

        Le due direzioni NON sono simmetriche:

        * **Eccesso** (piu' eventi-gol del parziale) e' impossibile per
          costruzione: nessuna mancata rilevazione puo' produrlo. E' sempre un
          errore di estrazione. Resta valido anche se altri gol non hanno periodo,
          perche' assegnarli potrebbe solo aumentare i conteggi.
        * **Difetto** (meno eventi-gol del parziale) e' spiegabile da una
          cronologia letta solo in parte. Diventa significativo solo quando
          l'estrazione della squadra si dichiara completa (somma eventi-gol ==
          punteggio finale della squadra), e non e' valutabile affatto se qualche
          gol di quella squadra e' privo di periodo.

        Returns:
            dict con la tabella per-periodo (``rows``), gli esiti separati per
            direzione, i gol senza periodo e i messaggi gia' formattati. Ogni
            impossibilita' di concludere e' esplicita (``applicable``,
            ``not_applicable_reason``, ``deficit_not_applicable``,
            ``PERIOD_NOT_APPLICABLE`` sulla riga): non esiste un caso in cui il
            check taccia senza dire perche'.
        """
        from ..event_types import SCORE_EVENT_CODES

        result: Dict[str, Any] = {
            "applicable": False,
            "not_applicable_reason": None,
            "rows": [],
            "excess": [],
            "deficit": [],
            "deficit_not_applicable": {"home": None, "away": None},
            "unassigned_goals": {"home": 0, "away": 0},
            "extraction_complete": {"home": None, "away": None},
            "counts": {
                "periods": 0,
                "periods_excess": 0,
                "periods_deficit": 0,
                "periods_not_applicable": 0,
            },
            "messages": {"excess": [], "distribution": [], "evidence": []},
        }

        def _bail(reason: str) -> Dict[str, Any]:
            """Uscita anticipata che DICHIARA perche' il check non e' eseguibile.

            Nessun ramo puo' restituire un risultato silenzioso: un check muto
            si legge come "tutto a posto", ed e' la patologia che A1 ha rimosso.
            """
            result["not_applicable_reason"] = reason
            result["messages"]["evidence"].append(f"{PERIOD_EVIDENCE_PREFIX}: {reason}")
            return result

        if not isinstance(data, dict):
            return _bail("Payload OCR non valido: confronto per-periodo non eseguibile.")

        scores = data.get("scores", {})
        quarters = scores.get("quarters", {}) if isinstance(scores, dict) else {}
        if not isinstance(quarters, dict) or not quarters:
            return _bail(
                "Nessun punteggio parziale per periodo nel referto: "
                "il confronto per-periodo non e' eseguibile."
            )

        events = data.get("events", [])
        if not isinstance(events, list):
            return _bail("Sezione 'events' malformata: confronto per-periodo non eseguibile.")

        goals = [
            e for e in events
            if isinstance(e, dict)
            and e.get("type") in SCORE_EVENT_CODES
            and e.get("team") in ("home", "away")
        ]

        # Gol per (periodo, squadra); il periodo e' preso com'e', mai dedotto.
        per_period: Dict[str, Dict[str, int]] = {}
        for e in goals:
            side = e["team"]
            q = e.get("quarter")
            if q is None:
                result["unassigned_goals"][side] += 1
                continue
            key = str(q).strip()
            per_period.setdefault(key, {"home": 0, "away": 0})[side] += 1

        # Completezza dichiarata dell'estrazione, per squadra: serve a separare
        # D2 (distribuzione sbagliata) da D3 (cronologia letta solo in parte).
        home_total, away_total = None, None
        final_score = scores.get("final_score") if isinstance(scores, dict) else None
        if isinstance(final_score, str) and "-" in final_score:
            try:
                home_total, away_total = map(int, [p.strip() for p in final_score.split("-")])
            except (ValueError, TypeError):
                home_total, away_total = None, None
        totals_by_side = {"home": home_total, "away": away_total}
        for side in ("home", "away"):
            if totals_by_side[side] is None:
                continue
            extracted = sum(1 for e in goals if e["team"] == side)
            result["extraction_complete"][side] = (extracted == totals_by_side[side])

        # Il difetto non e' valutabile se qualche gol di quella squadra non ha periodo.
        for side in ("home", "away"):
            if result["unassigned_goals"][side]:
                result["deficit_not_applicable"][side] = (
                    f"{result['unassigned_goals'][side]} gol {'CASA' if side == 'home' else 'OSPITE'} "
                    f"senza periodo: il difetto per-periodo non e' valutabile per questa squadra."
                )

        #: Difetti con la squadra a cui appartengono, per non doverla riestrarre
        #: dal testo del messaggio quando si decide la severita'.
        deficit_by_side: List[Tuple[str, str]] = []

        def _sort_key(k):
            try:
                return (0, int(str(k).strip()))
            except (ValueError, TypeError):
                return (1, str(k))

        for q_key in sorted(quarters.keys(), key=_sort_key):
            q_vals = quarters[q_key]
            counted = per_period.get(str(q_key).strip(), {"home": 0, "away": 0})
            row = {
                "quarter": str(q_key),
                "home_partial": None,
                "away_partial": None,
                "home_goals": counted["home"],
                "away_goals": counted["away"],
                "home_outcome": PERIOD_NOT_APPLICABLE,
                "away_outcome": PERIOD_NOT_APPLICABLE,
                "outcome": PERIOD_NOT_APPLICABLE,
                "not_applicable_reason": None,
            }

            parsed = None
            if isinstance(q_vals, (list, tuple)) and len(q_vals) == 2:
                try:
                    parsed = (int(q_vals[0]), int(q_vals[1]))
                except (ValueError, TypeError):
                    parsed = None

            if parsed is None:
                row["not_applicable_reason"] = (
                    "Parziale illeggibile o assente per questo periodo."
                    if q_vals is None else
                    "Parziale in forma non confrontabile per questo periodo."
                )
                result["counts"]["periods_not_applicable"] += 1
                result["rows"].append(row)
                continue

            result["applicable"] = True
            result["counts"]["periods"] += 1
            row["home_partial"], row["away_partial"] = parsed

            outcomes = []
            for side, partial, count in (
                ("home", parsed[0], counted["home"]),
                ("away", parsed[1], counted["away"]),
            ):
                label = "CASA" if side == "home" else "OSPITE"
                if count > partial:
                    row[f"{side}_outcome"] = PERIOD_EXCESS
                    result["excess"].append(
                        f"Periodo {q_key} {label}: {count} eventi-gol estratti "
                        f"contro un parziale di {partial}."
                    )
                elif count < partial:
                    if result["deficit_not_applicable"][side]:
                        row[f"{side}_outcome"] = PERIOD_NOT_APPLICABLE
                    else:
                        row[f"{side}_outcome"] = PERIOD_DEFICIT
                        text = (
                            f"Periodo {q_key} {label}: {count} eventi-gol estratti "
                            f"contro un parziale di {partial}."
                        )
                        result["deficit"].append(text)
                        deficit_by_side.append((side, text))
                else:
                    row[f"{side}_outcome"] = PERIOD_OK
                outcomes.append(row[f"{side}_outcome"])

            if PERIOD_EXCESS in outcomes:
                row["outcome"] = PERIOD_EXCESS
                result["counts"]["periods_excess"] += 1
            elif PERIOD_DEFICIT in outcomes:
                row["outcome"] = PERIOD_DEFICIT
                result["counts"]["periods_deficit"] += 1
            elif PERIOD_NOT_APPLICABLE in outcomes:
                row["outcome"] = PERIOD_NOT_APPLICABLE
            else:
                row["outcome"] = PERIOD_OK

            result["rows"].append(row)

        if not result["applicable"] and result["not_applicable_reason"] is None:
            result["not_applicable_reason"] = (
                "Nessun periodo con un parziale confrontabile: "
                "il confronto per-periodo non e' eseguibile."
            )

        # --- Messaggi, gia' separati per severita' ratificata (D1/D2/D3) ---
        if result["excess"]:
            result["messages"]["excess"] = [
                f"{PERIOD_BLOCKER_PREFIX}: {m} Piu' gol del parziale e' impossibile "
                f"per costruzione, non e' una mancata rilevazione."
                for m in result["excess"]
            ]

        for side, m in deficit_by_side:
            # La direzione "difetto" pesa solo se la squadra dichiara di aver
            # estratto tutti i suoi gol: allora il totale torna ma la
            # distribuzione fra i periodi no, ed e' un errore vero (D2).
            # Altrimenti e' semplice cronologia letta in parte (D3).
            if result["extraction_complete"].get(side):
                result["messages"]["distribution"].append(
                    f"{PERIOD_BLOCKER_PREFIX}: {m} La squadra ha estratto tutti i suoi gol, "
                    f"quindi la distribuzione fra i periodi e' sbagliata."
                )
            else:
                result["messages"]["evidence"].append(
                    f"{PERIOD_EVIDENCE_PREFIX}: {m} Estrazione incompleta per questa "
                    f"squadra: puo' essere solo cronologia letta in parte."
                )

        for side in ("home", "away"):
            reason = result["deficit_not_applicable"][side]
            if reason:
                result["messages"]["evidence"].append(f"{PERIOD_EVIDENCE_PREFIX}: {reason}")

        if not result["applicable"]:
            result["messages"]["evidence"].append(
                f"{PERIOD_EVIDENCE_PREFIX}: {result['not_applicable_reason']}"
            )

        return result

    @staticmethod
    def validate_coherence(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Esegue controlli di coerenza logica profonda sui dati.
        Ritorna: (is_coherent: bool, warnings: List[str])
        I warnings non bloccano il salvataggio strutturale ma segnalano incongruenze all'admin.
        """
        warnings = []
        scores = data.get("scores", {})
        final_score_str = scores.get("final_score")
        quarters = scores.get("quarters", {})

        home_total, away_total = None, None

        # 0. Parse final score
        if final_score_str and isinstance(final_score_str, str) and "-" in final_score_str:
            try:
                home_total, away_total = map(int, [p.strip() for p in final_score_str.split("-")])
            except (ValueError, AttributeError):
                warnings.append("Punteggio finale non parsabile.")

        # 1. Impossible scores
        if home_total is not None:
            if home_total < 0 or away_total < 0:
                warnings.append(f"Punteggio negativo rilevato: {home_total}-{away_total}")
            if home_total > 40 or away_total > 40:
                warnings.append(f"Punteggio insolitamente alto: {home_total}-{away_total} (possibile errore OCR)")

        # 2. Quarter-level sanity
        for q_key, q_vals in quarters.items():
            if q_vals is None:
                continue  # null quarters are allowed (unreadable)
            if isinstance(q_vals, (list, tuple)) and len(q_vals) == 2:
                try:
                    qh, qa = int(q_vals[0]), int(q_vals[1])
                    if qh < 0 or qa < 0:
                        warnings.append(f"Quarto {q_key}: punteggio negativo ({qh}-{qa})")
                    if qh > 15 or qa > 15:
                        warnings.append(f"Quarto {q_key}: punteggio insolitamente alto ({qh}-{qa})")
                except (ValueError, TypeError):
                    warnings.append(f"Quarto {q_key}: valori non numerici")

        # 3. Coerenza Somma Quarti vs Totale
        if home_total is not None and quarters:
            try:
                h_sum, a_sum = 0, 0
                has_null_quarter = False
                for q_vals in quarters.values():
                    if q_vals is None:
                        has_null_quarter = True
                        continue
                    if isinstance(q_vals, (list, tuple)) and len(q_vals) == 2:
                        h_sum += int(q_vals[0])
                        a_sum += int(q_vals[1])
                
                if not has_null_quarter and (h_sum != home_total or a_sum != away_total):
                    warnings.append(f"Incoerenza punteggio: Somma quarti ({h_sum}-{a_sum}) != Finale ({home_total}-{away_total})")
            except (ValueError, AttributeError, TypeError):
                pass

        # 4. Coerenza Goal in eventi vs Totale
        from ..event_types import SCORE_EVENT_CODES
        events = data.get("events", [])
        goal_count_h = sum(1 for e in events if e.get("type") in SCORE_EVENT_CODES and e.get("team") == "home")
        goal_count_a = sum(1 for e in events if e.get("type") in SCORE_EVENT_CODES and e.get("team") == "away")

        
        if home_total is not None and events:
            if goal_count_h != home_total:
                warnings.append(f"Incoerenza eventi: {goal_count_h} gol estratti per CASA != {home_total} punteggio finale")
            if goal_count_a != away_total:
                warnings.append(f"Incoerenza eventi: {goal_count_a} gol estratti per OSPITE != {away_total} punteggio finale")

        # 4-bis. Coerenza gol-eventi vs parziale, periodo per periodo (§8.5(b)-1).
        # Qui il per-periodo si AFFIANCA all'aggregato del punto 4, non lo
        # sostituisce: al publish l'uguaglianza stretta fra gol estratti e
        # punteggio finale resta un requisito a se' (D6).
        # Passano solo le due direzioni "pesanti" (eccesso, e difetto con
        # estrazione dichiarata completa): `assess_publish_readiness` le promuove
        # a blocker. L'evidenza informativa NON entra qui — vive nella tabella
        # per-periodo mostrata in review, dove il revisore la legge come dato e
        # non come problema.
        period_check = OCRSchemaValidator.check_goal_events_per_period(data)
        warnings.extend(period_check["messages"]["excess"])
        warnings.extend(period_check["messages"]["distribution"])

        # 4-ter. Espulsioni per giocatore oltre il limite di 3 (regolamento pallanuoto).
        # Un 4o cartellino per lo stesso giocatore e' impossibile a regolamento: alla
        # terza il giocatore e' fuori partita. Se l'estrazione lo produce, e' un errore
        # di lettura (es. due giocatori diversi collassati sullo stesso nome, o un evento
        # duplicato). Simmetrico alla validazione sui casi gold (trascrizione umana).
        from ..event_types import players_over_exclusion_limit, FOUL_OUT_EXCLUSIONS
        for team, identity, cnt in players_over_exclusion_limit(events):
            side = {"home": "CASA", "away": "OSPITE"}.get(team, team or "?")
            warnings.append(
                f"Espulsioni oltre il limite: giocatore {identity} ({side}) con {cnt} "
                f"espulsioni (max {FOUL_OUT_EXCLUSIONS} a regolamento) — possibile errore di estrazione."
            )

        # 5. Unicità numeri giocatori
        teams = data.get("teams", {})
        for t_side in ["home", "away"]:
            players = teams.get(t_side, {}).get("players", [])
            numbers = [p.get("number") for p in players if p.get("number") is not None]
            if len(numbers) != len(set(numbers)):
                warnings.append(f"Duplicati: Numeri calottina duplicati nella squadra {t_side.upper()}.")
            
            # Duplicate player names
            names = [p.get("name") for p in players if p.get("name")]
            if len(names) != len(set(names)):
                warnings.append(f"Duplicati: Nomi giocatore duplicati nella squadra {t_side.upper()}.")

        # 6. Roster size sanity
        for t_side in ["home", "away"]:
            players = teams.get(t_side, {}).get("players", [])
            if len(players) > 0:
                if len(players) < 7:
                    warnings.append(f"Roster {t_side.upper()} con solo {len(players)} giocatori (minimo atteso: 7)")
                elif len(players) > 15:
                    warnings.append(f"Roster {t_side.upper()} con {len(players)} giocatori (massimo atteso: 15)")

        # 7. Team plays itself
        match_info = data.get("match_info", {})
        ht = match_info.get("home_team")
        at = match_info.get("away_team")
        if ht and at and isinstance(ht, str) and isinstance(at, str):
            if ht.strip().lower() == at.strip().lower():
                warnings.append(f"Squadra gioca contro se stessa: '{ht}' vs '{at}'")

        # 8. Missing date
        if not match_info.get("date"):
            warnings.append("Data partita mancante nel referto.")

        # 9. Confidence — NESSUN WARNING (neutralizzato 2026-07-21, fetta A1)
        # Vedi la nota estesa in ocr_quality_gate.py: la confidence auto-dichiarata
        # non e' calibrata, gli errori osservati stanno tutti fra 0.90 e 1.00.
        meta = data.get("metadata", {})

        # 10. Surface extraction_warnings from provider
        extraction_warnings = meta.get("extraction_warnings", [])
        if extraction_warnings:
            for w in extraction_warnings:
                warnings.append(f"[OCR] {w}")

        # 11. Officials — il controllo strutturale resta, quello su confidence no (A1)
        officials = data.get("officials")
        if officials is not None and isinstance(officials, dict):
            referees = officials.get("referees", [])
            if isinstance(referees, list) and len(referees) == 0:
                warnings.append("Sezione officials presente ma nessun arbitro estratto.")

        # 12. Team-level confidence — NESSUN WARNING (neutralizzato 2026-07-21, A1)

        return len(warnings) == 0, warnings

    @staticmethod
    def assess_publish_readiness(data: Dict[str, Any], level: str = LEVEL_FULL) -> Tuple[bool, List[str], List[str]]:
        """
        Valuta se i dati sono pronti per la pubblicazione, al livello dichiarato.
        Ritorna: (safe_to_publish: bool, blockers: List[str], warnings: List[str])

        Blockers impediscono la pubblicazione.
        Warnings vengono loggati ma non bloccano (l'admin ha già revisionato).

        `level` (Opzione A):
          - LEVEL_FULL (default): comportamento storico, INVARIATO byte per byte.
          - LEVEL_SCORE_ONLY: i blocker EVENT-SCOPED (`_EVENT_SCOPED_BLOCKER_MARKERS`)
            sono declassati a warning marcati `OUT_OF_LEVEL_PREFIX` — il referto
            dichiara "eventi non disponibili", quindi non bloccano. I blocker
            SCORE-SCOPED (punteggio, nomi squadre, coerenza somma-quarti) restano
            blocker. Non e' un `force`: e' una valutazione al livello giusto.
        """
        blockers = []
        warnings = []

        if not data or not isinstance(data, dict):
            blockers.append("Nessun dato normalizzato presente.")
            return False, blockers, warnings

        # --- BLOCKERS ---

        # Missing final score
        scores = data.get("scores", {})
        final_score = scores.get("final_score")
        if not final_score or not isinstance(final_score, str) or "-" not in final_score:
            blockers.append("Punteggio finale mancante o non valido.")
        else:
            try:
                parts = [p.strip() for p in final_score.split("-")]
                if not all(p.isdigit() for p in parts):
                    blockers.append("Punteggio finale contiene valori non numerici.")
            except Exception:
                blockers.append("Punteggio finale non parsabile.")

        # Confidence: nessun blocker (neutralizzato 2026-07-21, fetta A1)
        meta = data.get("metadata", {})

        # Both team names missing
        match_info = data.get("match_info", {})
        if not match_info.get("home_team") and not match_info.get("away_team"):
            blockers.append("Nomi squadre mancanti.")

        # --- BLOCKERS ---

        # Rosters empty
        teams = data.get("teams", {})
        if not teams.get("home", {}).get("players", []) and not teams.get("away", {}).get("players", []):
            blockers.append("Entrambi i roster sono vuoti.")

        # --- WARNINGS ---
        # (nessun warning su confidence: neutralizzato 2026-07-21, fetta A1)

        # --- BLOCKERS (Coherence) ---
        _, coherence_warnings = OCRSchemaValidator.validate_coherence(data)
        # `PERIOD_BLOCKER_PREFIX` copre le due direzioni ratificate come blocco al
        # publish: eccesso per-periodo (D1) e difetto con estrazione completa (D2).
        critical_keywords = ["Incoerenza punteggio", "Incoerenza eventi", PERIOD_BLOCKER_PREFIX]
        
        # Filtriamo i warnings di validate_coherence: se sono critici diventano blockers
        for cw in coherence_warnings:
            if any(k in cw for k in critical_keywords):
                blockers.append(cw)
            else:
                warnings.append(cw)

        # --- NEW GUARDRAILS ---
        events = data.get("events", [])

        # 1. Zero Events Validation (Critical)
        from ..event_types import SCORE_EVENT_CODES
        final_score_str = scores.get("final_score", "0-0")
        try:
            h_total, a_total = map(int, [p.strip() for p in final_score_str.split("-")])
        except (ValueError, AttributeError):
            h_total, a_total = 0, 0
        
        goal_events = [
            e for e in events
            if e.get("type") in SCORE_EVENT_CODES
            and (e.get("player_name") or e.get("player"))
        ]
        if (h_total > 0 or a_total > 0) and len(goal_events) == 0:
            blockers.append("Zero Eventi: Risultato positivo rilevato ma nessun evento goal con autore identificato. Il publish è bloccato per evitare drift sulle statistiche atleti.")

        # 2. Entity Completeness (Warning)
        teams = data.get("teams", {})
        total_players = 0
        for side in ["home", "away"]:
            total_players += len(teams.get(side, {}).get("players", []))
        
        reconciliation = data.get("reconciliation", {})
        resolved_players = 0
        for side in ["home_players", "away_players"]:
            resolved_players += len(reconciliation.get(side, {}))
            
        if total_players > 0:
            unresolved_count = total_players - resolved_players
            if (unresolved_count / total_players) > 0.5:
                warnings.append(f"Incompletezza: {unresolved_count}/{total_players} atleti non riconciliati (oltre 50%). Verifica i nomi.")

        # Unreconciled events check (Chirurgico: se un evento ha un player ma non è riconciliato, è un blocco)
        # Perché questo produrrebbe drift nelle statistiche
        player_map = {}
        for side in ["home_players", "away_players"]:
            side_map = reconciliation.get(side, {})
            if isinstance(side_map, dict):
                player_map.update(side_map)
        
        events_with_player = [e for e in events if e.get("player_name") or e.get("player")]
        unreconciled_names = [ (e.get("player_name") or e.get("player")) 
                              for e in events_with_player 
                              if (e.get("player_name") or e.get("player")) not in player_map]
        
        if unreconciled_names:
            unique_unreconciled = sorted(list(set(unreconciled_names)))
            blockers.append(f"Riconciliazione incompleta per: {', '.join(unique_unreconciled)}. Il publish è bloccato per evitare drift nelle statistiche.")

        # Extraction warnings from provider
        extraction_warnings = meta.get("extraction_warnings", [])
        if extraction_warnings:
            warnings.append(f"{len(extraction_warnings)} avvisi dall'engine OCR.")

        # --- SOFT WARNINGS v2: sezioni opzionali mancanti ---
        # Officials missing (non blocca, ma avvisa per referti che dovrebbero averli)
        officials = data.get("officials")
        if officials is None:
            warnings.append("Sezione 'officials' assente: arbitri non estratti (opzionale ma consigliato).")
        elif isinstance(officials, dict):
            referees = officials.get("referees", [])
            if not referees:
                warnings.append("Arbitri non estratti dalla sezione officials.")

        # --- Scoping per livello (Opzione A) ---
        # SOLO su SCORE_ONLY: i blocker event-scoped diventano warning marcati
        # [fuori livello]. Su FULL questo ramo non viene eseguito, quindi i
        # blocker restano identici al comportamento storico.
        if level == LEVEL_SCORE_ONLY:
            kept = []
            for b in blockers:
                if any(m in b for m in _EVENT_SCOPED_BLOCKER_MARKERS):
                    warnings.append(f"{OUT_OF_LEVEL_PREFIX} {b}")
                else:
                    kept.append(b)
            blockers = kept

        safe = len(blockers) == 0
        return safe, blockers, warnings
