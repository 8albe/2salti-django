from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from core.models import Sport, League, Team
from matches.models import Match, MatchReport
from matches.forms import MatchReportUploadForm
from django.utils import timezone

User = get_user_model()

class MatchReportDeduplicationTest(TestCase):
    def setUp(self):
        from core.models import Society
        self.sport = Sport.objects.create(name="Water Polo", slug="wp")
        self.society = Society.objects.create(name="Pro Recco Society", sport=self.sport, city="Recco")
        self.league = League.objects.create(name="Serie A1", sport=self.sport, category='SENIOR')
        self.team1 = Team.objects.create(society=self.society, category='SENIOR')
        self.team2 = Team.objects.create(society=self.society, category='U20')
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team1,
            away_team=self.team2,
            match_date=timezone.now()
        )
        self.user = User.objects.create_user(username="staff", password="password", role='staff')

    def test_unique_file_upload_stores_hash(self):
        """Un file nuovo viene caricato e l'hash viene memorizzato."""
        file_content = b"content of unique file 1"
        uploaded_file = SimpleUploadedFile("report1.pdf", file_content, content_type="application/pdf")
        
        form = MatchReportUploadForm(data={}, files={'file': uploaded_file})
        self.assertTrue(form.is_valid())
        
        report = form.save(commit=False)
        report.match = self.match
        report.uploader = self.user
        report.save()
        
        self.assertIsNotNone(report.file_hash)
        self.assertEqual(len(report.file_hash), 64) # SHA256 length

    def test_duplicate_file_upload_is_blocked(self):
        """Caricare lo stesso file due volte deve fallire la validazione del form."""
        file_content = b"content of same file"
        
        # Primo caricamento
        MatchReport.objects.create(
            match=self.match,
            uploader=self.user,
            file=SimpleUploadedFile("first.pdf", file_content, content_type="application/pdf")
        )
        
        # Secondo caricamento (stesso contenuto)
        uploaded_file = SimpleUploadedFile("duplicate.pdf", file_content, content_type="application/pdf")
        form = MatchReportUploadForm(data={}, files={'file': uploaded_file})
        
        self.assertFalse(form.is_valid())
        self.assertIn("già stato caricato", form.errors['file'][0])

    def test_different_files_allowed(self):
        """File diversi devono essere caricati senza problemi."""
        MatchReport.objects.create(
            match=self.match,
            uploader=self.user,
            file=SimpleUploadedFile("first.pdf", b"content 1", content_type="application/pdf")
        )
        
        uploaded_file = SimpleUploadedFile("second.pdf", b"content 2", content_type="application/pdf")
        form = MatchReportUploadForm(data={}, files={'file': uploaded_file})
        
        self.assertTrue(form.is_valid())

    def test_file_pointer_reset_after_hashing(self):
        """Verifica che il puntatore del file venga resettato e il file salvato correttamente."""
        file_content = b"content of file with pointer reset check"
        uploaded_file = SimpleUploadedFile("reset.pdf", file_content, content_type="application/pdf")
        
        form = MatchReportUploadForm(data={}, files={'file': uploaded_file})
        self.assertTrue(form.is_valid())
        
        report = form.save(commit=False)
        report.match = self.match
        report.uploader = self.user
        report.save()
        
        # Rileggiamo il file dal disco per vedere se il contenuto è completo
        report.refresh_from_db()
        with report.file.open('rb') as f:
            self.assertEqual(f.read(), file_content)
