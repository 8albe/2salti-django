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
            return False, ["Il payload OCR non è un oggetto JSON valido o è vuoto."], []

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
        events = data.get("events", [])
        if not isinstance(events, list):
            blockers.append("La sezione 'events' deve essere una lista.")
        elif home_total is not None and away_total is not None:
            from ..event_types import SCORE_EVENT_CODES
            goals_home = sum(1 for e in events if isinstance(e, dict) and e.get("type") in SCORE_EVENT_CODES and e.get("team") == "home")
            goals_away = sum(1 for e in events if isinstance(e, dict) and e.get("type") in SCORE_EVENT_CODES and e.get("team") == "away")

            
            # Contradiction: we have MORE goals extracted than the final score says
            if goals_home > home_total:
                blockers.append(f"Incoerenza eventi: trovati {goals_home} gol CASA, ma il finale indica {home_total}.")
            if goals_away > away_total:
                blockers.append(f"Incoerenza eventi: trovati {goals_away} gol OSPITE, ma il finale indica {away_total}.")

        # 6. Garbage/placeholder values catching
        garbage_terms = ["unknown", "da inserire", "tbd", "n/a", "null", "none"]
        if isinstance(match_info, dict):
            for side in ["home_team", "away_team"]:
                val = str(match_info.get(side, "")).lower()
                if val in garbage_terms:
                    blockers.append(f"Valore placeholder inaccettabile trovato per {side}: '{match_info.get(side)}'")

        # 7. Confidence Gates
        metadata = data.get("metadata", {})
        if isinstance(metadata, dict):
            confidence = metadata.get("confidence", 1.0)
            if isinstance(confidence, (int, float)) and confidence < 0.3:
                blockers.append(f"Affidabilità OCR troppo bassa ({confidence*100:.0f}%).")
            elif isinstance(confidence, (int, float)) and confidence < 0.6:
                warnings.append(f"Affidabilità OCR marginale ({confidence*100:.0f}%).")
            
            # Per-field confidence (Hardened check)
            conf_fields = metadata.get("confidence_fields", {})
            header_fields = ["home_team", "away_team", "final_score"]
            for field in header_fields:
                f_conf = conf_fields.get(field)
                if isinstance(f_conf, (int, float)) and f_conf < 0.5:
                    blockers.append(f"Bassa affidabilità nel campo intestazione '{field}' ({f_conf*100:.0f}%).")
                elif isinstance(f_conf, (int, float)) and f_conf < 0.8:
                    info.append(f"Affidabilità accettabile ma non perfetta in '{field}' ({f_conf*100:.0f}%).")

        return len(blockers) == 0, blockers, warnings, info
