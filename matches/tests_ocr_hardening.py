from django.test import TestCase
from matches.services.ocr_quality_gate import OCRQualityGate
from matches.models import Match, MatchReport
from core.models import League, Sport, Team, Society
from django.utils import timezone

class OCRHardeningTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="WP", slug="wp-hard")
        self.soc_a = Society.objects.create(name="Pro Recco", slug="recco", sport=self.sport, city="Recco")
        self.soc_b = Society.objects.create(name="Pescara", slug="pescara", sport=self.sport, city="Pescara")
        self.league = League.objects.create(name="Serie A1", sport=self.sport)
        self.team_a = Team.objects.create(society=self.soc_a, name="Pro Recco")
        self.team_b = Team.objects.create(society=self.soc_b, name="Pescara")
        
        self.context = {
            'home_team': "Pro Recco",
            'away_team': "Pescara",
            'location': "Piscina Comunale, Recco"
        }

        self.valid_data = {
            "metadata": {
                "confidence": 0.95,
                "confidence_fields": {
                    "home_team": 0.98,
                    "away_team": 0.97,
                    "final_score": 0.99
                }
            },
            "match_info": {
                "home_team": "PRO RECCO",  # Case insensitive Match
                "away_team": "Pescara N. e P.",  # Containment Match
                "date": "2024-04-13",
                "city": "Recco"
            },
            "scores": {
                "final_score": "10-5",
                "quarters": {
                    "1": [3, 1],
                    "2": [2, 1],
                    "3": [3, 1],
                    "4": [2, 2]
                }
            },
            "teams": {
                "home": {"name": "Pro Recco", "players": []},
                "away": {"name": "Pescara", "players": []}
            },
            "events": [
                {"type": "GOAL", "team": "home", "quarter": 1},
                {"type": "GOAL", "team": "home", "quarter": 1},
                {"type": "GOAL", "team": "home", "quarter": 1},
                {"type": "GOAL", "team": "away", "quarter": 1},
            ]
        }

    def test_clean_pass(self):
        """Clean data matching context should pass."""
        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data, context=self.context)
        self.assertTrue(is_valid, f"Expected valid, got blockers: {blockers}")
        self.assertEqual(len(blockers), 0)

    def test_team_mismatch_fails(self):
        """Team name completely different should block."""
        self.valid_data["match_info"]["home_team"] = "Villa York"
        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data, context=self.context)
        self.assertFalse(is_valid)
        self.assertTrue(any("non corrisponde alla partita selezionata" in b for b in blockers))

    def test_score_inconsistency_fails(self):
        """Sum of quarters mismatching final score should block (used to be warning)."""
        self.valid_data["scores"]["quarters"]["1"] = [10, 10]
        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data, context=self.context)
        self.assertFalse(is_valid)
        self.assertTrue(any("Incoerenza punteggio" in b for b in blockers))

    def test_low_field_confidence_does_not_block(self):
        """A1 (2026-07-21): `confidence_fields` non e' piu' un criterio di gating.

        Prima: < 0.5 su un campo di intestazione era blocker, < 0.8 era info.
        Rimossi — la confidence per campo non correla con la correttezza
        (syllabus §8.5(c), §8.9, §8.10).
        """
        self.valid_data["metadata"]["confidence_fields"]["final_score"] = 0.4
        self.valid_data["metadata"]["confidence_fields"]["home_team"] = 0.1
        is_valid, blockers, warnings, info = OCRQualityGate.evaluate(self.valid_data, context=self.context)
        self.assertTrue(is_valid)
        self.assertEqual(blockers, [])
        self.assertFalse(any("affidabilit" in msg.lower() for msg in warnings + info))

    def test_perfect_field_confidence_does_not_bypass_structural_checks(self):
        """Confidence 1.0 ovunque non deve rendere valido un payload incoerente."""
        self.valid_data["metadata"]["confidence_fields"] = {
            k: 1.0 for k in self.valid_data["metadata"]["confidence_fields"]
        }
        self.valid_data["scores"]["quarters"]["1"] = [10, 10]
        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data, context=self.context)
        self.assertFalse(is_valid)
        self.assertTrue(any("Incoerenza punteggio" in b for b in blockers))

    def test_event_total_exceeds_final_fails(self):
        """Too many goals in events vs final score should block.

        D6 (2026-07-21): al gate il confronto per-periodo SOSTITUISCE quello
        aggregato quando lo domina — qui tutti i parziali sono leggibili e ogni
        gol ha un periodo, quindi il blocco arriva dal periodo 4 e non dal
        totale. Il messaggio cambia, la difesa no: e' piu' specifica di prima
        perche' dice in quale periodo l'eccesso e' impossibile.
        """
        for _ in range(20):
             self.valid_data["events"].append({"type": "GOAL", "team": "home", "quarter": 4})

        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data, context=self.context)
        self.assertFalse(is_valid)
        self.assertTrue(any("Incoerenza per-periodo" in b and "Periodo 4" in b for b in blockers))
        self.assertFalse(any("Incoerenza eventi" in b for b in blockers))

    def test_event_total_exceeds_final_fails_con_gol_senza_periodo(self):
        """Se i gol non hanno periodo il per-periodo non domina: resta l'aggregato.

        Contro-prova della sostituzione D6: senza periodo il confronto
        per-periodo non puo' vedere l'eccesso, e la copertura non deve sparire.
        """
        for _ in range(20):
            self.valid_data["events"].append({"type": "GOAL", "team": "home", "quarter": None})

        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data, context=self.context)
        self.assertFalse(is_valid)
        self.assertTrue(any("Incoerenza eventi" in b for b in blockers))

    def test_wrong_location_warns(self):
        """Location mismatch should only warn (as it might be city vs venue)."""
        self.valid_data["match_info"]["city"] = "Milan"
        is_valid, blockers, warnings, _ = OCRQualityGate.evaluate(self.valid_data, context=self.context)
        self.assertTrue(is_valid)
        self.assertTrue(any("Località OCR 'Milan' sospetta" in w for w in warnings))
