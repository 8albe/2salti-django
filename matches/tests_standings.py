from django.test import TestCase
from django.utils import timezone
from core.models import Sport, Society, Team, League, LeagueStanding
from matches.models import Match, MatchReport
from matches.services.publishing_service import PublishingService
from matches.services.standings_service import StandingsService
from django.core.management import call_command
from io import StringIO

class StandingsVerificationTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.soc_a = Society.objects.create(name="Soc A", slug="soc-a", sport=self.sport)
        self.soc_b = Society.objects.create(name="Soc B", slug="soc-b", sport=self.sport)
        self.league = League.objects.create(name="A1", sport=self.sport, category="SENIOR", slug="a1")
        
        self.t1 = Team.objects.create(society=self.soc_a, category="SENIOR", league=self.league, name="T1")
        self.t2 = Team.objects.create(society=self.soc_b, category="SENIOR", league=self.league, name="T2")
        
        # Match 1
        self.m1 = Match.objects.create(
            league=self.league, home_team=self.t1, away_team=self.t2,
            home_score=0, away_score=0, is_finished=False, match_date=timezone.now()
        )
        # Create minimal valid data that passes assess_publish_readiness
        valid_data = {
            'metadata': {'confidence': 0.9},
            'match_info': {'home_team': 'Soc A', 'away_team': 'Soc B', 'date': '2026-03-26'},
            'scores': {'final_score': '10-5', 'quarters': {}},
            'teams': {
                'home': {'name': 'Soc A', 'score': 10, 'players': [{'name': 'P1', 'number': 1}]},
                'away': {'name': 'Soc B', 'score': 5, 'players': [{'name': 'P2', 'number': 1}]}
            },
            'events': []
        }
        self.r1 = MatchReport.objects.create(
            match=self.m1, status='VALIDATED', 
            normalized_data=valid_data
        )

    def test_standings_updated_on_publish(self):
        # Initial: no persisted standings
        self.assertFalse(LeagueStanding.objects.filter(league=self.league).exists())
        
        # Publish report
        success, msg = PublishingService.publish_report(self.r1)
        self.assertTrue(success)
        
        # Now standings should exist
        self.assertTrue(LeagueStanding.objects.filter(league=self.league).exists())
        s1 = LeagueStanding.objects.get(league=self.league, team=self.t1)
        self.assertEqual(s1.points, 3)
        self.assertEqual(s1.rank, 1)
        
        s2 = LeagueStanding.objects.get(league=self.league, team=self.t2)
        self.assertEqual(s2.points, 0)
        self.assertEqual(s2.rank, 2)

    def test_rebuild_command(self):
        # Manually publish WITHOUT service (simulating legacy or sync issues)
        self.r1.status = 'PUBLISHED'
        self.r1.save()
        
        # We MUST also set the match as finished with scores, 
        # as the StandingsService only counts finished/published matches.
        self.m1.is_finished = True
        self.m1.home_score = 10
        self.m1.away_score = 5
        self.m1.save()
        
        out = StringIO()
        call_command('rebuild_standings', stdout=out)
        
        self.assertIn("Ricalcolate 1 classifiche", out.getvalue())
        self.assertTrue(LeagueStanding.objects.filter(league=self.league).exists())
        s1 = LeagueStanding.objects.get(team=self.t1)
        self.assertEqual(s1.points, 3)

    def test_get_standings_uses_persisted(self):
        # Create a "fake" persisted standing to prove it uses it
        LeagueStanding.objects.create(
            league=self.league, team=self.t1, season=self.league.season,
            points=99, played=1, rank=1
        )
        
        standings = self.league.get_standings()
        self.assertEqual(standings[0]['points'], 99)
        self.assertEqual(standings[0]['team'], self.t1)
