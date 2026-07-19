import json

from django.test import TestCase, override_settings
from django.core import mail
from django.utils import timezone

from matches.models import Match, MatchReport
from matches.services.ocr_service import OCRService
from core.services.notification_service import NotificationService
from core.models import Team, Society, Sport, League


class _StubProvider:
    """
    Provider di test: ritorna dati OCR fissi senza toccare file o API esterne.
    Volutamente SENZA process_document, così OCRService.process_and_update usa
    il ramo extract_data (interfaccia legacy). Non dereferenzia match_report.match,
    quindi è utilizzabile anche su report senza match collegato (a differenza di
    MockVisionProvider, che legge match.home_team).
    """
    def __init__(self, data):
        self._data = data

    def extract_data(self, match_report):
        return self._data, json.dumps(self._data)


def _ocr_payload(home, away, final="10-8", quarters=None, confidence=0.95):
    if quarters is None:
        # somma coerente col finale 10-8: home 3+2+3+2=10, away 2+2+2+2=8
        quarters = {"1": [3, 2], "2": [2, 2], "3": [3, 2], "4": [2, 2]}
    return {
        "metadata": {
            "schema_version": "2.0",
            "confidence": confidence,
            "confidence_fields": {"home_team": 0.99, "away_team": 0.99, "final_score": 0.99},
            "extraction_warnings": [],
        },
        "match_info": {"home_team": home, "away_team": away, "date": None},
        "officials": {"confidence": 0.8, "referees": [], "timekeeper": None},
        "scores": {"final_score": final, "quarters": quarters},
        "teams": {
            "home": {"name": home, "players": [{"number": 1, "name": "Rossi"}]},
            "away": {"name": away, "players": [{"number": 1, "name": "Bianchi"}]},
        },
        "events": [],
    }


class OCRNoMatchPathTests(TestCase):
    """
    Copre il path 'report senza match collegato' in process_and_update, che
    prima crashava: reconciliation dereferenziava match=None (AttributeError),
    l'except chiamava il notifier che dereferenziava di nuovo match=None
    (seconda AttributeError, non gestita, propagata al chiamante → 500).
    """

    def setUp(self):
        OCRService._provider = None
        self.sport = Sport.objects.create(name="WP-nm", slug="wp-nm")
        self.league = League.objects.create(name="L-nm", sport=self.sport, slug="l-nm")

    def tearDown(self):
        OCRService._provider = None

    def test_no_match_discovery_fails_lands_needs_review_without_crash(self):
        # Nessun team creato → la discovery non risolve le squadre → match resta None.
        OCRService.set_provider(_StubProvider(_ocr_payload("Fantasma Casa", "Fantasma Ospite")))
        report = MatchReport.objects.create(
            match=None, source_channel='DIGITAL', status='UPLOADED',
        )

        # Non deve sollevare eccezioni.
        result = OCRService.process_and_update(report)

        report.refresh_from_db()
        self.assertTrue(result)  # elaborazione completata senza crash
        self.assertEqual(report.status, MatchReport.Status.NEEDS_REVIEW)
        self.assertIsNone(report.match_id)

        notes = json.loads(report.validation_notes)
        self.assertTrue(
            any("Nessun match collegato" in b for b in notes["blocking"]),
            f"blocker 'no match' assente: {notes['blocking']}",
        )
        # reconciliation presente ma vuota: non ha dereferenziato match.
        rec = report.normalized_data.get("reconciliation", {})
        self.assertIsNone(rec.get("home_team_id"))
        self.assertIsNone(rec.get("away_team_id"))

    @override_settings(
        OPS_EMAIL_RECIPIENTS=["ops@example.com"],
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_notifier_handles_match_none_safely(self):
        report = MatchReport.objects.create(
            match=None, source_channel='DIGITAL', status='NEEDS_REVIEW',
            validation_notes=json.dumps({"blocking": ["Nessun match collegato rilevato."]}),
        )

        # Il notifier non deve sollevare con match=None.
        NotificationService.notify_report_needs_review(report)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("nessuna partita collegata", mail.outbox[0].subject)
        self.assertIn(str(report.id), mail.outbox[0].subject)

    def test_no_match_discovery_resolves_links_match(self):
        # Con teams e match presenti, la discovery risolve dal solo OCR e collega il match.
        soc1 = Society.objects.create(name="Alfa Nuoto", sport=self.sport, slug="alfa-nm", city="Roma")
        soc2 = Society.objects.create(name="Beta Nuoto", sport=self.sport, slug="beta-nm", city="Roma")
        t1 = Team.objects.create(society=soc1, league=self.league, name="Alfa Nuoto", slug="alfa-t-nm")
        t2 = Team.objects.create(society=soc2, league=self.league, name="Beta Nuoto", slug="beta-t-nm")
        match = Match.objects.create(
            league=self.league, home_team=t1, away_team=t2,
            match_date=timezone.now(), location="Piscina",
        )

        OCRService.set_provider(_StubProvider(_ocr_payload("Alfa Nuoto", "Beta Nuoto")))
        report = MatchReport.objects.create(
            match=None, source_channel='DIGITAL', status='UPLOADED',
        )

        result = OCRService.process_and_update(report)

        report.refresh_from_db()
        self.assertTrue(result)
        self.assertEqual(report.match_id, match.id)  # discovery ha collegato il match
        self.assertEqual(report.status, MatchReport.Status.EXTRACTED)
