import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from core.models import Sport, Society, League, Team
from matches.models import Match, MatchReport, MatchReportAuditLog, MatchJuryLink
from matches.services.jury_link_service import JuryLinkService

User = get_user_model()


def valid_digital_payload(home="Pro Recco", away="AN Brescia"):
    return {
        "metadata": {"version": "2.0", "confidence": 1.0, "source": "digital_app"},
        "match_info": {"home_team": home, "away_team": away, "date": "2026-07-19", "city": "Genova"},
        "scores": {"final_score": "0-0", "quarters": {}},
        "teams": {"home": {"players": []}, "away": {"players": []}},
        "events": [],
    }


class JuryBaseTestCase(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto-jury")
        self.society_h = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco-jury")
        self.society_a = Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia-jury")
        self.league = League.objects.create(name="Serie A1", sport=self.sport, slug="serie-a1-jury")
        self.team_h = Team.objects.create(society=self.society_h, league=self.league)
        self.team_a = Team.objects.create(society=self.society_a, league=self.league)
        self.match = Match.objects.create(
            league=self.league, home_team=self.team_h, away_team=self.team_a,
            match_date=timezone.now(),
        )
        # Un secondo match per i test di "match sbagliato".
        self.other_match = Match.objects.create(
            league=self.league, home_team=self.team_a, away_team=self.team_h,
            match_date=timezone.now(),
        )

        self.uploader = User.objects.create_user(
            username="uploader_j", password="pw-test-123", role="fan", staff_role="UPLOADER"
        )
        self.plain_user = User.objects.create_user(
            username="plain_j", password="pw-test-123", role="fan"
        )
        self.superuser = User.objects.create_superuser(
            username="admin_j", email="admin_j@test.com", password="pw-test-123"
        )


# ---------------------------------------------------------------------------
# Ciclo di vita del modello / service
# ---------------------------------------------------------------------------
class JuryLinkLifecycleTestCase(JuryBaseTestCase):
    def test_issue_creates_active_link_with_backstop_expiry(self):
        link = JuryLinkService.issue(self.match, created_by=self.uploader)
        self.assertEqual(link.status, MatchJuryLink.Status.ACTIVE)
        self.assertEqual(link.created_by, self.uploader)
        self.assertTrue(link.token)
        self.assertGreaterEqual(len(link.token), 32)
        delta = link.expires_at - link.created_at
        self.assertAlmostEqual(delta.total_seconds(), timedelta(days=7).total_seconds(), delta=5)
        self.assertTrue(link.is_valid())

    def test_issue_revokes_previous_active(self):
        first = JuryLinkService.issue(self.match, created_by=self.uploader)
        second = JuryLinkService.issue(self.match, created_by=self.uploader)

        first.refresh_from_db()
        self.assertEqual(first.status, MatchJuryLink.Status.REVOKED)
        self.assertIsNotNone(first.revoked_at)
        self.assertEqual(second.status, MatchJuryLink.Status.ACTIVE)

        active = MatchJuryLink.objects.filter(match=self.match, status=MatchJuryLink.Status.ACTIVE)
        self.assertEqual(active.count(), 1)

    def test_only_one_active_per_match_constraint(self):
        from django.db import IntegrityError
        JuryLinkService.issue(self.match, created_by=self.uploader)
        # Bypassa il service e forza un secondo ACTIVE a mano -> il partial
        # unique index deve rifiutarlo.
        with self.assertRaises(IntegrityError):
            MatchJuryLink.objects.create(
                match=self.match, token="dup-active-token",
                status=MatchJuryLink.Status.ACTIVE,
                expires_at=timezone.now() + timedelta(days=7),
            )

    def test_revoke_sets_revoked(self):
        JuryLinkService.issue(self.match, created_by=self.uploader)
        n = JuryLinkService.revoke(self.match)
        self.assertEqual(n, 1)
        self.assertFalse(
            MatchJuryLink.objects.filter(match=self.match, status=MatchJuryLink.Status.ACTIVE).exists()
        )

    def test_resolve_valid_token(self):
        link = JuryLinkService.issue(self.match, created_by=self.uploader)
        resolved = JuryLinkService.resolve(link.token, match=self.match)
        self.assertEqual(resolved.id, link.id)

    def test_resolve_wrong_match_returns_none(self):
        link = JuryLinkService.issue(self.match, created_by=self.uploader)
        self.assertIsNone(JuryLinkService.resolve(link.token, match=self.other_match))

    def test_resolve_revoked_returns_none(self):
        link = JuryLinkService.issue(self.match, created_by=self.uploader)
        JuryLinkService.revoke(self.match)
        self.assertIsNone(JuryLinkService.resolve(link.token, match=self.match))

    def test_resolve_expired_lazily_marks_expired(self):
        link = JuryLinkService.issue(self.match, created_by=self.uploader)
        # Forza la scadenza nel passato.
        MatchJuryLink.objects.filter(pk=link.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertIsNone(JuryLinkService.resolve(link.token, match=self.match))
        link.refresh_from_db()
        self.assertEqual(link.status, MatchJuryLink.Status.EXPIRED)

    def test_resolve_unknown_token_returns_none(self):
        self.assertIsNone(JuryLinkService.resolve("does-not-exist"))
        self.assertIsNone(JuryLinkService.resolve(""))


# ---------------------------------------------------------------------------
# Endpoint di emissione / revoca
# ---------------------------------------------------------------------------
class JuryLinkIssueEndpointTestCase(JuryBaseTestCase):
    def setUp(self):
        super().setUp()
        self.issue_url = reverse('api_jury_link_issue', args=[self.match.id])
        self.revoke_url = reverse('api_jury_link_revoke', args=[self.match.id])

    def test_issue_by_staff_returns_url_and_expiry(self):
        self.client.force_login(self.uploader)
        response = self.client.post(self.issue_url)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['match_id'], self.match.id)
        self.assertIn(f"/r/{data['token']}/", data['url'])
        self.assertEqual(data['status'], MatchJuryLink.Status.ACTIVE)
        self.assertIn('expires_at', data)

        link = MatchJuryLink.objects.get(token=data['token'])
        self.assertEqual(link.created_by, self.uploader)

    def test_issue_forbidden_for_plain_user(self):
        self.client.force_login(self.plain_user)
        response = self.client.post(self.issue_url)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(MatchJuryLink.objects.filter(match=self.match).exists())

    def test_issue_forbidden_for_anonymous(self):
        response = self.client.post(self.issue_url)
        self.assertIn(response.status_code, (302, 401, 403))
        self.assertFalse(MatchJuryLink.objects.filter(match=self.match).exists())

    def test_issue_replaces_previous_active(self):
        self.client.force_login(self.superuser)
        first = self.client.post(self.issue_url).json()
        second = self.client.post(self.issue_url).json()
        self.assertNotEqual(first['token'], second['token'])
        self.assertEqual(
            MatchJuryLink.objects.filter(match=self.match, status=MatchJuryLink.Status.ACTIVE).count(), 1
        )

    def test_revoke_endpoint(self):
        self.client.force_login(self.uploader)
        self.client.post(self.issue_url)
        response = self.client.post(self.revoke_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['revoked'], 1)
        self.assertFalse(
            MatchJuryLink.objects.filter(match=self.match, status=MatchJuryLink.Status.ACTIVE).exists()
        )


# ---------------------------------------------------------------------------
# Landing pubblica /r/{token}
# ---------------------------------------------------------------------------
class JuryLandingTestCase(JuryBaseTestCase):
    def test_landing_valid_token(self):
        link = JuryLinkService.issue(self.match, created_by=self.uploader)
        response = self.client.get(reverse('jury_link_landing', args=[link.token]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['match']['id'], self.match.id)
        self.assertEqual(data['status'], MatchJuryLink.Status.ACTIVE)
        self.assertIsNone(data['draft_report_id'])

    def test_landing_surfaces_existing_draft(self):
        link = JuryLinkService.issue(self.match, created_by=self.uploader)
        draft = MatchReport.objects.create(
            match=self.match, source_channel='DIGITAL', status=MatchReport.Status.DRAFT,
            raw_extracted_data=valid_digital_payload(),
        )
        response = self.client.get(reverse('jury_link_landing', args=[link.token]))
        self.assertEqual(response.json()['draft_report_id'], draft.id)

    def test_landing_unknown_token_404(self):
        response = self.client.get(reverse('jury_link_landing', args=['nope']))
        self.assertEqual(response.status_code, 404)

    def test_landing_revoked_token_410(self):
        link = JuryLinkService.issue(self.match, created_by=self.uploader)
        JuryLinkService.revoke(self.match)
        response = self.client.get(reverse('jury_link_landing', args=[link.token]))
        self.assertEqual(response.status_code, 410)

    def test_landing_expired_token_410(self):
        link = JuryLinkService.issue(self.match, created_by=self.uploader)
        MatchJuryLink.objects.filter(pk=link.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        response = self.client.get(reverse('jury_link_landing', args=[link.token]))
        self.assertEqual(response.status_code, 410)
        link.refresh_from_db()
        self.assertEqual(link.status, MatchJuryLink.Status.EXPIRED)


# ---------------------------------------------------------------------------
# Accesso via token alle tre API digitali
# ---------------------------------------------------------------------------
class JuryTokenAccessTestCase(JuryBaseTestCase):
    def setUp(self):
        super().setUp()
        self.link = JuryLinkService.issue(self.match, created_by=self.uploader)
        self.start_url = reverse('api_digital_report_start')

    def _start_with_token(self, token, match_id=None):
        return self.client.post(
            self.start_url,
            data=json.dumps({"match_id": match_id or self.match.id}),
            content_type='application/json',
            HTTP_X_JURY_TOKEN=token,
        )

    def test_start_via_valid_token_creates_no_account_draft(self):
        response = self._start_with_token(self.link.token)
        self.assertEqual(response.status_code, 201)
        report = MatchReport.objects.get(id=response.json()['id'])
        self.assertEqual(report.status, MatchReport.Status.DRAFT)
        self.assertIsNone(report.uploader)  # nessun account

        log = MatchReportAuditLog.objects.get(report=report, action='create_digital')
        self.assertIsNone(log.user)  # azione tracciata come proveniente dal link
        self.assertIn('link giuria', log.reason)

    def test_start_via_expired_token_forbidden(self):
        MatchJuryLink.objects.filter(pk=self.link.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        response = self._start_with_token(self.link.token)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(MatchReport.objects.filter(match=self.match).exists())

    def test_start_via_revoked_token_forbidden(self):
        JuryLinkService.revoke(self.match)
        response = self._start_with_token(self.link.token)
        self.assertEqual(response.status_code, 403)

    def test_start_via_token_wrong_match_forbidden(self):
        # Token valido ma per un match diverso da quello richiesto.
        response = self._start_with_token(self.link.token, match_id=self.other_match.id)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(MatchReport.objects.filter(match=self.other_match).exists())

    def test_start_without_token_anonymous_forbidden(self):
        response = self.client.post(
            self.start_url,
            data=json.dumps({"match_id": self.match.id}),
            content_type='application/json',
        )
        self.assertIn(response.status_code, (302, 401, 403))
        self.assertFalse(MatchReport.objects.filter(match=self.match).exists())

    def test_update_via_token(self):
        report = MatchReport.objects.get(id=self._start_with_token(self.link.token).json()['id'])
        update_url = reverse('api_digital_report_update', args=[report.id])
        payload = valid_digital_payload()
        payload['scores']['final_score'] = "7-5"
        response = self.client.put(
            update_url,
            data=json.dumps({"data": payload}),
            content_type='application/json',
            HTTP_X_JURY_TOKEN=self.link.token,
        )
        self.assertEqual(response.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.raw_extracted_data['scores']['final_score'], "7-5")
        # Azione via link tracciata con user=None.
        log = MatchReportAuditLog.objects.get(report=report, action='update_digital')
        self.assertIsNone(log.user)

    def test_update_via_wrong_match_token_forbidden(self):
        report = MatchReport.objects.get(id=self._start_with_token(self.link.token).json()['id'])
        other_link = JuryLinkService.issue(self.other_match)
        update_url = reverse('api_digital_report_update', args=[report.id])
        response = self.client.put(
            update_url,
            data=json.dumps({"data": valid_digital_payload()}),
            content_type='application/json',
            HTTP_X_JURY_TOKEN=other_link.token,
        )
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# Close via token: firma, NEEDS_REVIEW, consume, idempotenza
# ---------------------------------------------------------------------------
class JuryCloseTestCase(JuryBaseTestCase):
    def setUp(self):
        super().setUp()
        self.link = JuryLinkService.issue(self.match, created_by=self.uploader)
        self.start_url = reverse('api_digital_report_start')
        start = self.client.post(
            self.start_url,
            data=json.dumps({"match_id": self.match.id}),
            content_type='application/json',
            HTTP_X_JURY_TOKEN=self.link.token,
        )
        self.report = MatchReport.objects.get(id=start.json()['id'])
        self.report.raw_extracted_data = valid_digital_payload()
        self.report.save()
        self.close_url = reverse('api_digital_report_close', args=[self.report.id])

    def _close(self, token, signature="Mario Rossi"):
        payload = {} if signature is None else {"signature": signature}
        return self.client.post(
            self.close_url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_JURY_TOKEN=token,
        )

    def test_close_via_token_needs_review_and_consumes_link(self):
        response = self._close(self.link.token)
        self.assertEqual(response.status_code, 200)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MatchReport.Status.NEEDS_REVIEW)
        self.assertNotEqual(self.report.status, MatchReport.Status.PUBLISHED)
        self.assertEqual(self.report.referee_signature, "Mario Rossi")

        self.link.refresh_from_db()
        self.assertEqual(self.link.status, MatchJuryLink.Status.CONSUMED)
        self.assertIsNotNone(self.link.consumed_at)
        self.assertEqual(self.link.report_id, self.report.id)

        log = MatchReportAuditLog.objects.get(report=self.report, action='close_digital')
        self.assertIsNone(log.user)
        self.assertIn('link giuria', log.reason)

    def test_close_via_token_requires_signature(self):
        response = self._close(self.link.token, signature=None)
        self.assertEqual(response.status_code, 400)
        # Fallito il close, il link resta ACTIVE (consume solo su close riuscito).
        self.link.refresh_from_db()
        self.assertEqual(self.link.status, MatchJuryLink.Status.ACTIVE)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MatchReport.Status.DRAFT)

    def test_double_close_via_token_rejected(self):
        first = self._close(self.link.token)
        self.assertEqual(first.status_code, 200)
        second = self._close(self.link.token)
        # Dopo il primo close il link e' CONSUMED: non risolve piu', quindi il
        # secondo tentativo via lo stesso token e' respinto in autenticazione
        # (403) prima ancora della guardia di stato. Il link morto non riapre.
        self.assertEqual(second.status_code, 403)
        close_logs = MatchReportAuditLog.objects.filter(report=self.report, action='close_digital')
        self.assertEqual(close_logs.count(), 1)

    def test_authenticated_close_consumes_outstanding_link(self):
        # Uno staff chiude via login un referto che ha ancora un link ACTIVE:
        # il link muore comunque alla chiusura.
        self.client.force_login(self.uploader)
        # Il report ha uploader=None; can_review dell'uploader e' False -> serve
        # un reviewer o superuser. Uso il superuser per il close autenticato.
        self.client.force_login(self.superuser)
        response = self.client.post(
            self.close_url,
            data=json.dumps({"signature": "Anna Bianchi"}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.link.refresh_from_db()
        self.assertEqual(self.link.status, MatchJuryLink.Status.CONSUMED)
        self.assertEqual(self.link.report_id, self.report.id)
