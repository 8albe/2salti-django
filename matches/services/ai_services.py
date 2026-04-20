import logging
import json
from typing import Dict, Any, Optional, List
from django.conf import settings
from django.urls import reverse
from django.db.models import Q, Count
from openai import OpenAI

from matches.models import Match, MatchEvent, MatchReport, AIQueryLog
from core.models import League, Team
from accounts.models import User

logger = logging.getLogger(__name__)

class AIStatsEngine:
    """
    Live SQL Engine (AI Stats V2)
    Translates Natural Language to Django ORM Queries.
    Architecture:
    1. Parse Intent (LLM)
    2. Resolve Entities (DB)
    3. Execute Query (ORM)
    4. Synthesize Response (LLM)
    """

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "gpt-4o"

    def process_query(self, query: str, user_context: Optional[Dict] = None) -> Dict[str, Any]:
        """Main entry point for the AI Stats Engine."""
        logger.info(f"[AIStatsEngine] Processing query: {query}")
        
        # 1. Parse Intent
        intent = self._parse_intent(query)
        logger.info(f"[AIStatsEngine] Parsed Intent: {intent}")

        if intent.get("intent") == "REDIRECT":
            return self._handle_redirect(intent, query)
        
        return self._handle_query(intent, query)

    def _parse_intent(self, query: str) -> Dict[str, Any]:
        """Uses LLM to extract intent and entities from the query."""
        system_prompt = """
        Sei il Query Resolver della piattaforma 2salti. 
        Traduci le domande dell'utente in un intento strutturato JSON.

        TIPI DI INTENTO:
        - REDIRECT: L'utente vuole visualizzare una pagina esistente (classifica, statistiche league, calendario).
        - QUERY: L'utente chiede un dato numerico specifico (gol, partite, espulsioni).

        MAPPATURA TARGET:
        - standings: Classifica campionato.
        - stats: Marcatori/Leaderboard campionato.
        - matches: Calendario/Partite.
        - profile: Profilo di un giocatore.
        - goals: Conteggio gol.
        - expulsions: Conteggio espulsioni.

        REGOLE:
        1. Identifica se l'utente vuole VEDERE (REDIRECT) o SAPERE UN NUMERO (QUERY).
        2. Estrai entità: player (nome), team (squadra), league (campionato).
        3. Estrai filtri temporali: last_n (numero intero) o season (es: 'current' o '2024/2025').
        4. Rispondi SOLO con il JSON.

        ESEMPI:
        - "Mostrami la classifica" -> {"intent": "REDIRECT", "target": "standings", "entities": {}}
        - "Quanti gol ha fatto Rossi?" -> {"intent": "QUERY", "target": "goals", "entities": {"player": "Rossi"}}
        - "Gol di Bianchi nell'ultima partita" -> {"intent": "QUERY", "target": "goals", "entities": {"player": "Bianchi"}, "filters": {"last_n": 1}}
        - "Bianchi gol ultime 3 partite" -> {"intent": "QUERY", "target": "goals", "entities": {"player": "Bianchi"}, "filters": {"last_n": 3}}
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Error parsing intent: {e}")
            return {"intent": "UNKNOWN", "error": str(e)}

    def _handle_redirect(self, intent: Dict, raw_query: str) -> Dict[str, Any]:
        """Resolves an intent into a target URL."""
        target = intent.get("target")
        entities = intent.get("entities", {})
        
        target_url = None
        message = ""

        if target == "standings":
            league = self._resolve_entity(League, entities.get("league") or entities.get("team"))
            if league:
                target_url = reverse('league_standings', args=[league.id])
                message = f"Ecco la classifica di {league.name}."
            else:
                # Default to a general search or ask which league
                message = "Per quale campionato vuoi vedere la classifica?"

        elif target == "stats":
            league = self._resolve_entity(League, entities.get("league") or entities.get("team"))
            if league:
                target_url = reverse('league_stats', args=[league.slug])
                message = f"Ecco le statistiche di {league.name}."

        elif target == "profile":
            player = self._resolve_entity(User, entities.get("player"), role='athlete')
            if player:
                target_url = reverse('player_profile', args=[player.username])
                message = f"Ecco il profilo di {player.get_full_name()}."

        if target_url:
            return {
                "type": "redirect",
                "text": message,
                "target_url": target_url,
                "data": intent
            }
        
        return {
            "type": "answer",
            "text": message or "Non sono riuscito a trovare la pagina richiesta. Puoi essere più specifico?",
            "data": intent
        }

    def _handle_query(self, intent: Dict, raw_query: str) -> Dict[str, Any]:
        """Executes the data extraction logic using ORM."""
        target = intent.get("target")
        entities = intent.get("entities", {})
        filters = intent.get("filters", {})
        
        # 1. Entity Validation
        player = None
        team = None
        league = None

        if entities.get("player"):
            players = self._resolve_entities(User, entities.get("player"), role='athlete')
            if len(players) > 1:
                return self._disambiguation_response("giocatore", players, intent)
            player = players[0] if players else None

        if not player and entities.get("team"):
            team = self._resolve_entity(Team, entities.get("team"))
        
        if not player and not team and entities.get("league"):
            league = self._resolve_entity(League, entities.get("league"))

        # 2. Guardrail: Existence Check
        if entities.get("player") and not player:
            return self._error_response(f"Non ho trovato nessun giocatore chiamato '{entities.get('player')}'.", intent)

        # 3. Data Extraction
        result_data = {}
        if target == "goals" and player:
            result_data = self._get_player_goals(player, filters)
        
        # 4. Synthesize Response
        if result_data:
            text_response = self._synthesize_answer(raw_query, result_data)
            self._log_query(raw_query, intent, text_response, player, success=True)
            return {
                "type": "answer",
                "text": text_response,
                "data": result_data
            }

        return self._error_response("Non ho trovato i dati richiesti. Assicurati che il nome sia corretto.", intent)

    def _resolve_entities(self, model, name: str, **extra_filters) -> List[Any]:
        """Fuzzy-ish resolver for database entities."""
        if not name or len(name) < 2:
            return []
        
        query = Q(name__icontains=name) if hasattr(model, 'name') else Q()
        if model == User:
            query = Q(last_name__icontains=name) | Q(first_name__icontains=name) | Q(username__icontains=name)
        
        return list(model.objects.filter(query, **extra_filters)[:5])

    def _resolve_entity(self, model, name: str, **extra_filters) -> Optional[Any]:
        results = self._resolve_entities(model, name, **extra_filters)
        return results[0] if results else None

    def _get_player_goals(self, player: User, filters: Dict) -> Dict:
        """Secure ORM logic for goal counting."""
        qs = MatchEvent.objects.filter(
            player=player, 
            event_type='GOAL',
            match__reports__status='PUBLISHED'
        )

        last_n = filters.get("last_n")
        if last_n:
            # Get last N matches of the player's team
            team = getattr(player.athlete_profile, 'current_team', None)
            if team:
                match_ids = Match.objects.filter(
                    Q(home_team=team) | Q(away_team=team),
                    reports__status='PUBLISHED'
                ).order_by('-match_date').values_list('id', flat=True)[:last_n]
                qs = qs.filter(match_id__in=list(match_ids))
                time_context = f"nelle ultime {last_n} partite"
            else:
                time_context = "nella stagione"
        else:
            time_context = "nella stagione"

        count = qs.count()
        return {
            "entity_name": player.get_full_name(),
            "stat_name": "gol",
            "value": count,
            "time_context": time_context,
            "entity_id": player.id
        }

    def _synthesize_answer(self, query: str, data: Dict) -> str:
        """LLM synthezises the final answer from DB data."""
        prompt = f"""
        Rispondi alla domanda dell'utente usando ESCLUSIVAMENTE i dati forniti.
        Domanda: {query}
        Dati DB: {json.dumps(data)}
        
        Regole:
        1. Sii naturale e professionale.
        2. Non inventare numeri. Usa quelli nel JSON.
        3. Se il valore è 0, dillo chiaramente.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content.strip()
        except:
            return f"{data['entity_name']} ha segnato {data['value']} {data['stat_name']} {data['time_context']}."

    def _disambiguation_response(self, type_str: str, options: List, intent: Dict) -> Dict:
        names = [f"{o.get_full_name()} ({o.username})" if hasattr(o, 'get_full_name') else str(o) for o in options]
        return {
            "type": "answer",
            "text": f"Ho trovato più di un {type_str}. A chi ti riferisci? ({', '.join(names)})",
            "data": {"intent": intent, "options": names}
        }

    def _error_response(self, message: str, intent: Dict) -> Dict:
        return {
            "type": "answer",
            "text": message,
            "data": intent
        }

    def _log_query(self, query: str, intent: Dict, response: str, athlete: User = None, success: bool = True):
        try:
            AIQueryLog.objects.create(
                raw_query=query,
                response_type="answer" if success else "error",
                response_text=response,
                success=success,
                matched_athlete=athlete,
                time_range=str(intent.get("filters", {}))
            )
        except:
            pass
