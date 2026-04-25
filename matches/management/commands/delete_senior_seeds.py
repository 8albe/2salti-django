import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import League, LeagueStanding
from matches.models import Match, MatchEvent, MatchReport

logger = logging.getLogger(__name__)

SENIOR_LEAGUE_ID = 6
SENIOR_LEAGUE_NAME = "Senior"
SEED_MATCH_IDS = [5, 6, 7, 8, 9, 10, 11, 12]


class Command(BaseCommand):
    help = (
        "Cancella in modo idempotente gli 8 match seed della League Senior "
        "(id=6) creati a mano via scratch/seed_match_events.py. "
        "Filtri di sicurezza hard-coded: id IN [5..12], is_finished=True, "
        "has_report=False, zero MatchReport collegati."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Mostra cosa farebbe senza modificare il DB.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            default=False,
            help="Richiesto per eseguire la cancellazione vera.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        confirm = options["confirm"]

        if not dry_run and not confirm:
            raise CommandError(
                "Specificare --dry-run per simulare oppure --confirm per "
                "eseguire la cancellazione."
            )
        if dry_run and confirm:
            raise CommandError("--dry-run e --confirm sono mutualmente esclusivi.")

        league = self._validate_league()
        matches = self._validate_matches(league)
        events_count = MatchEvent.objects.filter(match_id__in=SEED_MATCH_IDS).count()

        self._print_summary(matches, events_count)

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — nessuna modifica al DB."))
            return

        self._execute_deletion(matches, events_count)

    def _validate_league(self):
        try:
            league = League.objects.get(id=SENIOR_LEAGUE_ID)
        except League.DoesNotExist:
            raise CommandError(
                f"League id={SENIOR_LEAGUE_ID} non trovata."
            )
        if league.name != SENIOR_LEAGUE_NAME:
            raise CommandError(
                f"League id={SENIOR_LEAGUE_ID} ha name={league.name!r}, "
                f"atteso {SENIOR_LEAGUE_NAME!r}. Abort."
            )
        return league

    def _validate_matches(self, league):
        matches = list(
            Match.objects.filter(id__in=SEED_MATCH_IDS)
            .select_related("home_team", "away_team", "league")
            .order_by("id")
        )
        found_ids = [m.id for m in matches]
        missing = sorted(set(SEED_MATCH_IDS) - set(found_ids))
        if missing:
            raise CommandError(
                f"Match attesi non presenti in DB: {missing}. Abort."
            )

        violations = []
        for m in matches:
            if m.league_id != league.id:
                violations.append(
                    f"id={m.id} appartiene a league_id={m.league_id}, "
                    f"atteso {league.id}"
                )
            if not m.is_finished:
                violations.append(f"id={m.id} ha is_finished=False")
            if m.has_report:
                violations.append(f"id={m.id} ha has_report=True")
            n_reports = MatchReport.objects.filter(match=m).count()
            if n_reports != 0:
                violations.append(
                    f"id={m.id} ha {n_reports} MatchReport collegati"
                )

        if violations:
            raise CommandError(
                "Filtri di sicurezza non rispettati, abort senza cancellazione "
                "parziale:\n  - " + "\n  - ".join(violations)
            )
        return matches

    def _print_summary(self, matches, events_count):
        self.stdout.write("Match seed Senior individuati:")
        self.stdout.write(
            f"  {'id':>3}  {'date':<19}  {'home':<22}  {'away':<22}  "
            f"{'score':<7}  {'events':>6}"
        )
        for m in matches:
            n_ev = MatchEvent.objects.filter(match_id=m.id).count()
            date_str = m.match_date.strftime("%Y-%m-%d %H:%M:%S") if m.match_date else "-"
            score_str = f"{m.home_score}-{m.away_score}"
            self.stdout.write(
                f"  {m.id:>3}  {date_str:<19}  "
                f"{m.home_team.name[:22]:<22}  {m.away_team.name[:22]:<22}  "
                f"{score_str:<7}  {n_ev:>6}"
            )
        self.stdout.write(
            f"Totale: {len(matches)} match, {events_count} MatchEvent."
        )

    def _execute_deletion(self, matches, events_count):
        match_ids = [m.id for m in matches]
        logger.info(
            "Deleting Senior seeds: %s, %d MatchEvent",
            match_ids,
            events_count,
        )
        try:
            with transaction.atomic():
                for m in matches:
                    n_ev = MatchEvent.objects.filter(match_id=m.id).count()
                    home = m.home_team.name
                    away = m.away_team.name
                    score = f"{m.home_score}-{m.away_score}"
                    m.delete()
                    logger.info(
                        "Deleted Match id=%s home=%s away=%s score=%s events=%d",
                        m.id, home, away, score, n_ev,
                    )
                    self.stdout.write(
                        f"  cancellato Match id={m.id} ({home} vs {away} "
                        f"{score}, {n_ev} eventi)"
                    )

                self._verify_post_delete()
        except Exception:
            logger.exception("Senior seeds deletion failed, rollback eseguito")
            raise

        logger.info(
            "Senior seeds deletion completed: %d matches, %d events",
            len(matches),
            events_count,
        )
        self.stdout.write(self.style.SUCCESS(
            f"Cancellazione completata: Match={len(matches)}, "
            f"MatchEvent={events_count}."
        ))

    def _verify_post_delete(self):
        residual_matches = Match.objects.filter(id__in=SEED_MATCH_IDS).count()
        residual_events = MatchEvent.objects.filter(
            match_id__in=SEED_MATCH_IDS
        ).count()
        standings = list(
            LeagueStanding.objects.filter(league_id=SENIOR_LEAGUE_ID)
        )

        problems = []
        if residual_matches != 0:
            problems.append(f"residual Match: {residual_matches} (atteso 0)")
        if residual_events != 0:
            problems.append(f"residual MatchEvent: {residual_events} (atteso 0)")
        if len(standings) != 4:
            problems.append(
                f"LeagueStanding Senior count={len(standings)} (atteso 4)"
            )
        for s in standings:
            non_zero = (
                s.played or s.won or s.drawn or s.lost
                or s.goals_for or s.goals_against or s.points
            )
            if non_zero:
                problems.append(
                    f"LeagueStanding team_id={s.team_id} non a zero "
                    f"(P={s.played} W={s.won} D={s.drawn} L={s.lost} "
                    f"GF={s.goals_for} GA={s.goals_against} pts={s.points})"
                )

        if problems:
            msg = "VERIFICA FALLITA: " + "; ".join(problems)
            self.stdout.write(self.style.ERROR(msg))
            raise CommandError(msg)

        self.stdout.write(self.style.SUCCESS("VERIFICA OK"))
