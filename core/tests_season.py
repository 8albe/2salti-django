from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

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
