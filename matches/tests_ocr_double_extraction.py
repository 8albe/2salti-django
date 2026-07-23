"""
Test della regola di divergenza fra due letture OCR indipendenti
(matches.services.ocr_double_extraction.compare_passes).

Funzione pura: nessun provider, nessun DB, nessuna chiamata reale.
"""
from django.test import SimpleTestCase

from matches.services.ocr_double_extraction import ZONES, compare_passes


def _extraction(final_score=None, quarters=None, date=None):
    """Estrazione minimale in schema OCR (scores + match_info.date)."""
    return {
        "scores": {"final_score": final_score, "quarters": quarters or {}},
        "match_info": {"date": date},
    }


TRUTH_QUARTERS = {"1": [1, 3], "2": [0, 5], "3": [3, 6], "4": [0, 5]}


class ComparePassesTest(SimpleTestCase):
    def test_identical_reads_do_not_diverge(self):
        a = _extraction("4-19", TRUTH_QUARTERS, "2026-04-11")
        result = compare_passes(a, dict(a))
        self.assertFalse(result["diverges"])
        self.assertFalse(result["review"])
        self.assertEqual(result["diverging_zones"], [])
        for zone in ZONES:
            self.assertEqual(result["zones"][zone]["status"], "agree")

    def test_final_score_divergence_flags_review(self):
        """Il caso Bellator: finale casa 5 vs 4 -> divergenza sul finale."""
        first = _extraction("5-19", TRUTH_QUARTERS, "2026-04-11")
        second = _extraction("4-19", TRUTH_QUARTERS, "2026-04-11")
        result = compare_passes(first, second)
        self.assertTrue(result["diverges"])
        self.assertTrue(result["review"])
        self.assertEqual(result["diverging_zones"], ["final_score"])
        self.assertEqual(result["zones"]["final_score"]["status"], "diverge")
        self.assertEqual(result["zones"]["final_score"]["first"], "5-19")
        self.assertEqual(result["zones"]["final_score"]["second"], "4-19")

    def test_date_divergence_flags_review(self):
        """Il caso Triscelon: data 28 vs 25 -> divergenza sulla data."""
        first = _extraction("20-12", None, "2026-04-28")
        second = _extraction("20-12", None, "2026-04-25")
        result = compare_passes(first, second)
        self.assertTrue(result["diverges"])
        self.assertEqual(result["diverging_zones"], ["date"])
        self.assertEqual(result["zones"]["date"]["status"], "diverge")

    def test_single_quarter_cell_divergence(self):
        first = _extraction("4-19", {"1": [1, 3], "2": [0, 5], "3": [3, 6], "4": [0, 5]})
        second = _extraction("4-19", {"1": [1, 3], "2": [0, 5], "3": [3, 5], "4": [1, 6]})
        result = compare_passes(first, second)
        self.assertTrue(result["diverges"])
        self.assertEqual(result["diverging_zones"], ["quarters"])
        cells = result["zones"]["quarters"]["cells"]
        self.assertEqual(cells["3_away"]["status"], "diverge")
        self.assertEqual(cells["4_home"]["status"], "diverge")
        self.assertEqual(cells["1_home"]["status"], "agree")

    def test_null_read_is_abstain_not_divergence(self):
        """Una lettura null (astensione) non è una contraddizione: niente review."""
        first = _extraction("4-19", TRUTH_QUARTERS, "2026-04-11")
        second = _extraction(None, TRUTH_QUARTERS, "2026-04-11")
        result = compare_passes(first, second)
        self.assertFalse(result["diverges"])
        self.assertEqual(result["zones"]["final_score"]["status"], "abstain")

    def test_both_dates_null_is_abstain(self):
        first = _extraction("4-19", TRUTH_QUARTERS, None)
        second = _extraction("4-19", TRUTH_QUARTERS, None)
        result = compare_passes(first, second)
        self.assertFalse(result["diverges"])
        self.assertEqual(result["zones"]["date"]["status"], "abstain")

    def test_quarter_cell_null_on_one_side_is_abstain(self):
        first = _extraction("4-19", {"1": [1, 3], "2": [0, 5], "3": [3, 6], "4": [0, 5]})
        second = _extraction("4-19", {"1": [1, 3], "2": [0, 5], "3": [None, 6], "4": [0, 5]})
        result = compare_passes(first, second)
        self.assertFalse(result["diverges"])
        self.assertEqual(result["zones"]["quarters"]["status"], "agree")
        self.assertEqual(result["zones"]["quarters"]["cells"]["3_home"]["status"], "abstain")

    def test_all_quarters_null_both_sides_is_abstain_zone(self):
        first = _extraction("4-19", {})
        second = _extraction("4-19", {})
        result = compare_passes(first, second)
        self.assertEqual(result["zones"]["quarters"]["status"], "abstain")
        self.assertFalse(result["diverges"])

    def test_multiple_zones_diverge(self):
        first = _extraction("5-19", {"1": [1, 3]}, "2026-04-11")
        second = _extraction("4-19", {"1": [2, 3]}, "2026-04-12")
        result = compare_passes(first, second)
        self.assertTrue(result["diverges"])
        self.assertEqual(set(result["diverging_zones"]), {"final_score", "quarters", "date"})

    def test_empty_inputs_do_not_crash(self):
        result = compare_passes({}, {})
        self.assertFalse(result["diverges"])
        result_none = compare_passes(None, None)
        self.assertFalse(result_none["diverges"])
