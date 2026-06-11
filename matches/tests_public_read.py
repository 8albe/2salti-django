from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import Season, Sport, Society, Team, League, LeagueStanding
from matches.models import Match, MatchEvent, MatchReport
import json
from django.utils import timezone

User = get_user_model()

class PublicReadLayerTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.society = Society.objects.create(name="Pro Recco", slug="pro-recco", sport=self.sport)
        self.team = Team.objects.create(society=self.society, category="SENIOR")
        self.league = League.objects.create(name="Serie A1", sport=self.sport, category="SENIOR", season="2024-2025")
        self.team.league = self.league
        self.team.save()
        
        # Test Athlete
        self.athlete_user = User.objects.create_user(username="atleta1", role="athlete", first_name="Mario", last_name="Rossi")
        self.athlete_profile = self.athlete_user.athlete_profile
        self.athlete_profile.current_team = self.team
        self.athlete_profile.save()
        
        # Test Match
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team, # Just for testing
            match_date=timezone.now(),
            is_finished=True,
            home_score=10,
            away_score=8
        )
        
        # Create a published report to ensure data is "public"
        self.report = MatchReport.objects.create(
            match=self.match,
            status='PUBLISHED'
        )
        
        # Create a standing
        self.standing = LeagueStanding.objects.create(
            league=self.league,
            team=self.team,
            season="2024-2025",
            points=3,
            played=1,
            won=1,
            rank=1
        )

    def test_home_page_public(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pallanuoto")

    def test_league_standings_public(self):
        response = self.client.get(reverse('league_standings', args=[self.league.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.team.name)
        # The position is just a number in a td
        self.assertContains(response, '1') 

    def test_team_detail_public(self):
        response = self.client.get(reverse('team_detail', args=[self.team.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.team.name)
        self.assertContains(response, "Posizione #1")
        self.assertContains(response, self.athlete_user.get_full_name())

    def test_match_detail_public(self):
        response = self.client.get(reverse('match_detail', args=[self.match.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.match.home_score))
        self.assertContains(response, str(self.match.away_score))

    def test_athlete_profile_public(self):
        response = self.client.get(reverse('profile', args=[self.athlete_user.username]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.athlete_user.get_full_name())

    def test_athlete_alias_url(self):
        """Verifica che il nuovo alias /player/ funzioni."""
        response = self.client.get(reverse('player_profile', args=[self.athlete_user.username]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.athlete_user.get_full_name())

    def test_hardening_excludes_non_published_matches(self):
        """Verifica che i match NON pubblicati non appaiano nelle liste pubbliche."""
        # 1. Crea un match finito con un report VALIDATED (ma non PUBLISHED)
        draft_match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team,
            match_date=timezone.now() - timezone.timedelta(hours=5),
            is_finished=True,
            home_score=5,
            away_score=5
        )
        MatchReport.objects.create(match=draft_match, status='VALIDATED')
        
        # 2. Verifica pagina Team: non deve contenere il punteggio del draft match
        response = self.client.get(reverse('team_detail', args=[self.team.slug]))
        self.assertNotContains(response, "5-5")
        
        # 3. Verifica pagina Athlete: non deve contenere il punteggio del draft match
        response = self.client.get(reverse('player_profile', args=[self.athlete_user.username]))
        self.assertNotContains(response, "5-5")

    def test_empty_states_render_safely(self):
        """Verifica che stati vuoti non mandino in crash le pagine."""
        empty_team = Team.objects.create(society=self.society, category="U10", slug="empty-team")
        response = self.client.get(reverse('team_detail', args=[empty_team.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nessuna partita recente")
        
        empty_user = User.objects.create_user(username="empty_atleta", role="athlete")
        response = self.client.get(reverse('player_profile', args=[empty_user.username]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nessuna prestazione recente registrata")

    def test_api_standings(self):
        response = self.client.get(reverse('api_league_standings', args=[self.league.id]))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['league']['id'], self.league.id)
        self.assertEqual(data['standings'][0]['team_name'], self.team.name)

    def test_api_match_detail(self):
        response = self.client.get(reverse('api_match_detail', args=[self.match.id]))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['home_team'], self.team.name)
        self.assertEqual(data['home_score'], 10)
