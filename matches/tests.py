from django.test import TestCase
from django.contrib.auth import get_user_model
from core.models import League, Sport, Society, Team
from matches.models import Match, MatchEvent
from matches.stats_services import get_top_scorers, get_discipline_stats
from django.utils import timezone

User = get_user_model()

class StatsTestCase(TestCase):
    def setUp(self):
        # Setup basic data
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.society = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco")
        self.league = League.objects.create(name="Serie A1", sport=self.sport, category="SENIOR", slug="serie-a1")
        
        self.team = Team.objects.create(society=self.society, category="SENIOR", league=self.league)
        
        # Players
        self.p1 = User.objects.create_user(username="p1", first_name="Alessandro", last_name="Velotto", role="athlete")
        self.p2 = User.objects.create_user(username="p2", first_name="Francesco", last_name="Di Fulvio", role="athlete")
        
        # Match
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team, # Same team for simplicity
            match_date=timezone.now()
        )
        
        # Events
        # P1 scores 2 goals
        MatchEvent.objects.create(match=self.match, event_type='GOAL', player=self.p1, team=self.team, minute=1, quarter=1)
        MatchEvent.objects.create(match=self.match, event_type='GOAL', player=self.p1, team=self.team, minute=2, quarter=2)
        
        # P2 scores 1 goal
        MatchEvent.objects.create(match=self.match, event_type='GOAL', player=self.p2, team=self.team, minute=3, quarter=3)
        
        # P2 gets expelled
        MatchEvent.objects.create(match=self.match, event_type='EXPULSION', player=self.p2, team=self.team, minute=4, quarter=4)

    def test_top_scorers(self):
        scorers = get_top_scorers(self.league.id)
        # Convert to list to restart iteration if needed, though here we just access by index
        scorers_list = list(scorers)
        self.assertEqual(len(scorers_list), 2)
        
        # Identify scorers by last name
        p1_stats = next(s for s in scorers_list if s['player__last_name'] == "Velotto")
        p2_stats = next(s for s in scorers_list if s['player__last_name'] == "Di Fulvio")
        
        self.assertEqual(p1_stats['total_goals'], 2)
        self.assertEqual(p2_stats['total_goals'], 1)

    def test_discipline(self):
        bad_boys = get_discipline_stats(self.league.id)
        bad_boys_list = list(bad_boys)
        self.assertEqual(len(bad_boys_list), 1)
        self.assertEqual(bad_boys_list[0]['player__last_name'], "Di Fulvio")
        self.assertEqual(bad_boys_list[0]['total_expulsions'], 1)
