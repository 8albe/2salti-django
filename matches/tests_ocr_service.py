from django.test import TestCase
from django.utils import timezone
from core.models import Season, Sport, Society, League, Team
from matches.models import Match, MatchReport
from matches.services.ocr_service import OCRService
from matches.services.schema import OCRSchemaValidator
from matches.services.converters import MatchDataConverter
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


class OCRServiceTestCase(TestCase):
    def setUp(self):
        # Force mock provider for all tests (env may have gemini)
        from matches.services.vision_providers import MockVisionProvider
        OCRService.set_provider(MockVisionProvider())

        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")

        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.soc_home = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco")
        self.soc_away = Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia")
        self.league = League.objects.create(name="Serie A1", sport=self.sport, slug="serie-a1")
        self.team_home = Team.objects.create(society=self.soc_home, league=self.league)
        self.team_away = Team.objects.create(society=self.soc_away, league=self.league)
        self.user = User.objects.create_user(username="testuser", role="athlete")
        
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_home,
            away_team=self.team_away,
            match_date=timezone.now(),
            home_score=8,
            away_score=6
        )
        
        self.report = MatchReport.objects.create(
            match=self.match,
            uploader=self.user,
            file=SimpleUploadedFile("referto.pdf", b"pdf_content", content_type="application/pdf")
        )

    def tearDown(self):
        OCRService._provider = None  # Reset provider for other test classes

    def test_extract_data_format(self):
        """Verifica che l'estrazione restituisca il formato JSON atteso"""
        data, _ = OCRService.extract_data(self.report)
        
        self.assertIn("metadata", data)
        self.assertIn("match_info", data)
        self.assertIn("scores", data)
        self.assertEqual(data["match_info"]["home_team"], "Pro Recco")
        self.assertEqual(data["match_info"]["away_team"], "AN Brescia")
        self.assertEqual(data["scores"]["final_score"], "8-6")
        self.assertGreater(data["metadata"]["confidence"], 0.9)

    def test_extract_data_has_confidence_fields(self):
        """Verifica che l'estrazione includa confidence_fields e extraction_warnings"""
        data, _ = OCRService.extract_data(self.report)
        
        self.assertIn("confidence_fields", data["metadata"])
        self.assertIn("extraction_warnings", data["metadata"])
        self.assertIsInstance(data["metadata"]["extraction_warnings"], list)

    def test_process_and_update_workflow(self):
        """Verifica che il processo aggiorni correttamente lo stato del MatchReport"""
        success = OCRService.process_and_update(self.report)
        
        self.assertTrue(success)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, 'EXTRACTED')
        self.assertIsNotNone(self.report.raw_extracted_data)
        self.assertEqual(self.report.raw_extracted_data["match_info"]["home_team"], "Pro Recco")

    def test_admin_action_ocr(self):
        """L'azione admin accoda il referto; l'OCR lo esegue poi il worker (Macro 22)."""
        admin_user = User.objects.create_superuser(username='superadmin', password='password', email='admin@test.com')
        self.client.force_login(admin_user)
        
        url = reverse('admin:matches_matchreport_changelist')
        data = {
            'action': 'process_ocr',
            '_selected_action': [self.report.id],
            'index': 0,
            'select_across': 0,
        }
        
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, 'QUEUED')
        self.assertContains(response, "Accodati: 1, Saltati: 0.")

        # Il worker consuma la coda e porta il referto a EXTRACTED.
        from django.core.management import call_command
        call_command('ocr_worker', '--once', '--no-startup-sweep')

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, 'EXTRACTED')
        self.assertIsNotNone(self.report.raw_extracted_data)

    def test_review_view_flow(self):
        """Verifica che la vista di revisione aggiorni i dati e lo stato a VALIDATED"""
        self.report.status = MatchReport.Status.EXTRACTED
        self.report.raw_extracted_data = {"home_team": "Pro Recco", "away_team": "Brescia"}
        self.report.save()
        
        admin_user = User.objects.create_superuser(username='reviewer', password='password', email='rev@test.com')
        self.client.force_login(admin_user)
        
        url = reverse('admin:matches_matchreport_review', args=[self.report.id])
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pro Recco")
        
        normalized_data_dict = {
            "metadata": {"confidence": 0.99},
            "match_info": {"home_team": "PRO RECCO ASD", "away_team": "AN BRESCIA"},
            "scores": {"final_score": "12-8"},
            "teams": {},
            "events": []
        }
        import json
        normalized_json = json.dumps(normalized_data_dict)
        data = {
            'normalized_data': normalized_json,
            '_save': 'Salva'
        }

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MatchReport.Status.VALIDATED)
        self.assertEqual(self.report.normalized_data['match_info']['home_team'], "PRO RECCO ASD")

    def test_idempotency_ocr_processing(self):
        """Verifica che non si possa processare un report già in corso o completato"""
        self.report.status = MatchReport.Status.EXTRACTED
        self.report.save()
        
        success = OCRService.process_and_update(self.report)
        self.assertFalse(success)
        self.assertEqual(self.report.status, MatchReport.Status.EXTRACTED)

    def test_schema_validation_types(self):
        """Verifica che il validatore controlli i tipi corretti (numeric confidence)"""
        invalid_data = {
            "metadata": {"confidence": "high"},
            "match_info": {"home_team": "A", "away_team": "B"},
            "scores": {}, "teams": {}, "events": []
        }
        success, msg = OCRSchemaValidator.validate(invalid_data)
        self.assertFalse(success)
        self.assertIn("confidence", msg)

    def test_schema_validation_score_format(self):
        """Verifica che il punteggio debba avere parti numeriche"""
        invalid_data = {
            "metadata": {"confidence": 0.9},
            "match_info": {"home_team": "A", "away_team": "B"},
            "scores": {"final_score": "10-X"},
            "teams": {}, "events": []
        }
        success, msg = OCRSchemaValidator.validate(invalid_data)
        self.assertFalse(success)
        self.assertIn("numeri separati da '-'", msg)


