from django.test import TestCase
from django.urls import reverse
from core.models import Sport, Society, Team, League
from matches.models import Match, MatchReport
from django.contrib.auth import get_user_model
import json

User = get_user_model()

class StructuredDataTestCase(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="SchemaSport", slug="schemasport")
        self.society = Society.objects.create(name="Schema Team A", slug="s-team-a", sport=self.sport)
        self.league = League.objects.create(name="Schema League", sport=self.sport, season="2023/24")
        self.team = Team.objects.create(society=self.society, category="SENIOR", league=self.league, slug="s-team-a")
        
    def test_home_has_structured_data(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'application/ld+json')
        self.assertContains(response, '"@type": "WebSite"')
        self.assertContains(response, '"@type": "Organization"')

    def test_match_detail_has_structured_data(self):
        team_b = Team.objects.create(
            society=Society.objects.create(name="Schema Team B", slug="s-team-b", sport=self.sport),
            category="SENIOR", league=self.league
        )
        match = Match.objects.create(
            home_team=self.team, away_team=team_b, league=self.league,
            match_date="2024-03-26T15:00:00Z"
        )
        response = self.client.get(reverse('match_detail', args=[match.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"@type": "SportsEvent"')
        self.assertContains(response, '"@type": "BreadcrumbList"')

    def test_team_detail_has_structured_data(self):
        response = self.client.get(reverse('team_detail', args=[self.team.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"@type": "SportsOrganization"')
        self.assertContains(response, '"@type": "BreadcrumbList"')

    def test_profile_has_structured_data(self):
        user = User.objects.create(username="athlete1", role="athlete", first_name="Mario", last_name="Rossi")
        response = self.client.get(reverse('profile', args=[user.username]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"@type": "Person"')
        self.assertContains(response, '"name": "Mario Rossi"')
