"""Test della data migration core/0009 (bonifica season -> formato slash).

Usa l'infrastruttura migration di Django (MigrationExecutor): rewind allo stato
0008 (pre-bonifica), seeding dei 4 rami rappresentativi, poi forward a 0010 che
ESEGUE davvero 0009 (bonifica) + 0010 (alterfield+validator); infine asserzioni.

Lo schema DB e' identico tra 0008 e 0010 (0009 e' data-only, 0010 cambia solo
validator/default/help_text, non colonne): il seeding usa quindi i modelli reali.
Il validator non viene triggerato perche' .save()/.create() non chiama full_clean,
quindi i valori dash/typo seminati sono accettati.
"""
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

# I modelli (core.League/Society/Team/LeagueStanding, management.Membership,
# accounts.User) sono ottenuti come modelli STORICI dal project_state in setUp:
# il modello reale core.League ha ora season_fk, assente nello schema 0008/0010.


def _current_leaf(loader, app_label):
    """Risolve dinamicamente il leaf corrente di un'app dal grafo migration.

    Sostituisce l'hardcoding della stringa di migration leaf: una nuova
    migration sull'app sposta il leaf, ma il test continua a targettare lo
    schema fisico corrente (== leaf) senza lockstep manuale. Si applica SOLO
    alle app che nel test restano allo schema fisico corrente (accounts, mai
    retrocessa); NON agli anchor storici (core@0008/0010, management@0009) che
    sono semantici e devono restare fissi.
    """
    leaves = loader.graph.leaf_nodes(app_label)
    assert len(leaves) == 1, (
        f"atteso 1 leaf per '{app_label}', trovati {len(leaves)}: {leaves}"
    )
    return leaves[0]


