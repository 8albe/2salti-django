from django.test import TestCase, override_settings
from django.core import mail
from django.utils import timezone
from matches.models import Match, MatchReport
from core.models import Sport, League, Team, Society
from accounts.models import User
from matches.services.ocr_service import OCRService
from unittest.mock import patch, MagicMock
import json

class NotificationTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.society_h = Society.objects.create(name="Pro Recco", city="Recco", sport=self.sport)
        self.society_a = Society.objects.create(name="AN Brescia", city="Brescia", sport=self.sport)
        self.league = League.objects.create(name="Serie A1", sport=self.sport, category="SENIOR")
        self.team_h = Team.objects.create(society=self.society_h, category="SENIOR", league=self.league)
        self.team_a = Team.objects.create(society=self.society_a, category="SENIOR", league=self.league)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_h,
            away_team=self.team_a,
            match_date=timezone.now()
        )
        self.admin = User.objects.create_superuser(username="admin", email="admin@test.com", password="pass")
        self.report = MatchReport.objects.create(
            match=self.match,
            uploader=self.admin,
            status=MatchReport.Status.UPLOADED,
            source_channel='DIGITAL'
        )

    @override_settings(OPS_EMAIL_RECIPIENTS=['ops@test.com'], TELEGRAM_BOT_TOKEN='', TELEGRAM_CHAT_ID='')
    @patch('matches.services.ocr_quality_gate.OCRQualityGate.evaluate')
    @patch('matches.services.ocr_service.OCRService.get_provider')
    def test_notification_on_quality_gate_failure(self, mock_get_provider, mock_evaluate):
        # Mock provider
        mock_provider = MagicMock()
        mock_provider.extract_data.return_value = ({'metadata': {'confidence': 0.1}}, "raw content")
        mock_get_provider.return_value = mock_provider
        
        # Mock Quality Gate failure
        mock_evaluate.return_value = (False, ["Confidence too low"], ["Warning"], ["Info"])
        
        # Run process
        OCRService.process_and_update(self.report)
        
        # Verify status
        self.assertEqual(self.report.status, MatchReport.Status.NEEDS_REVIEW)
        
        # Verify Email
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("REVISIONE NECESSARIA", mail.outbox[0].subject)
        self.assertIn("ops@test.com", mail.outbox[0].to)
        self.assertIn("Confidence too low", mail.outbox[0].body)

    @override_settings(OPS_EMAIL_RECIPIENTS=['ops@test.com'], TELEGRAM_BOT_TOKEN='fake_token', TELEGRAM_CHAT_ID='fake_id')
    @patch('httpx.Client.post')
    def test_telegram_notification_call(self, mock_post):
        from core.services.notification_service import NotificationService
        
        mock_post.return_value.status_code = 200
        
        # Update report status to NEEDS_REVIEW manually to test the service
        self.report.status = MatchReport.Status.NEEDS_REVIEW
        self.report.validation_notes = json.dumps({"blocking": ["Test error"]})
        self.report.save()
        
        NotificationService.notify_report_needs_review(self.report)
        
        # Verify Telegram call
        self.assertTrue(mock_post.called)
        args, kwargs = mock_post.call_args
        self.assertIn("fake_token", args[0])
        self.assertIn("Test error", kwargs['json']['text'])
