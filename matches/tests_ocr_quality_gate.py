from django.test import TestCase
from django.urls import reverse
from matches.services.ocr_quality_gate import OCRQualityGate
from matches.models import Match, MatchReport
from core.models import League, Sport, Team, Society
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class OCRQualityGateTest(TestCase):
    def setUp(self):
        self.valid_data = {
            "metadata": {"confidence": 0.95},
            "match_info": {
                "home_team": "Team A",
                "away_team": "Team B",
                "date": "2024-01-01"
            },
            "scores": {
                "final_score": "5-3",
                "quarters": {
                    "q1": [1, 0],
                    "q2": [1, 1],
                    "q3": [2, 1],
                    "q4": [1, 1]
                }
            },
            "teams": {
                "home": {"players": []},
                "away": {"players": []}
            },
            "events": [
                {"type": "GOAL", "team": "home", "player": "John"},
                {"type": "GOAL", "team": "home", "player": "John"},
                {"type": "GOAL", "team": "home", "player": "John"},
                {"type": "GOAL", "team": "home", "player": "John"},
                {"type": "GOAL", "team": "home", "player": "John"},
                {"type": "GOAL", "team": "away", "player": "Mike"},
                {"type": "GOAL", "team": "away", "player": "Mike"},
                {"type": "GOAL", "team": "away", "player": "Mike"}
            ]
        }

    def test_valid_data(self):
        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data)
        self.assertTrue(is_valid)
        self.assertEqual(len(blockers), 0)
        self.assertEqual(len(warnings), 0)

    def test_missing_root_sections(self):
        del self.valid_data["scores"]
        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data)
        self.assertFalse(is_valid)
        self.assertIn("Sezioni base mancanti dal risultato OCR: scores", blockers)

    def test_missing_team_name(self):
        self.valid_data["match_info"]["home_team"] = ""
        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data)
        self.assertFalse(is_valid)
        self.assertTrue(any("Nomi squadre mancanti" in b for b in blockers))

    def test_teams_play_itself(self):
        self.valid_data["match_info"]["home_team"] = "Team A"
        self.valid_data["match_info"]["away_team"] = "team a"
        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data)
        self.assertFalse(is_valid)
        self.assertTrue(any("coincidono" in b for b in blockers))

    def test_malformed_final_score(self):
        self.valid_data["scores"]["final_score"] = "5 to 3"
        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data)
        self.assertFalse(is_valid)
        self.assertTrue(any("in formato non valido" in b for b in blockers))

    def test_quarter_totals_mismatch(self):
        self.valid_data["scores"]["quarters"]["q1"] = [5, 5]
        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data)
        # Should be invalid based on current hardening (blocker)
        self.assertFalse(is_valid)
        self.assertTrue(any("Incoerenza punteggio" in b for b in blockers))


    def test_event_totals_mismatch(self):
        self.valid_data["events"].append({"type": "GOAL", "team": "home", "player": "Extra"})
        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data)
        # Now a blocker for data integrity
        self.assertFalse(is_valid)
        self.assertTrue(any("Incoerenza eventi" in b for b in blockers))


    def test_garbage_values(self):
        self.valid_data["match_info"]["home_team"] = "TBD"
        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data)
        self.assertFalse(is_valid)
        self.assertTrue(any("inaccettabile" in b for b in blockers))

    def test_low_confidence(self):
        self.valid_data["metadata"]["confidence"] = 0.15
        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data)
        self.assertFalse(is_valid)
        self.assertTrue(any("troppo bassa" in b for b in blockers))

    def test_none_data_returns_four_tuple(self):
        ok, blockers, warnings, info = OCRQualityGate.evaluate(None)
        self.assertFalse(ok)
        self.assertGreater(len(blockers), 0)

    def test_empty_dict_data_returns_four_tuple(self):
        ok, blockers, warnings, info = OCRQualityGate.evaluate({})
        self.assertFalse(ok)
        self.assertGreater(len(blockers), 0)


class OCRQualityGateIntegrationTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="WP", slug="wp-qg")
        self.soc_a = Society.objects.create(name="TempA", slug="temp-a", sport=self.sport, city="X")
        self.soc_b = Society.objects.create(name="TempB", slug="temp-b", sport=self.sport, city="X")
        self.league = League.objects.create(name="BootLeague", sport=self.sport)
        self.team_a = Team.objects.create(society=self.soc_a, name="TempA")
        self.team_b = Team.objects.create(society=self.soc_b, name="TempB")
        self.match = Match.objects.create(
            league=self.league, home_team=self.team_a, away_team=self.team_b,
            match_date=timezone.now()
        )
        self.report = MatchReport.objects.create(
            match=self.match,
            status=MatchReport.Status.NEEDS_REVIEW,
            normalized_data={
                "metadata": {"confidence": 0.1},
                "match_info": {"home_team": "Team A", "away_team": "Team B"},
                "scores": {"final_score": "bad-score"},
                "teams": {"home": {"players": []}, "away": {"players": []}},
                "events": [],
            },
            raw_extracted_data={"metadata": {"confidence": 0.1}},
        )
        self.admin_user = User.objects.create_superuser(
            username='admin_qg', password='password', email='admin@test.com'
        )
        self.client.login(username='admin_qg', password='password')

    def test_review_page_shows_quality_gate(self):
        url = reverse('op_admin:matches_matchreport_review', args=[self.report.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['ocr_is_valid'])
        self.assertTrue(len(response.context['ocr_blockers']) > 0)
        self.assertContains(response, "Qualità OCR Critica")
        self.assertContains(response, "bad-score")
