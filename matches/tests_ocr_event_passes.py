"""
Test della doppia estrazione per zona sugli EVENTI (§8.24 stadio B):
  - compare_event_passes (matches.services.ocr_double_extraction): confronto puro
    fra due letture di eventi sulla chiave (type, quarter, clock), payload (cap, team);
  - i due check da regolamento (matches.event_types): max 2 timeout/squadra, max 1
    espulsione definitiva/giocatore — e la loro emersione come WARNING (mai blocker)
    in OCRSchemaValidator.validate_coherence.

Funzioni pure: nessun provider OCR, nessuna chiamata reale, nessun accesso a DB.
"""
from django.test import SimpleTestCase

from matches.services.ocr_double_extraction import compare_event_passes
from matches.event_types import (
    timeouts_over_team_limit, definitive_exclusions_over_player_limit,
    count_timeouts_per_team, count_definitive_exclusions_per_player,
)
from matches.services.schema import OCRSchemaValidator


def _ev(**kw):
    return kw


def _pass(events):
    return {"events": events}


class CompareEventPassesTest(SimpleTestCase):
    def test_identical_events_agree(self):
        e = [_ev(type="GOAL", quarter=1, clock="7:40", cap=9, team="home")]
        res = compare_event_passes(_pass(e), _pass([dict(e[0])]))
        self.assertFalse(res["diverges"])
        self.assertEqual(res["counts"]["agree"], 1)
        self.assertEqual(res["events"][0]["cap_status"], "agree")
        self.assertEqual(res["events"][0]["team_status"], "agree")

    def test_cap_divergence_flags_review(self):
        first = _pass([_ev(type="GOAL", quarter=1, clock="7:40", cap=9, team="home")])
        second = _pass([_ev(type="GOAL", quarter=1, clock="7:40", cap=8, team="home")])
        res = compare_event_passes(first, second)
        self.assertTrue(res["diverges"])
        self.assertTrue(res["review"])
        self.assertEqual(res["events"][0]["cap_status"], "diverge")
        self.assertEqual(len(res["diverging_events"]), 1)

    def test_team_divergence_flags_review(self):
        """L'errore di attribuzione squadra: stesso evento, team diverso fra i due passaggi."""
        first = _pass([_ev(type="TIMEOUT", quarter=4, clock="2:00", cap=None, team="home")])
        second = _pass([_ev(type="TIMEOUT", quarter=4, clock="2:00", cap=None, team="away")])
        res = compare_event_passes(first, second)
        self.assertTrue(res["diverges"])
        self.assertEqual(res["events"][0]["team_status"], "diverge")

    def test_event_only_in_one_pass_is_abstain(self):
        first = _pass([_ev(type="GOAL", quarter=1, clock="7:40", cap=9, team="home")])
        second = _pass([])
        res = compare_event_passes(first, second)
        self.assertFalse(res["diverges"])
        self.assertEqual(res["events"][0]["presence"], "first_only")
        self.assertEqual(res["events"][0]["cap_status"], "abstain")
        self.assertEqual(res["counts"]["first_only"], 1)

    def test_null_cap_on_one_side_is_abstain_not_divergence(self):
        first = _pass([_ev(type="GOAL", quarter=1, clock="7:40", cap=9, team="home")])
        second = _pass([_ev(type="GOAL", quarter=1, clock="7:40", cap=None, team="home")])
        res = compare_event_passes(first, second)
        self.assertFalse(res["diverges"])
        self.assertEqual(res["events"][0]["cap_status"], "abstain")
        self.assertEqual(res["events"][0]["team_status"], "agree")

    def test_different_clock_makes_them_distinct_events(self):
        first = _pass([_ev(type="GOAL", quarter=1, clock="7:40", cap=9, team="home")])
        second = _pass([_ev(type="GOAL", quarter=1, clock="6:12", cap=9, team="home")])
        res = compare_event_passes(first, second)
        # Chiavi diverse -> due eventi distinti, ciascuno one-only, nessuna divergenza.
        self.assertFalse(res["diverges"])
        self.assertEqual(res["counts"]["first_only"], 1)
        self.assertEqual(res["counts"]["second_only"], 1)

    def test_ambiguous_multiplicity_flagged(self):
        dup = [
            _ev(type="GOAL", quarter=2, clock=None, cap=7, team="home"),
            _ev(type="GOAL", quarter=2, clock=None, cap=8, team="home"),
        ]
        res = compare_event_passes(_pass(dup), _pass([dict(dup[0])]))
        self.assertTrue(res["events"][0]["ambiguous_multiplicity"])

    def test_empty_inputs_do_not_crash(self):
        self.assertFalse(compare_event_passes({}, {})["diverges"])
        self.assertFalse(compare_event_passes(None, None)["diverges"])


