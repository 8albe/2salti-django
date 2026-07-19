from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from matches.models import Match, MatchReport
from core.models import Season, Sport, Society, Team, League

User = get_user_model()


class MatchReportAdminChangeformTest(TestCase):
    """La changeform admin di MatchReport non deve crashare quando 'match'
    è readonly (ogni change view) e quindi assente dal form."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.society_h = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco")
        self.society_a = Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia")

        self.league = League.objects.create(name="Serie A1", sport=self.sport, season="2024", slug="serie-a1")

        self.team_h = Team.objects.create(society=self.society_h, league=self.league)
        self.team_a = Team.objects.create(society=self.society_a, league=self.league)

        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_h,
            away_team=self.team_a,
            match_date=timezone.now(),
            location="Sori"
        )

        self.admin_user = User.objects.create_superuser(username='admin', password='password', email='admin@test.com')
        self.client = Client()
        self.client.login(username='admin', password='password')

    def test_change_view_with_match_readonly_returns_200(self):
        """Change view di un report esistente: 'match' è readonly e assente
        dal form → prima del fix la GET esplodeva con KeyError ('match')."""
        report = MatchReport.objects.create(
            match=self.match,
            status=MatchReport.Status.EXTRACTED,
        )
        url = reverse('admin:matches_matchreport_change', args=[report.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_change_view_orphan_report_returns_200(self):
        """Change view di un report senza match associato (discovery pendente)."""
        report = MatchReport.objects.create(
            match=None,
            status=MatchReport.Status.NEEDS_REVIEW,
        )
        url = reverse('admin:matches_matchreport_change', args=[report.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_add_view_with_match_editable_returns_200(self):
        """Add view: 'match' è editabile e presente nel form, non required."""
        url = reverse('admin:matches_matchreport_add')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        form = response.context['adminform'].form
        self.assertIn('match', form.fields)
        self.assertFalse(form.fields['match'].required)
