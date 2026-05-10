from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Sport, Society, Team, League
from matches.models import Match, MatchEvent
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds a sample Water Polo match with detailed stats'

    def handle(self, *args, **kwargs):
        sport, _ = Sport.objects.get_or_create(name="Pallanuoto", slug="pallanuoto")
        soc1, _ = Society.objects.get_or_create(name="Pro Recco", sport=sport, slug="pro-recco")
        soc2, _ = Society.objects.get_or_create(name="AN Brescia", sport=sport, slug="an-brescia")
        
        league_24, _ = League.objects.get_or_create(name="Serie A1", sport=sport, category="SENIOR", season="2024-2025", slug="serie-a1-24")
        
        t1, _ = Team.objects.get_or_create(society=soc1, category="SENIOR", defaults={'league': league_24})
        t2, _ = Team.objects.get_or_create(society=soc2, category="SENIOR", defaults={'league': league_24})
        
        # Ensure league is correct if they already existed
        t1.league = league_24
        t1.save()
        t2.league = league_24
        t2.save()
        
        # Players
        p1, _ = User.objects.get_or_create(username="velotto", first_name="Alessandro", last_name="Velotto", role="athlete")
        p2, _ = User.objects.get_or_create(username="difulvio", first_name="Francesco", last_name="Di Fulvio", role="athlete")
        p3, _ = User.objects.get_or_create(username="delungo", first_name="Marco", last_name="Del Lungo", role="athlete")
        
        # Create Match
        match = Match.objects.create(
            league=league_24,
            home_team=t1,
            away_team=t2,
            match_date=timezone.now(),
            location="Piscina Comunale",
            home_score=8,
            away_score=6,
            is_finished=True,
            quarter_scores={
                "1": [2, 1],
                "2": [3, 2],
                "3": [1, 2],
                "4": [2, 1]
            }
        )
        
        # Events Q1
        MatchEvent.objects.create(match=match, event_type='GOAL', player=p1, team=t1, minute=2, quarter=1)
        MatchEvent.objects.create(match=match, event_type='EXCLUSION_20', player=p2, team=t2, minute=4, quarter=1)
        MatchEvent.objects.create(match=match, event_type='GOAL', player=p1, team=t1, minute=5, quarter=1, is_superiority=True)
        
        # Events Q2
        MatchEvent.objects.create(match=match, event_type='GOAL', player=p2, team=t2, minute=3, quarter=2, is_penalty=True)

        # Events Q3
        MatchEvent.objects.create(match=match, event_type='EXCLUSION_20', player=p1, team=t1, minute=1, quarter=3)
        
        self.stdout.write(self.style.SUCCESS(f'Successfully seeded match: {match.id}'))