class SeasonBonificaMigrationTest(TransactionTestCase):
    # §10.7: management viene RETROCESSO fisicamente a 0009 insieme a core. Da
    # management/0014_remove_membership_dates le colonne start_date/end_date non
    # esistono piu', ma il pin storico 0009 le emette negli INSERT; un pin
    # management al leaf e' impossibile perche' trascinerebbe core oltre 0008 nel
    # project_state (management/0010+ dipende da core.Season). 0009 e' percio' un
    # anchor storico semantico (NON un leaf): resta hardcoded di proposito. Si
    # riallineano schema fisico e modello storico retrocedendo core e management.
    migrate_from = [
        ("core", "0008_alter_league_options_alter_sport_options_and_more"),
        ("management", "0009_membership_end_date_constraint"),
    ]
    migrate_to = [("core", "0010_alter_league_season_alter_leaguestanding_season")]

    def setUp(self):
        # Rewind allo stato pre-bonifica.
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)

        # Modelli STORICI dello stato pre-bonifica. Il modello reale core.League
        # ha ora season_fk (introdotto in 0013, assente nello schema storico
        # 0008/0010): un seeding/una query col modello reale emetterebbe
        # season_fk_id e fallirebbe ("no such column"). Si usa un project_state
        # combinato che riproduce il DB reale dopo il rewind del SOLO core a 0008:
        # core e management vengono retrocessi (anchor storici, vedi sopra),
        # mentre accounts NON viene mai retrocesso e resta allo schema fisico
        # corrente. Per questo accounts va targettato al suo LEAF (User con i
        # campi correnti, es. identity_status): il leaf e' risolto in modo
        # dinamico (_current_leaf) invece che con la stringa fissa, cosi' una
        # futura migration accounts non rompe il test ne' richiede lockstep
        # manuale. Tutti i modelli provengono cosi' dallo stesso registro
        # storico: niente ibridi, FK coerenti dentro lo stesso apps registry.
        old_apps = executor.loader.project_state(
            self.migrate_from + [_current_leaf(executor.loader, "accounts")]
        ).apps
        Sport = old_apps.get_model("core", "Sport")
        Society = old_apps.get_model("core", "Society")
        League = old_apps.get_model("core", "League")
        Team = old_apps.get_model("core", "Team")
        LeagueStanding = old_apps.get_model("core", "LeagueStanding")
        Membership = old_apps.get_model("management", "Membership")
        User = old_apps.get_model("accounts", "User")
        # Riusati dalle asserzioni (gli altri modelli restano impliciti via id).
        self.League = League
        self.LeagueStanding = LeagueStanding
        self.Team = Team
        self.Membership = Membership

        sport = Sport.objects.create(name="PN MigTest", slug="pn-migtest")
        society = Society.objects.create(name="Soc MigTest", slug="soc-migtest", sport=sport, city="Roma")

        # (a) lega season pura 2025-2026 -> CONVERT 2025/2026
        self.league_a = League.objects.create(
            name="Lega A", sport=sport, category="SENIOR", season="2025-2026", slug="lega-a")

        # (b) lega typo 2025-5026 + 1 standing -> CONVERT typo 2025/2026 lockstep
        self.league_b = League.objects.create(
            name="Lega B", sport=sport, season="2025-5026", slug="lega-b")
        # Schema storico 0008: category esiste ancora (unique_together society+category).
        self.team_b = Team.objects.create(society=society, category="U16", league=self.league_b, name="Team B", slug="team-b")
        self.std_b = LeagueStanding.objects.create(league=self.league_b, team=self.team_b, season="2025-5026")

        # (c) lega 2024-2025 mal-datata CON team + Membership PLAYER attiva + standing
        self.league_c = League.objects.create(
            name="Lega C", sport=sport, season="2024-2025", slug="lega-c")
        self.team_c = Team.objects.create(society=society, category="SENIOR", league=self.league_c, name="Team C", slug="team-c")
        self.std_c = LeagueStanding.objects.create(league=self.league_c, team=self.team_c, season="2024-2025")
        self.player = User.objects.create(username="player_migtest", role="athlete")
        # Niente date (sparite al leaf 0014) e niente season (a core@0008 la
        # tabella core_season non esiste): la riga viaggia su user/team/role.
        self.membership = Membership.objects.create(
            user=self.player, society=society, team=self.team_c, role="PLAYER",
            is_active=True)

        # (d) lega 2024-2025 SENZA team E SENZA standing -> DELETE (orfana)
        self.league_d = League.objects.create(
            name="Lega D", sport=sport, season="2024-2025", slug="lega-d")

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
        self.assertEqual(self.League.objects.get(pk=self.ids["a"]).season, "2025/2026")

    def test_branch_b_typo_converted_lockstep(self):
        self.assertEqual(self.League.objects.get(pk=self.ids["b"]).season, "2025/2026")
        self.assertEqual(self.LeagueStanding.objects.get(pk=self.ids["std_b"]).season, "2025/2026")

    def test_branch_c_maldated_with_links_converted_not_deleted(self):
        league_c = self.League.objects.get(pk=self.ids["c"])  # esiste ancora
        self.assertEqual(league_c.season, "2025/2026")
        self.assertEqual(self.LeagueStanding.objects.get(pk=self.ids["std_c"]).season, "2025/2026")
        self.assertEqual(self.Team.objects.get(pk=self.ids["team_c"]).league_id, self.ids["c"])
        membership = self.Membership.objects.get(pk=self.ids["membership"])
        self.assertEqual(membership.role, "PLAYER")
        self.assertTrue(membership.is_active)

    def test_branch_d_orphan_deleted(self):
        self.assertFalse(self.League.objects.filter(pk=self.ids["d"]).exists())

    def test_no_noncanonical_season_left(self):
        for value in self.League.objects.values_list("season", flat=True):
            self.assertRegex(value, r"^\d{4}/\d{4}$")
        for value in self.LeagueStanding.objects.values_list("season", flat=True):
            self.assertRegex(value, r"^\d{4}/\d{4}$")