class RegolamentoTimeoutCheckTest(SimpleTestCase):
    def _events(self, home_to, away_to):
        return (
            [_ev(type="TIMEOUT", team="home") for _ in range(home_to)]
            + [_ev(type="TIMEOUT", team="away") for _ in range(away_to)]
        )

    def test_two_timeouts_per_team_is_ok(self):
        self.assertEqual(timeouts_over_team_limit(self._events(2, 2)), [])

    def test_three_timeouts_one_team_over_limit(self):
        over = timeouts_over_team_limit(self._events(3, 1))
        self.assertEqual(over, [("home", 3)])

    def test_count_timeouts_per_team(self):
        self.assertEqual(count_timeouts_per_team(self._events(2, 1)), {"home": 2, "away": 1})

    def test_timeout_over_limit_surfaces_as_warning_not_blocker(self):
        data = {
            "scores": {"final_score": "5-3"},
            "teams": {},
            "events": self._events(3, 0),
        }
        _, warnings = OCRSchemaValidator.validate_coherence(data)
        self.assertTrue(any("Timeout oltre il limite" in w for w in warnings))
        # Mai un blocker: assess_publish_readiness non lo promuove.
        safe, blockers, _ = OCRSchemaValidator.assess_publish_readiness({
            "scores": {"final_score": "5-3"},
            "match_info": {"home_team": "A", "away_team": "B"},
            "teams": {"home": {"players": [{"number": 1, "name": "X"}]}},
            "events": self._events(3, 0) + [_ev(type="GOAL", team="home", player_name="X", cap=1)],
            "reconciliation": {"home_players": {"X": 1}},
        })
        self.assertFalse(any("Timeout oltre il limite" in b for b in blockers))


class RegolamentoDefinitiveExclusionCheckTest(SimpleTestCase):
    def test_one_edcs_per_player_is_ok(self):
        events = [_ev(type="EXCLUSION_DEF", team="home", cap=9)]
        self.assertEqual(definitive_exclusions_over_player_limit(events), [])

    def test_two_edcs_same_cap_over_limit(self):
        """Rosso duplicato per calottina: stesso giocatore, due EDCS -> oltre il limite."""
        events = [
            _ev(type="EXCLUSION_DEF", team="home", cap=9),
            _ev(type="EXCLUSION_DEF", team="home", cap=9),
        ]
        over = definitive_exclusions_over_player_limit(events)
        self.assertEqual(len(over), 1)
        self.assertEqual(over[0][0], "home")
        self.assertEqual(over[0][2], 2)

    def test_two_edcs_different_players_ok(self):
        events = [
            _ev(type="EXCLUSION_DEF", team="home", cap=9),
            _ev(type="EXCLUSION_DEF", team="home", cap=7),
        ]
        self.assertEqual(definitive_exclusions_over_player_limit(events), [])

    def test_count_edcs_per_player_uses_cap_identity(self):
        events = [_ev(type="EXCLUSION_DEF", team="away", cap=12)]
        self.assertEqual(count_definitive_exclusions_per_player(events), {("away", "#12"): 1})

    def test_edcs_over_limit_surfaces_as_warning_not_blocker(self):
        data = {
            "scores": {"final_score": "5-3"},
            "teams": {},
            "events": [
                _ev(type="EXCLUSION_DEF", team="home", cap=9),
                _ev(type="EXCLUSION_DEF", team="home", cap=9),
            ],
        }
        _, warnings = OCRSchemaValidator.validate_coherence(data)
        self.assertTrue(any("Espulsioni definitive oltre il limite" in w for w in warnings))
