from typing import Dict, Any, List, Optional
from matches.models import Match, MatchEvent
from matches.event_types import EVENT_TYPE_EXCLUSION_DEF, EVENT_TYPE_RED_CARD

class MatchDataConverter:
    """
    Funzioni pure per la conversione dei dati normalizzati (JSON) 
    in parametri per i modelli Django.
    """

    @staticmethod
    def get_match_scores(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Estrae punteggi finali e parziali.
        """
        scores = data.get("scores", {})
        final_str = scores.get("final_score", "0-0")
        
        # Parsing robusto (già hardenizzato in precedenza)
        try:
            parts = [p.strip() for p in final_str.split("-")]
            if len(parts) == 2:
                home, away = int(parts[0]), int(parts[1])
            else:
                home, away = 0, 0
        except (ValueError, IndexError):
            home, away = 0, 0

        return {
            "home_score": home,
            "away_score": away,
            "quarter_scores": scores.get("quarters", {}),
            "is_finished": True
        }

    @staticmethod
    def get_events_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Estrae la lista degli eventi dal JSON.
        Se presente la sezione 'reconciliation', prova a mappare i player names agli ID.
        """
        raw_events = data.get("events", [])
        reconciliation = data.get("reconciliation", {})
        
        # Mappa nomi -> ID per facile lookup
        player_map = {}
        # Combiniamo home e away reconciliation
        for side in ["home_players", "away_players"]:
            side_map = reconciliation.get(side, {})
            if isinstance(side_map, dict):
                player_map.update(side_map)

        processed_events = []
        for e in raw_events:
            event_type = e.get("type")
            if not event_type:
                continue

            # In pallanuoto l'espulsione definitiva (EDCS) e il cartellino rosso sono
            # lo STESSO evento reale: normalizziamo EXCLUSION_DEF -> RED_CARD, tipo gia'
            # canonico (DEFAULT_EVENT_TYPES), pubblicabile e con blocco di template
            # dedicato. Il V3 di produzione emette gia' RED_CARD di suo (senza articolo);
            # il V3.4 emette EXCLUSION_DEF con articolo: dopo questa mappatura le due
            # forme convergono sullo stesso tipo persistito. Non tocca il conteggio
            # fouled-out, che opera solo su EXCLUSION_20 (DEBITI §10.35).
            if event_type == EVENT_TYPE_EXCLUSION_DEF:
                event_type = EVENT_TYPE_RED_CARD

            # Support both "player" and "player_name" keys (prompt version compat)
            player_name = e.get("player_name") or e.get("player")
            player_id = player_map.get(player_name) if player_name else None

            processed_events.append({
                "event_type": event_type,
                "minute": e.get("minute"),
                "player_id": player_id,
                "player_name": player_name,  # serve al warning di publish per nominare un evento non riconciliato
                "team": e.get("team"), # 'home' or 'away'
                "quarter": e.get("quarter"),
                "is_penalty": bool(e.get("is_penalty", False)),  # rigore: additivo, default false
                # Metadati sanzione portati a valle VERBATIM (non piu' scartati, DEBITI §10.35).
                # Possono restare null su un rosso legittimo privo di articolo (forma V3):
                # nessuna validazione qui li pretende. La classificazione NON si persiste:
                # si deriva a render-time da classify_definitive_exclusion.
                "regulation_article": e.get("regulation_article"),
                "sanction_sigla": e.get("sanction_sigla"),
                "notes": f"Estratto da OCR: {player_name}" if player_name else ""
            })

        return processed_events
