import json
from unittest.mock import patch
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
        
        self.league = League.objects.create(name="Serie A1", sport=self.sport, season="2024", slug="serie-a1")
        
        self.team_h = Team.objects.create(society=self.society_h, league=self.league)
        self.team_a = Team.objects.create(society=self.society_a, league=self.league)
        
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


class ReviewContextAndReasonTest(TestCase):
    """Riparazione della review admin (2026-07-22): context completo, serializzazione
    JSON pulita, reason_message passata a publish_report (§10.32)."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.society_h = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco")
        self.society_a = Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia")
        self.league = League.objects.create(name="Serie A1", sport=self.sport, season="2024", slug="serie-a1")
        self.team_h = Team.objects.create(society=self.society_h, league=self.league)
        self.team_a = Team.objects.create(society=self.society_a, league=self.league)
        self.match = Match.objects.create(
            league=self.league, home_team=self.team_h, away_team=self.team_a,
            match_date=timezone.now(), location="Sori",
        )
        self.admin_user = User.objects.create_superuser(username='admin', password='pw', email='a@t.com')
        self.client = Client()
        self.client.login(username='admin', password='pw')
        self.report = MatchReport.objects.create(
            match=self.match, status=MatchReport.Status.VALIDATED,
            raw_extracted_data={"scores": {"final_score": "1-0"}, "flag": True, "empty": None},
            normalized_data={
                "metadata": {"confidence": 0.9},
                "match_info": {"home_team": "Pro Recco", "away_team": "AN Brescia", "date": "2024-01-01"},
                "scores": {"final_score": "1-0", "quarters": {"1": [1, 0]}},
                "teams": {"home": {"players": [{"name": "Mario Rossi", "number": 10}]},
                          "away": {"players": []}},
                "events": [{"type": "GOAL", "team": "home", "player_name": "Mario Rossi",
                            "minute": 5, "quarter": 1}],
                "reconciliation": {},
            },
        )
        self.url = reverse('admin:matches_matchreport_review', args=[self.report.id])

    def test_context_has_previously_missing_variables(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        ctx = resp.context
        # roster_names alimenta l'editor eventi: lista nomi per lato
        self.assertIn("Mario Rossi", ctx["roster_names"]["home"])
        # event_types: lista di tipi con code/label
        self.assertTrue(any(t["code"] == "GOAL" for t in ctx["event_types"]))
        # publish_warnings: era calcolato ma mai passato (contatore sempre 0)
        self.assertIn("publish_warnings", ctx)
        self.assertIsInstance(ctx["publish_warnings"], list)
        # raw_data_json: dump leggibile del raw OCR
        self.assertIn("final_score", ctx["raw_data_json"])

    def test_no_python_repr_serialization_uses_json_script(self):
        resp = self.client.get(self.url)
        html = resp.content.decode()
        # I payload passano da json_script, non dal repr Python via |safe
        self.assertIn('id="roster-names-data"', html)
        self.assertIn('id="event-types-data"', html)
        self.assertIn("JSON.parse(document.getElementById('roster-names-data')", html)
        # Il const morto e il suo repr non ci sono piu'
        self.assertNotIn("const rawExtractedData", html)
        # raw_extracted_data conteneva True/None: json_script/dumps li rende JSON validi,
        # il vecchio |safe avrebbe stampato il repr Python (True/None) in contesto JS.
        self.assertNotIn("const rawExtractedData = {'scores'", html)

    def test_reason_message_passed_to_publish_report(self):
        with patch("matches.admin.PublishingService.publish_report",
                   return_value=(True, "ok")) as mock_pub:
            resp = self.client.post(self.url, {
                "normalized_data": json.dumps(self.report.normalized_data),
                "reason_message": "  correzione punteggio dal cartaceo  ",
                "_action": "publish_now",
            })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(mock_pub.called)
        _, kwargs = mock_pub.call_args
        self.assertEqual(kwargs["reason"], "correzione punteggio dal cartaceo")

    def test_service_failure_keeps_operator_on_review_page(self):
        # Il servizio rifiuta (es. reason mancante su downgrade/dato verificato):
        # l'operatore resta sulla review per compilare Motivazione, non in changelist.
        with patch("matches.admin.PublishingService.publish_report",
                   return_value=(False, "Pubblicazione bloccata")):
            resp = self.client.post(self.url, {
                "normalized_data": json.dumps(self.report.normalized_data),
                "reason_message": "una ragione",
                "_action": "publish_now",
            })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, self.url)

    def test_force_without_reason_refused_before_calling_service(self):
        # §10.32: il force senza Motivazione e' rifiutato in UI, senza nemmeno
        # invocare il servizio, e l'operatore resta sulla review.
        with patch("matches.admin.PublishingService.publish_report") as mock_pub:
            resp = self.client.post(self.url, {
                "normalized_data": json.dumps(self.report.normalized_data),
                "reason_message": "   ",
                "_action": "publish_force",
            })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, self.url)
        self.assertFalse(mock_pub.called)

    def test_publish_success_redirects_to_changelist(self):
        with patch("matches.admin.PublishingService.publish_report",
                   return_value=(True, "ok")):
            resp = self.client.post(self.url, {
                "normalized_data": json.dumps(self.report.normalized_data),
                "reason_message": "ok",
                "_action": "publish_now",
            })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('admin:matches_matchreport_changelist'))
