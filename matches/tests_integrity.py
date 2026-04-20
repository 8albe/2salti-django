from django.test import TestCase
from core.models import Sport, Society, Team, League, LeagueStanding
from matches.models import Match, MatchReport
from matches.services.integrity_service import DataIntegrityService
from matches.services.standings_service import StandingsService
from django.contrib.auth import get_user_model

User = get_user_model()

class DataHardeningTestCase(TestCase):
    def setUp(self):
        self.sport, _ = Sport.objects.get_or_create(name="TestBasket", slug="testbasket")
        self.society = Society.objects.create(name="Team A", slug="team-a", sport=self.sport)
        self.society_b = Society.objects.create(name="Team B", slug="team-b", sport=self.sport)
        
        self.league = League.objects.create(name="Serie A", sport=self.sport, season="2023/24")
        self.team_a = Team.objects.create(society=self.society, category="SENIOR", league=self.league)
        self.team_b = Team.objects.create(society=self.society_b, category="SENIOR", league=self.league)
        
        self.user = User.objects.create_superuser(username="admin", email="admin@test.com", password="password")
        
        self.match = Match.objects.create(
            home_team=self.team_a,
            away_team=self.team_b,
            league=self.league,
            match_date="2024-03-26T15:00:00Z",
            is_finished=True,
            home_score=80,
            away_score=70
        )
        self.report = MatchReport.objects.create(
            match=self.match,
            status=MatchReport.Status.PUBLISHED
        )
        # Initial rebuild
        StandingsService.rebuild_for_league(self.league)

    def test_integrity_check_detects_drift(self):
        # 1. Verify initially OK
        issues = DataIntegrityService.check_league_standings(self.league)
        self.assertEqual(len(issues), 0)
        
        # 2. Simulate drift: Manual score change without standings update
        self.match.home_score = 100
        self.match.save()
        
        # 3. Verify drift DETECTED
        issues = DataIntegrityService.check_league_standings(self.league)
        self.assertGreater(len(issues), 0)
        self.assertEqual(issues[0]['type'], 'DATA_MISMATCH')
        self.assertIn('goals_for', issues[0]['message'])

    def test_realign_data_fixes_drift(self):
        # 1. Force drift
        self.match.home_score = 90
        self.match.save()
        
        # 2. Realign
        self.report.realign_data()
        
        # 3. Verify FIXED
        issues = DataIntegrityService.check_league_standings(self.league)
        self.assertEqual(len(issues), 0)

    def test_rebuild_standings_is_idempotent(self):
        count1 = StandingsService.rebuild_for_league(self.league)
        count2 = StandingsService.rebuild_for_league(self.league)
        self.assertEqual(count1, count2)
        self.assertEqual(count1, 2) # Two teams
