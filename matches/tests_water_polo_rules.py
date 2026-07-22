"""Regole di dominio pallanuoto derivate dagli eventi (non estratte dal modello).

- Espulsioni per giocatore: alla 3a il giocatore e' fuori partita ("fouled out").
  3 e' il massimo possibile: un 4o valore e' un errore (di trascrizione o di estrazione).
- Validazione automatica: sui casi gold (trascrizione umana) e sui dati OCR
  (validate_coherence) un giocatore con >3 espulsioni deve emergere in modo rumoroso.
"""
import glob
import json
import os

from django.conf import settings
from django.test import SimpleTestCase

from matches.event_types import (
    EVENT_TYPE_EXCLUSION_20,
    FOUL_OUT_EXCLUSIONS,
    count_exclusions_per_player,
    fouled_out_players,
    players_over_exclusion_limit,
)
from matches.services.schema import OCRSchemaValidator


def _exclusions(spec):
    """spec: lista di (team, identita', quante volte) -> lista eventi EXCLUSION_20."""
    events = []
    for team, ident, n in spec:
        key = {"cap": ident} if isinstance(ident, int) else {"player_name": ident}
        events += [{"type": EVENT_TYPE_EXCLUSION_20, "team": team, **key}] * n
    return events


class ExclusionCountingHelpersTest(SimpleTestCase):
    def test_counts_by_team_and_identity(self):
        events = _exclusions([("away", 7, 3), ("home", 7, 1), ("away", 12, 2)])
        counts = count_exclusions_per_player(events)
        self.assertEqual(counts[("away", "#7")], 3)   # calottina 7 ospite: 3
        self.assertEqual(counts[("home", "#7")], 1)   # calottina 7 casa: giocatore diverso
        self.assertEqual(counts[("away", "#12")], 2)

    def test_events_without_identity_are_ignored(self):
        events = [{"type": EVENT_TYPE_EXCLUSION_20, "team": "home"}]  # nessun cap/nome
        self.assertEqual(count_exclusions_per_player(events), {})

    def test_fouled_out_is_three_or_more(self):
        events = _exclusions([("away", 3, 3), ("away", 5, 2)])
        fouled = dict((f"{t}{i}", c) for t, i, c in fouled_out_players(events))
        self.assertEqual(fouled, {"away#3": 3})   # #5 (2) non e' fouled out

    def test_over_limit_is_strictly_more_than_three(self):
        # 3 e' legittimo (fouled out), 4 e' impossibile a regolamento.
        self.assertEqual(players_over_exclusion_limit(_exclusions([("home", 9, 3)])), [])
        over = players_over_exclusion_limit(_exclusions([("home", 9, 4)]))
        self.assertEqual(over, [("home", "#9", 4)])
        self.assertEqual(FOUL_OUT_EXCLUSIONS, 3)


class ExclusionLimitInOcrCoherenceTest(SimpleTestCase):
    def test_more_than_three_exclusions_warns(self):
        data = {
            "scores": {"final_score": "1-0", "quarters": {}},
            "events": _exclusions([("home", "Rossi M.", 4)]),
            "teams": {}, "match_info": {}, "metadata": {},
        }
        _, warnings = OCRSchemaValidator.validate_coherence(data)
        self.assertTrue(any("oltre il limite" in w and "rossi m." in w.lower() for w in warnings))

    def test_exactly_three_does_not_warn(self):
        data = {
            "scores": {"final_score": "1-0", "quarters": {}},
            "events": _exclusions([("home", "Rossi M.", 3)]),
            "teams": {}, "match_info": {}, "metadata": {},
        }
        _, warnings = OCRSchemaValidator.validate_coherence(data)
        self.assertFalse(any("oltre il limite" in w for w in warnings))


class GoldCasesExclusionLimitTest(SimpleTestCase):
    """Validazione automatica dei casi gold: nessun giocatore supera 3 espulsioni.

    Sostituisce il check fatto a mano sull'Olympic. Una trascrizione futura che sfora
    fa fallire QUESTO test in modo rumoroso: >3 non e' mai un dato valido.
    """

    def _cases(self):
        cases_dir = os.path.join(settings.BASE_DIR, "docs", "ocr_gold_standard", "cases")
        for path in sorted(glob.glob(os.path.join(cases_dir, "*.json"))):
            with open(path, encoding="utf-8") as f:
                yield os.path.basename(path), json.load(f)

    def test_no_gold_truth_player_exceeds_three_exclusions(self):
        checked_any_events = False
        for name, case in self._cases():
            events = (case.get("truth") or {}).get("events")
            if not isinstance(events, list) or not events:
                continue
            checked_any_events = True
            over = players_over_exclusion_limit(events)
            self.assertEqual(
                over, [],
                msg=f"Caso gold {name}: giocatori con >3 espulsioni {over} — "
                    f"errore di trascrizione umana, non un dato valido.",
            )
        # almeno il caso Olympic ha eventi in truth: il test misura qualcosa.
        self.assertTrue(checked_any_events, "Nessun caso gold con truth.events da validare.")
