"""Comp/de-comp di una società via seam entitlement (Opzione 1: command dedicato).

Wiring a regime per concedere l'entitlement Club Pro gratuito (``is_comped``)
a una società — es. la pilota Zero9 — senza passare dai seed. Identifica la
società per NOME + sport (mai per pk: i pk divergono tra dev e prod) e passa
ESCLUSIVAMENTE da ``entitlement_service.set_society_comped`` (audit log
``ENTITLEMENT_SOCIETY_COMPED_CHANGED``, ``source='comp_society_command'``).
Idempotente: ri-eseguirlo su uno stato già corretto è un no-op senza audit.
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import Society
from core.services.entitlement_service import set_society_comped

SOURCE = 'comp_society_command'


class Command(BaseCommand):
    help = (
        "Rende una società comped (Club Pro gratuito) via seam entitlement. "
        "Lookup per nome + sport, mai per pk. Con --revoke toglie il comped."
    )

    def add_arguments(self, parser):
        parser.add_argument('name', help="Nome esatto della società (case-insensitive)")
        parser.add_argument('--sport', required=True,
                            help="Nome dello sport della società (case-insensitive)")
        parser.add_argument('--revoke', action='store_true',
                            help="Revoca il comped (is_comped=False) invece di concederlo")

    def handle(self, *args, **options):
        name = options['name']
        sport = options['sport']
        target = not options['revoke']

        matches = Society.objects.filter(name__iexact=name, sport__name__iexact=sport)
        count = matches.count()
        if count == 0:
            raise CommandError(
                f"Nessuna società trovata con nome '{name}' e sport '{sport}'. Nessuna azione."
            )
        if count > 1:
            dettagli = ', '.join(f"pk={s.pk} ({s.city})" for s in matches)
            raise CommandError(
                f"Trovate {count} società con nome '{name}' e sport '{sport}': {dettagli}. "
                "Lookup ambiguo, nessuna azione."
            )

        society = matches.first()
        before = society.is_comped
        set_society_comped(society, target, source=SOURCE)
        society.refresh_from_db()

        if before == society.is_comped:
            self.stdout.write(self.style.WARNING(
                f"Nessun cambiamento: '{society.name}' ({sport}) era già "
                f"is_comped={before}. Nessun audit scritto (seam idempotente)."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Società '{society.name}' ({sport}): is_comped {before} -> "
                f"{society.is_comped} (source={SOURCE}, audit ENTITLEMENT_SOCIETY_COMPED_CHANGED)."
            ))
