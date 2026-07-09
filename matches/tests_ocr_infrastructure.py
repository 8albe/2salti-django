from django.test import TestCase
from matches.models import Match, MatchReport, OCRRawResponse
from core.models import Team, League, Sport, Society
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()


class OCRInfrastructureTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Waterpolo")
        self.league = League.objects.create(name="Serie A", sport=self.sport)

        self.soc_a = Society.objects.create(name="Society A", sport=self.sport, city="Rome")
        self.soc_b = Society.objects.create(name="Society B", sport=self.sport, city="Milan")

        self.home_team = Team.objects.create(society=self.soc_a)
        self.away_team = Team.objects.create(society=self.soc_b)

        self.match = Match.objects.create(
            league=self.league,
            home_team=self.home_team,
            away_team=self.away_team,
            match_date=timezone.now()
        )
        self.report = MatchReport.objects.create(
            match=self.match,
            status=MatchReport.Status.UPLOADED,
            source_channel='FILE'
        )

    def test_ocr_raw_response_creation(self):
        """Verify that OCRRawResponse can be saved and linked to a report."""
        raw_data = {"raw": "payload", "tokens": 123}
        response = OCRRawResponse.objects.create(
            report=self.report,
            provider_id="dummy-provider",
            raw_response=raw_data,
            status_code=200,
            latency_ms=150
        )

        self.assertEqual(self.report.ocr_responses.count(), 1)
        resp = self.report.ocr_responses.first()
        self.assertEqual(resp.provider_id, "dummy-provider")
        self.assertEqual(resp.raw_response["raw"], "payload")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.latency_ms, 150)
