import importlib

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
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
            name="Serie A1", sport=sport, category="SENIOR", season="2025/2026"
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


# Modulo data-migration importato via importlib (nome con cifra iniziale non
# importabile con la sintassi `import`).
_populate_module = importlib.import_module("core.migrations.0012_populate_season")


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

        # Stato 0011: schema Season presente, nessuna riga. Seeding leghe.
        sport_pn = Sport.objects.create(name="PN PopTest", slug="pn-poptest")
        sport_bk = Sport.objects.create(name="BK PopTest", slug="bk-poptest")

        # PN: due label distinte; la label 2025/2026 compare su due leghe
        # diverse -> deve generare UNA sola Season (coppia distinta).
        League.objects.create(name="PN A", sport=sport_pn, category="SENIOR", season="2024/2025", slug="pn-a")
        League.objects.create(name="PN B", sport=sport_pn, category="SENIOR", season="2025/2026", slug="pn-b")
        League.objects.create(name="PN C", sport=sport_pn, category="U16", season="2025/2026", slug="pn-c")

        # BK: una sola label distinta.
        League.objects.create(name="BK A", sport=sport_bk, category="SENIOR", season="2023/2024", slug="bk-a")

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
        League.objects.create(name="L A", sport=self.sport, category="SENIOR", season="2024/2025", slug="vt-a")
        League.objects.create(name="L B", sport=self.sport, category="SENIOR", season="2025/2026", slug="vt-b")

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
