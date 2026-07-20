"""
Test della coda OCR DB-backed e del worker (Macro 22).

Nessuna chiamata al provider reale: si usa MockVisionProvider o uno stub locale.
"""
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import League, Season, Society, Sport, Team
from management.models import Membership
from matches.models import Match, MatchReport, MatchReportAuditLog
from matches.services.ocr_queue import OCRQueueService
from matches.services.ocr_service import OCRService
from matches.services.vision_providers import MockVisionProvider

User = get_user_model()


class _BoomProvider:
    """Provider che simula un errore tecnico (5xx / timeout / rete)."""

    def __init__(self, message="Gemini 503 Service Unavailable"):
        self.message = message
        self.calls = 0

    def extract_data(self, match_report):
        self.calls += 1
        raise RuntimeError(self.message)


class _StubProvider:
    """
    Provider di test con payload fisso. A differenza di MockVisionProvider non
    dereferenzia `match_report.match`, quindi regge i referti senza match
    collegato (stesso stub di tests_ocr_no_match).
    """

    def __init__(self, home="Fantasma Casa", away="Fantasma Ospite"):
        self._data = {
            "metadata": {
                "schema_version": "2.0", "confidence": 0.95,
                "confidence_fields": {"home_team": 0.99, "away_team": 0.99, "final_score": 0.99},
                "extraction_warnings": [],
            },
            "match_info": {"home_team": home, "away_team": away, "date": None},
            "officials": {"confidence": 0.8, "referees": [], "timekeeper": None},
            "scores": {"final_score": "10-8", "quarters": {"1": [3, 2], "2": [2, 2], "3": [3, 2], "4": [2, 2]}},
            "teams": {
                "home": {"name": home, "players": [{"number": 1, "name": "Rossi"}]},
                "away": {"name": away, "players": [{"number": 1, "name": "Bianchi"}]},
            },
            "events": [],
        }

    def extract_data(self, match_report):
        return self._data, json.dumps(self._data)


class OCRQueueBaseTestCase(TestCase):
    def setUp(self):
        OCRService.set_provider(MockVisionProvider())
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto-q")
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.league = League.objects.create(name="Serie A1", sport=self.sport, slug="a1-q")
        self.soc_home = Society.objects.create(name="Pro Recco", sport=self.sport, slug="recco-q")
        self.soc_away = Society.objects.create(name="AN Brescia", sport=self.sport, slug="brescia-q")
        self.team_home = Team.objects.create(society=self.soc_home, league=self.league)
        self.team_away = Team.objects.create(society=self.soc_away, league=self.league)
        self.uploader = User.objects.create_user(username="uploader-q", role="athlete")
        self.match = Match.objects.create(
            league=self.league, home_team=self.team_home, away_team=self.team_away,
            match_date=timezone.now(), home_score=8, away_score=6,
        )

    def tearDown(self):
        OCRService._provider = None

    def _report(self, **kwargs):
        defaults = dict(
            match=self.match, uploader=self.uploader, status=MatchReport.Status.UPLOADED,
            file=SimpleUploadedFile("referto.pdf", b"pdf", content_type="application/pdf"),
        )
        defaults.update(kwargs)
        return MatchReport.objects.create(**defaults)


class EnqueueTests(OCRQueueBaseTestCase):
    def test_enqueue_moves_uploaded_to_queued_with_audit(self):
        report = self._report()

        self.assertTrue(OCRService.enqueue(report, user=self.uploader))

        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.QUEUED)
        self.assertIsNotNone(report.ocr_queued_at)
        self.assertIsNone(report.ocr_next_attempt_at)
        self.assertEqual(report.ocr_attempts, 0)
        log = MatchReportAuditLog.objects.get(report=report, action='enqueue')
        self.assertEqual(log.old_status, MatchReport.Status.UPLOADED)
        self.assertEqual(log.new_status, MatchReport.Status.QUEUED)

    def test_enqueue_allowed_from_rejected_and_needs_review(self):
        for state in (MatchReport.Status.REJECTED, MatchReport.Status.NEEDS_REVIEW):
            report = self._report(status=state)
            self.assertTrue(OCRService.enqueue(report), state)
            report.refresh_from_db()
            self.assertEqual(report.status, MatchReport.Status.QUEUED)

    def test_enqueue_refused_from_non_enqueueable_states(self):
        for state in (MatchReport.Status.QUEUED, MatchReport.Status.PROCESSING,
                      MatchReport.Status.EXTRACTED, MatchReport.Status.PUBLISHED):
            report = self._report(status=state)
            self.assertFalse(OCRService.enqueue(report), state)
            report.refresh_from_db()
            self.assertEqual(report.status, state)

    def test_enqueue_without_file_rejects_immediately(self):
        # Fail veloce sincrono: e' l'unico errore che ha senso mostrare subito.
        report = MatchReport.objects.create(
            match=self.match, uploader=self.uploader, source_channel='FILE',
            status=MatchReport.Status.UPLOADED,
        )

        self.assertFalse(OCRService.enqueue(report))

        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.REJECTED)
        self.assertIn("Nessun file associato", report.validation_notes)


