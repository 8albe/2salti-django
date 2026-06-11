from django.test import TestCase
from django.utils import timezone
from core.models import Season, Sport, Society, League, Team, LeagueStanding
from matches.models import Match, MatchReport
from matches.services.publishing_service import PublishingService
from matches.services.standings_service import StandingsService
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from accounts.models import AthleteProfile

User = get_user_model()

# Numero di GOAL events per side nel normalized_data del setUp (final_score 12-8)
HOME_GOALS = 12
AWAY_GOALS = 8


class PublishingServiceTestCase(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
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

        # Roster reconciliable: un atleta verificato per ogni GOAL event,
        # iscritto al team corrispondente. AthleteProfile è auto-creato dal
        # signal post_save su User; lo recuperiamo e impostiamo current_team.
        self.home_athletes = []
        for i in range(HOME_GOALS):
            u = User.objects.create_user(
                username=f'home_player_{i}',
                first_name=f'HomePlayer{i}',
                last_name='Test',
                role='athlete',
                identity_status='VERIFIED',
                subscription_status='ACTIVE',
                setup_completed=True,
            )
            profile = u.athlete_profile
            profile.current_team = self.team_home
            profile.save(update_fields=['current_team'])
            self.home_athletes.append((u, profile))

        self.away_athletes = []
        for i in range(AWAY_GOALS):
            u = User.objects.create_user(
                username=f'away_player_{i}',
                first_name=f'AwayPlayer{i}',
                last_name='Test',
                role='athlete',
                identity_status='VERIFIED',
                subscription_status='ACTIVE',
                setup_completed=True,
            )
            profile = u.athlete_profile
            profile.current_team = self.team_away
            profile.save(update_fields=['current_team'])
            self.away_athletes.append((u, profile))

        # Eventi GOAL con player_name riconciliabile (un atleta dedicato per evento)
        events = []
        for i in range(HOME_GOALS):
            events.append({
                "type": "GOAL", "team": "home", "minute": i + 1,
                "player_name": f"HomePlayer{i} Test",
            })
        for i in range(AWAY_GOALS):
            events.append({
                "type": "GOAL", "team": "away", "minute": HOME_GOALS + i + 1,
                "player_name": f"AwayPlayer{i} Test",
            })

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
                "events": events,
                "reconciliation": {
                    "home_team_id": self.team_home.id,
                    "away_team_id": self.team_away.id,
                    "home_players": {
                        f"HomePlayer{i} Test": self.home_athletes[i][0].id
                        for i in range(HOME_GOALS)
                    },
                    "away_players": {
                        f"AwayPlayer{i} Test": self.away_athletes[i][0].id
                        for i in range(AWAY_GOALS)
                    },
                },
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

    # ------------------------------------------------------------------
    # GUARDRAIL Policy A — Zero eventi creati con score>0 deve abortire
    # anche con force=True (drift su statistiche atleti).
    # ------------------------------------------------------------------

    def test_publish_aborts_with_zero_events_and_positive_score(self):
        """
        Policy A: anche con force=True, il publishing service deve abortire
        se created_events_count==0 e score>0, fare rollback completo (match
        e report invariati) e persistere un MatchReportAuditLog
        action='abort_zero_events' in transazione separata.
        """
        from matches.models import MatchReportAuditLog

        # Sabotare la riconciliazione: rimuovendola, gli eventi hanno
        # player_name ma nessun player_id risolvibile → 0 eventi creati
        # nel converter, pur avendo score 12-8 nei dati.
        data = dict(self.report.normalized_data)
        data.pop('reconciliation', None)
        self.report.normalized_data = data
        self.report.save()

        # Snapshot pre-publish: deve restare invariato dopo il rollback
        pre_status = self.report.status
        pre_home_score = self.match.home_score
        pre_away_score = self.match.away_score
        pre_is_finished = self.match.is_finished

        # force=True bypassa il gate schema (Riconciliazione incompleta)
        # ma NON deve bypassare il guardrail Policy A.
        success, msg = PublishingService.publish_report(
            self.report, user=self.user, force=True, reason='Test guardrail Policy A'
        )

        # Esito: abort
        self.assertFalse(success, "Il publish doveva essere abortito dal guardrail Policy A")
        self.assertIn('0 eventi creati', msg)
        self.assertIn('12-8', msg)

        # Stato DB invariato (rollback transazionale ha funzionato)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, pre_status,
                         "Il report deve restare nello stato pre-publish dopo il rollback")
        self.match.refresh_from_db()
        self.assertEqual(self.match.home_score, pre_home_score,
                         "match.home_score deve essere ripristinato dal rollback")
        self.assertEqual(self.match.away_score, pre_away_score,
                         "match.away_score deve essere ripristinato dal rollback")
        self.assertEqual(self.match.is_finished, pre_is_finished,
                         "match.is_finished deve essere ripristinato dal rollback")

        # Audit log persistente (transazione separata post-rollback)
        audit_logs = MatchReportAuditLog.objects.filter(
            report=self.report, action='abort_zero_events'
        )
        self.assertEqual(audit_logs.count(), 1,
                         "Audit log abort_zero_events deve essere stato creato")
        audit = audit_logs.first()
        self.assertEqual(audit.user, self.user)
        self.assertEqual(audit.old_status, pre_status)
        self.assertEqual(audit.new_status, pre_status)
        self.assertIsNotNone(audit.after)
        # Il payload after cattura lo stato post-conversione (pre-rollback):
        # score derivati dai dati (12-8) e flag force.
        self.assertEqual(audit.after.get('force'), True)
        self.assertEqual(audit.after.get('home_score'), 12)
        self.assertEqual(audit.after.get('away_score'), 8)
        self.assertEqual(audit.after.get('events_data_count'), HOME_GOALS + AWAY_GOALS)

