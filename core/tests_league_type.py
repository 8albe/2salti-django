"""Macro 16 Fase 3: tipo lega (lista chiusa), helper "dei grandi", display.

Copre il campo League.league_type, la property is_senior_league (gate del
prestito, Fase 4), il mapping display LEAGUE_TYPE_DISPLAY (dizionario in
codice, decisione D1) e la funzione di classificazione per nome della data
migration core/0016.
"""
import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import League, LeagueStanding, Season, Society, Sport, Team

_mig = importlib.import_module("core.migrations.0016_classify_league_type")
_rifusione = importlib.import_module(
    "core.migrations.0017_rifusione_scaffolding_senior"
)

User = get_user_model()


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


class RifusioneScaffoldingSeniorTests(TestCase):
    """Data migration core/0017 (D4-A): la lega-ombrello 'Senior' diventa
    'serie C Maschile' (tipo C) IN PLACE — pk conservato, link intatti."""

    def setUp(self):
        self.sport = Sport.objects.create(name="PN RifTest", slug="pn-riftest")
        self.season = Season.objects.create(
            sport=self.sport, label='2025/2026', is_current=True
        )
        self.society = Society.objects.create(
            name="Soc Rif", slug="soc-rif", sport=self.sport, city="Roma"
        )
        self.umbrella = League.objects.create(
            name="Senior", sport=self.sport, category="SENIOR",
            season="2025/2026", season_fk=self.season, slug="senior-riftest",
            league_type=None,
        )
        self.team = Team.objects.create(
            society=self.society, category="SENIOR", league=self.umbrella,
            name="Team Rif", slug="team-riftest",
        )
        self.standing = LeagueStanding.objects.create(
            league=self.umbrella, team=self.team, season="2025/2026"
        )
        self.user = User.objects.create_user(username='rif_user', role='athlete')
        from management.models import Membership
        self.membership = Membership.objects.create(
            user=self.user, society=self.society, team=self.team,
            role='PLAYER', season=self.season,
        )

    def test_umbrella_converted_in_place_links_intact(self):
        _rifusione.rifusione_scaffolding_senior(django_apps, None)

        self.umbrella.refresh_from_db()
        self.assertEqual(self.umbrella.name, "serie C Maschile")
        self.assertEqual(self.umbrella.league_type, "C")
        self.assertTrue(self.umbrella.is_senior_league)
        self.assertIn("serie-c-maschile", self.umbrella.slug)
        # Stesso pk: team, standing e membership restano agganciati.
        self.team.refresh_from_db()
        self.assertEqual(self.team.league_id, self.umbrella.pk)
        self.standing.refresh_from_db()
        self.assertEqual(self.standing.league_id, self.umbrella.pk)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.team_id, self.team.pk)

    def test_idempotent_second_run_no_op(self):
        _rifusione.rifusione_scaffolding_senior(django_apps, None)
        self.umbrella.refresh_from_db()
        snapshot = (self.umbrella.name, self.umbrella.league_type, self.umbrella.slug)

        _rifusione.rifusione_scaffolding_senior(django_apps, None)
        self.umbrella.refresh_from_db()
        self.assertEqual(
            (self.umbrella.name, self.umbrella.league_type, self.umbrella.slug),
            snapshot,
        )

    def test_real_senior_league_with_type_not_touched(self):
        # Una lega legittimamente chiamata "Senior" ma GIA' classificata non
        # viene rifusa (filtro: league_type IS NULL).
        classified = League.objects.create(
            name="Senior", sport=self.sport, category="SENIOR",
            season="2024/2025", slug="senior-classificata", league_type="D",
        )
        _rifusione.rifusione_scaffolding_senior(django_apps, None)
        classified.refresh_from_db()
        self.assertEqual(classified.name, "Senior")
        self.assertEqual(classified.league_type, "D")
