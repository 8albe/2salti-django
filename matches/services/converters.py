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
        Se presente la sezione 'reconciliation', prova a mappare gli eventi agli ID.

        Chiave d'identita' dell'autore (schema V3.5, §8.24): il NUMERO DI CALOTTINA
        ("cap") e' primario. Se l'evento porta cap e squadra, si aggancia il
        giocatore per (team, cap) sul roster — match ESATTO: la calottina in
        tabella e' piu' affidabile della grafia del nome. Il NOME resta come
        FALLBACK, usato solo quando la calottina manca (cap null). Una calottina
        che non esiste nel roster NON aggancia nulla (nessun aggancio inventato):
        resta player_id None e la incoerenza e' segnalata da
        `validate_coherence` (warning "Calottina evento non nel roster").
        """
        raw_events = data.get("events", [])
        reconciliation = data.get("reconciliation", {})
        teams = data.get("teams", {})

        # Mappa nomi -> ID per facile lookup (fallback quando la calottina manca)
        player_map = {}
        # Combiniamo home e away reconciliation
        for side in ["home_players", "away_players"]:
            side_map = reconciliation.get(side, {})
            if isinstance(side_map, dict):
                player_map.update(side_map)

        # Mappa (team, calottina) -> ID: due salti — dal numero di calottina al
        # nome del giocatore nel roster estratto (teams[side].players), e dal nome
        # all'ID riconciliato (reconciliation[side_players]). Cosi' un evento con
        # cap ma senza nome (o con nome misletto) si aggancia comunque all'atleta
        # giusto, purche' quella calottina sia nel roster e il roster sia stato
        # riconciliato per nome.
        cap_map: Dict[tuple, Any] = {}
        # Numeri di calottina presenti nel roster, per lato: distinguono "cap non
        # nel roster" (nessun aggancio) da "cap nel roster ma non riconciliato".
        roster_caps = {"home": set(), "away": set()}
        for side in ["home", "away"]:
            side_recon = reconciliation.get(f"{side}_players", {})
            if not isinstance(side_recon, dict):
                side_recon = {}
            for p in teams.get(side, {}).get("players", []) or []:
                num = p.get("number")
                if not isinstance(num, int):
                    continue
                roster_caps[side].add(num)
                name = p.get("name")
                if name and name in side_recon:
                    cap_map[(side, num)] = side_recon[name]

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
            cap = e.get("cap")
            side = e.get("team")

            # Riconciliazione: calottina (esatta) prima, nome (fallback) poi.
            if isinstance(cap, int) and side in ("home", "away"):
                # Cap presente: la calottina governa. Se e' nel roster, aggancia
                # l'ID di quel giocatore (puo' essere None se il roster non e'
                # riconciliato a DB); se NON e' nel roster, nessun aggancio
                # inventato — player_id resta None (warning in validate_coherence).
                player_id = cap_map.get((side, cap))
            else:
                # Calottina assente: fallback sul nome (comportamento storico).
                player_id = player_map.get(player_name) if player_name else None

            processed_events.append({
                "event_type": event_type,
                "minute": e.get("minute"),
                "player_id": player_id,
                "player_name": player_name,  # serve al warning di publish per nominare un evento non riconciliato
                "cap": cap,  # calottina dell'autore portata a valle (schema V3.5, §8.24)
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
