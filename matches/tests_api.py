from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.models import Sport, Society, Team, League
from matches.models import Match, MatchReport

User = get_user_model()

class PublicAPITestCase(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.society_h = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco")
        self.society_a = Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia")
        
        self.league = League.objects.create(name="Serie A1", sport=self.sport, category="SENIOR", slug="serie-a1")
        
        self.team_h = Team.objects.create(society=self.society_h, league=self.league, category="SENIOR")
        self.team_a = Team.objects.create(society=self.society_a, league=self.league, category="SENIOR")
        
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
