"""
Test per matches/services/ocr_bench_analysis.py (analisi cross-check §8.20).

Nessuna chiamata reale: proposte sintetiche in memoria. Verifica la somma
dell'asse a, il bucketing del cross-check, le metriche di recall del disaccordo
e il conteggio eventi del referto 8.
"""
from django.test import SimpleTestCase

from matches.services import ocr_bench_analysis as A


def _agg(truth, *value_counts):
    """Costruisce un'entry aggregate: value_counts = (valore, conteggio) ordinati."""
    dv = [{"value": v, "count": c} for v, c in value_counts]
    return {"truth": truth, "distinct_values": dv,
            "stability": "stabile" if len(dv) == 1 else "instabile"}


def _proposal(case_id, summary, aggregate, repeats=None):
    return {"case_id": case_id, "summary": summary, "aggregate": aggregate,
            "repeats": repeats or []}


class AxisATest(SimpleTestCase):
    def test_axis_a_sums_summaries(self):
        p1 = _proposal("c1", {"stable_correct": 10, "stable_wrong": 1, "stable_null": 0,
                              "instabile": 2, "ambiguo": 0}, {})
        p2 = _proposal("c2", {"stable_correct": 8, "stable_wrong": 0, "stable_null": 1,
                              "instabile": 3, "ambiguo": 1}, {})
        a = A.axis_a([p1, p2])
        self.assertEqual(a["stable_correct"], 18)
        self.assertEqual(a["stable_wrong"], 1)
        self.assertEqual(a["stable_null"], 1)
        self.assertEqual(a["instabile"], 5)
        self.assertEqual(a["ambiguo"], 1)
        self.assertEqual(a["n_fields"], 26)


