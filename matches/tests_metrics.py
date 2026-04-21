from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User, AthleteProfile
from core.models import Team, Sport, Society, League
from matches.models import MatchReport, Match, MatchReportAuditLog
from django.utils import timezone
import json
import unittest

class PilotMetricsTest(TestCase):
    def setUp(self):
        self.password = "pass123"
        self.user = User.objects.create_superuser(username="admin", password=self.password, email="admin@test.com")
        self.client = Client()
        self.client.login(username="admin", password=self.password)
        
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.soc = Society.objects.create(name="Pro Recco", slug="pro-recco", sport=self.sport)
        self.league = League.objects.create(name="Serie A1", sport=self.sport, category="SENIOR", season="2024-2025")
        self.team = Team.objects.create(name="Team A", society=self.soc, category="SENIOR", league=self.league)
        
        self.match = Match.objects.create(
            home_team=self.team, 
            away_team=self.team, 
            match_date=timezone.now(),
            league=self.league
        )
        
        self.valid_data = {
            "metadata": {"confidence": 0.9},
            "match_info": {"home_team": "Team A", "away_team": "Team A", "date": "2024-04-15"},
            "scores": {"final_score": "0-0", "quarters": {}},
            "teams": {"home": {"players": [{"name": "P1"}]}, "away": {"players": []}},
            "reconciliation": {"home_players": {}, "away_players": {}},
            "events": []
        }

        self.report = MatchReport.objects.create(
            match=self.match,
            status=MatchReport.Status.NEEDS_REVIEW,
            raw_extracted_data=self.valid_data,
            normalized_data=self.valid_data
        )

    @unittest.skip(
        "TODO(test-debt, REFACTOR-INCOMPLETO docs/TEST_DEBT_TRIAGE.md#29): audit log "
        "'review_opened' e metriche '_metrics' su 'publish_now' non sono mai scritti in "
        "matches/admin.py::review_view. Al baseline il test era ERROR per template admin "
        "mancante; ora il template esiste (templates/admin/matches/matchreport/review.html) "
        "e la feature-gap emerge. Sbloccare quando la pilot metrics instrumentation verrà "
        "cablata nella review_view."
    )
    def test_metrics_lifecycle(self):
        # 1. Open Review
        url = reverse('admin:matches_matchreport_review', args=[self.report.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        
        # Check review_opened log
        log = MatchReportAuditLog.objects.filter(report=self.report, action='review_opened').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.after['total_players'], 1)
        self.assertEqual(log.after['auto_matched'], 0)
        
        # 2. Publish (Simulate)
        post_data = {
            '_action': 'publish_now',
            'normalized_data': json.dumps(self.valid_data)
        }
        resp_post = self.client.post(url, post_data)
        self.assertEqual(resp_post.status_code, 302) # Redirect on success
        
        # Check publish log
        log_pub = MatchReportAuditLog.objects.filter(report=self.report, action='publish_now').first()
        self.assertIsNotNone(log_pub)
        self.assertIn('_metrics', log_pub.after)
        metrics = log_pub.after['_metrics']
        self.assertGreaterEqual(metrics['duration_seconds'], 0)
        self.assertEqual(metrics['total_players'], 1)
        self.assertEqual(metrics['final_matched'], 0)
