import os
import io
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from django.test import TestCase
from django.core.files.storage import default_storage
from matches.models import Match, MatchReport, InboundEmail
from matches.services.email_ingestion import EmailIngestionService
from core.models import League, Team, Sport, Society
from seasons.models import SeasonArchive
from django.utils import timezone

class EmailIngestionTestCase(TestCase):
    def setUp(self):
        # Setup basic data
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.society = Society.objects.create(name="Pro Recco", slug="pro-recco", sport=self.sport)
        self.league = League.objects.create(name="Serie A1", sport=self.sport, category='SENIOR')
        self.team_h = Team.objects.create(society=self.society, category='SENIOR', league=self.league)
        self.team_a = Team.objects.create(
            society=Society.objects.create(name="AN Brescia", slug="an-brescia", sport=self.sport), 
            category='SENIOR', 
            league=self.league
        )
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_h,
            away_team=self.team_a,
            match_date=timezone.now()
        )

    def create_mock_eml(self, message_id, subject, attachment_name, attachment_content):
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = 'referee@example.com'
        msg['Message-ID'] = message_id
        msg['Date'] = timezone.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
        
        body = MIMEText("In allegato il referto.")
        msg.attach(body)
        
        part = MIMEApplication(attachment_content)
        part.add_header('Content-Disposition', 'attachment', filename=attachment_name)
        msg.attach(part)
        
        return msg.as_bytes()

    def test_successful_ingestion(self):
        """Verifica che un'email valida crei un MatchReport."""
        eml_raw = self.create_mock_eml(
            '<msg1@example.com>', 
            f"Referto Match ID: {self.match.id}", 
            "referto.pdf", 
            b"%PDF-1.4 dummy content"
        )
        
        results = EmailIngestionService.process_raw_eml(eml_raw)
        
        self.assertEqual(len(results), 1)
        report, created = results[0]
        self.assertTrue(created)
        self.assertEqual(report.match, self.match)
        self.assertEqual(report.source_type, 'EMAIL')
        self.assertEqual(report.inbound_email.message_id, '<msg1@example.com>')
        # Assert that the file is in the right directory and has the right extension
        self.assertTrue(report.file.name.startswith('match_reports/'))
        self.assertTrue(report.file.name.endswith('.pdf'))

    def test_deduplication_message_id(self):
        """Verifica che la stessa email non venga processata due volte."""
        eml_raw = self.create_mock_eml('<msg-dedup@example.com>', "Test", "r1.pdf", b"content")
        
        # Primo processamento
        EmailIngestionService.process_raw_eml(eml_raw)
        self.assertEqual(InboundEmail.objects.count(), 1)
        self.assertEqual(MatchReport.objects.count(), 1)
        
        # Secondo processamento
        results = EmailIngestionService.process_raw_eml(eml_raw)
        self.assertEqual(InboundEmail.objects.count(), 1)
        self.assertEqual(MatchReport.objects.count(), 1)
        self.assertFalse(results[0][1]) # Non creato

    def test_deduplication_file_hash(self):
        """Verifica che lo stesso file in email diverse non crei duplicati."""
        file_content = b"very unique content"
        
        # Email 1
        EmailIngestionService.process_raw_eml(
            self.create_mock_eml('<m1@ex.com>', "Match 1", "file.pdf", file_content)
        )
        
        # Email 2 (stesso file, diverso message-id)
        results = EmailIngestionService.process_raw_eml(
            self.create_mock_eml('<m2@ex.com>', "Match 2", "other_name.pdf", file_content)
        )
        
        self.assertEqual(MatchReport.objects.count(), 1)
        self.assertFalse(results[0][1])

    def test_invalid_extension_skipped(self):
        """Verifica che i file non supportati (es. .exe) vengano scartati."""
        eml_raw = self.create_mock_eml('<msg-exe@example.com>', "Virus", "malware.exe", b"bad stuff")
        results = EmailIngestionService.process_raw_eml(eml_raw)
        
        self.assertEqual(len(results), 0)
        self.assertEqual(MatchReport.objects.count(), 0)
        self.assertEqual(InboundEmail.objects.count(), 1) # L'email è comunque loggata come processata
