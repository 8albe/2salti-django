from typing import Dict, Any, Tuple, List
import difflib

class OCRQualityGate:
    """
    Focused validation layer that evaluates raw/normalized OCR output quality
    BEFORE the report is considered ready for human review ("EXTRACTED").
    
    Prevents clearly broken outputs, hallucinations, or malformed structures 
    from silently entering the review workflow.
    """

    @staticmethod
    def _is_fuzzy_match(ocr_name: str, expected_name: str, threshold: float = 0.6) -> bool:
        if not ocr_name or not expected_name:
            return False
        
        ocr_clean = str(ocr_name).strip().lower()
        exp_clean = str(expected_name).strip().lower()
        
        # Direct containment or exact match
        if exp_clean in ocr_clean or ocr_clean in exp_clean:
            return True
            
        # Fuzzy match
        ratio = difflib.SequenceMatcher(None, ocr_clean, exp_clean).ratio()
        return ratio >= threshold

    @staticmethod
    def evaluate(data: Dict[str, Any], context: Dict[str, Any] = None) -> Tuple[bool, List[str], List[str], List[str]]:
        """
        Evaluate OCR data quality.
        Returns: (is_valid, blockers, warnings, info)
        is_valid = False means the data is too unsafe/broken to confidently review.
        """
        blockers = []
        warnings = []
        info = []
        context = context or {}

        if not data or not isinstance(data, dict):
            return False, ["Il payload OCR non è un oggetto JSON valido o è vuoto."], [], []

        # 1. Required root sections
        required_roots = ["metadata", "match_info", "scores", "teams", "events"]
        missing = [r for r in required_roots if r not in data]
        if missing:
            blockers.append(f"Sezioni base mancanti dal risultato OCR: {', '.join(missing)}")

        if blockers:
            return False, blockers, warnings, info

        # 2. Required match fields & team names
        match_info = data.get("match_info", {})
        if not isinstance(match_info, dict):
            blockers.append("Sezione 'match_info' malformata.")
        else:
            home = match_info.get("home_team")
            away = match_info.get("away_team")
            if not home or not away:
                blockers.append("Nomi squadre mancanti (home_team o away_team).")
            else:
                if str(home).strip().lower() == str(away).strip().lower():
                    blockers.append("I nomi delle due squadre estratte coincidono (incoerenza OCR).")
                
                # Context validation (Safety Hardening)
                exp_home = context.get('home_team')
                exp_away = context.get('away_team')
                
                if exp_home and not OCRQualityGate._is_fuzzy_match(home, exp_home):
                    blockers.append(f"Squadra Casa '{home}' non corrisponde alla partita selezionata '{exp_home}'.")
                
                if exp_away and not OCRQualityGate._is_fuzzy_match(away, exp_away):
                    blockers.append(f"Squadra Ospite '{away}' non corrisponde alla partita selezionata '{exp_away}'.")

            if not match_info.get("date"):
                warnings.append("Data partita mancante.")
            
            # City/Venue check
            city = match_info.get("city")
            exp_location = context.get('location')
            if city and exp_location:
                if not OCRQualityGate._is_fuzzy_match(city, exp_location, threshold=0.5):
                    warnings.append(f"Località OCR '{city}' sospetta rispetto a DB '{exp_location}'.")

        # 3. Final score structure
        scores = data.get("scores", {})
        final_score = scores.get("final_score")
        home_total, away_total = None, None

        if not isinstance(scores, dict):
            blockers.append("Sezione 'scores' malformata.")
        else:
            if not final_score or not isinstance(final_score, str) or "-" not in final_score:
                blockers.append("Punteggio finale assente o in formato non valido (atteso 'X-Y').")
            else:
                try:
                    parts = [p.strip() for p in final_score.split("-")]
                    if len(parts) == 2 and all(p.isdigit() for p in parts):
                        home_total, away_total = int(parts[0]), int(parts[1])
                    else:
                        blockers.append("Punteggio finale contiene caratteri non numerici o formato errato.")
                except Exception:
                    blockers.append("Errore nel parsing del punteggio finale.")

        # 4. Period/quarter scores compatibility (MOVED TO BLOCKERS for safety)
        quarters = scores.get("quarters", {})
        if isinstance(quarters, dict) and home_total is not None and away_total is not None:
            q_home_sum, q_away_sum = 0, 0
            has_unparseable_quarter = False
            for val in quarters.values():
                if val is None:
                    # null is allowed if illegible, but weakens the check
                    continue
                if isinstance(val, (list, tuple)) and len(val) == 2:
                    try:
                        q_home_sum += int(val[0])
                        q_away_sum += int(val[1])
                    except (ValueError, TypeError):
                        has_unparseable_quarter = True
                else:
                    has_unparseable_quarter = True
            
            if not has_unparseable_quarter and quarters:
                # If we could parse all quarters and there is at least one, check sum
                if q_home_sum != home_total or q_away_sum != away_total:
                    blockers.append(
                        f"Incoerenza punteggio: Somma quarti ({q_home_sum}-{q_away_sum}) ≠ Finale ({home_total}-{away_total})."
                    )

        # 5. Events contradict score totals
        #
        # D6 (2026-07-21): qui il confronto PER PERIODO sostituisce quello
        # aggregato, perche' e' strettamente piu' informativo — con tutti i
        # parziali leggibili e tutti i gol dotati di periodo, un eccesso sul
        # totale implica un eccesso su almeno un periodo, mentre il contrario non
        # vale: una squadra puo' avere il totale giusto e un periodo in eccesso.
        # La sostituzione vale solo dove il per-periodo domina davvero. Se un
        # parziale e' illeggibile, o se qualche gol e' privo di periodo, i gol
        # possono "nascondersi" e il per-periodo non copre piu' l'aggregato: in
        # quel caso il controllo aggregato resta al suo posto, per quella squadra.
        events = data.get("events", [])
        if not isinstance(events, list):
            blockers.append("La sezione 'events' deve essere una lista.")
        elif home_total is not None and away_total is not None:
            from ..event_types import SCORE_EVENT_CODES
            from .schema import OCRSchemaValidator

            goals_home = sum(1 for e in events if isinstance(e, dict) and e.get("type") in SCORE_EVENT_CODES and e.get("team") == "home")
            goals_away = sum(1 for e in events if isinstance(e, dict) and e.get("type") in SCORE_EVENT_CODES and e.get("team") == "away")

            period_check = OCRSchemaValidator.check_goal_events_per_period(data)
            all_periods_readable = (
                period_check["applicable"]
                and period_check["counts"]["periods_not_applicable"] == 0
            )

            # D1: piu' eventi-gol del parziale e' impossibile per costruzione.
            blockers.extend(period_check["messages"]["excess"])
            # D2: totale di squadra giusto ma distribuito male fra i periodi.
            # Non declassa da solo il referto: e' un avviso al revisore, il blocco
            # scatta al publish.
            warnings.extend(period_check["messages"]["distribution"])
            # D3: difetto con estrazione incompleta, e ogni motivo per cui il
            # confronto non e' stato eseguibile. Evidenza, mai giudizio.
            info.extend(period_check["messages"]["evidence"])

            # Contradiction: we have MORE goals extracted than the final score says
            for side, goals, total, label in (
                ("home", goals_home, home_total, "CASA"),
                ("away", goals_away, away_total, "OSPITE"),
            ):
                covered_by_period = (
                    all_periods_readable and period_check["unassigned_goals"][side] == 0
                )
                if goals > total and not covered_by_period:
                    blockers.append(
                        f"Incoerenza eventi: trovati {goals} gol {label}, ma il finale indica {total}."
                    )

        # 6. Garbage/placeholder values catching
        garbage_terms = ["unknown", "da inserire", "tbd", "n/a", "null", "none"]
        if isinstance(match_info, dict):
            for side in ["home_team", "away_team"]:
                val = str(match_info.get(side, "")).lower()
                if val in garbage_terms:
                    blockers.append(f"Valore placeholder inaccettabile trovato per {side}: '{match_info.get(side)}'")

        # 7. Confidence — NESSUN GATE (neutralizzato 2026-07-21, fetta A1)
        #
        # Fino al 2026-07-21 qui vivevano quattro decisioni automatiche basate sulla
        # confidence auto-dichiarata dal provider: blocker sotto 0.3 globale, warning
        # sotto 0.6 globale, blocker sotto 0.5 e info sotto 0.8 sui campi di
        # intestazione (`metadata.confidence_fields`).
        #
        # Sono state rimosse perché la misura che le giustificava le smentisce:
        # sul dataset gold e sulla prima estrazione reale in produzione (report 15)
        # TUTTI gli errori osservati — nomi allucinati, finale invertito, parziali
        # inventati, date sbagliate — stanno fra 0.90 e 1.00, spesso esattamente a
        # 1.00. Nessuna di queste soglie e' mai scattata, e nessuna POTREBBE
        # scattare: la confidence del provider non e' calibrata e non correla con
        # la correttezza. Un gate che non puo' attivarsi non protegge — comunica
        # solo una falsa garanzia a chi legge la review.
        # Dettaglio e dati in docs/syllabus/8_ocr_affidabilita.md §8.5(c), §8.9 e §8.10.
        #
        # La confidence NON viene rimossa dai dati: resta in `normalized_data` e
        # resta visibile in review come dato grezzo, etichettata "non calibrata".

        return len(blockers) == 0, blockers, warnings, info
