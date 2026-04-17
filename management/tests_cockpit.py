from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from matches.models import Match, MatchReport
from core.models import Sport, Society, Team, League
from django.utils import timezone

User = get_user_model()

class OpsCockpitTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff_user = User.objects.create_user(username="admin_user", is_staff=True, password="password")
        self.regular_user = User.objects.create_user(username="regular_user", is_staff=False, password="password")
        
        # Base data
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.society = Society.objects.create(name="Pro Recco", slug="pro-recco", sport=self.sport)
        self.team = Team.objects.create(society=self.society, category="SENIOR")
        self.league = League.objects.create(name="Serie A1", sport=self.sport, category="SENIOR", season="2024-2025")
        
        self.match = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.team,
            match_date=timezone.now()
        )

    def test_access_denied_to_anonymous(self):
        response = self.client.get(reverse('ops_cockpit'))
        self.assertEqual(response.status_code, 302) # Redirect to login

    def test_access_denied_to_regular_user(self):
        self.client.login(username="regular_user", password="password")
        response = self.client.get(reverse('ops_cockpit'))
        self.assertEqual(response.status_code, 403)

    def test_access_granted_to_staff(self):
        self.client.login(username="admin_user", password="password")
        response = self.client.get(reverse('ops_cockpit'))
        self.assertEqual(response.status_code, 200)

    def test_kpi_counts(self):
        """Verifica che i conteggi KPI siano corretti."""
        # Create various reports
        MatchReport.objects.create(match=self.match, status='UPLOADED')    # In Flight
        MatchReport.objects.create(match=self.match, status='PROCESSING')  # In Flight
        MatchReport.objects.create(match=self.match, status='EXTRACTED')   # Pending Review
        MatchReport.objects.create(match=self.match, status='NEEDS_REVIEW') # Needs Review
        MatchReport.objects.create(match=self.match, status='REJECTED')    # Failed
        
        # Published today
        MatchReport.objects.create(
            match=self.match, status='PUBLISHED', 
            published_at=timezone.now(), published_by=self.staff_user
        )

        self.client.login(username="admin_user", password="password")
        response = self.client.get(reverse('ops_cockpit'))
        stats = response.context['stats']
        
        self.assertEqual(stats['in_flight'], 2)
        self.assertEqual(stats['pending_review'], 1)
        self.assertEqual(stats['needs_review'], 1)
        self.assertEqual(stats['failed'], 1)
        self.assertEqual(stats['published_24h'], 1)

    def test_unpublished_matches_count(self):
        """Verifica conteggio partite senza alcun report pubblicato."""
        Match.objects.create(league=self.league, home_team=self.team, away_team=self.team, match_date=timezone.now())
        # Total matches: 2. One has a published report (from test_kpi_counts if combined, but tests are separate).
        # In this clean test:
        self.assertEqual(Match.objects.exclude(reports__status='PUBLISHED').distinct().count(), 2)

        self.client.login(username="admin_user", password="password")
        response = self.client.get(reverse('ops_cockpit'))
        self.assertEqual(response.context['matches_no_report'], 2)

    def test_lists_rendering(self):
        """Verifica che le liste oldest/latest siano presenti nel contesto."""
        self.client.login(username="admin_user", password="password")
        response = self.client.get(reverse('ops_cockpit'))
        self.assertIn('oldest_unpublished', response.context)
        self.assertIn('latest_published', response.context)
