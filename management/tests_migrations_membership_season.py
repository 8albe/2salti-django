"""Test della data migration management/0011 (backfill Membership.season).

Usa l'infrastruttura migration di Django (MigrationExecutor): rewind allo stato
0010 (FK season presente, tutta NULL), seeding dei rami rappresentativi
(derivazione via team.league.season_fk, fallback is_current, ramo difensivo),
forward a 0011 che ESEGUE il backfill; poi asserzioni + idempotenza.

I modelli sono ottenuti come modelli STORICI dal project_state: a 0010, core e'
gia' al suo leaf (League.season_fk e Season esistono), quindi il seeding puo'
collegare league.season_fk a una Season reale.
"""
import importlib

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from core.tests_migrations_season import _applied_leaf

# Import via importlib: il nome modulo inizia con una cifra.
_mig = importlib.import_module(
    "management.migrations.0011_backfill_membership_season"
)


class BackfillMembershipSeasonMigrationTest(TransactionTestCase):
    migrate_from = [("management", "0010_membership_season")]
    migrate_to = [("management", "0011_backfill_membership_season")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        # Rewind allo stato pre-backfill (FK season presente, valori NULL).
        executor.migrate(self.migrate_from)

        # accounts pinnato all'ultima migration APPLICATA dopo il rewind
        # (_applied_leaf, come tests_migrations_season): il leaf di GRAFO
        # trascinerebbe core in avanti nel modello storico via dipendenze
        # cross-app (accounts/0012 -> core/0025) mentre il rewind ha
        # retrocesso lo schema fisico; il set applicato e' la verita' fisica.
        # core resta implicito (Season/League.season_fk presenti a mgmt@0010).
        old_apps = executor.loader.project_state(
            self.migrate_from + [_applied_leaf(executor, "accounts")]
        ).apps
        Sport = old_apps.get_model("core", "Sport")
        Society = old_apps.get_model("core", "Society")
        League = old_apps.get_model("core", "League")
        Team = old_apps.get_model("core", "Team")
        Season = old_apps.get_model("core", "Season")
        Membership = old_apps.get_model("management", "Membership")
        User = old_apps.get_model("accounts", "User")

        # Sport 1: HA una Season corrente -> derivazione e fallback risolvono.
        sport1 = Sport.objects.create(name="PN BackfillTest", slug="pn-bktest")
        society1 = Society.objects.create(
            name="Soc1 BackfillTest", slug="soc1-bktest", sport=sport1, city="Roma")
        season1 = Season.objects.create(sport=sport1, label="2025/2026", is_current=True)
        league1 = League.objects.create(
            name="Lega1", sport=sport1, season="2025/2026",
            season_fk=season1, slug="lega1-bktest")
        team1 = Team.objects.create(
            society=society1, league=league1, name="Team1", slug="team1-bktest")

        # Sport 2: NESSUNA Season corrente -> ramo difensivo (resta NULL).
        sport2 = Sport.objects.create(name="Basket BackfillTest", slug="bk-bktest")
        society2 = Society.objects.create(
            name="Soc2 BackfillTest", slug="soc2-bktest", sport=sport2, city="Milano")

        u_derive = User.objects.create(username="u_derive_bk", role="athlete")
        u_fallback = User.objects.create(username="u_fallback_bk", role="athlete")
        u_defensive = User.objects.create(username="u_defensive_bk", role="athlete")

        # (a) derivazione primaria: team -> league -> season_fk = season1
        m_derive = Membership.objects.create(
            user=u_derive, society=society1, team=team1, role="PLAYER",
            is_active=True, season=None)
        # (b) fallback: niente team, ma society1.sport ha season corrente = season1
        m_fallback = Membership.objects.create(
            user=u_fallback, society=society1, team=None, role="PLAYER",
            is_active=True, season=None)
        # (c) ramo difensivo: niente team, society2.sport senza season corrente
        m_defensive = Membership.objects.create(
            user=u_defensive, society=society2, team=None, role="PLAYER",
            is_active=True, season=None)

        self.ids = {
            "season1": season1.id,
            "derive": m_derive.id,
            "fallback": m_fallback.id,
            "defensive": m_defensive.id,
        }

        # Forward: ESEGUE 0011 (backfill).
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)

        # Modelli storici post-migration, per riletture e re-run idempotenza.
        self.new_apps = executor.loader.project_state(self.migrate_to).apps
        self.Membership = self.new_apps.get_model("management", "Membership")

    def tearDown(self):
        # Il forward al leaf attraversa 0015 (flip NOT NULL), che e' fail-fast
        # sui NULL non derivabili: il record difensivo seminato va rimosso
        # prima, altrimenti la migrazione di chiusura solleva.
        self.Membership.objects.filter(pk=self.ids["defensive"]).delete()
        call_command("migrate", verbosity=0)

    def test_derivation_via_team_league_season_fk(self):
        m = self.Membership.objects.get(pk=self.ids["derive"])
        self.assertEqual(m.season_id, self.ids["season1"])

    def test_fallback_current_season_for_sport(self):
        m = self.Membership.objects.get(pk=self.ids["fallback"])
        self.assertEqual(m.season_id, self.ids["season1"])

    def test_defensive_branch_keeps_null_and_logs(self):
        # Dopo la migration il record difensivo e' ancora NULL (no crash).
        m = self.Membership.objects.get(pk=self.ids["defensive"])
        self.assertIsNone(m.season_id)
        # Ri-eseguendo il backfill, il ramo difensivo emette un warning per quel pk.
        with self.assertLogs(_mig.logger, level="WARNING") as cm:
            _mig.backfill_membership_season(self.new_apps, None)
        self.assertTrue(
            any(str(self.ids["defensive"]) in line for line in cm.output),
            cm.output,
        )
        self.assertIsNone(
            self.Membership.objects.get(pk=self.ids["defensive"]).season_id)

    def test_idempotent_second_run_no_change(self):
        before = dict(self.Membership.objects.values_list("pk", "season_id"))
        # Seconda esecuzione del backfill: stato identico.
        _mig.backfill_membership_season(self.new_apps, None)
        after = dict(self.Membership.objects.values_list("pk", "season_id"))
        self.assertEqual(before, after)

    def test_reverse_resets_to_null(self):
        _mig.reverse_backfill(self.new_apps, None)
        for season_id in self.Membership.objects.values_list("season_id", flat=True):
            self.assertIsNone(season_id)