class SemanticValidationTestCase(TestCase):
    """Test per i controlli di coerenza semantica aggiunti nella v2."""

    def _make_valid_data(self, **overrides):
        """Helper per creare un payload OCR valido con override facili."""
        data = {
            "metadata": {"confidence": 0.9, "confidence_fields": {}, "extraction_warnings": []},
            "match_info": {"home_team": "Pro Recco", "away_team": "AN Brescia", "date": "2026-01-15"},
            "scores": {"final_score": "8-6", "quarters": {"1": [2, 1], "2": [3, 2], "3": [2, 1], "4": [1, 2]}},
            "teams": {
                "home": {"name": "Pro Recco", "players": [
                    {"number": i, "name": f"Giocatore Casa {i}"} for i in range(1, 14)
                ]},
                "away": {"name": "AN Brescia", "players": [
                    {"number": i, "name": f"Giocatore Ospite {i}"} for i in range(1, 14)
                ]}
            },
            "events": [
                {"type": "GOAL", "player_name": "Giocatore Casa 2", "team": "home", "minute": 3, "quarter": 1},
            ]
        }
        for key, value in overrides.items():
            keys = key.split(".")
            obj = data
            for k in keys[:-1]:
                obj = obj[k]
            obj[keys[-1]] = value
        return data

    def test_coherent_data_passes(self):
        """Dati perfettamente coerenti non producono warnings."""
        data = self._make_valid_data()
        # Override events to match score exactly
        data["events"] = [
            {"type": "GOAL", "player_name": f"P{i}", "team": "home", "minute": i, "quarter": 1}
            for i in range(8)
        ] + [
            {"type": "GOAL", "player_name": f"A{i}", "team": "away", "minute": i, "quarter": 1}
            for i in range(6)
        ]
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        # Quarter sum mismatch will still fire, but goals match
        goal_warnings = [w for w in warnings if "Incoerenza eventi" in w]
        self.assertEqual(len(goal_warnings), 0)

    def test_negative_score_detected(self):
        """Quarter con punteggio negativo viene segnalato."""
        data = self._make_valid_data()
        data["scores"]["quarters"]["1"] = [-2, 1]
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        self.assertFalse(ok)
        negative_warnings = [w for w in warnings if "negativo" in w.lower()]
        self.assertTrue(len(negative_warnings) > 0)

    def test_impossibly_high_score_detected(self):
        """Punteggio singolo impossibilmente alto viene segnalato."""
        data = self._make_valid_data()
        data["scores"]["final_score"] = "45-3"
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        high_warnings = [w for w in warnings if "alto" in w.lower()]
        self.assertTrue(len(high_warnings) > 0)

    def test_quarter_impossibly_high(self):
        """Punteggio quarto > 15 viene segnalato."""
        data = self._make_valid_data()
        data["scores"]["quarters"]["1"] = [20, 1]
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        quarter_warnings = [w for w in warnings if "Quarto 1" in w and "alto" in w.lower()]
        self.assertTrue(len(quarter_warnings) > 0)

    def test_team_plays_itself_detected(self):
        """Squadra gioca contro se stessa."""
        data = self._make_valid_data()
        data["match_info"]["away_team"] = "Pro Recco"
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        self_play = [w for w in warnings if "se stessa" in w]
        self.assertTrue(len(self_play) > 0)

    def test_roster_too_small_detected(self):
        """Roster con meno di 7 giocatori viene segnalato."""
        data = self._make_valid_data()
        data["teams"]["home"]["players"] = [{"number": 1, "name": "Solo Player"}]
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        roster_warnings = [w for w in warnings if "Roster" in w and "giocatori" in w]
        self.assertTrue(len(roster_warnings) > 0)

    def test_roster_too_large_detected(self):
        """Roster con più di 15 giocatori viene segnalato."""
        data = self._make_valid_data()
        data["teams"]["home"]["players"] = [
            {"number": i, "name": f"Player {i}"} for i in range(1, 20)
        ]
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        roster_warnings = [w for w in warnings if "Roster" in w and "massimo" in w.lower()]
        self.assertTrue(len(roster_warnings) > 0)

    def test_duplicate_player_names_detected(self):
        """Nomi giocatore duplicati vengono segnalati."""
        data = self._make_valid_data()
        data["teams"]["home"]["players"] = [
            {"number": 1, "name": "Mario Rossi"},
            {"number": 2, "name": "Mario Rossi"},
        ] + [{"number": i, "name": f"Player {i}"} for i in range(3, 10)]
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        dup_warnings = [w for w in warnings if "Nomi giocatore duplicati" in w]
        self.assertTrue(len(dup_warnings) > 0)

    def test_missing_date_warning(self):
        """Data mancante viene segnalata."""
        data = self._make_valid_data()
        data["match_info"]["date"] = None
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        date_warnings = [w for w in warnings if "Data" in w]
        self.assertTrue(len(date_warnings) > 0)

    def test_low_confidence_warning(self):
        """Confidenza bassa viene segnalata."""
        data = self._make_valid_data()
        data["metadata"]["confidence"] = 0.3
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        conf_warnings = [w for w in warnings if "Confidenza" in w]
        self.assertTrue(len(conf_warnings) > 0)

    def test_extraction_warnings_surfaced(self):
        """Warnings dell'engine OCR vengono esposti nella validazione."""
        data = self._make_valid_data()
        data["metadata"]["extraction_warnings"] = ["Nome parzialmente leggibile: ROSS?"]
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        ocr_warnings = [w for w in warnings if "[OCR]" in w]
        self.assertTrue(len(ocr_warnings) > 0)

    def test_null_final_score_allowed_in_validation(self):
        """Un final_score null è strutturalmente valido (campo opzionale per OCR)."""
        data = self._make_valid_data()
        data["scores"]["final_score"] = None
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok)

    def test_null_quarter_allowed(self):
        """Un quarto null (illeggibile) non genera errore."""
        data = self._make_valid_data()
        data["scores"]["quarters"]["2"] = None
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        # Should not crash and should not flag quarter sum mismatch due to null
        quarter_errors = [w for w in warnings if "Quarto 2" in w]
        self.assertEqual(len(quarter_errors), 0)


