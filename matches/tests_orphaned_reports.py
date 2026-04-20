from django.test import TestCase
from django.core.exceptions import ValidationError
from matches.models import Match, MatchReport
from matches.forms import MatchReportAdminForm
from matches.services.ocr_service import OCRService
from core.models import Team, Society, Sport, League
from django.utils import timezone

class OrphanedReportsTests(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="WP", slug="wp")
        self.league = League.objects.create(name="L1", sport=self.sport, slug="l1")
        self.soc1 = Society.objects.create(name="S1", sport=self.sport, slug="s1")
        self.soc2 = Society.objects.create(name="S2", sport=self.sport, slug="s2")
        self.t1 = Team.objects.create(society=self.soc1, category="U18", league=self.league)
        self.t2 = Team.objects.create(society=self.soc2, category="U18", league=self.league)
        self.match = Match.objects.create(
            league=self.league, home_team=self.t1, away_team=self.t2, 
            match_date=timezone.now(), location="Piscina"
        )

    def test_form_rejects_missing_file_for_file_channel(self):
        """Verifica che il form admin blocchi la creazione di report FILE senza allegato."""
        data = {
            'match': self.match.id,
            'source_channel': 'FILE',
            'status': 'UPLOADED',
            'internal_notes': 'Test orphans'
        }
        form = MatchReportAdminForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('file', form.errors)
        self.assertIn("obbligatoriamente avere un file allegato", form.errors['file'][0])

    def test_ocr_service_handles_missing_file_gracefully(self):
        """Verifica che OCRService rifiuti di processare report orfani."""
        # Creiamo forzatamente un report orfano (bypassando il form)
        report = MatchReport.objects.create(
            match=self.match,
            source_channel='FILE',
            status='UPLOADED'
        )
        
        # Tentiamo l'elaborazione
        success = OCRService.process_and_update(report)
        
        # Verifica
        report.refresh_from_db()
        self.assertFalse(success)
        self.assertEqual(report.status, MatchReport.Status.REJECTED)
        self.assertIn("ERRORE: Nessun file associato", report.validation_notes)
