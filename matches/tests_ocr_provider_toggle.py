from django.test import TestCase, override_settings
from matches.services.ocr_service import OCRService
from matches.services.vision_providers import MockVisionProvider, GPT4oVisionProvider
from matches.models import Match, MatchReport
from core.models import League, Sport, Team, Society
from django.utils import timezone
from unittest.mock import patch


class OCRProviderToggleTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="WP", slug="wp-prov")
        self.soc_a = Society.objects.create(name="T1", slug="t1", sport=self.sport)
        self.league = League.objects.create(name="BootLeague", sport=self.sport, category="SENIOR")
        self.team_a = Team.objects.create(society=self.soc_a, category="SENIOR", name="T1")
        self.match = Match.objects.create(
            league=self.league, home_team=self.team_a, away_team=self.team_a, match_date=timezone.now()
        )
        self.report = MatchReport.objects.create(
            match=self.match,
            status=MatchReport.Status.UPLOADED,
        )
        OCRService._provider = None

    def tearDown(self):
        OCRService._provider = None

    @override_settings(OCR_PROVIDER='mock')
    def test_mock_provider_selected(self):
        provider = OCRService.get_provider()
        self.assertIsInstance(provider, MockVisionProvider)

    @override_settings(OCR_PROVIDER='gpt4o', OPENAI_API_KEY='test_key')
    @patch('matches.services.vision_providers.GPT4oVisionProvider.__init__', return_value=None)
    def test_gpt4o_provider_selected(self, mock_init):
        provider = OCRService.get_provider()
        self.assertIsInstance(provider, GPT4oVisionProvider)
        mock_init.assert_called_once()

    @override_settings(OCR_PROVIDER='gpt4o', OPENAI_API_KEY='')
    def test_missing_api_key_raises_error(self):
        with self.assertRaises(ValueError) as context:
            OCRService.get_provider()
        self.assertIn("OPENAI_API_KEY mancante", str(context.exception))

    @override_settings(OCR_PROVIDER='gpt4o', OPENAI_API_KEY='')
    def test_process_and_update_handles_init_failure_safely(self):
        # Even if get_provider raises an exception, process_and_update must handle it
        # and push the report to NEEDS_REVIEW without crashing.
        success = OCRService.process_and_update(self.report)
        self.report.refresh_from_db()
        self.assertFalse(success)
        self.assertEqual(self.report.status, MatchReport.Status.NEEDS_REVIEW)
        self.assertIn("OPENAI_API_KEY mancante", self.report.validation_notes)
        self.assertIn("Init/Config Error", self.report.validation_notes)

    @override_settings(OCR_PROVIDER='mock')
    def test_process_and_update_with_mock_runs_quality_gate(self):
        # Mock provider returns high confidence and good data,
        # but because match has home_team == away_team, quality gate blocks it!
        # This confirms quality gate runs after provider returns!
        success = OCRService.process_and_update(self.report)
        self.report.refresh_from_db()

        # Is it EXTRACTED or blocked to NEEDS_REVIEW?
        # MockVisionProvider injects home_team = match.home_team.society.name, away_team = match.away_team.society.name
        # Both will be "T1". Quality gate complains if home_team == away_team.
        self.assertTrue(success)
        self.assertEqual(self.report.status, MatchReport.Status.NEEDS_REVIEW)
        self.assertIn("coincidono", self.report.validation_notes)