class PublishReadinessTestCase(TestCase):
    """Test per assess_publish_readiness."""

    def _make_publishable_data(self):
        return {
            "metadata": {"confidence": 0.9, "confidence_fields": {}, "extraction_warnings": []},
            "match_info": {"home_team": "Pro Recco", "away_team": "AN Brescia", "date": "2026-01-15"},
            "scores": {"final_score": "8-6", "quarters": {"1": [2, 1], "2": [3, 2], "3": [2, 1], "4": [1, 2]}},
            "teams": {
                "home": {"name": "Pro Recco", "players": [
                    {"number": i, "name": f"Player {i}"} for i in range(1, 14)
                ]},
                "away": {"name": "AN Brescia", "players": [
                    {"number": i, "name": f"Opponent {i}"} for i in range(1, 14)
                ]}
            },
            "events": [
                {"type": "GOAL", "team": "home", "player_name": f"Player {i}", "minute": i, "quarter": ((i-1) // 2) + 1}
                for i in range(1, 9)
            ] + [
                {"type": "GOAL", "team": "away", "player_name": f"Opponent {i}", "minute": i, "quarter": ((i-1) // 2) + 1}
                for i in range(1, 7)
            ],
            "reconciliation": {
                "home_players": {f"Player {i}": i for i in range(1, 9)},
                "away_players": {f"Opponent {i}": 100 + i for i in range(1, 7)},
            },
        }

    def test_good_data_is_publishable(self):
        """Dati validi e completi sono pronti per la pubblicazione."""
        data = self._make_publishable_data()
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(data)
        self.assertTrue(safe)
        self.assertEqual(len(blockers), 0)

    def test_missing_score_blocks_publish(self):
        """Punteggio mancante blocca la pubblicazione."""
        data = self._make_publishable_data()
        data["scores"]["final_score"] = None
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(data)
        self.assertFalse(safe)
        self.assertTrue(any("Punteggio" in b for b in blockers))

    def test_empty_rosters_block_publish(self):
        """Roster vuoti bloccano la pubblicazione."""
        data = self._make_publishable_data()
        data["teams"]["home"]["players"] = []
        data["teams"]["away"]["players"] = []
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(data)
        self.assertFalse(safe)
        self.assertTrue(any("roster" in b.lower() for b in blockers))

    def test_very_low_confidence_blocks_publish(self):
        """Confidenza < 0.3 blocca la pubblicazione."""
        data = self._make_publishable_data()
        data["metadata"]["confidence"] = 0.1
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(data)
        self.assertFalse(safe)
        self.assertTrue(any("Confidenza" in b for b in blockers))

    def test_missing_team_names_blocks_publish(self):
        """Nomi squadre entrambi mancanti bloccano la pubblicazione."""
        data = self._make_publishable_data()
        data["match_info"]["home_team"] = None
        data["match_info"]["away_team"] = None
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(data)
        self.assertFalse(safe)
        self.assertTrue(any("squadre" in b.lower() for b in blockers))

    def test_low_confidence_generates_warning_not_blocker(self):
        """Confidenza bassa (0.3-0.6) genera warning, non blocker."""
        data = self._make_publishable_data()
        data["metadata"]["confidence"] = 0.45
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(data)
        self.assertTrue(safe)
        self.assertTrue(any("Confidenza" in w for w in warnings))

    def test_empty_data_blocks_publish(self):
        """Dati vuoti bloccano la pubblicazione."""
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness({})
        self.assertFalse(safe)

    def test_none_data_blocks_publish(self):
        """None come dato blocca la pubblicazione."""
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(None)
        self.assertFalse(safe)


class ConverterTestCase(TestCase):
    """Test per la logica del converter, incluso il fix player_name/player."""

    def test_player_name_key_preferred(self):
        """Il campo player_name ha priorità su player."""
        data = {
            "events": [
                {"type": "GOAL", "player_name": "Mario Rossi", "team": "home", "minute": 5}
            ],
            "reconciliation": {
                "home_players": {"Mario Rossi": 42}
            }
        }
        events = MatchDataConverter.get_events_data(data)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["player_id"], 42)

    def test_player_key_fallback(self):
        """Il campo player funziona come fallback se player_name è assente."""
        data = {
            "events": [
                {"type": "GOAL", "player": "Mario Rossi", "team": "home", "minute": 5}
            ],
            "reconciliation": {
                "home_players": {"Mario Rossi": 42}
            }
        }
        events = MatchDataConverter.get_events_data(data)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["player_id"], 42)

    def test_no_player_gives_none_id(self):
        """Evento senza giocatore ha player_id None."""
        data = {
            "events": [
                {"type": "TIMEOUT", "team": "home", "minute": 5}
            ]
        }
        events = MatchDataConverter.get_events_data(data)
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0]["player_id"])

    def test_quarter_is_extracted(self):
        """Il campo quarter viene estratto dagli eventi."""
        data = {
            "events": [
                {"type": "GOAL", "player_name": "X", "team": "home", "minute": 5, "quarter": 3}
            ]
        }
        events = MatchDataConverter.get_events_data(data)
        self.assertEqual(events[0]["quarter"], 3)

    def test_score_parsing_robustness(self):
        """Il parser gestisce spazi e formati anomali."""
        data = {"scores": {"final_score": " 12 - 8 ", "quarters": {}}}
        result = MatchDataConverter.get_match_scores(data)
        self.assertEqual(result["home_score"], 12)
        self.assertEqual(result["away_score"], 8)

    def test_score_parsing_invalid_falls_to_zero(self):
        """Un punteggio non parsabile cade a 0-0."""
        data = {"scores": {"final_score": "INVALID", "quarters": {}}}
        result = MatchDataConverter.get_match_scores(data)
        self.assertEqual(result["home_score"], 0)
        self.assertEqual(result["away_score"], 0)


