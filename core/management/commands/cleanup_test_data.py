"""
Cleanup chirurgico del DB di sviluppo — Lista A dall'audit.

DRY-RUN di default. Con --execute esegue le DELETE in una transazione atomica.

Cosa elimina:
  1. Match senza report o con soli report REJECTED
  2. MatchReport REJECTED collegati a quei match
  3. MatchEvent collegati a quei match
  4. MatchReportAuditLog dei report eliminati
  5. Society #19 "Test Soc" se sicura
  6. Team #17 se sicuro
  7. League #10 "Serie A1 Test" se sicura

Dopo --execute, ricalcola le stats degli atleti coinvolti.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import AthleteProfile
from core.models import League, Society, Team
from management.models import ActivationCode, Membership
from matches.models import Match, MatchEvent, MatchReport, MatchReportAuditLog


SOCIETY_TEST_SOC_ID = 19
TEAM_TEST_ID = 17
LEAGUE_SERIE_A1_TEST_ID = 10

FINAL_KEEP_STATUSES = {
    "PUBLISHED", "UPLOADED", "EXTRACTED", "VALIDATED", "NEEDS_REVIEW",
    "DRAFT", "PROCESSING",
}


class Command(BaseCommand):
    help = "Pulizia chirurgica dei dati di test (Lista A audit). DRY-RUN di default."

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Esegue davvero le DELETE in transaction.atomic(). Default: dry-run.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Stampa dettaglio per ogni record toccato.",
        )

    # ------------------------------------------------------------------
    # Analisi
    # ------------------------------------------------------------------

    def find_match_candidates(self):
        """Ritorna queryset dei Match da eliminare: zero report oppure tutti REJECTED."""
        candidates = []
        for m in Match.objects.all().order_by("id"):
            statuses = set(m.reports.values_list("status", flat=True))
            if not statuses or statuses.issubset({"REJECTED"}):
                candidates.append(m)
        return candidates

    def check_unexpected_statuses(self, matches):
        """Verifica che nessun match candidato abbia report in stato non-REJECTED."""
        anomalies = []
        for m in matches:
            non_rejected = list(
                MatchReport.objects.filter(match=m).exclude(status="REJECTED").values("id", "status")
            )
            if non_rejected:
                anomalies.append((m.id, non_rejected))
        return anomalies

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def handle(self, *args, **opts):
        execute = opts["execute"]
        verbose = opts["verbose"]

        out = self.stdout.write
        header = "=== EXECUTE — modifiche reali ===" if execute else "=== DRY RUN — Niente verrà cancellato ==="
        out(header)
        out("")

        # ---- 1. Match candidati ----
        matches = self.find_match_candidates()
        out(f"Match da eliminare: {len(matches)}")
        for m in matches:
            reports = list(m.reports.values_list("id", "status"))
            home = m.home_team.name if m.home_team_id else "?"
            away = m.away_team.name if m.away_team_id else "?"
            league = m.league.name if m.league_id else "?"
            out(f"  ID: {m.id}, date: {m.match_date}, "
                f"home: {home}, away: {away}, league: {league}, "
                f"reports: {reports}")

        # Anomaly check
        anomalies = self.check_unexpected_statuses(matches)
        if anomalies:
            out("")
            out("!!! ANOMALIA: trovati match con report in stato non-REJECTED tra i candidati.")
            out("!!! Incoerente con l'audit. ABORT — non procedere.")
            for mid, reports in anomalies:
                out(f"    Match #{mid} → {reports}")
            return

        match_ids = [m.id for m in matches]

        # ---- 2. MatchReport collegati ----
        reports_qs = MatchReport.objects.filter(match_id__in=match_ids)
        out("")
        out(f"MatchReport da eliminare: {reports_qs.count()}")
        for r in reports_qs.order_by("id"):
            out(f"  ID: {r.id}, match: #{r.match_id}, status: {r.status}")

        # ---- 3. MatchReportAuditLog collegati ----
        report_ids = list(reports_qs.values_list("id", flat=True))
        audit_qs = MatchReportAuditLog.objects.filter(report_id__in=report_ids)
        out("")
        out(f"MatchReportAuditLog da eliminare: {audit_qs.count()} (collegati ai report sopra)")
        if verbose:
            for a in audit_qs.order_by("id"):
                out(f"  ID: {a.id}, report: #{a.report_id}, action: {a.action}, "
                    f"{a.old_status}→{a.new_status}")

        # ---- 4. MatchEvent collegati ----
        events_qs = MatchEvent.objects.filter(match_id__in=match_ids)
        out("")
        out(f"MatchEvent da eliminare: {events_qs.count()}")
        for ev in events_qs.order_by("id"):
            player_user_id = ev.player_id
            out(f"  ID: {ev.id}, match: #{ev.match_id}, type: {ev.event_type}, "
                f"player_user_id: {player_user_id}, team_id: {ev.team_id}")

        # ---- 5. Atleti coinvolti (stats pre-cancellazione) ----
        affected_user_ids = list(
            events_qs.exclude(player_id__isnull=True).values_list("player_id", flat=True).distinct()
        )
        affected_athletes = list(
            AthleteProfile.objects.filter(user_id__in=affected_user_ids).select_related("user")
        )
        out("")
        out(f"Atleti coinvolti negli eventi (stats attuali, da ricalcolare): {len(affected_athletes)}")
        for ap in affected_athletes:
            out(f"  AthleteProfile #{ap.id} user={ap.user.username if ap.user_id else None} "
                f"goals={ap.total_goals} matches={ap.total_matches} expulsions={ap.total_expulsions}")

        # ---- 6. Society / Team / League (valutazione POST-eliminazione match) ----
        out("")

        # Team #17 valutato per primo: la sua condizione non dipende dalla Society
        # (controlla membership attive e match residui dopo cleanup).
        team_status, team_reason = self._evaluate_team(
            TEAM_TEST_ID, match_ids, society_will_be_deleted=False
        )
        out(f"Team #{TEAM_TEST_ID}: {team_status}"
            + (f"  ({team_reason})" if team_reason else ""))

        # Society #19 — valutata DOPO il team, considerando l'eventuale rimozione di Team #17.
        doomed_team_ids = [TEAM_TEST_ID] if team_status == "ELIMINABILE" else []
        soc_status, soc_reason = self._evaluate_society(
            SOCIETY_TEST_SOC_ID, match_ids, doomed_team_ids=doomed_team_ids
        )
        out(f'Society "Test Soc" #{SOCIETY_TEST_SOC_ID}: {soc_status}'
            + (f"  ({soc_reason})" if soc_reason else ""))

        # League #10 — eliminabile?
        league_status, league_reason = self._evaluate_league(LEAGUE_SERIE_A1_TEST_ID, match_ids)
        out(f'League "Serie A1 Test" #{LEAGUE_SERIE_A1_TEST_ID}: {league_status}'
            + (f"  ({league_reason})" if league_reason else ""))

        # ActivationCode su Society #19 (se eliminabile)
        ac_qs = ActivationCode.objects.filter(society_id=SOCIETY_TEST_SOC_ID)
        memb_team_qs = Membership.objects.filter(team_id=TEAM_TEST_ID)
        memb_soc_qs = Membership.objects.filter(society_id=SOCIETY_TEST_SOC_ID)
        out("")
        out(f"ActivationCode su Society #{SOCIETY_TEST_SOC_ID}: {ac_qs.count()}")
        out(f"Membership su Team #{TEAM_TEST_ID}: {memb_team_qs.count()}")
        out(f"Membership su Society #{SOCIETY_TEST_SOC_ID} (qualsiasi team): {memb_soc_qs.count()}")

        # ---- 7. TOTALE ----
        total = (
            audit_qs.count()
            + events_qs.count()
            + reports_qs.count()
            + len(matches)
            + (memb_team_qs.count() if team_status == "ELIMINABILE" else 0)
            + (1 if team_status == "ELIMINABILE" else 0)
            + (ac_qs.count() if soc_status == "ELIMINABILE" else 0)
            + (memb_soc_qs.count() if soc_status == "ELIMINABILE" else 0)
            + (1 if soc_status == "ELIMINABILE" else 0)
            + (1 if league_status == "ELIMINABILE" else 0)
        )
        out("")
        out(f"TOTALE record che verrebbero rimossi: {total}")

        if not execute:
            out("")
            out("Per eseguire davvero, rilancia con:")
            out("  python manage.py cleanup_test_data --execute")
            return

        # ===========================================================
        # EXECUTE
        # ===========================================================
        out("")
        out(">>> Esecuzione DELETE in transaction.atomic()...")

        with transaction.atomic():
            audit_deleted, _ = audit_qs.delete()
            events_deleted, _ = events_qs.delete()
            reports_deleted, _ = reports_qs.delete()
            matches_deleted, _ = Match.objects.filter(id__in=match_ids).delete()

            team_memb_deleted = 0
            team_deleted = 0
            if team_status == "ELIMINABILE":
                team_memb_deleted, _ = memb_team_qs.delete()
                team_deleted, _ = Team.objects.filter(id=TEAM_TEST_ID).delete()

            ac_deleted = 0
            soc_memb_deleted = 0
            soc_deleted = 0
            if soc_status == "ELIMINABILE":
                ac_deleted, _ = ac_qs.delete()
                # Eventuali memberships residue (post team-cancellazione)
                soc_memb_deleted, _ = Membership.objects.filter(society_id=SOCIETY_TEST_SOC_ID).delete()
                soc_deleted, _ = Society.objects.filter(id=SOCIETY_TEST_SOC_ID).delete()

            league_deleted = 0
            if league_status == "ELIMINABILE":
                league_deleted, _ = League.objects.filter(id=LEAGUE_SERIE_A1_TEST_ID).delete()

            # Ricalcolo stats atleti coinvolti
            for ap in AthleteProfile.objects.filter(user_id__in=affected_user_ids):
                ap.update_stats()

        out("")
        out("Conteggio cancellazioni:")
        out(f"  MatchReportAuditLog: {audit_deleted}")
        out(f"  MatchEvent:          {events_deleted}")
        out(f"  MatchReport:         {reports_deleted}")
        out(f"  Match:               {matches_deleted}")
        out(f"  Membership(team):    {team_memb_deleted}")
        out(f"  Team:                {team_deleted}")
        out(f"  ActivationCode:      {ac_deleted}")
        out(f"  Membership(soc):     {soc_memb_deleted}")
        out(f"  Society:             {soc_deleted}")
        out(f"  League:              {league_deleted}")

        out("")
        out("Stats atleti ricalcolate:")
        for ap in AthleteProfile.objects.filter(user_id__in=affected_user_ids).select_related("user"):
            out(f"  AthleteProfile #{ap.id} user={ap.user.username if ap.user_id else None} "
                f"goals={ap.total_goals} matches={ap.total_matches} expulsions={ap.total_expulsions}")

        out("")
        out("Pulizia completata.")
        out(f"Match TOTALI in DB:    {Match.objects.count()}")
        out(f"Society TOTALI in DB:  {Society.objects.count()}")
        out(f"Team TOTALI in DB:     {Team.objects.count()}")
        out(f"League TOTALI in DB:   {League.objects.count()}")

    # ------------------------------------------------------------------
    # Helpers di valutazione (simulano lo stato POST-eliminazione match)
    # ------------------------------------------------------------------

    def _evaluate_society(self, soc_id, doomed_match_ids, doomed_team_ids=None):
        doomed_team_ids = doomed_team_ids or []
        soc = Society.objects.filter(id=soc_id).first()
        if not soc:
            return ("NON ELIMINABILE", "Society non esiste")
        active_memb = (
            Membership.objects.filter(society_id=soc_id, is_active=True)
            .exclude(team_id__in=doomed_team_ids)
            .count()
        )
        teams_remaining = (
            Team.objects.filter(society_id=soc_id).exclude(id__in=doomed_team_ids).count()
        )
        if active_memb > 0:
            return ("NON ELIMINABILE", f"{active_memb} membership attive (dopo cleanup)")
        if teams_remaining > 0:
            return ("NON ELIMINABILE", f"{teams_remaining} team residui dopo cleanup")
        return ("ELIMINABILE", "")

    def _evaluate_team(self, team_id, doomed_match_ids, society_will_be_deleted):
        team = Team.objects.filter(id=team_id).first()
        if not team:
            return ("NON ELIMINABILE", "Team non esiste")
        if society_will_be_deleted:
            return ("ELIMINABILE", "Society padre verrà eliminata")
        active_memb = Membership.objects.filter(team_id=team_id, is_active=True).count()
        # Match come home/away esclusi quelli che andranno via
        home_remaining = Match.objects.filter(home_team_id=team_id).exclude(id__in=doomed_match_ids).count()
        away_remaining = Match.objects.filter(away_team_id=team_id).exclude(id__in=doomed_match_ids).count()
        if active_memb > 0:
            return ("NON ELIMINABILE", f"{active_memb} membership attive")
        if home_remaining + away_remaining > 0:
            return ("NON ELIMINABILE",
                    f"{home_remaining + away_remaining} match residui dopo cleanup")
        return ("ELIMINABILE", "")

    def _evaluate_league(self, league_id, doomed_match_ids):
        lg = League.objects.filter(id=league_id).first()
        if not lg:
            return ("NON ELIMINABILE", "League non esiste")
        remaining = Match.objects.filter(league_id=league_id).exclude(id__in=doomed_match_ids).count()
        if remaining > 0:
            return ("NON ELIMINABILE", f"{remaining} match residui dopo cleanup")
        return ("ELIMINABILE", "")