class ClaimTests(OCRQueueBaseTestCase):
    def test_claim_is_atomic_only_one_winner(self):
        report = self._report()
        OCRService.enqueue(report)

        first = OCRQueueService.claim(report.pk)
        second = OCRQueueService.claim(report.pk)

        self.assertIsNotNone(first)
        self.assertIsNone(second, "il secondo claim sullo stesso referto deve perdere")
        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.PROCESSING)
        self.assertEqual(report.ocr_attempts, 1, "il tentativo si conta una sola volta")
        self.assertIsNotNone(report.ocr_started_at)

    def test_claim_refused_if_not_queued(self):
        report = self._report(status=MatchReport.Status.EXTRACTED)
        self.assertIsNone(OCRQueueService.claim(report.pk))

    def test_next_candidate_is_fifo_and_respects_backoff(self):
        old = self._report()
        OCRService.enqueue(old)
        MatchReport.objects.filter(pk=old.pk).update(ocr_queued_at=timezone.now() - timedelta(minutes=5))
        recent = self._report()
        OCRService.enqueue(recent)

        self.assertEqual(OCRQueueService.next_candidate_id(), old.pk)

        # Con un backoff in futuro, il piu' vecchio non e' eleggibile.
        MatchReport.objects.filter(pk=old.pk).update(
            ocr_next_attempt_at=timezone.now() + timedelta(minutes=1)
        )
        self.assertEqual(OCRQueueService.next_candidate_id(), recent.pk)

    def test_next_candidate_none_on_empty_queue(self):
        self._report()  # UPLOADED, mai accodato: il worker non deve prenderlo
        self.assertIsNone(OCRQueueService.next_candidate_id())


