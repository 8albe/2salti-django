"""
Regressione della review page front-office (`report_review`) su TUTTI gli stati
di MatchReport, con e senza partita collegata.

Origine (2026-07-19, Macro 22 giro 1): l'upload asincrono redirige sulla review
page mentre il referto e' ancora QUEUED e non ha ancora una partita collegata.
La view dereferenziava `report.match` senza guardia -> AttributeError e 500.
La suite passava perche' nessun test esercitava la review page senza match.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import League, Season, Society, Sport, Team
from matches.models import Match, MatchReport

User = get_user_model()

ALL_STATUSES = [s for s, _ in MatchReport.Status.choices]


class ReportReviewStatesTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.league = League.objects.create(
            name="Serie A1", sport=self.sport, season="2024", slug="serie-a1"
        )
        soc_h = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco")
        soc_a = Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia")
        self.team_h = Team.objects.create(society=soc_h, league=self.league)
        self.team_a = Team.objects.create(society=soc_a, league=self.league)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_h,
            away_team=self.team_a,
            match_date=timezone.now(),
            location="Sori",
        )

        self.admin = User.objects.create_superuser(
            username='admin', password='password', email='admin@test.com'
        )
        self.admin.identity_status = 'VERIFIED'
        self.admin.save()

        self.client = Client()
        self.client.login(username='admin', password='password')

    def _url(self, report):
        return reverse('report_review', args=[report.id])

    # --- GET: nessuna partita collegata (il caso che produceva il 500) ---

    def test_get_queued_report_without_match_renders(self):
        """QUEUED + match=None: e' lo stato subito dopo l'upload asincrono."""
        report = MatchReport.objects.create(match=None, status=MatchReport.Status.QUEUED)
        response = self.client.get(self._url(report))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['match'], None)

    def test_get_all_statuses_without_match_render(self):
        """Nessuno stato del modello deve rompere la review page senza match."""
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                report = MatchReport.objects.create(match=None, status=status)
                response = self.client.get(self._url(report))
                self.assertEqual(response.status_code, 200)

    def test_get_all_statuses_with_match_render(self):
        """Stessa copertura con partita collegata (incluso il nuovo QUEUED)."""
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                report = MatchReport.objects.create(match=self.match, status=status)
                response = self.client.get(self._url(report))
                self.assertEqual(response.status_code, 200)

    # --- initial dello stato nella form di revisione ---

    def test_transient_statuses_are_normalized_to_extracted(self):
        """QUEUED e PROCESSING non sono esiti: la form propone EXTRACTED."""
        for status in [MatchReport.Status.QUEUED, MatchReport.Status.PROCESSING]:
            with self.subTest(status=status):
                report = MatchReport.objects.create(match=self.match, status=status)
                response = self.client.get(self._url(report))
                self.assertEqual(
                    response.context['form'].initial['report_status'],
                    MatchReport.Status.EXTRACTED,
                )

    def test_final_statuses_keep_their_value_in_initial(self):
        """Ogni altro stato passa inalterato: lookup con default, mai nudo."""
        transient = {MatchReport.Status.QUEUED, MatchReport.Status.PROCESSING}
        for status in [s for s in ALL_STATUSES if s not in transient]:
            with self.subTest(status=status):
                report = MatchReport.objects.create(match=self.match, status=status)
                response = self.client.get(self._url(report))
                self.assertEqual(
                    response.context['form'].initial['report_status'], status
                )

    # --- POST senza partita collegata ---

    def test_post_without_match_is_refused_with_message(self):
        """Salvare punteggi senza partita non ha senso: messaggio, non 500."""
        report = MatchReport.objects.create(match=None, status=MatchReport.Status.NEEDS_REVIEW)
        post_data = {
            'home_score': 5, 'away_score': 3, 'report_status': MatchReport.Status.VALIDATED,
            'home_q1': 5, 'home_q2': 0, 'home_q3': 0, 'home_q4': 0,
            'away_q1': 3, 'away_q2': 0, 'away_q3': 0, 'away_q4': 0,
        }
        response = self.client.post(self._url(report), post_data)
        self.assertRedirects(response, self._url(report))
        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.NEEDS_REVIEW)

    def test_post_link_match_attaches_the_match(self):
        """Il percorso corretto per un referto orfano: collegare la partita."""
        report = MatchReport.objects.create(match=None, status=MatchReport.Status.NEEDS_REVIEW)
        response = self.client.post(
            self._url(report), {'_action': 'link_match', 'selected_match_id': self.match.id}
        )
        self.assertRedirects(response, self._url(report))
        report.refresh_from_db()
        self.assertEqual(report.match_id, self.match.id)


class OpsCockpitQueuedKpiTest(TestCase):
    """`in_flight` del cockpit deve contare anche i referti QUEUED."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='ops', password='password', email='ops@test.com'
        )
        self.admin.identity_status = 'VERIFIED'
        self.admin.save()
        self.client = Client()
        self.client.login(username='ops', password='password')

    def test_queued_report_counts_as_in_flight(self):
        MatchReport.objects.create(match=None, status=MatchReport.Status.QUEUED)
        MatchReport.objects.create(match=None, status=MatchReport.Status.PROCESSING)
        MatchReport.objects.create(match=None, status=MatchReport.Status.UPLOADED)
        response = self.client.get(reverse('ops_cockpit'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['stats']['in_flight'], 3)
