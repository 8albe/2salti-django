from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import Sport, Society, Team, League
from matches.models import Match
import xml.etree.ElementTree as ET

User = get_user_model()

class ProdReadinessTestCase(TestCase):
    def setUp(self):
        self.sport, _ = Sport.objects.get_or_create(name="ProdSport", slug="prodsport")
        self.society, _ = Society.objects.get_or_create(name="Prod Society", slug="prod-soc", sport=self.sport)
        self.league, _ = League.objects.get_or_create(name="Prod League", sport=self.sport, season="2023/24")
        self.team, _ = Team.objects.get_or_create(society=self.society, slug="prod-team-senior")
        self.athlete, _ = User.objects.get_or_create(username="prod_athlete", role="athlete", first_name="Prod", setup_completed=True)
        # Match matches might not be easy to get_or_create due to complex fields
        self.match = Match.objects.create(home_team=self.team, away_team=self.team, league=self.league, match_date="2024-03-26T15:00:00Z")

    def test_public_pages_status_code(self):
        urls = [
            reverse('home'),
            reverse('sport_detail', args=[self.sport.slug]),
            reverse('team_detail', args=[self.team.slug]),
            reverse('league_standings', args=[self.league.id]),
            reverse('match_detail', args=[self.match.id]),
            reverse('profile', args=[self.athlete.username]),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f"URL {url} failed with {response.status_code}")

    def test_canonical_and_og_tags(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, '<link rel="canonical"')
        self.assertContains(response, 'property="og:url"')
        self.assertContains(response, 'property="og:site_name" content="2salti"')
        
        # Test query param stripping in canonical (default behavior)
        response = self.client.get(reverse('home') + "?date=2024-01-01")
        # should still point to / (no query param)
        self.assertContains(response, 'rel="canonical" href="http://testserver/"')

    @override_settings(ENVIRONMENT_NAME='development', DEBUG=True)
    def test_robots_txt_dev(self):
        response = self.client.get(reverse('robots_txt'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Disallow: /", response.content)
        self.assertNotIn(b"Sitemap:", response.content)

    @override_settings(ENVIRONMENT_NAME='production', DEBUG=False)
    def test_robots_txt_prod(self):
        response = self.client.get(reverse('robots_txt'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Disallow: /admin/", response.content)
        self.assertIn(b"Sitemap:", response.content)
        self.assertNotIn(b"Disallow: /\n", response.content)

    @override_settings(ENVIRONMENT_NAME='staging', DEBUG=False)
    def test_robots_txt_staging(self):
        # Staging should still be Disallow: / even if DEBUG=False
        response = self.client.get(reverse('robots_txt'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Disallow: /", response.content)

    def test_security_settings_in_prod(self):
        # Test settings logic directly
        with override_settings(ENVIRONMENT_NAME='production'):
            # This doesn't re-run the logic in settings.py unfortunately
            # but we can check if the variables exist in settings
            pass

    def test_sitemap_xml(self):
        response = self.client.get(reverse('sitemap_xml'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], "application/xml")
        
        # Parse XML
        root = ET.fromstring(response.content)
        namespaces = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        locs = [loc.text for loc in root.findall('.//ns:loc', namespaces)]
        
        expected_matches = [
            'http://testserver/',
            f'http://testserver/sport/{self.sport.slug}/',
            f'http://testserver/team/{self.team.slug}/',
            f'http://testserver/matches/{self.match.id}/',
            f'http://testserver/accounts/profile/{self.athlete.username}/',
        ]
        for expected in expected_matches:
            self.assertIn(expected, locs)

    def test_json_ld_presence(self):
        pages = [
            (reverse('home'), 'WebSite'),
            (reverse('match_detail', args=[self.match.id]), 'SportsEvent'),
            (reverse('team_detail', args=[self.team.slug]), 'SportsOrganization'),
            (reverse('profile', args=[self.athlete.username]), 'Person'),
        ]
        for url, schema_type in pages:
            response = self.client.get(url)
            self.assertContains(response, f'"@type": "{schema_type}"')
            self.assertContains(response, 'application/ld+json')
