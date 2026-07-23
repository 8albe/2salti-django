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
    DEFINITIVE_EXCLUSION_ARTICLES,
    EVENT_TYPE_EXCLUSION_20,
    EVENT_TYPE_EXCLUSION_DEF,
    FOUL_OUT_EXCLUSIONS,
    classify_definitive_exclusion,
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


class DefinitiveExclusionMappingTest(SimpleTestCase):
    """Mappatura articolo -> tipo di espulsione definitiva (tabella dati, non nel prompt).

    La tassonomia degli articoli vive nel NOSTRO codice: il modello estrae l'articolo
    verbatim, la classificazione avviene a valle. Un articolo mai visto NON si inventa:
    resta grezzo nel ramo 'sconosciuto'.
    """

    def test_9_13_is_misconduct_no_penalty(self):
        c = classify_definitive_exclusion("9.13")
        self.assertTrue(c["known"])
        self.assertEqual(c["kind"], "misconduct")
        self.assertFalse(c["penalty_awarded"])
        self.assertEqual(c["article"], "9.13")

    def test_9_14_is_brutality_with_penalty(self):
        c = classify_definitive_exclusion("9.14")
        self.assertTrue(c["known"])
        self.assertEqual(c["kind"], "brutality")
        self.assertTrue(c["penalty_awarded"])
        self.assertTrue(c["next_matches_ban"])

    def test_unknown_article_is_preserved_raw_not_invented(self):
        # Un articolo mai visto non blocca e non si inventa: ramo 'sconosciuto',
        # stringa grezza conservata.
        c = classify_definitive_exclusion("9.99")
        self.assertFalse(c["known"])
        self.assertEqual(c["kind"], "unknown")
        self.assertEqual(c["article"], "9.99")   # grezzo, conservato
        self.assertIsNone(c["penalty_awarded"])
        self.assertIsNone(c["label"])

    def test_only_two_verified_articles_in_table(self):
        # La tabella contiene SOLO i due articoli verificati a mano.
        self.assertEqual(set(DEFINITIVE_EXCLUSION_ARTICLES), {"9.13", "9.14"})

    def test_none_and_whitespace_do_not_crash(self):
        self.assertFalse(classify_definitive_exclusion(None)["known"])
        self.assertEqual(classify_definitive_exclusion("  9.13 ")["article"], "9.13")


class Referto8GoldDerivedAssertionsTest(SimpleTestCase):
    """Asserzioni derivate sul referto 8 (Unime vs Nautilus Roma), calcolate a valle
    dalla truth eventi. Sono valori esterni verificati a mano: se una fallisce, la
    trascrizione ha un errore, non è un bug da aggirare."""

    CASE = "2026-03-28_unime_vs_nautilus-roma.json"

    def _case(self):
        path = os.path.join(
            settings.BASE_DIR, "docs", "ocr_gold_standard", "cases", self.CASE
        )
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _events(self):
        return self._case()["truth"]["events"]

    def test_partials_and_final_match(self):
        goals = [e for e in self._events() if e["type"] == "GOAL"]
        per_q = {q: [0, 0] for q in (1, 2, 3, 4)}
        for g in goals:
            per_q[g["quarter"]][0 if g["team"] == "home" else 1] += 1
        self.assertEqual(per_q, {1: [4, 2], 2: [3, 1], 3: [3, 4], 4: [2, 3]})
        self.assertEqual(
            (sum(per_q[q][0] for q in per_q), sum(per_q[q][1] for q in per_q)),
            (12, 10),
        )

    def test_fouled_out_is_exactly_home_3_and_home_12(self):
        fo = {(t, i) for t, i, c in fouled_out_players(self._events())}
        self.assertEqual(fo, {("home", "#3"), ("home", "#12")})

    def test_definitive_exclusion_not_counted_among_20s(self):
        # L'espulsione definitiva di home #7 (art. 9.13) è un tipo diverso e NON
        # entra nel conteggio delle esclusioni di 20 secondi: #7 resta a 1.
        counts = count_exclusions_per_player(self._events())
        self.assertEqual(counts.get(("home", "#7")), 1)
        defs = [e for e in self._events() if e["type"] == EVENT_TYPE_EXCLUSION_DEF]
        self.assertEqual(len(defs), 1)
        self.assertEqual(defs[0]["regulation_article"], "9.13")
        self.assertEqual(defs[0]["sanction_sigla"], "EDCS")

    def test_article_never_enters_the_score_progression(self):
        # Trappola: l'articolo "9.13" sta in colonna punteggio ma NON è un punteggio.
        # Nessun gol lo porta come score_after, e la progressione dei gol è pulita.
        goals = [e for e in self._events() if e["type"] == "GOAL"]
        scores_after = {g["score_after"] for g in goals}
        self.assertNotIn("9.13", scores_after)
        self.assertNotIn("9-13", scores_after)
        sh = sa = 0
        for g in goals:
            if g["team"] == "home":
                sh += 1
            else:
                sa += 1
            self.assertEqual(g["score_after"], f"{sh}-{sa}")

    def test_timeouts_have_no_cap(self):
        tos = [e for e in self._events() if e["type"] == "TIMEOUT"]
        self.assertEqual(len(tos), 3)
        for e in tos:
            self.assertNotIn("cap", e)
            self.assertNotIn("player_name", e)

    def test_second_quarter_penalty_is_not_coupled_to_any_goal(self):
        # Rigore NON realizzato del 2° tempo (fallo home #10 @ 6:20): nessun gol a
        # quel clock+periodo. La regola di accoppiamento è derivata, non osservata.
        events = self._events()
        pens = [e for e in events if e["type"] == EVENT_TYPE_EXCLUSION_20 and e.get("is_penalty")]
        self.assertEqual(len(pens), 3)
        goals = [e for e in events if e["type"] == "GOAL"]

        def goal_at(q, clock):
            return [g for g in goals if g["quarter"] == q and g["clock"] == clock]

        # P2 6:20: nessun gol accoppiato (rigore non realizzato)
        self.assertEqual(goal_at(2, "6:20"), [])
        # P3 6:48 e P4 4:23: rigore realizzato, gol dell'away allo stesso clock
        self.assertEqual([(g["team"], g["cap"]) for g in goal_at(3, "6:48")], [("away", 9)])
        self.assertEqual([(g["team"], g["cap"]) for g in goal_at(4, "4:23")], [("away", 4)])
