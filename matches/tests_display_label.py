"""Test della catena display_label a tre livelli (DEBITI §10.38).

SportEventConfig e' vuota su dev e prod: senza un fallback a codice, la resa
mostrava il codice tecnico grezzo (es. "RED_CARD") all'utente. Qui si verifica
che, con SportEventConfig vuota, display_label restituisca l'etichetta leggibile
da EVENT_LABELS, e che SportEventConfig resti l'override piu' alto quando c'e'.
"""
from django.test import TestCase
from django.utils import timezone

from core.models import Sport, Society, League, Team
from matches.models import Match, MatchEvent, SportEventConfig
from matches.event_types import EVENT_TYPE_RED_CARD, EVENT_TYPE_TIMEOUT, DEFAULT_EVENT_TYPES, EVENT_LABELS


class DisplayLabelChainTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.soc_home = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco")
        self.soc_away = Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia")
        self.league = League.objects.create(name="Serie A1", sport=self.sport, slug="serie-a1")
        self.team_home = Team.objects.create(society=self.soc_home, league=self.league)
        self.team_away = Team.objects.create(society=self.soc_away, league=self.league)
        self.match = Match.objects.create(
            league=self.league, home_team=self.team_home, away_team=self.team_away,
            match_date=timezone.now(),
        )

    def _event(self, code):
        return MatchEvent.objects.create(
            match=self.match, event_type=code, team=self.team_home, minute=1, quarter=1,
        )

    def test_empty_config_returns_readable_label_not_code(self):
        """SportEventConfig vuota: display_label da' l'etichetta leggibile, non il codice."""
        self.assertEqual(SportEventConfig.objects.count(), 0)
        ev = self._event(EVENT_TYPE_RED_CARD)
        self.assertEqual(ev.display_label, "Cartellino Rosso")
        self.assertNotEqual(ev.display_label, EVENT_TYPE_RED_CARD)

    def test_team_level_event_readable_label(self):
        ev = self._event(EVENT_TYPE_TIMEOUT)
        self.assertEqual(ev.display_label, "Timeout Squadra")

    def test_sport_event_config_overrides(self):
        """SportEventConfig resta l'override piu' alto quando presente."""
        SportEventConfig.objects.create(
            sport=self.sport, event_code=EVENT_TYPE_RED_CARD, label="Espulsione definitiva",
        )
        ev = self._event(EVENT_TYPE_RED_CARD)
        self.assertEqual(ev.display_label, "Espulsione definitiva")

    def test_unknown_code_falls_back_to_raw(self):
        """Un tipo mai visto ripiega sul codice grezzo (ultima spiaggia)."""
        ev = self._event("MAI_VISTO")
        self.assertEqual(ev.display_label, "MAI_VISTO")

    def test_event_labels_cover_all_default_types(self):
        """EVENT_LABELS copre ogni tipo in DEFAULT_EVENT_TYPES (nessun buco di etichetta)."""
        for e in DEFAULT_EVENT_TYPES:
            self.assertIn(e["code"], EVENT_LABELS)
            self.assertTrue(EVENT_LABELS[e["code"]])
