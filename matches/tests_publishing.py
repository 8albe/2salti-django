from django.test import TestCase
from django.utils import timezone
from core.models import Sport, Society, League, Team, LeagueStanding
from matches.models import Match, MatchReport
from matches.services.publishing_service import PublishingService
from matches.services.standings_service import StandingsService
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model

User = get_user_model()

class PublishingServiceTestCase(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.soc_home = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco")
        self.soc_away = Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia")
        self.league = League.objects.create(name="Serie A1", sport=self.sport, category="SENIOR", slug="serie-a1")
        self.team_home = Team.objects.create(society=self.soc_home, category="SENIOR", league=self.league)
        self.team_away = Team.objects.create(society=self.soc_away, category="SENIOR", league=self.league)
        self.user = User.objects.create_superuser(username="admin", email="admin@test.com", password="password")
        
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_home,
            away_team=self.team_away,
            match_date=timezone.now(),
            home_score=0,
            away_score=0,
            is_finished=False
        )
        
        self.report = MatchReport.objects.create(
            match=self.match,
            uploader=self.user,
            status=MatchReport.Status.VALIDATED,
            file=SimpleUploadedFile("referto.pdf", b"pdf_content", content_type="application/pdf"),
            normalized_data={
                "metadata": {"confidence": 0.95, "confidence_fields": {}, "extraction_warnings": []},
                "match_info": {"home_team": "Pro Recco", "away_team": "AN Brescia", "date": "2026-01-15"},
                "scores": {
                    "final_score": "12-8",
                    "quarters": {"1": [3, 2], "2": [4, 2], "3": [3, 1], "4": [2, 3]}
                },
                "teams": {
                    "home": {"name": "Pro Recco", "players": [
                        {"number": i, "name": f"Player H{i}"} for i in range(1, 14)
                    ]},
                    "away": {"name": "AN Brescia", "players": [
                        {"number": i, "name": f"Player A{i}"} for i in range(1, 14)
                    ]}
                },
                "events": [
                    {"type": "GOAL", "team": "home", "minute": 1, "player_name": None},
                    {"type": "GOAL", "team": "home", "minute": 2, "player_name": None},
                    {"type": "GOAL", "team": "home", "minute": 3, "player_name": None},
                    {"type": "GOAL", "team": "home", "minute": 4, "player_name": None},
                    {"type": "GOAL", "team": "home", "minute": 5, "player_name": None},
                    {"type": "GOAL", "team": "home", "minute": 6, "player_name": None},
                    {"type": "GOAL", "team": "home", "minute": 7, "player_name": None},
                    {"type": "GOAL", "team": "home", "minute": 8, "player_name": None},
                    {"type": "GOAL", "team": "home", "minute": 9, "player_name": None},
                    {"type": "GOAL", "team": "home", "minute": 10, "player_name": None},
                    {"type": "GOAL", "team": "home", "minute": 11, "player_name": None},
                    {"type": "GOAL", "team": "home", "minute": 12, "player_name": None},
                    {"type": "GOAL", "team": "away", "minute": 13, "player_name": None},
                    {"type": "GOAL", "team": "away", "minute": 14, "player_name": None},
                    {"type": "GOAL", "team": "away", "minute": 15, "player_name": None},
                    {"type": "GOAL", "team": "away", "minute": 16, "player_name": None},
                    {"type": "GOAL", "team": "away", "minute": 17, "player_name": None},
                    {"type": "GOAL", "team": "away", "minute": 18, "player_name": None},
                    {"type": "GOAL", "team": "away", "minute": 19, "player_name": None},
                    {"type": "GOAL", "team": "away", "minute": 20, "player_name": None},
                ]
            }
        )

    def test_publish_valid_report(self):
        """Verifica che un report in stato VALIDATED aggiorni correttamente il match"""
        success, msg = PublishingService.publish_report(self.report)
        
        self.assertTrue(success)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MatchReport.Status.PUBLISHED)
        
        self.match.refresh_from_db()
        self.assertTrue(self.match.is_finished)
        self.assertEqual(self.match.home_score, 12)
        self.assertEqual(self.match.away_score, 8)
        self.assertEqual(self.match.quarter_scores["1"], [3, 2])

    def test_publish_invalid_state(self):
        """Verifica che i report non VALIDATED non vengano pubblicati"""
        self.report.status = MatchReport.Status.EXTRACTED
        self.report.save()
        
        success, msg = PublishingService.publish_report(self.report)
        
        self.assertFalse(success)
        self.assertIn("deve essere in stato VALIDATED", msg)
        self.match.refresh_from_db()
        self.assertFalse(self.match.is_finished)

    def test_admin_action_publish(self):
        """Verifica l'action 'publish_reports' via Django Admin"""
        self.client.force_login(self.user)
        from django.urls import reverse
        
        url = reverse('admin:matches_matchreport_changelist')
        data = {
            'action': 'publish_reports',
            '_selected_action': [self.report.id],
            'index': 0,
            'select_across': 0,
        }
        
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        
        self.match.refresh_from_db()
        self.assertEqual(self.match.home_score, 12)
        self.assertContains(response, "Pubblicati: 1")

    def test_idempotent_republish(self):
        """Verifica che ri-pubblicare un referto non duplichi gli eventi statistici."""
        success, msg = PublishingService.publish_report(self.report)
        self.assertTrue(success)
        
        from matches.models import MatchEvent
        count_before = MatchEvent.objects.filter(match=self.match).count()
        
        # Ripubblicazione
        success2, msg2 = PublishingService.publish_report(self.report)
        self.assertTrue(success2)
        self.assertIn("Ripubblicato", msg2)
        
        count_after = MatchEvent.objects.filter(match=self.match).count()
        self.assertEqual(count_before, count_after)

    def test_publish_atomic_rollback(self):
        """Verifica che se si verifica un errore durante la creazione degli eventi, l'intero publish faccia rollback"""
        import unittest.mock as mock
        
        # Mute logging temporarily to avoid noise in test output
        import logging
        logger = logging.getLogger('matches.services.publishing_service')
        logger.setLevel(logging.CRITICAL)
        
        with mock.patch('matches.models.MatchEvent.objects.filter') as mock_filter:
            # Simuliamo un'eccezione a runtime durante il processo di db
            mock_filter.side_effect = Exception("Simulated mid-flight crash")
            
            # force=True per bypassare il guardrail 'Zero eventi' e testare il rollback atomico
            success, msg = PublishingService.publish_report(self.report, force=True)
            self.assertFalse(success)
            self.assertIn("Simulated mid-flight crash", msg)
            
        # Il report non deve essere in stato PUBLISHED
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MatchReport.Status.VALIDATED)
        
        # Il match NON deve avere is_finished a True, dato che ha fatto rollback
        self.match.refresh_from_db()
        self.assertFalse(self.match.is_finished)
        self.assertEqual(self.match.home_score, 0)
        
        # Restore logger
        logger.setLevel(logging.NOTSET)

    def test_robust_score_parsing(self):
        """Verifica che il parser gestisca spazi extra nel punteggio.
        
        Usa force=True: questo test verifica il parsing del punteggio, non la
        coerenza eventi (il setUp ha 12+8 eventi, ma qui cambiamo lo score a 15-10).
        """
        self.report.normalized_data["scores"]["final_score"] = " 15 - 10 "
        self.report.normalized_data["scores"]["quarters"] = {"1": [4, 2], "2": [4, 3], "3": [4, 2], "4": [3, 3]} # Sum 15-10
        self.report.save()

        success, msg = PublishingService.publish_report(self.report, force=True)
        self.assertTrue(success)
        self.match.refresh_from_db()
        self.assertEqual(self.match.home_score, 15)
        self.assertEqual(self.match.away_score, 10)

    # ------------------------------------------------------------------
    # REGRESSION TESTS — Bug [MISSING_RECORD] (fix: standings sincrono)
    # ------------------------------------------------------------------

    def test_publish_creates_standings_when_missing(self):
        """
        BUG [MISSING_RECORD]: se la squadra non ha un LeagueStanding pre-esistente,
        il vecchio codice (needs_rebuild flag) non creava nulla.
        Verifica che publish_report() crei i record di classifica ex-novo.
        """
        # Pre-condizione: nessun record in classifica (stato esatto che causava il bug)
        self.assertEqual(LeagueStanding.objects.filter(league=self.league).count(), 0)

        # force=True: testiamo la logica standings indipendentemente dal guardrail eventi
        # (Il guardrail è testato separatamente; qui verifichiamo il bug [MISSING_RECORD])
        success, msg = PublishingService.publish_report(self.report, force=True)
        self.assertTrue(success, msg)

        # Post-condizione: le standings devono essere state create in autonomia
        standings = LeagueStanding.objects.filter(league=self.league)
        self.assertGreater(
            standings.count(), 0,
            "Il publish deve creare i record LeagueStanding anche se non esistevano."
        )
        # Entrambe le squadre del match devono comparire in classifica
        team_ids_in_standings = set(standings.values_list('team_id', flat=True))
        self.assertIn(self.team_home.id, team_ids_in_standings)
        self.assertIn(self.team_away.id, team_ids_in_standings)

        # Il match pubblicato (12-8 home) deve aver assegnato punti corretti
        home_standing = standings.get(team=self.team_home)
        away_standing = standings.get(team=self.team_away)
        self.assertEqual(home_standing.won, 1)
        self.assertEqual(home_standing.lost, 0)
        self.assertEqual(away_standing.won, 0)
        self.assertEqual(away_standing.lost, 1)

    def test_publish_reason_written_to_audit_log(self):
        """Verifica che il parametro reason venga scritto nel MatchReportAuditLog."""
        from matches.models import MatchReportAuditLog
        success, _ = PublishingService.publish_report(
            self.report, user=self.user, reason="Controllo manuale superato"
        )
        self.assertTrue(success)
        log = MatchReportAuditLog.objects.get(report=self.report, action='publish')
        self.assertEqual(log.reason, "Controllo manuale superato")

    def test_republish_standings_idempotent(self):
        """
        Verifica che ri-pubblicare un referto non duplichi i record di classifica
        (idempotenza di StandingsService.rebuild_for_league).
        """
        # Primo publish (force=True per bypassare guardrail eventi nei test di standings)
        success, _ = PublishingService.publish_report(self.report, force=True)
        self.assertTrue(success)
        count_after_first = LeagueStanding.objects.filter(league=self.league).count()

        # Secondo publish (re-publish)
        success2, msg2 = PublishingService.publish_report(self.report)
        self.assertTrue(success2)
        self.assertIn("Ripubblicato", msg2)

        count_after_second = LeagueStanding.objects.filter(league=self.league).count()
        self.assertEqual(
            count_after_first, count_after_second,
            "Il re-publish non deve duplicare i record LeagueStanding."
        )