class FullFlowRegressionTest(TestCase):
    """Test end-to-end: Mock OCR → Schema validate → Coherence → Publish readiness → Publish."""

    def setUp(self):
        # Force mock provider
        from matches.services.vision_providers import MockVisionProvider
        OCRService.set_provider(MockVisionProvider())

        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")

        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.soc_home = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco-ff")
        self.soc_away = Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia-ff")
        self.league = League.objects.create(name="Serie A1", sport=self.sport, slug="serie-a1-ff")
        self.team_home = Team.objects.create(society=self.soc_home, league=self.league)
        self.team_away = Team.objects.create(society=self.soc_away, league=self.league)
        self.user = User.objects.create_superuser(username="admin_ff", email="ff@test.com", password="password")

        # Atleti per coprire i nomi citati negli eventi del MockVisionProvider
        # ("Capitano Mock" home GOAL, "Difensore Mock" away EXCLUSION_20).
        # Servono per far popolare reconciliation a process_and_update via get_roster()+resolve_athlete.
        # Il signal post_save su User crea automaticamente AthleteProfile: lo recuperiamo e settiamo current_team.
        self.athlete_home_user = User.objects.create_user(
            username='capitano_mock', first_name='Capitano', last_name='Mock',
            role='athlete',
            identity_status='VERIFIED',
            onboarding_payment_done=True,
            setup_completed=True,
        )
        self.athlete_home = self.athlete_home_user.athlete_profile
        self.athlete_home.current_team = self.team_home
        self.athlete_home.save()

        self.athlete_away_user = User.objects.create_user(
            username='difensore_mock', first_name='Difensore', last_name='Mock',
            role='athlete',
            identity_status='VERIFIED',
            onboarding_payment_done=True,
            setup_completed=True,
        )
        self.athlete_away = self.athlete_away_user.athlete_profile
        self.athlete_away.current_team = self.team_away
        self.athlete_away.save()

        # Score 1-0 allineato agli eventi del MockVisionProvider (1 GOAL home, 0 GOAL away).
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_home,
            away_team=self.team_away,
            match_date=timezone.now(),
            home_score=1,
            away_score=0
        )

        self.report = MatchReport.objects.create(
            match=self.match,
            uploader=self.user,
            file=SimpleUploadedFile("referto.pdf", b"pdf_content", content_type="application/pdf")
        )

    def tearDown(self):
        OCRService._provider = None

    def test_full_flow_mock_extraction_to_publish(self):
        """Test completo: estrazione mock → validazione → pubblicazione."""
        from matches.services.publishing_service import PublishingService

        # 1. Estrazione OCR (Mock)
        success = OCRService.process_and_update(self.report)
        self.assertTrue(success)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MatchReport.Status.EXTRACTED)

        # 2. Schema validation
        data = self.report.normalized_data
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok, f"Schema validation failed: {msg}")

        # 3. Coherence check
        coherent, warnings = OCRSchemaValidator.validate_coherence(data)
        # Mock data may have coherence warnings (events vs score), that's expected

        # 4. Set as normalized + validate
        self.report.normalized_data = data
        self.report.status = MatchReport.Status.VALIDATED
        self.report.save()

        # 5. Publish readiness
        safe, blockers, pub_warnings = OCRSchemaValidator.assess_publish_readiness(data)
        self.assertTrue(safe, f"Publish blocked: {blockers}")

        # 6. Publish
        pub_success, msg = PublishingService.publish_report(self.report, user=self.user)
        self.assertTrue(pub_success, f"Publish failed: {msg}")

        # 7. Verify final state
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MatchReport.Status.PUBLISHED)
        self.match.refresh_from_db()
        self.assertTrue(self.match.is_finished)
        self.assertEqual(self.match.home_score, 1)
        self.assertEqual(self.match.away_score, 0)

