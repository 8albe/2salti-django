"""
Test dell'identita' dell'autore PER CALOTTINA negli eventi (schema V3.5, §8.24).

Copre le tre superfici toccate dallo stadio 1 del giro:
  - riconciliazione per (team, cap) nel converter (MatchDataConverter.get_events_data);
  - validazione opzionale del campo `cap` nello schema (OCRSchemaValidator.validate);
  - warning "calottina non nel roster" (OCRSchemaValidator.validate_coherence).

Funzioni pure: nessun provider OCR, nessuna chiamata reale, nessun accesso a DB.
"""
from django.test import SimpleTestCase

from matches.services.converters import MatchDataConverter
from matches.services.schema import OCRSchemaValidator


def _data(events, home_players=None, away_players=None,
          home_recon=None, away_recon=None):
    """normalized_data minimale con roster e reconciliation controllati."""
    return {
        "events": events,
        "teams": {
            "home": {"players": home_players or []},
            "away": {"players": away_players or []},
        },
        "reconciliation": {
            "home_players": home_recon or {},
            "away_players": away_recon or {},
        },
    }


HOME_ROSTER = [
    {"number": 9, "name": "ROSSI MARIO"},
    {"number": 7, "name": "BIANCHI LUCA"},
]
HOME_RECON = {"ROSSI MARIO": 101, "BIANCHI LUCA": 102}


class CapReconciliationTest(SimpleTestCase):
    def test_goal_with_cap_and_name_attaches_by_cap(self):
        data = _data(
            [{"type": "GOAL", "team": "home", "cap": 9, "player_name": "ROSSI MARIO"}],
            home_players=HOME_ROSTER, home_recon=HOME_RECON,
        )
        out = MatchDataConverter.get_events_data(data)
        self.assertEqual(out[0]["player_id"], 101)
        self.assertEqual(out[0]["cap"], 9)

    def test_goal_with_cap_and_null_name_still_attaches_by_cap(self):
        """Il nome null NON e' un fallimento quando la calottina c'e'."""
        data = _data(
            [{"type": "GOAL", "team": "home", "cap": 7, "player_name": None}],
            home_players=HOME_ROSTER, home_recon=HOME_RECON,
        )
        out = MatchDataConverter.get_events_data(data)
        self.assertEqual(out[0]["player_id"], 102)

    def test_goal_with_misread_name_but_cap_attaches_by_cap(self):
        """La calottina governa anche se il nome e' misletto: e' il guadagno del giro."""
        data = _data(
            [{"type": "GOAL", "team": "home", "cap": 9, "player_name": "R0SS1"}],
            home_players=HOME_ROSTER, home_recon=HOME_RECON,
        )
        out = MatchDataConverter.get_events_data(data)
        self.assertEqual(out[0]["player_id"], 101)

    def test_goal_with_name_and_null_cap_falls_back_to_name(self):
        data = _data(
            [{"type": "GOAL", "team": "home", "cap": None, "player_name": "BIANCHI LUCA"}],
            home_players=HOME_ROSTER, home_recon=HOME_RECON,
        )
        out = MatchDataConverter.get_events_data(data)
        self.assertEqual(out[0]["player_id"], 102)

    def test_cap_not_in_roster_produces_no_invented_attach(self):
        """Una calottina fuori roster non aggancia nulla (nessun aggancio inventato)."""
        data = _data(
            [{"type": "GOAL", "team": "home", "cap": 99, "player_name": "FANTASMA"}],
            home_players=HOME_ROSTER, home_recon=HOME_RECON,
        )
        out = MatchDataConverter.get_events_data(data)
        self.assertIsNone(out[0]["player_id"])
        self.assertEqual(out[0]["cap"], 99)

    def test_cap_in_roster_but_unreconciled_stays_none(self):
        """Cap nel roster ma roster non riconciliato a DB: player_id None, nessun fallback nome."""
        data = _data(
            [{"type": "GOAL", "team": "home", "cap": 9, "player_name": "ROSSI MARIO"}],
            home_players=HOME_ROSTER, home_recon={},  # nessuna riconciliazione a DB
        )
        out = MatchDataConverter.get_events_data(data)
        self.assertIsNone(out[0]["player_id"])

    def test_timeout_has_no_cap_no_attach(self):
        data = _data(
            [{"type": "TIMEOUT", "team": "home", "cap": None, "player_name": None}],
            home_players=HOME_ROSTER, home_recon=HOME_RECON,
        )
        out = MatchDataConverter.get_events_data(data)
        self.assertIsNone(out[0]["player_id"])
        self.assertIsNone(out[0]["cap"])


class CapSchemaValidationTest(SimpleTestCase):
    def _payload(self, events):
        return {
            "metadata": {"confidence": 0.9},
            "match_info": {"home_team": "A", "away_team": "B"},
            "scores": {"final_score": "1-0"},
            "teams": {},
            "events": events,
        }

    def test_integer_cap_is_valid(self):
        ok, _ = OCRSchemaValidator.validate(
            self._payload([{"type": "GOAL", "cap": 9}])
        )
        self.assertTrue(ok)

    def test_null_cap_is_valid(self):
        ok, _ = OCRSchemaValidator.validate(
            self._payload([{"type": "GOAL", "cap": None}])
        )
        self.assertTrue(ok)

    def test_missing_cap_is_valid_backcompat(self):
        ok, _ = OCRSchemaValidator.validate(
            self._payload([{"type": "GOAL"}])
        )
        self.assertTrue(ok)

    def test_non_integer_cap_is_rejected(self):
        ok, msg = OCRSchemaValidator.validate(
            self._payload([{"type": "GOAL", "cap": "nove"}])
        )
        self.assertFalse(ok)
        self.assertIn("cap", msg)


class CapNotInRosterWarningTest(SimpleTestCase):
    def test_cap_absent_from_roster_warns(self):
        data = _data(
            [{"type": "GOAL", "team": "home", "cap": 99}],
            home_players=HOME_ROSTER, home_recon=HOME_RECON,
        )
        _, warnings = OCRSchemaValidator.validate_coherence(data)
        self.assertTrue(any("Calottina evento non nel roster" in w and "99" in w for w in warnings))

    def test_cap_present_in_roster_no_warning(self):
        data = _data(
            [{"type": "GOAL", "team": "home", "cap": 9}],
            home_players=HOME_ROSTER, home_recon=HOME_RECON,
        )
        _, warnings = OCRSchemaValidator.validate_coherence(data)
        self.assertFalse(any("Calottina evento non nel roster" in w for w in warnings))

    def test_no_roster_no_cap_warning(self):
        """Senza roster estratto non si puo' dire che la calottina 'non c'e'."""
        data = _data(
            [{"type": "GOAL", "team": "home", "cap": 99}],
            home_players=[], home_recon={},
        )
        _, warnings = OCRSchemaValidator.validate_coherence(data)
        self.assertFalse(any("Calottina evento non nel roster" in w for w in warnings))
