from django.test import TestCase
from django.contrib.auth import get_user_model
from core.models import League, Sport, Society, Team
from matches.models import Match, MatchEvent, MatchReport
from matches.stats_services import get_top_scorers, get_discipline_stats
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

User = get_user_model()

class OCRWorkflowTestCase(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.society = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco")
        self.league = League.objects.create(name="Serie A1", sport=self.sport, category="SENIOR", slug="serie-a1")
        self.team = Team.objects.create(society=self.society, category="SENIOR", league=self.league)
        self.user = User.objects.create_user(
            username="admin", 
            is_staff=True, 
            is_superuser=True,
            identity_status='VERIFIED',
            subscription_status='ACTIVE'
        )
        self.team2 = Team.objects.create(
            society=Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia"), 
            category="SENIOR", 
            league=self.league
        )
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team2,
            match_date=timezone.now()
        )

    def test_upload_report_flow(self):
        self.client.force_login(self.user)
        # Create a dummy file
        pdf_file = SimpleUploadedFile("referto.pdf", b"file_content", content_type="application/pdf")
        
        # Test HTTP POST to upload view
        url = f"/matches/{self.match.id}/upload-report/"
        response = self.client.post(url, {'file': pdf_file})
        
        # Should redirect to match detail
        self.assertRedirects(response, f"/matches/{self.match.id}/")
        
        # Verify db record
        report = MatchReport.objects.filter(match=self.match).first()
        self.assertIsNotNone(report)
        self.assertEqual(report.status, 'UPLOADED')
        self.assertEqual(report.uploader, self.user)
        
        # Check admin accessibility
        admin_url = f"/admin/matches/matchreport/{report.id}/change/"
        admin_response = self.client.get(admin_url)
        self.assertEqual(admin_response.status_code, 200)


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
        
        # Match with quarter scores
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team,
            match_date=timezone.now(),
            quarter_scores={"1": [1, 0], "2": [1, 1]}
        )
        
        # Events
        # P1 scores 1 goal and 1 penalty goal
        MatchEvent.objects.create(match=self.match, event_type='GOAL', player=self.p1, team=self.team, minute=1, quarter=1)
        MatchEvent.objects.create(match=self.match, event_type='PENALTY_GOAL', player=self.p1, team=self.team, minute=2, quarter=2, is_penalty=True)
        
        # P2 scores 1 goal
        MatchEvent.objects.create(match=self.match, event_type='GOAL', player=self.p2, team=self.team, minute=3, quarter=3)
        
        # P2 gets excluded (20")
        MatchEvent.objects.create(match=self.match, event_type='EXCLUSION_20', player=self.p2, team=self.team, minute=4, quarter=4)

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
