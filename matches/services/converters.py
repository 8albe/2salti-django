from typing import Dict, Any, List, Optional
from matches.models import Match, MatchEvent

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
                
            # Support both "player" and "player_name" keys (prompt version compat)
            player_name = e.get("player_name") or e.get("player")
            player_id = player_map.get(player_name) if player_name else None
            
            processed_events.append({
                "event_type": event_type,
                "minute": e.get("minute"),
                "player_id": player_id,
                "team": e.get("team"), # 'home' or 'away'
                "quarter": e.get("quarter"),
                "is_penalty": bool(e.get("is_penalty", False)),  # rigore: additivo, default false
                "notes": f"Estratto da OCR: {player_name}" if player_name else ""
            })
            
        return processed_events
