"""
Backstop periodico sui referti orfani in PROCESSING (Macro 22, giro 2).

Il worker fa gia' una sweep di recupero al proprio avvio, che copre il caso
comune (deploy, restart, crash con successivo riavvio da systemd). Questo
comando copre il caso che quella sweep non vede: il worker fermo e basta —
unit disabilitata, `Restart=always` esaurito, box in cui nessuno rilancia il
processo. Senza backstop, un referto claimato da un worker morto resta in
PROCESSING per sempre e l'utente vede una rotella che gira all'infinito.

Semantica implementata (ratificata giro 2, sostituisce lo sketch di
OPS_RUNBOOK §10.19, scritto quando ne' worker ne' retry esistevano):

    STALE  = status PROCESSING con `ocr_started_at` piu' vecchio di --minutes.
    AZIONE = requeue *capped*, non NEEDS_REVIEW diretto:
             - tentativi residui  -> torna in QUEUED, audit `ocr_stale_requeue`,
                                     `ocr_next_attempt_at = now` (riparte subito)
             - tentativi esauriti -> NEEDS_REVIEW + notifica staff

Lo sketch originale mandava ogni orfano dritto in NEEDS_REVIEW. Con il claim
che incrementa i tentativi e il backoff introdotti nel giro 1, quella scelta
brucerebbe un referto perfettamente sano per un singolo restart sfortunato:
il cap a MAX_ATTEMPTS regge gia' la protezione contro le poison pill, quindi
il backstop puo' permettersi di riprovare.

Il lavoro vero NON e' qui: sta in `OCRQueueService.requeue_stale()`, lo stesso
metodo che usa la sweep di avvio del worker. Questo comando e' solo la
confezione CLI/systemd — una seconda implementazione della stessa regola
divergerebbe al primo cambio.
"""
from django.core.management.base import BaseCommand

from matches.services.ocr_queue import OCRQueueService


class Command(BaseCommand):
    help = (
        "Recupera i referti orfani rimasti in PROCESSING oltre la soglia: "
        "li riaccoda se hanno tentativi residui, altrimenti li manda in NEEDS_REVIEW."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--minutes', type=int, default=OCRQueueService.STALE_MINUTES,
            help=(
                "Soglia in minuti oltre la quale un referto in PROCESSING e' "
                f"considerato orfano (default: {OCRQueueService.STALE_MINUTES})."
            ),
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Mostra cosa verrebbe fatto senza scrivere nulla sul DB.",
        )

    def handle(self, *args, **options):
        minutes = options['minutes']
        dry_run = options['dry_run']

        if minutes <= 0:
            self.stderr.write(self.style.ERROR("--minutes deve essere un intero positivo."))
            return

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(f"{prefix}Ricerca referti orfani in PROCESSING da oltre {minutes} minuti...")

        requeued, exhausted = OCRQueueService.requeue_stale(
            older_than_minutes=minutes, dry_run=dry_run,
        )

        if not requeued and not exhausted:
            self.stdout.write(self.style.SUCCESS(f"{prefix}Nessun referto orfano: niente da fare."))
            return

        if requeued:
            verb = "da riaccodare" if dry_run else "riaccodati in QUEUED"
            self.stdout.write(self.style.WARNING(
                f"{prefix}{len(requeued)} referti {verb}: {sorted(requeued)}"
            ))
        if exhausted:
            verb = "con tentativi esauriti (andrebbero in NEEDS_REVIEW)" if dry_run \
                else f"con tentativi esauriti -> NEEDS_REVIEW (max {OCRQueueService.MAX_ATTEMPTS})"
            self.stdout.write(self.style.ERROR(
                f"{prefix}{len(exhausted)} referti {verb}: {sorted(exhausted)}"
            ))

        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Fatto: {len(requeued)} riaccodati, {len(exhausted)} esauriti."
        ))
