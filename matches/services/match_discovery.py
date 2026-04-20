import logging
from datetime import datetime
from django.db.models import Q
from matches.models import Match

logger = logging.getLogger(__name__)

class MatchDiscoveryService:
    @staticmethod
    def discover(ocr_data):
        """
        Tenta di individuare un match basandosi sui dati estratti dall'OCR.
        Rileva date, nomi squadre e campionato per filtrare i match esistenti.
        """
        from .ocr_service import resolve_team_entity
        from core.models import Team, League
        
        match_info = ocr_data.get('match_info', {})
        home_name = match_info.get('home_team')
        away_name = match_info.get('away_team')
        league_name = match_info.get('league')
        date_str = match_info.get('date')
        
        if not home_name or not away_name:
            logger.warning("MatchDiscovery: Nomi squadre mancanti nell'OCR.")
            return None
            
        # 1. Resolve Teams
        all_teams = Team.objects.all()
        home_team = resolve_team_entity(home_name, all_teams)
        away_team = resolve_team_entity(away_name, all_teams)
        
        if not home_team or not away_team:
            logger.warning(f"MatchDiscovery: Impossibile risolvere una o entrambe le squadre: {home_name} vs {away_name}")
            return None
            
        # 2. Resolve Date
        target_date = None
        if date_str:
            # Handle list if date comes as list of parts (common in some OCR outputs)
            if isinstance(date_str, list):
                date_str = "-".join([str(x) for x in date_str])
                
            try:
                for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y', '%Y/%m/%d']:
                    try:
                        target_date = datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue
            except Exception as e:
                logger.warning(f"MatchDiscovery: Errore parsing data '{date_str}': {str(e)}")
        
        # 3. Resolve League (Optional but used for disambiguation)
        league = None
        if league_name:
            # Simple fuzzy lookup or exact match for league
            # We use icontains for basic safety or could use a more complex fuzzy tool
            league_qs = League.objects.filter(name__icontains=league_name)
            if league_qs.count() == 1:
                league = league_qs.first()

        # 4. Query Match
        qs = Match.objects.filter(
            (Q(home_team=home_team) & Q(away_team=away_team)) |
            (Q(home_team=away_team) & Q(away_team=home_team))
        )
        
        if target_date:
            qs = qs.filter(match_date__date=target_date)
            
        if league:
            # If we found a league, prioritize those matches
            league_matches = qs.filter(league=league)
            if league_matches.exists():
                qs = league_matches

        matches = list(qs[:2])
        
        if len(matches) == 1:
            logger.info(f"MatchDiscovery: Trovato match univoco: {matches[0]}")
            return matches[0]
        elif len(matches) > 1:
            logger.warning(f"MatchDiscovery: Risultato ambiguo ({len(matches)} match trovati) per {home_team} vs {away_team}")
            return None
            
        logger.warning(f"MatchDiscovery: Nessun match trovato per {home_team} vs {away_team} in data {target_date}")
        return None
