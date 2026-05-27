"""
Backfill di Membership.start_date per i record creati prima dell'introduzione
del campo (Sprint C — §10.4).

Comportamento:
- Default = dry-run. Per applicare davvero serve --apply.
- Idempotente: salta righe con start_date già valorizzato.
- Per ogni Membership con start_date IS NULL: start_date = created_at.date().
- end_date NON viene toccato: resta NULL per default.

Riferimento: docs/OPS_RUNBOOK.md §10.4
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from management.models import Membership


class Command(BaseCommand):
    help = (
        "Backfill di Membership.start_date dai created_at per i record creati "
        "prima dell'introduzione del campo. Dry-run by default; usa --apply "
        "per scrivere davvero."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Applica le modifiche al DB. Senza questo flag il comando è dry-run.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        mode = "APPLY" if apply_changes else "DRY-RUN"

        self.stdout.write(self.style.WARNING(f"=== Membership backfill — modalità {mode} ==="))

        total = Membership.objects.count()
        candidates_qs = (
            Membership.objects
            .filter(start_date__isnull=True)
            .select_related("society", "team")
            .order_by("id")
        )
        candidates_count = candidates_qs.count()
        already_filled = total - candidates_count

        self.stdout.write(f"Totale Membership: {total}")
        self.stdout.write(f"Già con start_date: {already_filled}")
        self.stdout.write(f"Candidate (start_date NULL): {candidates_count}")

        if candidates_count == 0:
            self.stdout.write(self.style.SUCCESS("Nulla da fare. Backfill completo."))
            return

        per_group = defaultdict(int)
        processed = 0
        errors = 0

        def _do_backfill():
            nonlocal processed, errors
            for m in candidates_qs.iterator():
                try:
                    new_start = timezone.localtime(m.created_at).date()
                    society_name = m.society.name if m.society_id else "<no-society>"
                    team_name = m.team.name if m.team_id else "<no-team>"
                    per_group[(society_name, team_name)] += 1
                    if apply_changes:
                        Membership.objects.filter(pk=m.pk).update(start_date=new_start)
                    processed += 1
                except Exception as exc:  # pragma: no cover — diagnostica difensiva
                    errors += 1
                    self.stderr.write(
                        self.style.ERROR(f"Errore su Membership id={m.pk}: {exc}")
                    )

        if apply_changes:
            with transaction.atomic():
                _do_backfill()
        else:
            _do_backfill()

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Per società / team:"))
        for (society_name, team_name), n in sorted(per_group.items()):
            self.stdout.write(f"  {society_name} / {team_name}: {n}")

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Summary:"))
        self.stdout.write(f"  Totale:      {total}")
        self.stdout.write(f"  Skippate:    {already_filled}")
        self.stdout.write(f"  Processate:  {processed}")
        self.stdout.write(f"  Errori:      {errors}")

        if apply_changes:
            self.stdout.write(self.style.SUCCESS("APPLY completato."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "DRY-RUN. Nessuna scrittura. Per applicare: --apply"
                )
            )
