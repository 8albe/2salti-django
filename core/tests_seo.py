from django.test import TestCase
from django.urls import reverse
from core.models import Sport, Team, League, Society
from matches.models import Match
from django.contrib.auth import get_user_model

User = get_user_model()

class SEOTestCase(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.society = Society.objects.create(name="Pro Recco", slug="pro-recco", sport=self.sport)
        self.league = League.objects.create(name="Serie A1", slug="serie-a1", sport=self.sport, season="2023/24")
        self.team = Team.objects.create(society=self.society, category="SENIOR", league=self.league)
        # self.team name and slug are auto-generated
        self.user = User.objects.create_user(username="testathlete", first_name="Test", last_name="Athlete", role="athlete")
        self.match = Match.objects.create(
            home_team=self.team,
            away_team=self.team, # Just for test
            league=self.league,
            match_date="2024-03-26T15:00:00Z",
            is_finished=True,
            home_score=10,
            away_score=8
        )

    def test_robots_txt(self):
        response = self.client.get(reverse('robots_txt'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"User-agent: *", response.content)
        self.assertIn(b"Disallow: /", response.content)

    def test_sitemap_xml(self):
        response = self.client.get(reverse('sitemap_xml'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<?xml version="1.0" encoding="UTF-8"?>', response.content)
        self.assertIn(b'<urlset', response.content)
        self.assertIn(b'/league/1/standings/', response.content) # ID might be different but reverse uses ID
        self.assertIn(b'/team/pro-recco-senior/', response.content)

    def test_home_seo_tags(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>Risultati e Classifiche del")
        self.assertContains(response, '<meta name="description" content="Segui i risultati')
        self.assertContains(response, 'property="og:title"')

    def test_team_detail_seo_tags(self):
        response = self.client.get(reverse('team_detail', args=[self.team.slug]))
        self.assertContains(response, f"<title>{self.team.name} - {self.league.name}")
        self.assertContains(response, f'content="Dettagli, roster e risultati per {self.team.name}')
        self.assertContains(response, 'property="og:type" content="website"')

    def test_match_detail_seo_tags(self):
        response = self.client.get(reverse('match_detail', args=[self.match.id]))
        self.assertContains(response, f"<title>{self.team.name} vs {self.team.name}")
        self.assertContains(response, 'property="og:url"')
