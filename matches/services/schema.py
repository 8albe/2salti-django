from typing import Dict, Any, Tuple, List

# -- Schema version --
SCHEMA_VERSION = "2.0"

# -- Extended event types supported in v2 --
EXTENDED_EVENT_TYPES = {
    # Scoring
    "GOAL",
    "PENALTY_GOAL",
    "PENALTY_MISSED",
    # Exclusions / Fouls
    "EXCLUSION_20",
    "EXCLUSION_DEF",
    "RED_CARD",
    "YELLOW_CARD",
    # Timeouts
    "TIMEOUT",
    # Generic fallback
    "OTHER",
}

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

        # 9. Low confidence warning
        meta = data.get("metadata", {})
        confidence = meta.get("confidence", 1.0)
        if isinstance(confidence, (int, float)) and confidence < 0.6:
            warnings.append(f"Confidenza estrazione bassa: {confidence:.0%}")

        # 10. Surface extraction_warnings from provider
        extraction_warnings = meta.get("extraction_warnings", [])
        if extraction_warnings:
            for w in extraction_warnings:
                warnings.append(f"[OCR] {w}")

        # 11. Officials confidence (v2 — soft warning solo se la sezione esiste)
        officials = data.get("officials")
        if officials is not None and isinstance(officials, dict):
            off_conf = officials.get("confidence")
            if isinstance(off_conf, (int, float)) and off_conf < 0.5:
                warnings.append(f"Confidenza arbitri bassa: {off_conf:.0%} — verificare manualmente.")
            referees = officials.get("referees", [])
            if isinstance(referees, list) and len(referees) == 0:
                warnings.append("Sezione officials presente ma nessun arbitro estratto.")

        # 12. Team-level confidence (v2 — soft warning)
        teams_data = data.get("teams", {})
        for side in ["home", "away"]:
            t = teams_data.get(side, {})
            if isinstance(t, dict):
                t_conf = t.get("confidence")
                if isinstance(t_conf, (int, float)) and t_conf < 0.5:
                    warnings.append(f"Confidenza roster {side.upper()} bassa: {t_conf:.0%}")

        return len(warnings) == 0, warnings

    @staticmethod
    def assess_publish_readiness(data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """
        Valuta se i dati sono pronti per la pubblicazione.
        Ritorna: (safe_to_publish: bool, blockers: List[str], warnings: List[str])
        
        Blockers impediscono la pubblicazione.
        Warnings vengono loggati ma non bloccano (l'admin ha già revisionato).
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

        # Very low confidence
        meta = data.get("metadata", {})
        confidence = meta.get("confidence", 1.0)
        if isinstance(confidence, (int, float)) and confidence < 0.3:
            blockers.append(f"Confidenza estremamente bassa: {confidence:.0%}")

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

        # Low (but not critically low) confidence
        if isinstance(confidence, (int, float)) and 0.3 <= confidence < 0.6:
            warnings.append(f"Confidenza bassa: {confidence:.0%}")

        # --- BLOCKERS (Coherence) ---
        _, coherence_warnings = OCRSchemaValidator.validate_coherence(data)
        critical_keywords = ["Incoerenza punteggio", "Incoerenza eventi"]
        
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

        # --- WARNINGS ---

        # Low (but not critically low) confidence
        if isinstance(confidence, (int, float)) and 0.3 <= confidence < 0.6:
            warnings.append(f"Confidenza bassa: {confidence:.0%}")

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

        safe = len(blockers) == 0
        return safe, blockers, warnings
