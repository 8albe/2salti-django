from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import League, Sport
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