class WorkerTransitionTests(OCRQueueBaseTestCase):
    def test_worker_processes_queued_report_to_extracted(self):
        report = self._report()
        OCRService.enqueue(report)

        call_command('ocr_worker', '--once', '--no-startup-sweep')

        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.EXTRACTED)
        self.assertEqual(report.ocr_attempts, 1)
        self.assertTrue(report.normalized_data)

    def test_worker_leaves_untouched_reports_not_queued(self):
        report = self._report()  # UPLOADED

        call_command('ocr_worker', '--once', '--no-startup-sweep')

        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.UPLOADED)
        self.assertEqual(report.ocr_attempts, 0)

    def test_merit_failure_goes_to_needs_review_without_retry(self):
        # Referto senza match collegato: il quality gate blocca (path no-match).
        # E' un esito, non un errore: nessun retry, nessun backoff.
        OCRService.set_provider(_StubProvider())
        report = MatchReport.objects.create(
            match=None, source_channel='DIGITAL', status=MatchReport.Status.UPLOADED,
        )
        OCRService.enqueue(report)

        with patch('core.services.notification_service.NotificationService.notify_report_needs_review'):
            call_command('ocr_worker', '--once', '--no-startup-sweep')

        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.NEEDS_REVIEW)
        self.assertEqual(report.ocr_attempts, 1)
        self.assertIsNone(report.ocr_next_attempt_at, "un fallimento di merito non schedula retry")
        notes = json.loads(report.validation_notes)
        self.assertTrue(any("Nessun match collegato" in b for b in notes["blocking"]))

    def test_technical_error_schedules_retry_with_backoff(self):
        OCRService.set_provider(_BoomProvider())
        report = self._report()
        OCRService.enqueue(report)
        before = timezone.now()

        call_command('ocr_worker', '--once', '--no-startup-sweep')

        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.QUEUED, "torna in coda per il retry")
        self.assertEqual(report.ocr_attempts, 1)
        self.assertIn("503", report.ocr_error)
        # Primo backoff: 60s.
        self.assertGreaterEqual(report.ocr_next_attempt_at, before + timedelta(seconds=59))
        self.assertLessEqual(report.ocr_next_attempt_at, before + timedelta(seconds=75))
        self.assertTrue(MatchReportAuditLog.objects.filter(report=report, action='ocr_retry').exists())

    def test_retry_backoff_is_exponential_then_gives_up(self):
        OCRService.set_provider(_BoomProvider())
        report = self._report()
        OCRService.enqueue(report)

        with patch('core.services.notification_service.NotificationService.notify_report_needs_review') as notify:
            for expected_attempt in (1, 2, 3):
                # Azzera il backoff per rendere il referto subito eleggibile.
                MatchReport.objects.filter(pk=report.pk).update(ocr_next_attempt_at=None)
                call_command('ocr_worker', '--once', '--no-startup-sweep')
                report.refresh_from_db()
                self.assertEqual(report.ocr_attempts, expected_attempt)

            # Esauriti i 3 tentativi: NEEDS_REVIEW + notifica, niente piu' retry.
            self.assertEqual(report.status, MatchReport.Status.NEEDS_REVIEW)
            self.assertIsNone(report.ocr_next_attempt_at)
            self.assertEqual(notify.call_count, 1)
        self.assertTrue(MatchReportAuditLog.objects.filter(report=report, action='ocr_failed').exists())
        self.assertEqual(
            MatchReportAuditLog.objects.filter(report=report, action='ocr_retry').count(), 2,
            "due retry (60s, 120s) e poi la resa",
        )

    def test_second_backoff_is_120_seconds(self):
        OCRService.set_provider(_BoomProvider())
        report = self._report()
        OCRService.enqueue(report)

        call_command('ocr_worker', '--once', '--no-startup-sweep')
        MatchReport.objects.filter(pk=report.pk).update(ocr_next_attempt_at=None)
        before = timezone.now()
        call_command('ocr_worker', '--once', '--no-startup-sweep')

        report.refresh_from_db()
        self.assertEqual(report.ocr_attempts, 2)
        self.assertGreaterEqual(report.ocr_next_attempt_at, before + timedelta(seconds=119))
        self.assertLessEqual(report.ocr_next_attempt_at, before + timedelta(seconds=135))


class StartupSweepTests(OCRQueueBaseTestCase):
    def test_startup_sweep_requeues_orphan_processing(self):
        report = self._report(status=MatchReport.Status.PROCESSING)
        MatchReport.objects.filter(pk=report.pk).update(ocr_attempts=1, ocr_started_at=timezone.now())

        requeued, exhausted = OCRQueueService.requeue_stale(older_than_minutes=None)

        self.assertEqual(requeued, [report.pk])
        self.assertEqual(exhausted, [])
        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.QUEUED)
        self.assertIsNone(report.ocr_started_at)
        self.assertTrue(MatchReportAuditLog.objects.filter(report=report, action='ocr_stale_requeue').exists())

    def test_startup_sweep_gives_up_when_attempts_exhausted(self):
        report = self._report(status=MatchReport.Status.PROCESSING)
        MatchReport.objects.filter(pk=report.pk).update(
            ocr_attempts=OCRQueueService.MAX_ATTEMPTS, ocr_started_at=timezone.now()
        )

        with patch('core.services.notification_service.NotificationService.notify_report_needs_review') as notify:
            requeued, exhausted = OCRQueueService.requeue_stale(older_than_minutes=None)

        self.assertEqual(exhausted, [report.pk])
        self.assertEqual(requeued, [])
        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.NEEDS_REVIEW)
        self.assertEqual(notify.call_count, 1)

    def test_sweep_with_threshold_ignores_fresh_processing(self):
        fresh = self._report(status=MatchReport.Status.PROCESSING)
        MatchReport.objects.filter(pk=fresh.pk).update(ocr_started_at=timezone.now())

        requeued, exhausted = OCRQueueService.requeue_stale(older_than_minutes=OCRQueueService.STALE_MINUTES)

        self.assertEqual((requeued, exhausted), ([], []))
        fresh.refresh_from_db()
        self.assertEqual(fresh.status, MatchReport.Status.PROCESSING)

    def test_worker_runs_startup_sweep_then_processes(self):
        orphan = self._report(status=MatchReport.Status.PROCESSING)
        MatchReport.objects.filter(pk=orphan.pk).update(ocr_attempts=1, ocr_started_at=timezone.now())

        call_command('ocr_worker', '--once')

        orphan.refresh_from_db()
        # Riaccodato dalla sweep e poi elaborato nello stesso giro.
        self.assertEqual(orphan.status, MatchReport.Status.EXTRACTED)
        self.assertEqual(orphan.ocr_attempts, 2)


