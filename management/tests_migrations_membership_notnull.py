"""Test della migration management/0015 (consolidamento NULL + flip NOT NULL).

Gradino finale della Fase 2 (fetta 2d-7). Stessa infrastruttura dei test
migration esistenti (MigrationExecutor): rewind a 0014 (season nullable),
seeding di righe season=NULL, forward a 0015.

Due comportamenti sotto test:
  - consolidamento: un NULL derivabile (team -> league -> season_fk, o fallback
    is_current) viene popolato e il flip NOT NULL passa;
  - fail-fast: un NULL non derivabile fa SOLLEVARE la migration (atomica: il
    flip non viene applicato e lo stato resta 0014).
"""
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


def _season_notnull_in_schema():
    with connection.cursor() as cur:
        cur.execute("PRAGMA table_info('management_membership')")
        cols = {row[1]: row for row in cur.fetchall()}
    return bool(cols["season_id"][3])  # colonna notnull del PRAGMA


class MembershipSeasonNotNullMigrationTest(TransactionTestCase):
    migrate_from = [("management", "0014_remove_membership_dates")]
    migrate_to = [("management", "0015_membership_season_notnull")]

    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_from)

        # Pin storici coerenti con gli altri test migration (accounts 0005 =
        # leaf; core implicito al leaf: Season/League.season_fk presenti).
        self.old_apps = self.executor.loader.project_state(
            self.migrate_from + [("accounts", "0005_staff_role_pii")]
        ).apps
        self.Sport = self.old_apps.get_model("core", "Sport")
        self.Society = self.old_apps.get_model("core", "Society")
        self.League = self.old_apps.get_model("core", "League")
        self.Team = self.old_apps.get_model("core", "Team")
        self.Season = self.old_apps.get_model("core", "Season")
        self.Membership = self.old_apps.get_model("management", "Membership")
        self.User = self.old_apps.get_model("accounts", "User")

        self.sport = self.Sport.objects.create(name="PN NotNullTest", slug="pn-nntest")
        self.society = self.Society.objects.create(
            name="Soc NotNullTest", slug="soc-nntest", sport=self.sport, city="Roma")
        self.season = self.Season.objects.create(
            sport=self.sport, label="2025/2026", is_current=True)
        self.league = self.League.objects.create(
            name="Lega NN", sport=self.sport, season="2025/2026",
            season_fk=self.season, slug="lega-nntest")
        self.team = self.Team.objects.create(
            society=self.society, league=self.league,
            name="Team NN", slug="team-nntest")

    def tearDown(self):
        call_command("migrate", verbosity=0)

    def _forward(self):
        self.executor.loader.build_graph()
        self.executor.migrate(self.migrate_to)

    def test_derivable_null_consolidated_then_flip(self):
        user = self.User.objects.create(username="u_nn_derive", role="athlete")
        m = self.Membership.objects.create(
            user=user, society=self.society, team=self.team, role="PLAYER",
            is_active=True, season=None)

        self._forward()

        new_apps = self.executor.loader.project_state(self.migrate_to).apps
        Membership = new_apps.get_model("management", "Membership")
        self.assertEqual(Membership.objects.get(pk=m.pk).season_id, self.season.pk)
        self.assertTrue(_season_notnull_in_schema())

    def test_underivable_null_raises_and_blocks_flip(self):
        # Sport senza Season corrente, membership senza team: nessuna
        # derivazione possibile -> la migration solleva e resta atomica.
        sport2 = self.Sport.objects.create(name="BK NotNullTest", slug="bk-nntest")
        society2 = self.Society.objects.create(
            name="Soc2 NotNullTest", slug="soc2-nntest", sport=sport2, city="Milano")
        user = self.User.objects.create(username="u_nn_orphan", role="athlete")
        orphan = self.Membership.objects.create(
            user=user, society=society2, team=None, role="PLAYER",
            is_active=True, season=None)

        with self.assertRaises(RuntimeError) as ctx:
            self._forward()
        self.assertIn(str(orphan.pk), str(ctx.exception))

        # Migration atomica: il flip NON e' stato applicato, la riga e' intatta.
        self.assertFalse(_season_notnull_in_schema())
        self.assertIsNone(self.Membership.objects.get(pk=orphan.pk).season_id)

        # Sblocco per il tearDown (migrate al leaf): si risolve il record.
        orphan.delete()
