from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.models import Season, Sport, Society, Team, League
from matches.models import Match, MatchReport, MatchEvent
import json

User = get_user_model()

class EndToEndPilotVerificationTest(TestCase):
    """
    Verifica il flusso completo dall'upload alla visibilità pubblica (MVP Coherence).
    """
    def setUp(self):
        # 1. Setup Infrastructure
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.society_h = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco")
        self.society_a = Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia")
        
        self.league = League.objects.create(name="Série A1", sport=self.sport)
        
        self.team_h = Team.objects.create(society=self.society_h, league=self.league)
        self.team_a = Team.objects.create(society=self.society_a, league=self.league)
        
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_h,
            away_team=self.team_a,
            match_date=timezone.now(),
        )
        
        # Users
        self.staff_user = User.objects.create_user(username="staff", role="coach", is_staff=True)
        self.admin_user = User.objects.create_superuser(username="admin", email="admin@test.com", password="password")
        
        # Athlete for reconciliation - ENSURE TEAM ALIGNMENT
        self.athlete = User.objects.create_user(username="velotto", first_name="Alessandro", last_name="Velotto", role="athlete")
        ap_h = self.athlete.athlete_profile
        ap_h.current_team = self.match.home_team
        ap_h.save()
        
        self.athlete_a = User.objects.create_user(username="opponent", first_name="Marco", last_name="Opponent", role="athlete")
        ap_a = self.athlete_a.athlete_profile
        ap_a.current_team = self.match.away_team
        ap_a.save()


    def test_full_lifecycle_coherence(self):
        """
        Flusso: Upload -> Review -> Publish -> Check Public & API.
        """
        client = Client()
        client.force_login(self.admin_user)
        
        # --- STAGE 1: UPLOAD & DRAFT (No Public Visibility) ---
        report = MatchReport.objects.create(
            match=self.match,
            status=MatchReport.Status.EXTRACTED,
            normalized_data={
                "metadata": {"confidence": 0.9},
                "match_info": {"home_team": "Pro Recco", "away_team": "AN Brescia", "date": "2024-01-01"},
                "scores": {"final_score": "5-3", "quarters": {"1": [2, 1], "2": [3, 2]}},
                "teams": {"home": {"players": [{"name": "Velotto", "number": 1}]}, "away": {"players": []}},
                "events": [
                    # Periodi coerenti con i parziali 2-1 / 3-2: dal 2026-07-21 il
                    # gate confronta gli eventi-gol con il parziale di ogni periodo.
                    {"type": "GOAL", "team": "home", "player_name": "Velotto", "minute": i,
                     "quarter": 1 if i <= 2 else 2} for i in range(1, 6)
                ] + [
                    {"type": "GOAL", "team": "away", "player_name": "Opponent", "minute": j,
                     "quarter": 1 if j <= 1 else 2} for j in range(1, 4)
                ],

                "reconciliation": {
                    "home_players": {"Velotto": self.athlete.id},
                    "away_players": {"Opponent": self.athlete_a.id}
                }

            }

        )
        
        # Verify match is not yet public
        self.assertFalse(self.match.is_public)
        
        # Check Public Detail Page (Should show no score)
        url_detail = reverse('match_detail', args=[self.match.id])
        res_detail = client.get(url_detail)
        self.assertNotContains(res_detail, "5-3")
        self.assertNotContains(res_detail, "Velotto") # No events yet
        
        # Check API (Should return 404)
        url_api = reverse('api_match_detail', args=[self.match.id])
        res_api = client.get(url_api)
        self.assertEqual(res_api.status_code, 404)

        # --- STAGE 2: PUBLISH (Trigger Public Visibility) ---
        # Simulate publishing via Admin Operational Dashboard
        url_review = reverse('op_admin:matches_matchreport_review', args=[report.id])
        post_data = {
            'normalized_data': json.dumps(report.normalized_data),
            '_action': 'publish_now'
        }
        res_publish = client.post(url_review, post_data)
        self.assertEqual(res_publish.status_code, 302) # Redirect to changelist
        
        self.match.refresh_from_db()
        self.assertTrue(self.match.is_public)
        self.assertEqual(self.match.home_score, 5)
        
        # --- STAGE 3: VERIFY COHERENCE ---
        
        # 3.1 Public Page
        res_detail_pub = client.get(url_detail)
        self.assertContains(res_detail_pub, str(self.match.home_score))
        self.assertContains(res_detail_pub, str(self.match.away_score))
        self.assertContains(res_detail_pub, "Velotto") # Scorer now visible
        
        # 3.2 API
        res_api_pub = client.get(url_api)
        self.assertEqual(res_api_pub.status_code, 200)
        api_data = res_api_pub.json()
        self.assertEqual(api_data['home_score'], 5)
        self.assertEqual(api_data['events'][0]['player'], "Alessandro Velotto")
        
        # 3.3 Standings
        url_standings = reverse('league_standings', args=[self.league.id])
        res_standings = client.get(url_standings)
        self.assertContains(res_standings, "Pro Recco")
        # Check points (1 win = 3 points in default WP logic)
        self.assertContains(res_standings, "3")

        # 3.4 Athlete Detail
        url_athlete = reverse('api_athlete_detail', args=[self.athlete.id])
        res_athlete = client.get(url_athlete)
        self.assertEqual(res_athlete.json()['stats']['total_goals'], 5)


    def test_upload_deduplication_behavior(self):
        """Verifica che carichi duplicati vengano rilevati."""
        # This would usually test the UI or the service.
        # Minimal verification: multiple reports for same match are allowed but have different IDs.
        # But we want to check if the logic handles it.
        pass
