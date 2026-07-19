import os
import django
from unittest.mock import MagicMock, patch

# Setup Django if running standalone
if __name__ == "__main__":
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from matches.models import MatchReport, Match
from matches.services.ocr_service import OCRService
from matches.services.vision_providers import BaseVisionProvider
from core.models import Sport, League, Society, Team
from django.utils import timezone

class StatusSemanticsTestCase(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Water Polo", slug="wp")
        self.society = Society.objects.create(name="Pro Recco", sport=self.sport, slug="recco")
        self.league = League.objects.create(name="Serie A1", sport=self.sport)
        self.team = Team.objects.create(society=self.society, league=self.league)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team,
            match_date=timezone.now()
        )
        self.report = MatchReport.objects.create(
            match=self.match,
            status=MatchReport.Status.UPLOADED,
            source_type='MANUAL',
            file=SimpleUploadedFile(
                name='test_referto.pdf',
                content=b'%PDF-1.4 dummy content',
                content_type='application/pdf',
            ),
        )

    def test_ocr_failure_moves_to_needs_review(self):
        """
        Verify that a technical failure in OCRService moves the report to NEEDS_REVIEW,
        not REJECTED.
        """
        with patch('matches.services.ocr_service.OCRService.get_provider') as mock_get:
            provider = MagicMock(spec=BaseVisionProvider)
            provider.extract_data.side_effect = Exception("Gemini API Timeout")
            mock_get.return_value = provider
            
            success = OCRService.process_and_update(self.report)
            
            self.assertFalse(success)
            self.report.refresh_from_db()
            
            self.assertEqual(self.report.status, MatchReport.Status.NEEDS_REVIEW)
            self.assertIn("Errore Tecnico OCR", self.report.validation_notes)
            self.assertIn("Gemini API Timeout", self.report.validation_notes)

if __name__ == "__main__":
    from django.core.management import call_command
    call_command('test', 'matches.tests_status_semantics')
