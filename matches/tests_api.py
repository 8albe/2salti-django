from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.models import Season, Sport, Society, Team, League
from matches.models import Match, MatchReport

User = get_user_model()

class PublicAPITestCase(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.society_h = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco")
        self.society_a = Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia")
        
        self.league = League.objects.create(name="Serie A1", sport=self.sport, slug="serie-a1")
        
        self.team_h = Team.objects.create(society=self.society_h, league=self.league)
        self.team_a = Team.objects.create(society=self.society_a, league=self.league)
        
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_h,
            away_team=self.team_a,
            match_date=timezone.now(),
            is_finished=True,
            home_score=10,
            away_score=8
        )
        
        # Athlete
        self.user_p1 = User.objects.create_user(
            username="player1", 
            first_name="Alessandro", 
            last_name="Velotto", 
            role="athlete",
            phone="123456789", # Private info
            city="Napoli"      # Private info
        )
        self.profile_p1 = self.user_p1.athlete_profile
        self.profile_p1.current_team = self.team_h
        self.profile_p1.position = "Difensore"
        self.profile_p1.jersey_number = 7
        self.profile_p1.save()

    def test_api_match_detail_safety(self):
        """Verifica che i match non pubblicati ritornino 404."""
        url = reverse('api_match_detail', args=[self.match.id])
        
        # 1. Senza report -> 404
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        
        # 2. Con report VALIDATED -> 404
        report = MatchReport.objects.create(match=self.match, status=MatchReport.Status.VALIDATED)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        
        # 3. Con report PUBLISHED -> 200
        report.status = MatchReport.Status.PUBLISHED
        report.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['home_score'], 10)

    def test_api_league_matches_filtering(self):
        """Verifica che la lista match del campionato mostri solo quelli pubblicati."""
        url = reverse('api_league_matches', args=[self.league.id])
        
        # Senza report pubblicato -> lista vuota
        response = self.client.get(url)
        self.assertEqual(len(response.json()['matches']), 0)
        
        # Con report pubblicato -> lista contiene il match
        MatchReport.objects.create(match=self.match, status=MatchReport.Status.PUBLISHED)
        response = self.client.get(url)
        self.assertEqual(len(response.json()['matches']), 1)


class AIQueryAccessTestCase(TestCase):
    """L'endpoint AI query è chiuso agli anonimi (login_required) e non deve
    mai istanziare/chiamare il motore (quindi OpenAI) per un utente non loggato."""

    def setUp(self):
        self.url = reverse('api_ai_query')
        self.user = User.objects.create_user(
            username="fan1", password="pw-test-123", role="fan"
        )

    @patch('matches.api_views.AIStatsEngine')
    def test_anonymous_does_not_run_query(self, MockEngine):
        response = self.client.post(
            self.url,
            data={'query': 'gol Rossi'},
            content_type='application/json',
        )
        # login_required -> redirect al login (default-closed). Nessuna
        # esecuzione: il motore (e quindi OpenAI) non viene mai toccato.
        self.assertIn(response.status_code, (301, 302, 401, 403))
        MockEngine.assert_not_called()

    @patch('matches.api_views.AIStatsEngine')
    def test_authenticated_runs_query(self, MockEngine):
        MockEngine.return_value.process_query.return_value = {
            "type": "answer", "text": "ok",
        }
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            data={'query': 'gol Rossi'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['text'], "ok")
        MockEngine.return_value.process_query.assert_called_once()