class UploadAndAdminEntryPointTests(OCRQueueBaseTestCase):
    def test_upload_view_enqueues_without_running_ocr(self):
        staff = User.objects.create_user(
            username="staff-q", is_staff=True, is_superuser=True,
            identity_status='VERIFIED', onboarding_payment_done=True,
        )
        self.client.force_login(staff)

        with patch('matches.services.ocr_service.OCRService.process_claimed') as processed:
            response = self.client.post(
                f"/matches/{self.match.id}/upload-report/",
                {'file': SimpleUploadedFile("r.pdf", b"x", content_type="application/pdf")},
            )

        report = MatchReport.objects.filter(match=self.match).latest('created_at')
        self.assertRedirects(response, reverse('report_review', kwargs={'report_id': report.id}))
        self.assertEqual(report.status, MatchReport.Status.QUEUED)
        processed.assert_not_called()

    def test_admin_action_enqueues(self):
        from django.contrib.admin.sites import AdminSite
        from matches.admin import MatchReportAdmin

        report = self._report()
        admin_instance = MatchReportAdmin(MatchReport, AdminSite())
        request = type('R', (), {'user': self.uploader})()
        messages_seen = []
        admin_instance.message_user = lambda req, msg, level=None: messages_seen.append(msg)

        with patch('matches.services.ocr_service.OCRService.process_claimed') as processed:
            admin_instance.process_ocr(request, MatchReport.objects.filter(pk=report.pk))

        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.QUEUED)
        processed.assert_not_called()
        self.assertIn("Accodati: 1", messages_seen[0])


class ReportStatusEndpointTests(OCRQueueBaseTestCase):
    def setUp(self):
        super().setUp()
        self.report = self._report()
        OCRService.enqueue(self.report)
        self.report.refresh_from_db()
        self.url = reverse('api_report_status', kwargs={'report_id': self.report.id})

    def test_payload_shape_while_queued(self):
        self.client.force_login(self.uploader)

        data = self.client.get(self.url).json()

        self.assertEqual(data['report_id'], self.report.id)
        self.assertEqual(data['status'], 'QUEUED')
        self.assertEqual(data['status_display'], 'In Coda OCR')
        self.assertFalse(data['is_final'])
        self.assertIsNotNone(data['queued_at'])
        self.assertIsNone(data['started_at'])
        self.assertEqual(data['attempts'], 0)
        self.assertNotIn('validation_notes', data)

    def test_is_final_false_while_processing_true_when_done(self):
        self.client.force_login(self.uploader)
        OCRQueueService.claim(self.report.pk)

        data = self.client.get(self.url).json()
        self.assertEqual(data['status'], 'PROCESSING')
        self.assertFalse(data['is_final'])
        self.assertIsNotNone(data['started_at'])
        self.assertEqual(data['attempts'], 1)

        MatchReport.objects.filter(pk=self.report.pk).update(status=MatchReport.Status.EXTRACTED)
        data = self.client.get(self.url).json()
        self.assertEqual(data['status'], 'EXTRACTED')
        self.assertTrue(data['is_final'])

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_uploader_superuser_staff_and_referee_are_allowed(self):
        allowed = [
            self.uploader,
            User.objects.create_user(username="root-q", is_superuser=True, role="athlete"),
            User.objects.create_user(username="staffrole-q", role="athlete", staff_role='UPLOADER'),
            User.objects.create_user(username="ref-q", role="referee"),
        ]
        for user in allowed:
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 200, user.username)

    def test_president_and_head_coach_of_involved_team_are_allowed(self):
        for username, role, team in [
            ("pres-q", "PRESIDENT", self.team_home),
            ("coach-q", "HEAD_COACH", self.team_away),
        ]:
            user = User.objects.create_user(username=username, role="coach")
            Membership.objects.create(
                user=user, society=team.society, team=team, role=role,
                season=self.season, is_active=True,
            )
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 200, username)

    def test_unrelated_user_gets_403(self):
        stranger = User.objects.create_user(username="stranger-q", role="athlete")
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_missing_report_gets_404(self):
        self.client.force_login(self.uploader)
        url = reverse('api_report_status', kwargs={'report_id': 999999})
        self.assertEqual(self.client.get(url).status_code, 404)
