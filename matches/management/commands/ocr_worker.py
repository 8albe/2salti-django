"""
Worker della coda OCR (Macro 22).

Processo long-running, eseguito come servizio systemd (`2salti-ocrworker`),
che toglie l'OCR dal request cycle: un solo worker in v1, polling sul DB,
claim atomico, retry con backoff sugli errori tecnici.
"""
import logging
import signal
import subprocess
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from matches.models import MatchReport
from matches.services.ocr_queue import OCRQueueService
from matches.services.ocr_service import OCRService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Worker della coda OCR: consuma i referti in QUEUED ed esegue l'estrazione."

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval', type=float, default=3.0,
            help="Secondi di attesa fra due poll a coda vuota (default: 3).",
        )
        parser.add_argument(
            '--once', action='store_true',
            help="Elabora al piu' un referto e termina (diagnostica/test).",
        )
        parser.add_argument(
            '--no-startup-sweep', action='store_true',
            help="Salta la sweep di avvio sui referti orfani in PROCESSING.",
        )

    def handle(self, *args, **options):
        self.interval = options['interval']
        self._stop_requested = False
        self._code_revision = self._current_revision()

        signal.signal(signal.SIGTERM, self._request_stop)
        signal.signal(signal.SIGINT, self._request_stop)

        logger.info("[OCR_WORKER] Avvio (interval=%ss, revision=%s)", self.interval, self._code_revision or 'n/d')
        self.stdout.write(self.style.SUCCESS(f"OCR worker avviato (poll {self.interval}s)."))

        if not options['no_startup_sweep']:
            # Girando un solo worker, ogni referto in PROCESSING all'avvio e' per
            # definizione orfano: nessuno lo sta elaborando. Recuperarlo subito
            # copre il caso comune (deploy, restart, crash) senza aspettare il
            # timer di backstop.
            requeued, exhausted = OCRQueueService.requeue_stale(older_than_minutes=None)
            if requeued or exhausted:
                self.stdout.write(
                    f"Sweep di avvio: {len(requeued)} riaccodati, {len(exhausted)} esauriti -> NEEDS_REVIEW."
                )

        while not self._stop_requested:
            report_id = OCRQueueService.next_candidate_id()

            if report_id is None:
                if options['once']:
                    self.stdout.write("Coda vuota: nessun referto da elaborare.")
                    break
                # Il riavvio su codice nuovo avviene solo a coda vuota, mai a
                # meta' job: uscire con exit 0 lascia a systemd (Restart=always)
                # il compito di rilanciare il worker col codice aggiornato.
                if self._code_changed():
                    logger.info("[OCR_WORKER] Codice aggiornato: exit per restart da systemd.")
                    self.stdout.write(self.style.WARNING("Codice aggiornato: esco, systemd rilancia il worker."))
                    return
                self._sleep(self.interval)
                continue

            self._process(report_id)

            if options['once']:
                break

        logger.info("[OCR_WORKER] Uscita pulita.")
        self.stdout.write(self.style.SUCCESS("OCR worker terminato."))

    # --- elaborazione di un singolo referto -------------------------------

    def _process(self, report_id):
        report = OCRQueueService.claim(report_id)
        if report is None:
            # Corsa persa (o stato cambiato sotto): il loop riparte.
            logger.debug("[OCR_WORKER] Claim fallito sul referto %s", report_id)
            return

        started = time.time()
        logger.info("[OCR_WORKER] Claim referto %s (tentativo %s)", report.pk, report.ocr_attempts)
        try:
            OCRService.process_claimed(report)
        except Exception as exc:
            # Errore TECNICO (provider 5xx, timeout, rete): recuperabile.
            # I fallimenti di merito non arrivano qui — li gestisce il quality
            # gate dentro process_claimed, senza retry.
            logger.error("[OCR_WORKER] Referto %s: errore tecnico: %s", report.pk, exc)
            report.refresh_from_db()
            if not OCRQueueService.schedule_retry(report, exc):
                OCRQueueService.fail_permanently(
                    report,
                    reason=(
                        f"Tentativi OCR esauriti ({report.ocr_attempts}/{OCRQueueService.MAX_ATTEMPTS}). "
                        f"Ultimo errore: {str(exc)[:500]}"
                    ),
                    old_status=MatchReport.Status.PROCESSING,
                    error=exc,
                )
            return

        report.refresh_from_db()
        logger.info(
            "[OCR_WORKER] Referto %s completato in %ss con stato %s",
            report.pk, round(time.time() - started, 2), report.status,
        )

    # --- shutdown e self-restart ------------------------------------------

    def _request_stop(self, signum, frame):
        """
        SIGTERM/SIGINT: si finisce il job in corso e poi si esce.

        Abortire una chiamata al provider a meta' butterebbe ~80s di lavoro e
        un'estrazione probabilmente buona; la unit systemd concede
        TimeoutStopSec=150 per chiudere. Se arriva comunque SIGKILL, il referto
        resta in PROCESSING e lo recupera la sweep di avvio (o il backstop).
        """
        if self._stop_requested:
            return
        self._stop_requested = True
        logger.info("[OCR_WORKER] Segnale %s ricevuto: stop dopo il job corrente.", signum)
        self.stdout.write(self.style.WARNING("Stop richiesto: termino dopo il job corrente."))

    def _sleep(self, seconds):
        """Sleep a piccoli passi, per reagire subito a un segnale di stop."""
        deadline = time.monotonic() + seconds
        while not self._stop_requested and time.monotonic() < deadline:
            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))

    def _current_revision(self):
        """SHA di HEAD, o None se git non e' disponibile (non e' un errore)."""
        try:
            from django.conf import settings
            out = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=str(settings.BASE_DIR), capture_output=True, text=True, timeout=10,
            )
            return out.stdout.strip() if out.returncode == 0 else None
        except Exception:
            return None

    def _code_changed(self):
        if self._code_revision is None:
            return False
        current = self._current_revision()
        return current is not None and current != self._code_revision
