from django.test import TestCase
from django.core import mail
from core.models import Sport, Society, Team, League, LeagueStanding
from matches.models import Match, MatchReport
from matches.services.standings_service import StandingsService
from django.core.management import call_command
import io
from django.contrib.auth import get_user_model

User = get_user_model()

class MonitoringTestCase(TestCase):
    def setUp(self):
        self.sport, _ = Sport.objects.get_or_create(name="MonitorSport", slug="monitorsport")
        self.society = Society.objects.create(name="Monitor Team A", slug="m-team-a", sport=self.sport)
        self.society_b = Society.objects.create(name="Monitor Team B", slug="m-team-b", sport=self.sport)
        
        self.league = League.objects.create(name="Monitor League", sport=self.sport, season="2023/24")
        self.team_a = Team.objects.create(society=self.society, league=self.league)
        self.team_b = Team.objects.create(society=self.society_b, league=self.league)
        
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
        StandingsService.rebuild_for_league(self.league)

    def test_monitor_integrity_triggers_email(self):
        # 1. Induce drift
        self.match.home_score = 100
        self.match.save()
        
        # 2. Run monitor (should fail with exit code 1 because of issues)
        out = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            call_command('monitor_integrity', stdout=out)
        
        self.assertEqual(cm.exception.code, 1)
        
        # 3. Check for email
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Discrepanza Integrità: Monitor League", mail.outbox[0].subject)
        self.assertIn("goals_for: atteso 100, trovato 80", mail.outbox[0].body)

    def test_monitor_integrity_no_issues_no_email(self):
        # Everything is sane
        out = io.StringIO()
        call_command('monitor_integrity', stdout=out)
        
        # No email sent
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("Monitoraggio completato: Sistema in salute.", out.getvalue())

    def test_monitor_with_auto_rebuild(self):
        # 1. Induce drift
        self.match.home_score = 99
        self.match.save()
        
        # 2. Run monitor with --auto-rebuild
        out = io.StringIO()
        # Should NOT exit 1 if fixed? 
        # Actually my command exits 1 IF IT FOUND issues, even if it fixed them.
        # Let's check the command code... it checks total_issues at the end.
        with self.assertRaises(SystemExit):
            call_command('monitor_integrity', '--auto-rebuild', stdout=out)
            
        # 3. Check that it is FIXED now
        from matches.services.integrity_service import DataIntegrityService
        issues = DataIntegrityService.check_league_standings(self.league)
        self.assertEqual(len(issues), 0)
