"""Test della data migration core/0009 (bonifica season -> formato slash).

Usa l'infrastruttura migration di Django (MigrationExecutor): rewind allo stato
0008 (pre-bonifica), seeding dei 4 rami rappresentativi, poi forward a 0010 che
ESEGUE davvero 0009 (bonifica) + 0010 (alterfield+validator); infine asserzioni.

Lo schema DB e' identico tra 0008 e 0010 (0009 e' data-only, 0010 cambia solo
validator/default/help_text, non colonne): il seeding usa quindi i modelli reali.
Il validator non viene triggerato perche' .save()/.create() non chiama full_clean,
quindi i valori dash/typo seminati sono accettati.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from core.models import League, LeagueStanding, Society, Sport, Team
from management.models import Membership


class SeasonBonificaMigrationTest(TransactionTestCase):
    migrate_from = [("core", "0008_alter_league_options_alter_sport_options_and_more")]
    migrate_to = [("core", "0010_alter_league_season_alter_leaguestanding_season")]

    def setUp(self):
        # Rewind allo stato pre-bonifica.
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)

        User = get_user_model()
        sport = Sport.objects.create(name="PN MigTest", slug="pn-migtest")
        society = Society.objects.create(name="Soc MigTest", slug="soc-migtest", sport=sport, city="Roma")

        # (a) lega season pura 2025-2026 -> CONVERT 2025/2026
        self.league_a = League.objects.create(
            name="Lega A", sport=sport, category="SENIOR", season="2025-2026", slug="lega-a")

        # (b) lega typo 2025-5026 + 1 standing -> CONVERT typo 2025/2026 lockstep
        self.league_b = League.objects.create(
            name="Lega B", sport=sport, category="U16", season="2025-5026", slug="lega-b")
        self.team_b = Team.objects.create(society=society, category="U16", league=self.league_b, name="Team B", slug="team-b")
        self.std_b = LeagueStanding.objects.create(league=self.league_b, team=self.team_b, season="2025-5026")

        # (c) lega 2024-2025 mal-datata CON team + Membership PLAYER attiva + standing
        self.league_c = League.objects.create(
            name="Lega C", sport=sport, category="SENIOR", season="2024-2025", slug="lega-c")
        self.team_c = Team.objects.create(society=society, category="SENIOR", league=self.league_c, name="Team C", slug="team-c")
        self.std_c = LeagueStanding.objects.create(league=self.league_c, team=self.team_c, season="2024-2025")
        self.player = User.objects.create(username="player_migtest", role="athlete")
        self.membership = Membership.objects.create(
            user=self.player, society=society, team=self.team_c, role="PLAYER",
            is_active=True, start_date=date(2025, 9, 1), end_date=None)

        # (d) lega 2024-2025 SENZA team E SENZA standing -> DELETE (orfana)
        self.league_d = League.objects.create(
            name="Lega D", sport=sport, category="SENIOR", season="2024-2025", slug="lega-d")

        self.ids = {
            "a": self.league_a.id, "b": self.league_b.id, "c": self.league_c.id, "d": self.league_d.id,
            "std_b": self.std_b.id, "std_c": self.std_c.id,
            "team_c": self.team_c.id, "membership": self.membership.id,
        }

        # Forward: ESEGUE 0009 (bonifica) e 0010 (alterfield+validator).
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)

    def tearDown(self):
        call_command("migrate", verbosity=0)

    def test_branch_a_pure_dash_converted(self):
        self.assertEqual(League.objects.get(pk=self.ids["a"]).season, "2025/2026")

    def test_branch_b_typo_converted_lockstep(self):
        self.assertEqual(League.objects.get(pk=self.ids["b"]).season, "2025/2026")
        self.assertEqual(LeagueStanding.objects.get(pk=self.ids["std_b"]).season, "2025/2026")

    def test_branch_c_maldated_with_links_converted_not_deleted(self):
        league_c = League.objects.get(pk=self.ids["c"])  # esiste ancora
        self.assertEqual(league_c.season, "2025/2026")
        self.assertEqual(LeagueStanding.objects.get(pk=self.ids["std_c"]).season, "2025/2026")
        self.assertEqual(Team.objects.get(pk=self.ids["team_c"]).league_id, self.ids["c"])
        membership = Membership.objects.get(pk=self.ids["membership"])
        self.assertEqual(membership.role, "PLAYER")
        self.assertTrue(membership.is_active)
        self.assertIsNone(membership.end_date)

    def test_branch_d_orphan_deleted(self):
        self.assertFalse(League.objects.filter(pk=self.ids["d"]).exists())

    def test_no_noncanonical_season_left(self):
        for value in League.objects.values_list("season", flat=True):
            self.assertRegex(value, r"^\d{4}/\d{4}$")
        for value in LeagueStanding.objects.values_list("season", flat=True):
            self.assertRegex(value, r"^\d{4}/\d{4}$")