class ReviewUXTestCase(TestCase):
    """Test per la UX di revisione e la preservazione delle evidenze."""
    def setUp(self):
        from matches.services.ocr_service import OCRService
        from matches.services.vision_providers import MockVisionProvider
        OCRService.set_provider(MockVisionProvider())
        
        from core.models import Season, Sport, Society, League, Team
        from matches.models import Match, MatchReport
        from django.utils import timezone
        from django.contrib.auth import get_user_model
        
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto-ux")
        
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.soc_home = Society.objects.create(name="Home Soc", sport=self.sport)
        self.soc_away = Society.objects.create(name="Away Soc", sport=self.sport)
        self.team_home = Team.objects.create(society=self.soc_home)
        self.team_away = Team.objects.create(society=self.soc_away)
        self.league = League.objects.create(name="Test League", sport=self.sport)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_home,
            away_team=self.team_away,
            match_date=timezone.now()
        )
        self.user = get_user_model().objects.create_superuser('admin_ux', 'admin_ux@test.com', 'pass')

    def test_raw_api_response_is_preserved(self):
        """Verifica che raw_api_response venga salvato correttamente."""
        from matches.models import MatchReport
        from matches.services.ocr_service import OCRService
        report = MatchReport.objects.create(match=self.match, file="test.jpg")
        
        # Usiamo il MockVisionProvider (già aggiornato)
        success = OCRService.process_and_update(report)
        self.assertTrue(success)
        
        report.refresh_from_db()
        self.assertIsNotNone(report.raw_api_response)
        self.assertIn("MockVisionProvider", report.raw_api_response)
        # raw_extracted_data deve essere il dizionario normalizzato
        self.assertIsInstance(report.raw_extracted_data, dict)
        self.assertEqual(report.raw_extracted_data["metadata"]["provider"], "MockVisionProvider-v1")

    def test_review_view_context_reliability(self):
        """Verifica che la vista di revisione passi i segnali di affidabilità al context."""
        from django.test import RequestFactory
        from matches.admin import MatchReportAdmin
        from django.contrib.admin.sites import AdminSite
        from matches.models import MatchReport

        report = MatchReport.objects.create(
            match=self.match, 
            file="test.jpg",
            raw_extracted_data={
                "metadata": {
                    "confidence": 0.85,
                    "confidence_fields": {"home_team": 0.9, "away_team": 0.8},
                    "extraction_warnings": ["Luce scarsa"]
                },
                "match_info": {"home_team": "Home", "away_team": "Away"},
                "teams": {"home": {"players": []}, "away": {"players": []}},
                "scores": {"final_score": "10-5"}
            },
            status=MatchReport.Status.EXTRACTED
        )
        
        factory = RequestFactory()
        request = factory.get(f'/admin/matches/matchreport/{report.id}/review/')
        request.user = self.user
        
        admin = MatchReportAdmin(MatchReport, AdminSite())
        response = admin.review_view(request, report.id)
        
        self.assertEqual(response.status_code, 200)
        # In Django Admin views, context is often in response.context_data
        context = response.context_data
        self.assertEqual(context['confidence'], 0.85)
        self.assertEqual(context['confidence_percent'], 85)
        self.assertIn("Luce scarsa", context['extraction_warnings'])
        self.assertTrue('publish_safe' in context)
        # In questo caso dovrebbero esserci blockers (roster empty)
        self.assertFalse(context['publish_safe'])
        self.assertTrue(any("roster" in b.lower() for b in context['publish_blockers']))