class CrossCheckTest(SimpleTestCase):
    def _arms(self):
        # Cinque campi con classi note + un campo con null su un braccio (escluso).
        pro_agg = {
            "f_both_right": _agg(5, (5, 5)),
            "f_both_wrong": _agg(4, (8, 5)),          # concordi-sbagliati (cieco)
            "f_dis_pro_right": _agg(3, (3, 5)),
            "f_dis_pro_wrong": _agg(7, (2, 5)),
            "f_dis_both_wrong": _agg(1, (2, 5)),
            "f_null_pro": _agg(6, (None, 5)),          # escluso: Pro astiene
        }
        flash_agg = {
            "f_both_right": _agg(5, (5, 5)),
            "f_both_wrong": _agg(4, (8, 5)),
            "f_dis_pro_right": _agg(3, (9, 5)),
            "f_dis_pro_wrong": _agg(7, (7, 5)),
            "f_dis_both_wrong": _agg(1, (3, 5)),
            "f_null_pro": _agg(6, (6, 5)),
        }
        pro = {"C1": _proposal("C1", {}, pro_agg)}
        flash = {"C1": _proposal("C1", {}, flash_agg)}
        return pro, flash

    def test_buckets(self):
        pro, flash = self._arms()
        buckets, metrics, rows = A.crosscheck_fields(pro, flash)
        self.assertEqual(buckets["concordi_giusti"], 1)
        self.assertEqual(buckets["concordi_sbagliati"], 1)
        self.assertEqual(buckets["discordi_uno_giusto"], 2)
        self.assertEqual(buckets["discordi_entrambi_sbagliati"], 1)
        self.assertEqual(metrics["comparable_fields"], 5)
        self.assertEqual(metrics["excluded_null_fields"], 1)

    def test_disagreement_metrics(self):
        pro, flash = self._arms()
        _, metrics, _ = A.crosscheck_fields(pro, flash)
        self.assertEqual(metrics["error_fields"], 4)
        self.assertAlmostEqual(metrics["recall_union"], 0.75)
        self.assertAlmostEqual(metrics["blind_rate_union"], 0.25)
        self.assertEqual(metrics["precision_union"], 1.0)
        self.assertAlmostEqual(metrics["concordi_sbagliati_rate"], 0.2)

    def test_pro_perspective(self):
        pro, flash = self._arms()
        _, metrics, _ = A.crosscheck_fields(pro, flash)
        # Pro sbaglia: f_both_wrong (agree->cieco), f_dis_pro_wrong, f_dis_both_wrong.
        self.assertEqual(metrics["pro_error_fields"], 3)
        self.assertEqual(metrics["missed_pro"], 1)
        self.assertAlmostEqual(metrics["recall_pro"], 2 / 3)

    def test_team_name_normalization_agrees(self):
        # Punteggiatura/spazi diversi non sono disaccordo (nomi squadra normalizzati).
        pro = {"C1": _proposal("C1", {}, {"home_team_name": _agg("S.S. LAZIO", ("SS LAZIO", 5))})}
        flash = {"C1": _proposal("C1", {}, {"home_team_name": _agg("S.S. LAZIO", ("ss  lazio", 5))})}
        buckets, _, rows = A.crosscheck_fields(pro, flash)
        self.assertEqual(buckets["concordi_giusti"], 1)
        self.assertTrue(rows[0]["agree"])
        self.assertTrue(rows[0]["pro_correct"])

    def test_known_stable_error_rows_selected(self):
        pro = {
            A.CASE_BELLATOR: _proposal(A.CASE_BELLATOR, {}, {
                "final_score_home": _agg(4, (5, 5)), "final_score_away": _agg(19, (19, 5))}),
            A.CASE_TRISCELON: _proposal(A.CASE_TRISCELON, {}, {
                "date": _agg("2026-04-25", ("2026-04-28", 5))}),
        }
        flash = {
            A.CASE_BELLATOR: _proposal(A.CASE_BELLATOR, {}, {
                "final_score_home": _agg(4, (4, 5)), "final_score_away": _agg(19, (19, 5))}),
            A.CASE_TRISCELON: _proposal(A.CASE_TRISCELON, {}, {
                "date": _agg("2026-04-25", ("2026-04-28", 5))}),
        }
        _, _, rows = A.crosscheck_fields(pro, flash)
        known = A.known_stable_error_rows(rows)
        fields = {(r["case_id"], r["field"]) for r in known}
        self.assertIn((A.CASE_BELLATOR, "final_score_home"), fields)
        self.assertIn((A.CASE_TRISCELON, "date"), fields)
        # Bellator: Pro 5 (sbagliato), Flash 4 (giusto) -> discordi, catturato.
        bel = next(r for r in known if r["case_id"] == A.CASE_BELLATOR)
        self.assertFalse(bel["agree"])
        self.assertEqual(bel["class"], "discordi_uno_giusto")
        # Triscelon: entrambi 28-like sbagliato -> concordi-e-sbagliati (cieco).
        tri = next(r for r in known if r["case_id"] == A.CASE_TRISCELON)
        self.assertTrue(tri["agree"])
        self.assertEqual(tri["class"], "concordi_sbagliati")


class EventsReferto8Test(SimpleTestCase):
    def test_counts_types_per_repeat(self):
        events = (
            [{"type": "GOAL", "team": "home", "player_name": "X"}] * 12
            + [{"type": "GOAL", "team": "away", "player_name": "Y"}] * 10
            + [{"type": "TIMEOUT", "team": "home"}] * 3
            + [{"type": "EXCLUSION_DEF", "team": "home", "player_name": "Z"}]
            + [{"type": "EXCLUSION_20", "team": "home"}] * 24
        )
        prop = _proposal(A.CASE_REFERTO8, {}, {},
                         repeats=[{"extracted": {"events": events}}])
        by_case = {A.CASE_REFERTO8: prop}
        ev = A.events_referto8(by_case)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["goals_total"], 22)
        self.assertEqual(ev[0]["goals_home"], 12)
        self.assertEqual(ev[0]["goals_with_author"], 22)
        self.assertEqual(ev[0]["timeouts"], 3)
        self.assertEqual(ev[0]["edcs"], 1)

    def test_missing_case_returns_none(self):
        self.assertIsNone(A.events_referto8({}))
