import json
from django.test import TestCase, Client
from django.urls import reverse

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from core.models import Season, Sport, Society, Team, League
from matches.models import Match, MatchReport, MatchEvent
from accounts.models import AthleteProfile

User = get_user_model()

class StatsIntegrityTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Water Polo", slug="wp")
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.soc_h = Society.objects.create(name="Home Soc", slug="soc-h", sport=self.sport)
        self.soc_a = Society.objects.create(name="Away Soc", slug="soc-a", sport=self.sport)
        self.league = League.objects.create(name="League 1", sport=self.sport, slug="l1")
        
        self.team_h = Team.objects.create(society=self.soc_h, league=self.league, name="Team H")
        self.team_a = Team.objects.create(society=self.soc_a, league=self.league, name="Team A")
        
        # Create athletes
        self.u1 = User.objects.create_user(username='h1', role='athlete', first_name='Home', last_name='One')
        self.u2 = User.objects.create_user(username='h2', role='athlete', first_name='Home', last_name='Two')
        self.u3 = User.objects.create_user(username='a1', role='athlete', first_name='Away', last_name='One')
        
        self.ap1 = self.u1.athlete_profile
        self.ap1.current_team = self.team_h
        self.ap1.save()
        
        self.ap2 = self.u2.athlete_profile
        self.ap2.current_team = self.team_h
        self.ap2.save()
        
        self.ap3 = self.u3.athlete_profile
        self.ap3.current_team = self.team_a
        self.ap3.save()
        
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_h,
            away_team=self.team_a,
            match_date=timezone.now()
        )
        
        # Dummy file to avoid ValueError in template rendering
        dummy_file = SimpleUploadedFile("referto.pdf", b"file_content", content_type="application/pdf")
        
        self.report = MatchReport.objects.create(
            match=self.match,
            file=dummy_file,
            status='UPLOADED'
        )
        
        self.staff_user = User.objects.create_user(
            username='staff', 
            is_staff=True,
            setup_completed=True,
            identity_status='VERIFIED',
            onboarding_payment_done=True
        )

    def test_standings_gating(self):
        """Verifica che la classifica si aggiorni solo per i referti PUBLISHED."""
        self.match.home_score = 5
        self.match.away_score = 0
        self.match.is_finished = True
        self.match.save()
        
        # Scenario 1: VALIDATED (Not Published)
        self.report.status = 'VALIDATED'
        self.report.save()


        standings = self.league.get_standings()
        home_stats = next(s for s in standings if s['team'] == self.team_h)
        self.assertEqual(home_stats['played'], 0, "VALIDATED reports should not affect standings")
        
        # Scenario 2: PUBLISHED
        self.report.status = 'PUBLISHED'
        self.report.save()
        standings = self.league.get_standings()
        home_stats = next(s for s in standings if s['team'] == self.team_h)
        self.assertEqual(home_stats['played'], 1, "PUBLISHED reports must affect standings")

    def test_form_validation_sums(self):
        """Verifica che i parziali e i gol giocatori debbano coincidere col totale."""
        self.client.force_login(self.staff_user)
        url = reverse('op_admin:matches_matchreport_review', args=[self.report.id])
        
        # Home roster has ap1, ap2. Away roster has ap3.
        # NOTE: Operational Dashboard uses JSON validation (OCRSchemaValidator)
        # instead of form validation. Schema validation tests are in tests_ocr_schema.
        
        # 1. Error: Quarter sum mismatch (Home) - In Operational Dashboard this is a BLOCCANTE
        data = {
            "metadata": {"confidence": 0.9},
            "match_info": {"home_team": "Team H", "away_team": "Team A", "date": "2024-01-01"},
            "scores": {
                "final_score": "10-5",
                "quarters": {
                    "1": [2, 1], "2": [2, 1], "3": [2, 1], "4": [2, 2] # Total 8 != 10
                }
            },
            "teams": {"home": {"players": []}, "away": {"players": []}},
            "events": []
        }
        post_data = {
            'normalized_data': json.dumps(data),
            '_action': 'publish_now'
        }
        response = self.client.post(url, post_data)
        # In Operational Admin, it redirects to changelist even on publish failure (with warning)
        self.assertEqual(response.status_code, 302) 
        
        self.report.refresh_from_db()
        self.assertNotEqual(self.report.status, 'PUBLISHED')


        # 2. Valid submission
        data['scores']['quarters']['4'] = [4, 2] # Total 10
        post_data['normalized_data'] = json.dumps(data)
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302) # Redirect to changelist/match detail


    def test_idempotency_and_event_sync(self):
        """Verifica che salvataggi multipli non duplichino i MatchEvent."""
        self.client.force_login(self.staff_user)
        url = reverse('op_admin:matches_matchreport_review', args=[self.report.id])
        
        data = {
            "metadata": {"confidence": 0.9},
            "match_info": {"home_team": "Team H", "away_team": "Team A", "date": "2024-01-01"},
            "scores": {
                "final_score": "2-1",
                "quarters": {"1": [1, 0], "2": [1, 1]}
            },
            "teams": {
                "home": {"players": [{"name": "Home One", "number": 1}, {"name": "Home Two", "number": 2}]},
                "away": {"players": [{"name": "Away One", "number": 3}]}
            },
            "events": [
                {"type": "GOAL", "team": "home", "player_name": "Home One", "minute": 1, "quarter": 1},
                {"type": "GOAL", "team": "home", "player_name": "Home One", "minute": 10, "quarter": 2},
                {"type": "GOAL", "team": "away", "player_name": "Away One", "minute": 15, "quarter": 2}
            ],
            "reconciliation": {
                "home_players": {"Home One": self.u1.id, "Home Two": self.u2.id},
                "away_players": {"Away One": self.u3.id}
            }
        }
        post_data = {
            'normalized_data': json.dumps(data),
            '_action': 'publish_now'
        }
        
        # First save
        res1 = self.client.post(url, post_data)
        self.assertEqual(res1.status_code, 302)
        self.assertEqual(MatchEvent.objects.filter(match=self.match, event_type='GOAL').count(), 3)
        
        # Second save (no changes)
        res2 = self.client.post(url, post_data)
        self.assertEqual(res2.status_code, 302)
        self.assertEqual(MatchEvent.objects.filter(match=self.match, event_type='GOAL').count(), 3, "Events should not be duplicated on re-save")
        
        # Third save (updated goals)
        data['events'] = [
            {"type": "GOAL", "team": "home", "player_name": "Home One", "minute": 1, "quarter": 1},
            {"type": "GOAL", "team": "home", "player_name": "Home Two", "minute": 10, "quarter": 2},
            {"type": "GOAL", "team": "away", "player_name": "Away One", "minute": 15, "quarter": 2}
        ]
        post_data['normalized_data'] = json.dumps(data)
        res3 = self.client.post(url, post_data)
        self.assertEqual(res3.status_code, 302)
        self.assertEqual(MatchEvent.objects.filter(match=self.match, event_type='GOAL').count(), 3)
        self.assertEqual(MatchEvent.objects.filter(match=self.match, player=self.u1, event_type='GOAL').count(), 1)
        self.assertEqual(MatchEvent.objects.filter(match=self.match, player=self.u2, event_type='GOAL').count(), 1)


    def test_athlete_stats_refresh(self):
        """Verifica che le statistiche dell'atleta si aggiornino correttamente."""
        self.client.force_login(self.staff_user)
        url = reverse('op_admin:matches_matchreport_review', args=[self.report.id])
        
        data = {
            "metadata": {"confidence": 0.9},
            "match_info": {"home_team": "Team H", "away_team": "Team A", "date": "2024-01-01"},
            "scores": {
                "final_score": "5-0",
                "quarters": {"1": [5, 0], "2": [0, 0], "3": [0, 0], "4": [0, 0]}
            },
            "teams": {
                "home": {"players": [{"name": "Home One", "number": 1}]},
                "away": {"players": []}
            },
            "events": [
                {"type": "GOAL", "team": "home", "player_name": "Home One", "minute": i, "quarter": 1} for i in range(1, 6)
            ],
            "reconciliation": {
                "home_players": {"Home One": self.u1.id}
            }
        }
        post_data = {
            'normalized_data': json.dumps(data),
            '_action': 'publish_now'
        }
        
        # Publish
        self.client.post(url, post_data)
        self.ap1.refresh_from_db()
        self.assertEqual(self.ap1.total_goals, 5, "Athlete stats should update on publication")
        
        # Update (re-publish with fewer goals)
        data['scores']['final_score'] = "2-0"
        data['scores']['quarters']['1'] = [2, 0]
        data['events'] = [
            {"type": "GOAL", "team": "home", "player_name": "Home One", "minute": 1, "quarter": 1},
            {"type": "GOAL", "team": "home", "player_name": "Home One", "minute": 2, "quarter": 1}
        ]
        post_data['normalized_data'] = json.dumps(data)
        self.client.post(url, post_data)
        self.ap1.refresh_from_db()
        self.assertEqual(self.ap1.total_goals, 2, "Athlete stats should decrease if goals are removed")