class SchemaV2ExtensionTestCase(TestCase):
    """
    Test per le estensioni v2 dello schema OCR.
    Tutti i nuovi campi sono opzionali: i test verificano sia la retrocompatibilità
    dei payload v1 (senza nuovi campi) sia la corretta validazione dei payload v2.
    """

    def _make_v1_payload(self):
        """Payload minimo v1 — nessun campo v2 presente.
        Include una sezione reconciliation per evitare che il blocker
        pre-esistente di riconciliazione incompleta interferisca con i test.
        """
        home_players = {f"Player {i}": i for i in range(1, 10)}
        away_players = {f"Opponent {i}": 100 + i for i in range(1, 10)}
        return {
            "metadata": {"confidence": 0.9, "confidence_fields": {}, "extraction_warnings": []},
            "match_info": {"home_team": "Team A", "away_team": "Team B", "date": "2026-04-01"},
            "scores": {"final_score": "5-3", "quarters": {"1": [2, 1], "2": [1, 1], "3": [1, 0], "4": [1, 1]}},
            "teams": {
                "home": {"name": "Team A", "players": [{"number": i, "name": f"Player {i}"} for i in range(1, 10)]},
                "away": {"name": "Team B", "players": [{"number": i, "name": f"Opponent {i}"} for i in range(1, 10)]},
            },
            "events": [
                {"type": "GOAL", "player_name": f"Player {i}", "team": "home", "minute": i * 3, "quarter": 1}
                for i in range(1, 6)
            ] + [
                {"type": "GOAL", "player_name": f"Opponent {i}", "team": "away", "minute": i * 4, "quarter": 2}
                for i in range(1, 4)
            ],
            # Reconciliation pre-valorizzata: simula i referti reali già pubblicati
            "reconciliation": {
                "home_team_id": 1,
                "away_team_id": 2,
                "home_players": home_players,
                "away_players": away_players,
            },
        }


    # --- Retrocompatibilità ---

    def test_v1_payload_validates_without_new_fields(self):
        """Un payload v1 senza officials/coach/venue passa ancora la validazione strutturale."""
        data = self._make_v1_payload()
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok, f"validate() ha fallito su payload v1: {msg}")

    def test_v1_payload_no_new_coherence_blockers(self):
        """Un payload v1 non genera nuovi blockers di coerenza per assenza di campi v2."""
        data = self._make_v1_payload()
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        # I warning di coerenza v2 per officials vanno sul payload v1 (sezione assente)
        # ma non devono creare BLOCKERS critici — solo warning informativi
        blocking_keywords = ["Incoerenza punteggio", "Incoerenza eventi"]
        critical = [w for w in warnings if any(k in w for k in blocking_keywords)]
        self.assertEqual(len(critical), 0, f"Nuovi blockers critici su v1: {critical}")

    def test_v1_payload_still_publishable(self):
        """Un payload v1 valido rimane pubblicabile nonostante i nuovi warning soft."""
        data = self._make_v1_payload()
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(data)
        self.assertTrue(safe, f"assess_publish_readiness ha bloccato un payload v1 valido: {blockers}")
        self.assertEqual(len(blockers), 0)

    def test_v1_payload_gets_officials_warning_not_blocker(self):
        """Un payload v1 senza officials genera un warning (non un blocker)."""
        data = self._make_v1_payload()
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(data)
        self.assertTrue(safe)  # non bloccato
        officials_warnings = [w for w in warnings if "officials" in w.lower()]
        self.assertTrue(len(officials_warnings) > 0, "Atteso warning officials assente su payload v1")

    # --- Struttura Officials ---

    def test_officials_section_structural_validation(self):
        """Sezione officials ben formata supera la validazione."""
        data = self._make_v1_payload()
        data["officials"] = {
            "confidence": 0.85,
            "referees": [
                {"name": "Mario Bianchi", "role": "1st"},
                {"name": "Luigi Verdi", "role": "2nd"},
            ],
            "timekeeper": "Anna Rossi",
        }
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok, f"validate() ha fallito su payload v2 con officials: {msg}")

    def test_officials_empty_referees_is_valid_structure(self):
        """Lista referees vuota è strutturalmente valida (OCR non ha letto i nomi)."""
        data = self._make_v1_payload()
        data["officials"] = {"confidence": 0.3, "referees": [], "timekeeper": None}
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok, f"validate() ha rifiutato referees=[]: {msg}")

    def test_officials_wrong_type_blocked(self):
        """Sezione officials non-dict viene rifiutata."""
        data = self._make_v1_payload()
        data["officials"] = "Mario Bianchi"  # wrong type
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertFalse(ok)
        self.assertIn("officials", msg)

    def test_officials_referees_non_list_blocked(self):
        """officials.referees non-lista viene rifiutato."""
        data = self._make_v1_payload()
        data["officials"] = {"confidence": 0.8, "referees": "Mario Bianchi", "timekeeper": None}
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertFalse(ok)
        self.assertIn("referees", msg)

    def test_officials_empty_referees_generates_coherence_warning(self):
        """officials presente con referees=[] genera warning di coerenza."""
        data = self._make_v1_payload()
        data["officials"] = {"confidence": 0.8, "referees": [], "timekeeper": None}
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        ref_warnings = [w for w in warnings if "nessun arbitro" in w.lower()]
        self.assertTrue(len(ref_warnings) > 0)

    def test_officials_low_confidence_generates_warning(self):
        """officials.confidence < 0.5 genera warning in validate_coherence."""
        data = self._make_v1_payload()
        data["officials"] = {
            "confidence": 0.3,
            "referees": [{"name": "?????", "role": "1st"}],
            "timekeeper": None,
        }
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        conf_warnings = [w for w in warnings if "arbitri" in w.lower() and "bassa" in w.lower()]
        self.assertTrue(len(conf_warnings) > 0)

    # --- Coach ---

    def test_coach_field_optional_absent(self):
        """teams.home.coach assente è valido (campo opzionale)."""
        data = self._make_v1_payload()
        # home non ha coach — validazione deve passare
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok)

    def test_coach_field_string_accepted(self):
        """teams.home.coach come stringa è valido."""
        data = self._make_v1_payload()
        data["teams"]["home"]["coach"] = "Marco Rossi"
        data["teams"]["away"]["coach"] = "Luca Bianchi"
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok, f"validate() ha rifiutato coach stringa: {msg}")

    def test_coach_field_null_accepted(self):
        """teams.home.coach = null è valido."""
        data = self._make_v1_payload()
        data["teams"]["home"]["coach"] = None
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok)

    def test_coach_field_wrong_type_blocked(self):
        """teams.home.coach non-stringa (es. int) viene rifiutato."""
        data = self._make_v1_payload()
        data["teams"]["home"]["coach"] = 42  # wrong type
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertFalse(ok)
        self.assertIn("coach", msg)

    # --- Team confidence ---

    def test_team_confidence_optional_absent(self):
        """teams.home.confidence assente è valido."""
        data = self._make_v1_payload()
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok)

    def test_team_confidence_float_accepted(self):
        """teams.home.confidence come float è valido."""
        data = self._make_v1_payload()
        data["teams"]["home"]["confidence"] = 0.75
        data["teams"]["away"]["confidence"] = 0.80
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok)

    def test_team_confidence_wrong_type_blocked(self):
        """teams.home.confidence non-numerico viene rifiutato."""
        data = self._make_v1_payload()
        data["teams"]["home"]["confidence"] = "high"
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertFalse(ok)
        self.assertIn("confidence", msg)

    def test_low_team_confidence_generates_warning(self):
        """teams.home.confidence < 0.5 genera warning in validate_coherence."""
        data = self._make_v1_payload()
        data["teams"]["home"]["confidence"] = 0.3
        ok, warnings = OCRSchemaValidator.validate_coherence(data)
        conf_warnings = [w for w in warnings if "roster" in w.lower() and "bassa" in w.lower()]
        self.assertTrue(len(conf_warnings) > 0)

    # --- Extended event types ---

    def test_timeout_event_accepted(self):
        """Tipo evento TIMEOUT è accettato dalla validazione strutturale."""
        data = self._make_v1_payload()
        data["events"].append({"type": "TIMEOUT", "player_name": None, "team": "home", "minute": 20, "quarter": 2})
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok)

    def test_red_card_event_accepted(self):
        """Tipo evento RED_CARD è accettato."""
        data = self._make_v1_payload()
        data["events"].append({"type": "RED_CARD", "player_name": "Player 3", "team": "home", "minute": 12, "quarter": 1})
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok)

    def test_yellow_card_event_accepted(self):
        """Tipo evento YELLOW_CARD è accettato."""
        data = self._make_v1_payload()
        data["events"].append({"type": "YELLOW_CARD", "player_name": "Opponent 2", "team": "away", "minute": 8, "quarter": 1})
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok)

    def test_sanction_duration_field_accepted(self):
        """Campo sanction_duration negli eventi non rompe la validazione."""
        data = self._make_v1_payload()
        data["events"].append({
            "type": "EXCLUSION_20", "player_name": "Opponent 3", "team": "away",
            "minute": 15, "quarter": 2, "sanction_duration": 20
        })
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok)

    # --- Schema version ---

    def test_schema_version_in_mock_provider(self):
        """MockVisionProvider include schema_version: 2.0 in metadata."""
        from matches.services.vision_providers import MockVisionProvider
        from matches.models import MatchReport

        # Usa un payload costruito direttamente senza DB per velocità
        provider = MockVisionProvider()

        sport = Sport.objects.create(name="Pallanuoto", slug="pall-v2test")
        soc_h = Society.objects.create(name="SocHomeV2", sport=sport, slug="soc-h-v2")
        soc_a = Society.objects.create(name="SocAwayV2", sport=sport, slug="soc-a-v2")
        league = League.objects.create(name="LegaV2", sport=sport, slug="lega-v2")
        team_h = Team.objects.create(society=soc_h, league=league)
        team_a = Team.objects.create(society=soc_a, league=league)
        user = User.objects.create_user(username="userv2", role="athlete")
        from django.utils import timezone as tz
        match = Match.objects.create(league=league, home_team=team_h, away_team=team_a,
                                     match_date=tz.now(), home_score=3, away_score=2)
        from django.core.files.uploadedfile import SimpleUploadedFile
        report = MatchReport.objects.create(
            match=match, uploader=user,
            file=SimpleUploadedFile("f.pdf", b"x", content_type="application/pdf")
        )
        data, _ = provider.extract_data(report)
        self.assertEqual(data["metadata"].get("schema_version"), "2.0")

    def test_mock_provider_has_officials(self):
        """MockVisionProvider restituisce la sezione officials con arbitri."""
        from matches.services.vision_providers import MockVisionProvider
        from matches.models import MatchReport

        sport = Sport.objects.create(name="Pallanuoto", slug="pall-off-test")
        soc_h = Society.objects.create(name="OffHome", sport=sport, slug="off-h")
        soc_a = Society.objects.create(name="OffAway", sport=sport, slug="off-a")
        league = League.objects.create(name="OffLega", sport=sport, slug="off-lega")
        team_h = Team.objects.create(society=soc_h, league=league)
        team_a = Team.objects.create(society=soc_a, league=league)
        user = User.objects.create_user(username="useroff", role="athlete")
        from django.utils import timezone as tz
        match = Match.objects.create(league=league, home_team=team_h, away_team=team_a,
                                     match_date=tz.now(), home_score=2, away_score=1)
        from django.core.files.uploadedfile import SimpleUploadedFile
        report = MatchReport.objects.create(
            match=match, uploader=user,
            file=SimpleUploadedFile("f.pdf", b"x", content_type="application/pdf")
        )
        data, _ = MockVisionProvider().extract_data(report)

        self.assertIn("officials", data)
        self.assertIsInstance(data["officials"]["referees"], list)
        self.assertGreater(len(data["officials"]["referees"]), 0)

    def test_mock_provider_has_coaches(self):
        """MockVisionProvider restituisce coach per home e away."""
        from matches.services.vision_providers import MockVisionProvider
        from matches.models import MatchReport

        sport = Sport.objects.create(name="Pallanuoto", slug="pall-coach-test")
        soc_h = Society.objects.create(name="CoachHome", sport=sport, slug="coach-h")
        soc_a = Society.objects.create(name="CoachAway", sport=sport, slug="coach-a")
        league = League.objects.create(name="CoachLega", sport=sport, slug="coach-lega")
        team_h = Team.objects.create(society=soc_h, league=league)
        team_a = Team.objects.create(society=soc_a, league=league)
        user = User.objects.create_user(username="usercoach", role="athlete")
        from django.utils import timezone as tz
        match = Match.objects.create(league=league, home_team=team_h, away_team=team_a,
                                     match_date=tz.now(), home_score=4, away_score=3)
        from django.core.files.uploadedfile import SimpleUploadedFile
        report = MatchReport.objects.create(
            match=match, uploader=user,
            file=SimpleUploadedFile("f.pdf", b"x", content_type="application/pdf")
        )
        data, _ = MockVisionProvider().extract_data(report)

        self.assertIsNotNone(data["teams"]["home"].get("coach"))
        self.assertIsNotNone(data["teams"]["away"].get("coach"))

    def test_match_info_v2_fields_optional(self):
        """venue, round, group assenti sul payload v1 non rompono la validazione."""
        data = self._make_v1_payload()
        self.assertNotIn("venue", data["match_info"])
        self.assertNotIn("round", data["match_info"])
        self.assertNotIn("group", data["match_info"])
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok)

    def test_match_info_v2_fields_when_present(self):
        """venue, round, group presenti non rompono la validazione."""
        data = self._make_v1_payload()
        data["match_info"]["venue"] = "Piscina Comunale di Bergamo"
        data["match_info"]["round"] = "Giornata 5"
        data["match_info"]["group"] = "Girone A"
        ok, msg = OCRSchemaValidator.validate(data)
        self.assertTrue(ok)
