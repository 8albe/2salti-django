import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from matches.models import Match, MatchReport, MatchEvent
from core.models import Season, Sport, Society, Team, League
from django.utils import timezone

User = get_user_model()

class EventsReviewUITest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.society_h = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco")
        self.society_a = Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia")
        
        self.league = League.objects.create(name="Serie A1", sport=self.sport, category="SENIOR", season="2024", slug="serie-a1")
        
        self.team_h = Team.objects.create(society=self.society_h, league=self.league, category="SENIOR")
        self.team_a = Team.objects.create(society=self.society_a, league=self.league, category="SENIOR")
        
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_h,
            away_team=self.team_a,
            match_date=timezone.now(),
            location="Sori"
        )
        
        self.admin_user = User.objects.create_superuser(username='admin', password='password', email='admin@test.com')
        self.client = Client()
        self.client.login(username='admin', password='password')
        
        self.athlete_h = User.objects.create(username='ath_h', first_name='Mario', last_name='Rossi', role='athlete')
        self.athlete_h.athlete_profile.current_team = self.team_h
        self.athlete_h.athlete_profile.save()

        self.report = MatchReport.objects.create(
            match=self.match,
            status=MatchReport.Status.EXTRACTED,
            normalized_data={
                "metadata": {"confidence": 0.9},
                "match_info": {"home_team": "Pro Recco", "away_team": "Brescia", "date": "2024-01-01"},
                "scores": {"final_score": "1-0", "quarters": {"1": [1, 0]}},
                "teams": {
                    "home": {"players": [{"name": "Mario Rossi", "number": 10}]},
                    "away": {"players": []}
                },
                "events": [
                    {"type": "GOAL", "team": "home", "player_name": "Mario Rossi", "minute": 5, "quarter": 1}
                ],
                "reconciliation": {
                    "home_players": {"Mario Rossi": self.athlete_h.id}
                }
            }
        )

    def test_review_renders_events_table(self):
        """Verifica che la tabella eventi sia presente nel template."""
        url = reverse('admin:matches_matchreport_review', args=[self.report.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Eventi della Gara')
        self.assertContains(response, 'GOAL')
        self.assertContains(response, 'Mario Rossi')

    def test_save_events_changes(self):
        """Verifica che il salvataggio bozza persista le modifiche agli eventi."""
        url = reverse('admin:matches_matchreport_review', args=[self.report.id])
        
        # Modifichiamo l'evento esistente e aggiungiamo una espulsione
        new_data = self.report.normalized_data.copy()
        new_data['events'].append({
            "type": "EXCLUSION_20",
            "team": "home",
            "player_name": "Mario Rossi",
            "minute": 7,
            "quarter": 1
        })
        
        post_data = {
            'normalized_data': json.dumps(new_data),
            'validation_notes': 'Test update events',
            '_action': 'save_draft'
        }
        
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302) # Redirect on success
        
        self.report.refresh_from_db()
        self.assertEqual(len(self.report.normalized_data['events']), 2)
        self.assertEqual(self.report.normalized_data['events'][1]['type'], 'EXCLUSION_20')

    def test_publish_creates_non_scoring_match_events(self):
        """Verifica che la pubblicazione crei correttamente MatchEvent non-scoring."""
        # Aggiungiamo un evento non-scoring
        self.report.normalized_data['events'].append({
            "type": "YELLOW_CARD",
            "team": "home",
            "player_name": "Mario Rossi",
            "minute": 10,
            "quarter": 2
        })
        self.report.status = MatchReport.Status.VALIDATED
        self.report.save()
        
        url = reverse('admin:matches_matchreport_review', args=[self.report.id])
        post_data = {
            'normalized_data': json.dumps(self.report.normalized_data),
            '_action': 'publish_now'
        }
        
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302)
        
        # Verifichiamo MatchEvent
        events = MatchEvent.objects.filter(match=self.match)
        # 1 Goal + 1 Yellow Card
        self.assertEqual(events.count(), 2)
        
        yc = events.get(event_type='YELLOW_CARD')
        self.assertEqual(yc.player, self.athlete_h)
        self.assertEqual(yc.minute, 10)
        self.assertEqual(yc.quarter, 2)
