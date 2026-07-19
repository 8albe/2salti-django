"""
Coda OCR DB-backed (Macro 22).

La coda vive sul modello `MatchReport` (stato `QUEUED` + campi `ocr_*`): niente
modello job separato, niente broker esterno. Questo modulo contiene la meccanica
di coda — selezione, claim atomico, backoff, requeue degli orfani — mentre
l'elaborazione vera resta in `OCRService.process_claimed()`.

Regola d'oro: nessuna transazione aperta mentre gira il provider OCR (~80s con
Gemini). Il worker fa due scritture puntuali (claim ed esito) e lascia il DB
libero nel mezzo: su SQLite una transazione lunga bloccherebbe ogni writer.
"""
import logging
from datetime import timedelta

from django.db.models import F, Q
from django.utils import timezone

from matches.models import MatchReport, MatchReportAuditLog

logger = logging.getLogger(__name__)


class OCRQueueService:
    # Tentativi totali per referto prima di arrendersi a NEEDS_REVIEW.
    MAX_ATTEMPTS = 3
    # Backoff esponenziale sugli errori tecnici: 60s, poi 120s.
    BACKOFF_BASE_SECONDS = 60
    # Un referto in PROCESSING oltre questa soglia e' orfano (worker morto).
    STALE_MINUTES = 15

    @staticmethod
    def next_candidate_id(now=None):
        """
        pk del prossimo referto eleggibile, o None. FIFO su `ocr_queued_at`.
        Eleggibile = QUEUED e (nessun backoff pendente o backoff scaduto).
        """
        now = now or timezone.now()
        return (
            MatchReport.objects
            .filter(status=MatchReport.Status.QUEUED)
            .filter(Q(ocr_next_attempt_at__isnull=True) | Q(ocr_next_attempt_at__lte=now))
            .order_by('ocr_queued_at', 'pk')
            .values_list('pk', flat=True)
            .first()
        )

    @staticmethod
    def claim(report_id, now=None):
        """
        Claim atomico del referto. Ritorna l'istanza aggiornata se il claim ha
        avuto successo, None se un altro processo ha vinto la corsa.

        L'UPDATE condizionale su `status='QUEUED'` e' l'intero meccanismo di
        mutua esclusione: SQLite serializza le scritture, quindi al piu' un
        chiamante vede rowcount 1. I tentativi si incrementano QUI, al claim,
        non all'esito: un worker che muore a meta' job (crash, OOM, SIGKILL)
        ha comunque consumato un tentativo, e il referto non puo' diventare una
        poison pill che cicla all'infinito.
        """
        now = now or timezone.now()
        claimed = MatchReport.objects.filter(
            pk=report_id, status=MatchReport.Status.QUEUED
        ).update(
            status=MatchReport.Status.PROCESSING,
            ocr_started_at=now,
            ocr_attempts=F('ocr_attempts') + 1,
        )
        if not claimed:
            return None
        return MatchReport.objects.get(pk=report_id)

    @classmethod
    def schedule_retry(cls, report, error, now=None):
        """
        Errore tecnico recuperabile: rimette il referto in coda con backoff.
        Ritorna True se il retry e' stato schedulato, False se i tentativi sono
        esauriti (il chiamante lo manda in NEEDS_REVIEW).
        """
        now = now or timezone.now()
        if report.ocr_attempts >= cls.MAX_ATTEMPTS:
            return False

        delay = cls.BACKOFF_BASE_SECONDS * (2 ** (report.ocr_attempts - 1))
        report.status = MatchReport.Status.QUEUED
        report.ocr_next_attempt_at = now + timedelta(seconds=delay)
        report.ocr_started_at = None
        report.ocr_error = str(error)[:2000]
        report.save(update_fields=[
            'status', 'ocr_next_attempt_at', 'ocr_started_at', 'ocr_error', 'updated_at',
        ])
        MatchReportAuditLog.objects.create(
            report=report, user=None, action='ocr_retry',
            old_status=MatchReport.Status.PROCESSING, new_status=MatchReport.Status.QUEUED,
            reason=f"Errore tecnico OCR, retry {report.ocr_attempts}/{cls.MAX_ATTEMPTS} tra {delay}s: {str(error)[:300]}",
        )
        logger.warning(
            "[OCR_QUEUE] Report %s: errore tecnico, retry %s/%s fra %ss",
            report.pk, report.ocr_attempts, cls.MAX_ATTEMPTS, delay,
        )
        return True

    @classmethod
    def requeue_stale(cls, older_than_minutes=None, now=None, dry_run=False):
        """
        Recupera i referti orfani in PROCESSING (worker morto a meta' job).

        Con `older_than_minutes=None` non applica soglia temporale: e' la sweep
        di avvio del worker, dove — girando un solo worker — ogni referto in
        PROCESSING e' per definizione orfano. Con una soglia e' il backstop
        periodico (comando `recover_stale_reports`, giro 2).

        I tentativi sono gia' stati contati al claim: chi ne ha ancora torna in
        coda, chi li ha esauriti va in NEEDS_REVIEW + notifica.
        Ritorna (requeued, exhausted) come liste di pk.
        """
        now = now or timezone.now()
        qs = MatchReport.objects.filter(status=MatchReport.Status.PROCESSING)
        if older_than_minutes is not None:
            qs = qs.filter(ocr_started_at__lte=now - timedelta(minutes=older_than_minutes))

        requeued, exhausted = [], []
        for report in qs:
            if dry_run:
                (requeued if report.ocr_attempts < cls.MAX_ATTEMPTS else exhausted).append(report.pk)
                continue

            if report.ocr_attempts < cls.MAX_ATTEMPTS:
                report.status = MatchReport.Status.QUEUED
                report.ocr_next_attempt_at = now
                report.ocr_started_at = None
                report.save(update_fields=[
                    'status', 'ocr_next_attempt_at', 'ocr_started_at', 'updated_at',
                ])
                MatchReportAuditLog.objects.create(
                    report=report, user=None, action='ocr_stale_requeue',
                    old_status=MatchReport.Status.PROCESSING, new_status=MatchReport.Status.QUEUED,
                    reason=f"Referto orfano in PROCESSING riaccodato (tentativo {report.ocr_attempts}/{cls.MAX_ATTEMPTS}).",
                )
                requeued.append(report.pk)
            else:
                cls.fail_permanently(
                    report,
                    reason=f"Referto orfano in PROCESSING con tentativi esauriti ({report.ocr_attempts}/{cls.MAX_ATTEMPTS}).",
                    old_status=MatchReport.Status.PROCESSING,
                )
                exhausted.append(report.pk)

        if requeued or exhausted:
            logger.warning(
                "[OCR_QUEUE] Sweep stale: %s riaccodati, %s esauriti -> NEEDS_REVIEW",
                len(requeued), len(exhausted),
            )
        return requeued, exhausted

    @staticmethod
    def fail_permanently(report, reason, old_status=None, error=None):
        """
        Esito terminale tecnico: NEEDS_REVIEW + audit + notifica staff.
        Usato quando i tentativi sono esauriti; i fallimenti *di merito*
        (quality gate) restano gestiti da `OCRService.process_claimed`.
        """
        from core.services.notification_service import NotificationService

        old = old_status or report.status
        report.status = MatchReport.Status.NEEDS_REVIEW
        report.ocr_started_at = None
        report.ocr_next_attempt_at = None
        if error is not None:
            report.ocr_error = str(error)[:2000]
        report.validation_notes = f"Errore Tecnico OCR: {report.ocr_error or reason}"
        report.save(update_fields=[
            'status', 'ocr_started_at', 'ocr_next_attempt_at',
            'ocr_error', 'validation_notes', 'updated_at',
        ])
        MatchReportAuditLog.objects.create(
            report=report, user=None, action='ocr_failed',
            old_status=old, new_status=MatchReport.Status.NEEDS_REVIEW,
            reason=reason[:2000],
        )
        logger.error("[OCR_QUEUE] Report %s in NEEDS_REVIEW: %s", report.pk, reason)
        NotificationService.notify_report_needs_review(report)
