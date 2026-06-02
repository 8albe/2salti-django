"""Regression tests for the global navbar in templates/base.html.

BUG-001: la pagina /sport/<slug>/ sollevava un'eccezione quando lo sport non
aveva ancora leghe associate, perche' la navbar (riga 347 di base.html)
risolveva l'URL `league_stats` con `sport.leagues.first.slug` -> None.
"""
from django.test import TestCase
from django.urls import reverse

from core.models import Sport


class SportDetailNavbarWithoutLeaguesTests(TestCase):
    def test_sport_detail_renders_when_sport_has_no_leagues(self):
        sport = Sport.objects.create(name="SportSenzaLeghe", slug="sport-senza-leghe")
        response = self.client.get(reverse('sport_detail', args=[sport.slug]))
        self.assertEqual(response.status_code, 200)
