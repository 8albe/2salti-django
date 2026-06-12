import os
import django
from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from core.models import Team, League, Sport, Society
from matches.models import Match, MatchReport, OCRRawResponse
from matches.services.ocr_providers.openai import OpenAIProvider

class OpenAIProviderTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto")
        self.league = League.objects.create(name="Serie A", sport=self.sport)
        
        # Society is required for Team
        self.soc_home = Society.objects.create(name="Soc Home", sport=self.sport)
        self.soc_away = Society.objects.create(name="Soc Away", sport=self.sport)
        
        self.home = Team.objects.create(society=self.soc_home)
        self.away = Team.objects.create(society=self.soc_away)
        
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.home,
            away_team=self.away,
            match_date=timezone.now()
        )
        self.report = MatchReport.objects.create(
            match=self.match,
            file=SimpleUploadedFile("report.jpg", b"fake image content", content_type="image/jpeg"),
            status=MatchReport.Status.UPLOADED
        )

    @patch('matches.services.ocr_providers.openai.OpenAI')
    @patch('matches.services.ocr_providers.openai.ImagePreprocessor.process')
    def test_openai_provider_process_document(self, mock_preprocess, mock_openai_class):
        # Setup mock
        mock_preprocess.return_value = self.report.file.path
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.id = "req_123"
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"match_info": {"home_team": "Team Home"}, "metadata": {"confidence": 0.9}}'))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        
        provider = OpenAIProvider()
        context = {'report_id': self.report.id}
        
        # Execute
        data = provider.process_document(self.report.file.path, context=context)
        
        # Verify
        self.assertEqual(data['match_info']['home_team'], "Team Home")
        self.assertEqual(data['metadata']['provider'], "openai-gpt4o")
        
        # Verify RawResponse persistence
        raw_res = OCRRawResponse.objects.filter(report=self.report).first()
        self.assertIsNotNone(raw_res)
        self.assertEqual(raw_res.provider_id, "openai-gpt4o")
        self.assertEqual(raw_res.request_id, "req_123")
        self.assertEqual(raw_res.raw_response['match_info']['home_team'], "Team Home")
