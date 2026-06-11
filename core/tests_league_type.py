"""Macro 16 Fase 3: tipo lega (lista chiusa), helper "dei grandi", display.

Copre il campo League.league_type, la property is_senior_league (gate del
prestito, Fase 4), il mapping display LEAGUE_TYPE_DISPLAY (dizionario in
codice, decisione D1) e la funzione di classificazione per nome della data
migration core/0016.
"""
import importlib

from django.test import TestCase

from core.models import League, Sport

_mig = importlib.import_module("core.migrations.0016_classify_league_type")


class LeagueTypeModelTests(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn-lt")

    def _league(self, league_type=None, **kw):
        # name unico: unique_together (name, season, group_name) su League.
        kw.setdefault("name", f"Lega LT {league_type or 'none'}")
        kw.setdefault("category", "SENIOR")
        kw.setdefault("slug", f"lega-lt-{league_type or 'none'}")
        return League.objects.create(
            sport=self.sport, league_type=league_type, **kw
        )

    def test_closed_list_values(self):
        self.assertEqual(
            set(League.LeagueType.values),
            {'A1', 'A2', 'B', 'C', 'D', 'U10', 'U12', 'U14', 'U16', 'U18', 'U20'},
        )

    def test_senior_types_subset_of_closed_list(self):
        self.assertEqual(
            League.SENIOR_LEAGUE_TYPES, frozenset({'A1', 'A2', 'B', 'C', 'D'})
        )
        self.assertTrue(
            League.SENIOR_LEAGUE_TYPES <= set(League.LeagueType.values)
        )

    def test_is_senior_league(self):
        for t in ('A1', 'A2', 'B', 'C', 'D'):
            self.assertTrue(self._league(t).is_senior_league, t)
        for t in ('U10', 'U12', 'U14', 'U16', 'U18', 'U20'):
            self.assertFalse(self._league(t).is_senior_league, t)

    def test_unclassified_league_is_not_senior(self):
        # league_type NULL non passa il gate "dei grandi" (prestito vietato).
        self.assertFalse(self._league(None).is_senior_league)

    def test_display_mapping_complete_and_traditional(self):
        # Ogni tipo della lista chiusa ha un display.
        self.assertEqual(
            set(League.LEAGUE_TYPE_DISPLAY), set(League.LeagueType.values)
        )
        # Etichette tradizionali giovanili (decisione D1 2026-06-11).
        self.assertEqual(League.LEAGUE_TYPE_DISPLAY['U10'], 'Pulcini')
        self.assertEqual(League.LEAGUE_TYPE_DISPLAY['U12'], 'Esordienti')
        self.assertEqual(League.LEAGUE_TYPE_DISPLAY['U14'], 'Ragazzi')
        self.assertEqual(League.LEAGUE_TYPE_DISPLAY['U16'], 'Allievi')
        self.assertEqual(League.LEAGUE_TYPE_DISPLAY['U18'], 'Juniores')
        self.assertEqual(League.LEAGUE_TYPE_DISPLAY['U20'], 'Under 20')

    def test_league_type_label(self):
        self.assertEqual(self._league('U16').league_type_label, 'Allievi')
        self.assertEqual(self._league('B').league_type_label, 'Serie B')
        self.assertEqual(self._league(None).league_type_label, '')


class ClassifyLeagueTypeByNameTests(TestCase):
    """Unit test della derivazione per nome (data migration core/0016)."""

    def test_under_marker_wins(self):
        self.assertEqual(_mig._classify("Allievi nazionali - U16A"), "U16")
        self.assertEqual(_mig._classify("Juniores M - U18A"), "U18")
        self.assertEqual(_mig._classify("u20 regionale"), "U20")

    def test_traditional_labels(self):
        self.assertEqual(_mig._classify("Esordienti girone unico"), "U12")
        self.assertEqual(_mig._classify("Torneo Pulcini"), "U10")
        self.assertEqual(_mig._classify("RAGAZZI regionali"), "U14")

    def test_senior_serie_pattern(self):
        self.assertEqual(_mig._classify("serie B Maschile"), "B")
        self.assertEqual(_mig._classify("Serie A1 Femminile"), "A1")
        self.assertEqual(_mig._classify("SERIE C"), "C")

    def test_unrecognized_returns_none(self):
        # "Null invece di invenzione": mai indovinare.
        self.assertIsNone(_mig._classify("Senior"))
        self.assertIsNone(_mig._classify("Campionato Master"))

    def test_classify_runpython_idempotent_and_null_safe(self):
        sport = Sport.objects.create(name="PN ClassTest", slug="pn-classtest")
        recognized = League.objects.create(
            name="serie B Maschile", sport=sport, category="SENIOR",
            slug="lt-b", league_type=None,
        )
        umbrella = League.objects.create(
            name="Senior", sport=sport, category="SENIOR",
            slug="lt-senior", league_type=None,
        )

        from django.apps import apps
        _mig.classify_league_type(apps, None)
        recognized.refresh_from_db()
        umbrella.refresh_from_db()
        self.assertEqual(recognized.league_type, "B")
        self.assertIsNone(umbrella.league_type)

        # Seconda esecuzione: stato identico (idempotenza).
        _mig.classify_league_type(apps, None)
        recognized.refresh_from_db()
        umbrella.refresh_from_db()
        self.assertEqual(recognized.league_type, "B")
        self.assertIsNone(umbrella.league_type)
