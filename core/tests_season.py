import importlib

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from core.models import League, Season, Sport
from core.services.season_service import get_current_season
from core.validators import validate_season_format


class ValidateSeasonFormatTests(TestCase):
    def test_valid_canonical(self):
        # Non solleva eccezioni
        validate_season_format("2025/2026")
        validate_season_format("2024/2025")

    def test_wrong_format_raises(self):
        for bad in ["2025-2026", "2025", "2025/26", "abc", "", None]:
            with self.assertRaises(ValidationError):
                validate_season_format(bad)

    def test_second_year_not_first_plus_one_raises(self):
        for bad in ["2025/2027", "2025/5026", "2025/2025", "2025/2024"]:
            with self.assertRaises(ValidationError):
                validate_season_format(bad)


class LeagueSlugSanitizeTests(TestCase):
    def test_slug_has_no_slash_with_slash_season(self):
        sport = Sport.objects.create(name="Pallanuoto Slug Test")
        league = League.objects.create(
            name="Serie A1", sport=sport, season="2025/2026"
        )
        self.assertNotIn("/", league.slug)
        self.assertIn("2025-2026", league.slug)


class SeasonModelTests(TestCase):
    def setUp(self):
        self.sport_a = Sport.objects.create(name="Pallanuoto Season Test")
        self.sport_b = Sport.objects.create(name="Basket Season Test")

    def test_two_current_same_sport_raises(self):
        Season.objects.create(sport=self.sport_a, label="2025/2026", is_current=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Season.objects.create(sport=self.sport_a, label="2024/2025", is_current=True)

    def test_current_on_different_sports_ok(self):
        s_a = Season.objects.create(sport=self.sport_a, label="2025/2026", is_current=True)
        s_b = Season.objects.create(sport=self.sport_b, label="2025/2026", is_current=True)
        self.assertTrue(s_a.is_current)
        self.assertTrue(s_b.is_current)

    def test_duplicate_sport_label_raises(self):
        Season.objects.create(sport=self.sport_a, label="2025/2026")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Season.objects.create(sport=self.sport_a, label="2025/2026")

    def test_get_current_season_returns_current_or_none(self):
        self.assertIsNone(get_current_season(self.sport_a))
        current = Season.objects.create(sport=self.sport_a, label="2025/2026", is_current=True)
        Season.objects.create(sport=self.sport_a, label="2024/2025", is_current=False)
        self.assertEqual(get_current_season(self.sport_a), current)
        # Sport senza stagioni resta None
        self.assertIsNone(get_current_season(self.sport_b))

    def test_full_clean_rejects_malformed_label(self):
        season = Season(sport=self.sport_a, label="2025-2026")
        with self.assertRaises(ValidationError):
            season.full_clean()


# Moduli data-migration importati via importlib (nome con cifra iniziale non
# importabile con la sintassi `import`).
_populate_module = importlib.import_module("core.migrations.0012_populate_season")
_backfill_module = importlib.import_module("core.migrations.0014_backfill_league_season_fk")


class PopulateSeasonMigrationTest(TransactionTestCase):
    """Test della data-migration 0012 con MigrationExecutor (stesso pattern dei
    test Fase 0). Rewind a 0011 (schema Season presente, tabella vuota), seeding
    di leghe storiche, forward a 0012 che ESEGUE il populate; poi asserzioni.
    """

    migrate_from = [("core", "0011_season_season_unique_season_per_sport_and_more")]
    migrate_to = [("core", "0012_populate_season")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)

        # Modelli STORICI dello stato 0011: il modello reale core.League ha ora
        # season_fk (introdotto in 0013, assente nello schema storico 0011), quindi
        # un seeding col modello reale emetterebbe season_fk_id in INSERT e
        # fallirebbe. Niente Membership qui -> basta core dal project_state 0011.
        old_apps = executor.loader.project_state(self.migrate_from).apps
        HSport = old_apps.get_model("core", "Sport")
        HLeague = old_apps.get_model("core", "League")

        # Stato 0011: schema Season presente, nessuna riga. Seeding leghe.
        sport_pn = HSport.objects.create(name="PN PopTest", slug="pn-poptest")
        sport_bk = HSport.objects.create(name="BK PopTest", slug="bk-poptest")

        # PN: due label distinte; la label 2025/2026 compare su due leghe
        # diverse -> deve generare UNA sola Season (coppia distinta).
        HLeague.objects.create(name="PN A", sport=sport_pn, season="2024/2025", slug="pn-a")
        HLeague.objects.create(name="PN B", sport=sport_pn, season="2025/2026", slug="pn-b")
        HLeague.objects.create(name="PN C", sport=sport_pn, season="2025/2026", slug="pn-c")

        # BK: una sola label distinta.
        HLeague.objects.create(name="BK A", sport=sport_bk, season="2023/2024", slug="bk-a")

        self.sport_pn_id = sport_pn.id
        self.sport_bk_id = sport_bk.id

        executor.loader.build_graph()
        executor.migrate(self.migrate_to)

    def tearDown(self):
        call_command("migrate", verbosity=0)

    def test_one_season_per_distinct_pair(self):
        # PN: {2024/2025, 2025/2026} = 2 righe; BK: {2023/2024} = 1 riga.
        self.assertEqual(
            set(Season.objects.filter(sport_id=self.sport_pn_id).values_list("label", flat=True)),
            {"2024/2025", "2025/2026"},
        )
        self.assertEqual(
            set(Season.objects.filter(sport_id=self.sport_bk_id).values_list("label", flat=True)),
            {"2023/2024"},
        )
        self.assertEqual(Season.objects.count(), 3)

    def test_exactly_one_current_per_sport_and_is_max(self):
        for sport_id, expected_max in [
            (self.sport_pn_id, "2025/2026"),
            (self.sport_bk_id, "2023/2024"),
        ]:
            current = Season.objects.filter(sport_id=sport_id, is_current=True)
            self.assertEqual(current.count(), 1)
            self.assertEqual(current.first().label, expected_max)

    def test_idempotent_rerun_no_duplicates_no_reelection(self):
        before = set(Season.objects.values_list("sport_id", "label", "is_current"))
        # Ri-esegue il forward sui modelli reali (apps registry corrente).
        _populate_module.populate_seasons(django_apps, None)
        after = set(Season.objects.values_list("sport_id", "label", "is_current"))
        self.assertEqual(Season.objects.count(), 3)
        self.assertEqual(before, after)


class SportDetailCurrentSeasonViewTest(TestCase):
    """Regressione del cablaggio view -> get_current_season con fallback."""

    def setUp(self):
        self.sport = Sport.objects.create(name="PN ViewTest", slug="pn-viewtest")
        League.objects.create(name="L A", sport=self.sport, season="2024/2025", slug="vt-a")
        League.objects.create(name="L B", sport=self.sport, season="2025/2026", slug="vt-b")

    def test_view_uses_season_label_when_current_exists(self):
        # Elezione esplicita su una label NON-MAX, per provare che la view legge
        # davvero la Season corrente e non rifa' il MAX.
        Season.objects.create(sport=self.sport, label="2024/2025", is_current=True)
        Season.objects.create(sport=self.sport, label="2025/2026", is_current=False)
        resp = self.client.get(reverse("sport_detail", args=[self.sport.slug]))
        self.assertEqual(resp.context["current_season"], "2024/2025")

    def test_view_falls_back_to_max_when_no_season(self):
        # Nessuna Season per lo sport ma leghe presenti: fallback bit-identico
        # al vecchio MAX lessicografico (= 2025/2026).
        self.assertFalse(Season.objects.filter(sport=self.sport).exists())
        resp = self.client.get(reverse("sport_detail", args=[self.sport.slug]))
        old_max = self.sport.leagues.order_by("-season").first().season
        self.assertEqual(resp.context["current_season"], old_max)
        self.assertEqual(resp.context["current_season"], "2025/2026")


class SportDetailSeasonSelectorViewTest(TestCase):
    """Macro 3 fetta 1: selettore stagione sulla classifica pubblica
    (sport_detail). Il filtro lavora su League.season; il default e' la
    Season corrente, sovrascrivibile via querystring ?season=."""

    def setUp(self):
        self.sport = Sport.objects.create(name="PN SelTest", slug="pn-seltest")
        League.objects.create(name="L vecchia", sport=self.sport, season="2024/2025", slug="st-old")
        League.objects.create(name="L nuova", sport=self.sport, season="2025/2026", slug="st-new")
        # Stagione corrente = 2025/2026 (NON la richiesta nel caso (a)), cosi'
        # un ?season=2024/2025 prova che la querystring sovrascrive il default.
        Season.objects.create(sport=self.sport, label="2024/2025", is_current=False)
        Season.objects.create(sport=self.sport, label="2025/2026", is_current=True)

    def test_available_seasons_distinct_desc(self):
        resp = self.client.get(reverse("sport_detail", args=[self.sport.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["available_seasons"], ["2025/2026", "2024/2025"])

    def test_querystring_overrides_default(self):
        # (a) ?season valido (e diverso dalla corrente) -> selezione esplicita.
        resp = self.client.get(
            reverse("sport_detail", args=[self.sport.slug]), {"season": "2024/2025"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["selected_season"], "2024/2025")
        # current_season resta invariato (chiave preservata per i test esistenti).
        self.assertEqual(resp.context["current_season"], "2025/2026")

    def test_default_is_current_season(self):
        # (b) ?season assente -> default = Season corrente.
        resp = self.client.get(reverse("sport_detail", args=[self.sport.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["selected_season"], "2025/2026")
        self.assertEqual(resp.context["selected_season"], resp.context["current_season"])

    def test_invalid_season_falls_back_without_error(self):
        # (c) ?season non in available_seasons -> fallback alla corrente, 200.
        resp = self.client.get(
            reverse("sport_detail", args=[self.sport.slug]), {"season": "1999/2000"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["selected_season"], "2025/2026")

    def test_selector_rendered_with_multiple_seasons(self):
        resp = self.client.get(reverse("sport_detail", args=[self.sport.slug]))
        self.assertContains(resp, 'id="season-select"')

    def test_no_selector_and_200_without_leagues(self):
        # (d) sport senza leghe -> 200, nessun <select>, available_seasons vuoto.
        empty_sport = Sport.objects.create(name="PN Vuoto", slug="pn-vuoto")
        resp = self.client.get(reverse("sport_detail", args=[empty_sport.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["available_seasons"], [])
        self.assertNotContains(resp, 'id="season-select"')


class BackfillSeasonFkMigrationTest(TransactionTestCase):
    """Test della data-migration 0014 (backfill League.season_fk) con
    MigrationExecutor. Rewind a 0011, seeding storico di leghe, forward a 0014:
    0012 popola Season, 0013 aggiunge la colonna, 0014 collega le FK.

    Seeding con modelli STORICI a 0011 (il modello reale ha gia' season_fk,
    assente nello schema storico). Anche le asserzioni usano il modello STORICO
    a 0014 (lockstep §10.7): il modello reale ha league_type (0015), assente
    nello schema fisico a 0014.
    """

    migrate_initial = [("core", "0011_season_season_unique_season_per_sport_and_more")]
    migrate_to = [("core", "0014_backfill_league_season_fk")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_initial)
        old_apps = executor.loader.project_state(self.migrate_initial).apps
        HSport = old_apps.get_model("core", "Sport")
        HLeague = old_apps.get_model("core", "League")

        sport_pn = HSport.objects.create(name="PN BFTest", slug="pn-bftest")
        sport_bk = HSport.objects.create(name="BK BFTest", slug="bk-bftest")

        # PN: 2025/2026 su due leghe distinte -> stessa Season -> stessa FK.
        HLeague.objects.create(name="PN A", sport=sport_pn, season="2024/2025", slug="bf-pn-a")
        HLeague.objects.create(name="PN B", sport=sport_pn, season="2025/2026", slug="bf-pn-b")
        HLeague.objects.create(name="PN C", sport=sport_pn, season="2025/2026", slug="bf-pn-c")
        HLeague.objects.create(name="BK A", sport=sport_bk, season="2023/2024", slug="bf-bk-a")

        self.sport_pn_id = sport_pn.id
        self.sport_bk_id = sport_bk.id

        executor.loader.build_graph()
        executor.migrate(self.migrate_to)

        # Modelli storici a 0014 per asserzioni e re-run (lockstep §10.7).
        self.new_apps = executor.loader.project_state(self.migrate_to).apps
        self.HLeague = self.new_apps.get_model("core", "League")

    def tearDown(self):
        call_command("migrate", verbosity=0)

    def test_backfill_sets_correct_fk_per_league(self):
        # (a) ogni lega collegata alla Season con stessa (sport, label).
        for league in self.HLeague.objects.all():
            self.assertIsNotNone(league.season_fk_id)
            self.assertEqual(league.season_fk.sport_id, league.sport_id)
            self.assertEqual(league.season_fk.label, league.season)
        # Le due leghe PN 2025/2026 puntano alla stessa, unica Season.
        pn_2526 = self.HLeague.objects.filter(sport_id=self.sport_pn_id, season="2025/2026")
        self.assertEqual(pn_2526.count(), 2)
        self.assertEqual(len(set(pn_2526.values_list("season_fk_id", flat=True))), 1)

    def test_no_league_with_null_fk_on_seeded_data(self):
        # (b) zero leghe con season_fk NULL sui dati seminati.
        self.assertEqual(self.HLeague.objects.count(), 4)
        self.assertEqual(self.HLeague.objects.filter(season_fk__isnull=True).count(), 0)

    def test_backfill_idempotent(self):
        # (d) ri-eseguire il forward non cambia nulla.
        before = dict(self.HLeague.objects.values_list("id", "season_fk_id"))
        _backfill_module.backfill_season_fk(self.new_apps, None)
        after = dict(self.HLeague.objects.values_list("id", "season_fk_id"))
        self.assertEqual(before, after)
        self.assertEqual(self.HLeague.objects.filter(season_fk__isnull=True).count(), 0)

    def test_reverse_nulls_the_fk(self):
        # (e) il reverse di 0014 azzera tutte le FK (colonna ancora presente a 0013).
        self.assertEqual(self.HLeague.objects.filter(season_fk__isnull=False).count(), 4)
        executor = MigrationExecutor(connection)
        executor.migrate([("core", "0013_link_league_to_season")])
        self.assertEqual(self.HLeague.objects.filter(season_fk__isnull=False).count(), 0)
        self.assertEqual(self.HLeague.objects.filter(season_fk__isnull=True).count(), 4)


class LeagueSeasonFkProtectTests(TestCase):
    """(c) PROTECT: una Season con leghe collegate non e' cancellabile."""

    def test_delete_season_with_linked_league_raises_protected(self):
        sport = Sport.objects.create(name="PN ProtTest", slug="pn-prottest")
        season = Season.objects.create(sport=sport, label="2025/2026")
        League.objects.create(
            name="PN A", sport=sport, season="2025/2026",
            slug="prot-pn-a", season_fk=season,
        )
        with self.assertRaises(ProtectedError):
            season.delete()
        # La Season resta in piedi: il delete e' stato bloccato.
        self.assertTrue(Season.objects.filter(pk=season.pk).exists())

    def test_delete_season_without_leagues_ok(self):
        # Controprova: senza leghe collegate il delete passa.
        sport = Sport.objects.create(name="PN ProtTest2", slug="pn-prottest2")
        season = Season.objects.create(sport=sport, label="2025/2026")
        season.delete()
        self.assertFalse(Season.objects.filter(pk=season.pk).exists())
