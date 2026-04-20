from core.models import LeagueStanding
from .standings_service import StandingsService

class DataIntegrityService:
    @staticmethod
    def check_league_standings(league):
        """
        Confronta la classifica persistita con quella calcolata dai match.
        Ritorna una lista di discrepanze.
        """
        expected = StandingsService._calculate_expected_standings(league)
        actual_records = LeagueStanding.objects.filter(league=league).select_related('team')
        actual = {s.team_id: s for s in actual_records}
        
        discrepancies = []
        
        # Check if all teams are represented
        expected_team_ids = set(expected.keys())
        actual_team_ids = set(actual.keys())
        
        missing_in_db = expected_team_ids - actual_team_ids
        extra_in_db = actual_team_ids - expected_team_ids
        
        if missing_in_db:
            for tid in missing_in_db:
                discrepancies.append({
                    'team': expected[tid]['team'],
                    'type': 'MISSING_RECORD',
                    'message': f"Squadra {expected[tid]['team']} presente nei match ma non in classifica persistita."
                })
        
        if extra_in_db:
            for tid in extra_in_db:
                discrepancies.append({
                    'team': actual[tid].team,
                    'type': 'EXTRA_RECORD',
                    'message': f"Squadra {actual[tid].team} presente in classifica persistita ma non ha match pubblicati."
                })

        # Check values for existing records
        for tid in expected_team_ids & actual_team_ids:
            exp = expected[tid]
            act = actual[tid]
            
            fields_to_check = ['played', 'won', 'drawn', 'lost', 'goals_for', 'goals_against', 'points']
            mismatches = []
            for field in fields_to_check:
                if exp[field] != getattr(act, field):
                    mismatches.append(f"{field}: atteso {exp[field]}, trovato {getattr(act, field)}")
            
            if mismatches:
                discrepancies.append({
                    'team': exp['team'],
                    'type': 'DATA_MISMATCH',
                    'message': f"Discrepanza per {exp['team']}: " + ", ".join(mismatches)
                })
                
        return discrepancies
