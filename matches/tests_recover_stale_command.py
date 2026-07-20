"""
Test del backstop `recover_stale_reports` (Macro 22, giro 2).

Copre la semantica ratificata del requeue *capped* e — punto non ovvio — il
fatto che il comando condivida il code path con la sweep di avvio del worker
invece di reimplementarlo. Due implementazioni della stessa regola divergono
al primo cambio, e la divergenza qui significherebbe referti trattati in modo
diverso a seconda di chi li recupera.
"""
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from matches.models import MatchReport, MatchReportAuditLog
from matches.services.ocr_queue import OCRQueueService

Status = MatchReport.Status


class RecoverStaleReportsCommandTest(TestCase):
    def _processing(self, minutes_ago, attempts=1):
        """Referto in PROCESSING claimato `minutes_ago` minuti fa."""
        return MatchReport.objects.create(
            match=None,
            status=Status.PROCESSING,
            ocr_started_at=timezone.now() - timedelta(minutes=minutes_ago),
            ocr_attempts=attempts,
        )

    def _run(self, **kwargs):
        out = StringIO()
        call_command('recover_stale_reports', stdout=out, stderr=out, **kwargs)
        return out.getvalue()

    # --- requeue sotto il cap ---------------------------------------------

    def test_stale_report_under_the_cap_goes_back_to_queued(self):
        report = self._processing(minutes_ago=30, attempts=1)

        output = self._run()

        report.refresh_from_db()
        self.assertEqual(report.status, Status.QUEUED)
        self.assertIsNone(report.ocr_started_at)
        self.assertIsNotNone(report.ocr_next_attempt_at)
        self.assertIn(str(report.pk), output)

    def test_requeue_is_immediate_not_backed_off(self):
        """
        Un orfano non ha *fallito*: il worker e' morto sotto. Deve ripartire
        subito, non dopo il backoff previsto per gli errori tecnici.
        """
        before = timezone.now()
        report = self._processing(minutes_ago=30, attempts=1)

        self._run()

        report.refresh_from_db()
        self.assertGreaterEqual(report.ocr_next_attempt_at, before)
        self.assertLessEqual(report.ocr_next_attempt_at, timezone.now())

    def test_requeue_writes_the_stale_requeue_audit_entry(self):
        report = self._processing(minutes_ago=30, attempts=1)

        self._run()

        entry = MatchReportAuditLog.objects.get(report=report)
        self.assertEqual(entry.action, 'ocr_stale_requeue')
        self.assertEqual(entry.old_status, Status.PROCESSING)
        self.assertEqual(entry.new_status, Status.QUEUED)

    def test_attempts_are_not_incremented_by_the_recovery(self):
        """I tentativi si contano al claim, non al recupero: qui non si tocca."""
        report = self._processing(minutes_ago=30, attempts=1)

        self._run()

        report.refresh_from_db()
        self.assertEqual(report.ocr_attempts, 1)

    # --- oltre il cap ------------------------------------------------------

    def test_stale_report_at_the_cap_goes_to_needs_review_and_notifies(self):
        report = self._processing(minutes_ago=30, attempts=OCRQueueService.MAX_ATTEMPTS)

        with patch(
            'core.services.notification_service.NotificationService.notify_report_needs_review'
        ) as notify:
            self._run()

        report.refresh_from_db()
        self.assertEqual(report.status, Status.NEEDS_REVIEW)
        self.assertIsNone(report.ocr_started_at)
        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[0].pk, report.pk)

    def test_exhausted_report_gets_the_failed_audit_entry(self):
        report = self._processing(minutes_ago=30, attempts=OCRQueueService.MAX_ATTEMPTS)

        with patch(
            'core.services.notification_service.NotificationService.notify_report_needs_review'
        ):
            self._run()

        entry = MatchReportAuditLog.objects.get(report=report)
        self.assertEqual(entry.action, 'ocr_failed')
        self.assertEqual(entry.new_status, Status.NEEDS_REVIEW)

    # --- soglia temporale --------------------------------------------------

    def test_recent_processing_report_is_left_alone(self):
        """Un referto preso in carico 2 minuti fa e' semplicemente al lavoro."""
        report = self._processing(minutes_ago=2, attempts=1)

        self._run()

        report.refresh_from_db()
        self.assertEqual(report.status, Status.PROCESSING)
        self.assertIsNotNone(report.ocr_started_at)
        self.assertFalse(MatchReportAuditLog.objects.filter(report=report).exists())

    def test_minutes_option_moves_the_threshold(self):
        report = self._processing(minutes_ago=8, attempts=1)

        self._run(minutes=60)          # sopra la soglia: non lo tocca
        report.refresh_from_db()
        self.assertEqual(report.status, Status.PROCESSING)

        self._run(minutes=5)           # sotto la soglia: lo recupera
        report.refresh_from_db()
        self.assertEqual(report.status, Status.QUEUED)

    def test_reports_in_other_statuses_are_never_touched(self):
        others = {
            status: MatchReport.objects.create(match=None, status=status)
            for status in [s for s, _ in Status.choices] if status != Status.PROCESSING
        }

        self._run()

        for status, report in others.items():
            with self.subTest(status=status):
                report.refresh_from_db()
                self.assertEqual(report.status, status)

    # --- dry run -----------------------------------------------------------

    def test_dry_run_writes_nothing(self):
        under_cap = self._processing(minutes_ago=30, attempts=1)
        at_cap = self._processing(minutes_ago=30, attempts=OCRQueueService.MAX_ATTEMPTS)

        with patch(
            'core.services.notification_service.NotificationService.notify_report_needs_review'
        ) as notify:
            output = self._run(dry_run=True)

        under_cap.refresh_from_db()
        at_cap.refresh_from_db()
        self.assertEqual(under_cap.status, Status.PROCESSING)
        self.assertEqual(at_cap.status, Status.PROCESSING)
        self.assertFalse(MatchReportAuditLog.objects.exists())
        notify.assert_not_called()

        # ...ma dice cosa avrebbe fatto, distinguendo i due esiti.
        self.assertIn("DRY-RUN", output)
        self.assertIn(str(under_cap.pk), output)
        self.assertIn(str(at_cap.pk), output)

    def test_empty_run_says_so_without_touching_anything(self):
        output = self._run()
        self.assertIn("Nessun referto orfano", output)

    def test_non_positive_minutes_is_refused(self):
        report = self._processing(minutes_ago=30, attempts=1)

        output = self._run(minutes=0)

        report.refresh_from_db()
        self.assertEqual(report.status, Status.PROCESSING)
        self.assertIn("positivo", output)

    # --- condivisione del code path con la sweep di avvio ------------------

    def test_command_delegates_to_the_queue_service(self):
        """
        Il comando NON reimplementa la regola: chiama `requeue_stale`, lo
        stesso metodo che il worker usa nella sweep di avvio. Se qualcuno
        duplicasse la logica qui dentro, questo test si accorge.
        """
        with patch.object(
            OCRQueueService, 'requeue_stale', return_value=([], []),
        ) as requeue:
            self._run(minutes=42)

        requeue.assert_called_once_with(older_than_minutes=42, dry_run=False)

    def test_worker_startup_sweep_uses_the_same_entry_point(self):
        """
        Controprova: la sweep di avvio del worker passa dallo stesso metodo,
        con `older_than_minutes=None` (nessuna soglia — girando un solo worker,
        all'avvio ogni referto in PROCESSING e' per definizione orfano).
        """
        with patch.object(
            OCRQueueService, 'requeue_stale', return_value=([], []),
        ) as requeue:
            call_command('ocr_worker', once=True, stdout=StringIO())

        requeue.assert_called_once_with(older_than_minutes=None)

    def test_command_and_startup_sweep_agree_on_a_stale_report(self):
        """
        Stesso referto, stesso esito, indipendentemente da chi lo recupera.
        E' l'invariante che la condivisione del code path deve garantire.
        """
        via_command = self._processing(minutes_ago=30, attempts=1)
        self._run()
        via_command.refresh_from_db()

        via_sweep = self._processing(minutes_ago=30, attempts=1)
        # Coda vista come vuota: il worker fa la sweep di avvio e poi esce
        # senza rielaborare il referto appena riaccodato, che altrimenti
        # proseguirebbe nella pipeline e sporcherebbe il confronto.
        with patch.object(OCRQueueService, 'next_candidate_id', return_value=None):
            call_command('ocr_worker', once=True, stdout=StringIO())
        via_sweep.refresh_from_db()

        self.assertEqual(via_command.status, via_sweep.status)
        self.assertEqual(
            MatchReportAuditLog.objects.get(report=via_command).action,
            MatchReportAuditLog.objects.get(report=via_sweep).action,
        )
