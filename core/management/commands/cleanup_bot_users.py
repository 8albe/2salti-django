"""
Cancella via ORM un elenco esplicito di utenti bot-signup (Task 4, recon 2026-07-05).

DRY-RUN di default. Con --apply esegue la cancellazione in transaction.atomic().

Guard di sicurezza HARD (abortano senza cancellare nulla se violati):
  - nessun id target puo' avere is_staff=True o is_superuser=True
  - nessun id target puo' avere un legame reale: Membership, AthleteProfile/
    CoachProfile con current_team valorizzato, PresidentProfile con
    managed_society valorizzato (stesso criterio "legame reale" del recon
    di caratterizzazione — un id con uno di questi non e' un bot husk).

I 5 profili (Athlete/Coach/Referee/Fan/President) dichiarano
on_delete=models.CASCADE verso User a livello Django ORM (non nel DDL
SQLite, che e' NO ACTION su tutte le FK — vedi recon FK). Cancellare lo
User tramite queryset.delete() e' quindi sufficiente: l'ORM porta via da
solo i profili husk collegati.

Lista target: DEFAULT_BOT_IDS (i 27 id ratificati da Alberto il
2026-07-05) oppure --ids per un override esplicito (usato per i test su
dev, dove i bot hanno id diversi). L'assert sui conteggi attesi
EXPECTED_COUNTS scatta SOLO quando si usa la lista di default: quei
conteggi valgono per la lista prod, non per liste custom.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import Collector

from accounts.models import AthleteProfile, CoachProfile, PresidentProfile
from management.models import Membership

User = get_user_model()

DEFAULT_BOT_IDS = [
    # 18 candidati "certi" (zero legami, zero profilo)
    63, 64, 65, 69, 70, 72, 73, 74, 75, 76, 78, 79, 80, 81, 82, 83, 85, 88,
    # 8 "husk": profilo Athlete/Coach/Referee vuoto auto-creato alla registrazione
    61, 62, 67, 68, 71, 77, 84, 87,
    # test manuale di Alberto, rimosso insieme ai bot su sua richiesta esplicita
    89,
]

EXPECTED_COUNTS = {
    "accounts.user": 27,
    "accounts.presidentprofile": 10,
    "accounts.fanprofile": 8,
    "accounts.athleteprofile": 5,
    "accounts.coachprofile": 2,
    "accounts.refereeprofile": 2,
}


class Command(BaseCommand):
    help = (
        "Cancella via ORM la lista ratificata di utenti bot-signup (Task 4). "
        "DRY-RUN di default; --apply per eseguire davvero."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--ids",
            type=str,
            default=None,
            help=(
                "Override della lista target: id separati da virgola. "
                "Se omesso usa DEFAULT_BOT_IDS (i 27 id ratificati per prod). "
                "Con --ids l'assert sui conteggi attesi (EXPECTED_COUNTS) "
                "viene saltato, perche' quei conteggi valgono solo per la "
                "lista di default."
            ),
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Esegue davvero la cancellazione in transaction.atomic(). Default: dry-run.",
        )
        parser.add_argument(
            "--flush-sessions",
            action="store_true",
            default=False,
            help=(
                "Dopo la cancellazione, invalida le sessioni scadute "
                "(clearsessions). Default: off."
            ),
        )

    def handle(self, *args, **options):
        apply_ = options["apply"]
        flush_sessions = options["flush_sessions"]
        using_default_list = options["ids"] is None

        target_ids = self._resolve_target_ids(options["ids"])
        self.stdout.write(f"Lista target ({len(target_ids)} id): {target_ids}")

        found_ids, missing_ids = self._resolve_existing_ids(target_ids)
        if missing_ids:
            self.stdout.write(self.style.WARNING(
                "Id non trovati in DB (gia' cancellati o mai esistiti, "
                f"ignorati): {missing_ids}"
            ))
        if not found_ids:
            self.stdout.write("Nessun utente target trovato in DB. Niente da fare.")
            return

        self._run_safety_guards(found_ids)

        observed_counts = self._collect_dry_run_counts(found_ids)
        self._print_counts("Conteggi per modello (collector ORM, dry-run):", observed_counts)

        if using_default_list:
            diff = self._diff_counts(observed_counts, EXPECTED_COUNTS)
            if diff:
                raise CommandError(
                    "I conteggi osservati divergono dagli attesi (EXPECTED_COUNTS) "
                    f"per la lista di default. Abort, nessuna modifica. Divergenze: {diff}"
                )
            self.stdout.write(self.style.SUCCESS(
                "Conteggi conformi agli attesi (EXPECTED_COUNTS)."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "Lista custom (--ids): assert sui conteggi attesi saltato."
            ))

        if not apply_:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "DRY RUN — nessuna modifica al DB. Rilancia con --apply per eseguire."
            ))
            return

        self._execute_deletion(found_ids, using_default_list, flush_sessions)

    # ------------------------------------------------------------------
    # Risoluzione lista target
    # ------------------------------------------------------------------

    def _resolve_target_ids(self, ids_arg):
        if ids_arg is None:
            return sorted(DEFAULT_BOT_IDS)
        try:
            ids = sorted({int(x) for x in ids_arg.split(",") if x.strip()})
        except ValueError:
            raise CommandError("--ids deve essere una lista di interi separati da virgola.")
        if not ids:
            raise CommandError("--ids ha prodotto una lista vuota. Abort.")
        return ids

    def _resolve_existing_ids(self, target_ids):
        found_ids = sorted(User.objects.filter(id__in=target_ids).values_list("id", flat=True))
        missing_ids = sorted(set(target_ids) - set(found_ids))
        return found_ids, missing_ids

    # ------------------------------------------------------------------
    # Guard di sicurezza
    # ------------------------------------------------------------------

    def _run_safety_guards(self, user_ids):
        privileged = list(
            User.objects.filter(id__in=user_ids)
            .filter(Q(is_staff=True) | Q(is_superuser=True))
            .values_list("id", "username", "is_staff", "is_superuser")
        )
        if privileged:
            raise CommandError(
                "GUARD FALLITO: id con is_staff/is_superuser nella lista target, "
                f"abort senza cancellare nulla: {privileged}"
            )

        real_membership_ids = sorted(set(
            Membership.objects.filter(user_id__in=user_ids)
            .values_list("user_id", flat=True)
        ))
        if real_membership_ids:
            raise CommandError(
                "GUARD FALLITO: id con Membership reale nella lista target "
                f"(non sono bot husk), abort: {real_membership_ids}"
            )

        real_seed_ids = sorted(
            set(AthleteProfile.objects.filter(
                user_id__in=user_ids, current_team__isnull=False
            ).values_list("user_id", flat=True))
            | set(CoachProfile.objects.filter(
                user_id__in=user_ids, current_team__isnull=False
            ).values_list("user_id", flat=True))
            | set(PresidentProfile.objects.filter(
                user_id__in=user_ids, managed_society__isnull=False
            ).values_list("user_id", flat=True))
        )
        if real_seed_ids:
            raise CommandError(
                "GUARD FALLITO: id con profilo reale (team/societa' assegnati), "
                f"non sono husk bot, abort: {real_seed_ids}"
            )

        self.stdout.write(self.style.SUCCESS(
            "Guard di sicurezza superati: nessuno staff/superuser, nessun legame reale."
        ))

    # ------------------------------------------------------------------
    # Conteggi
    # ------------------------------------------------------------------

    def _collect_dry_run_counts(self, user_ids):
        # I modelli non referenziati da nessun'altra FK (es. PresidentProfile,
        # FanProfile) finiscono nell'ottimizzazione "fast delete" di Django e
        # non compaiono in collector.data — vanno contati a parte via .count()
        # sulla queryset (sola lettura, nessuna modifica).
        collector = Collector(using="default")
        collector.collect(User.objects.filter(id__in=user_ids))
        counts = {
            model._meta.label_lower: len(instances)
            for model, instances in collector.data.items()
        }
        for qs in collector.fast_deletes:
            label = qs.model._meta.label_lower
            counts[label] = counts.get(label, 0) + qs.count()
        return counts

    def _diff_counts(self, observed, expected):
        diff = {}
        for key in set(observed) | set(expected):
            o, e = observed.get(key, 0), expected.get(key, 0)
            if o != e:
                diff[key] = {"observed": o, "expected": e}
        return diff

    def _print_counts(self, header, counts):
        self.stdout.write("")
        self.stdout.write(header)
        for label, count in sorted(counts.items()):
            self.stdout.write(f"  {label}: {count}")

    # ------------------------------------------------------------------
    # Esecuzione
    # ------------------------------------------------------------------

    def _execute_deletion(self, user_ids, using_default_list, flush_sessions):
        self.stdout.write("")
        self.stdout.write(">>> Esecuzione cancellazione in transaction.atomic()...")
        with transaction.atomic():
            deleted_total, deleted_by_model = User.objects.filter(id__in=user_ids).delete()
            deleted_by_model = {k.lower(): v for k, v in deleted_by_model.items()}

            if using_default_list:
                diff = self._diff_counts(deleted_by_model, EXPECTED_COUNTS)
                if diff:
                    raise CommandError(
                        "Conteggi post-delete divergenti dagli attesi. Rollback. "
                        f"Divergenze: {diff}"
                    )

            if flush_sessions:
                call_command("clearsessions")
                self.stdout.write("Sessioni scadute invalidate (clearsessions).")

        self._print_counts(
            f"Cancellazione completata ({deleted_total} record totali):",
            deleted_by_model,
        )
        self.stdout.write(self.style.SUCCESS("OK."))
