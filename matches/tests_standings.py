from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from core.models import Sport, Society, Team, League, LeagueStanding
from matches.models import Match, MatchReport
from matches.services.publishing_service import PublishingService
from matches.services.standings_service import StandingsService
from django.core.management import call_command
from io import StringIO

User = get_user_model()

# GOAL events per side allineati al final_score '10-5' del setUp.
HOME_GOALS = 10
AWAY_GOALS = 5


class StandingsVerificationTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.soc_a = Society.objects.create(name="Soc A", slug="soc-a", sport=self.sport)
        self.soc_b = Society.objects.create(name="Soc B", slug="soc-b", sport=self.sport)
        self.league = League.objects.create(name="A1", sport=self.sport, category="SENIOR", slug="a1")

        self.t1 = Team.objects.create(society=self.soc_a, category="SENIOR", league=self.league, name="T1")
        self.t2 = Team.objects.create(society=self.soc_b, category="SENIOR", league=self.league, name="T2")

        # Match 1
        self.m1 = Match.objects.create(
            league=self.league, home_team=self.t1, away_team=self.t2,
            home_score=0, away_score=0, is_finished=False, match_date=timezone.now()
        )

        # Roster reconciliable: un atleta verificato per ogni GOAL event,
        # iscritto al team corrispondente. AthleteProfile è auto-creato dal
        # signal post_save su User; lo recuperiamo e impostiamo current_team.
        self.home_athletes = []
        for i in range(HOME_GOALS):
            u = User.objects.create_user(
                username=f't1_player_{i}',
                first_name=f'T1Player{i}',
                last_name='Test',
                role='athlete',
                identity_status='VERIFIED',
                subscription_status='ACTIVE',
                setup_completed=True,
            )
            profile = u.athlete_profile
            profile.current_team = self.t1
            profile.save(update_fields=['current_team'])
            self.home_athletes.append((u, profile))

        self.away_athletes = []
        for i in range(AWAY_GOALS):
            u = User.objects.create_user(
                username=f't2_player_{i}',
                first_name=f'T2Player{i}',
                last_name='Test',
                role='athlete',
                identity_status='VERIFIED',
                subscription_status='ACTIVE',
                setup_completed=True,
            )
            profile = u.athlete_profile
            profile.current_team = self.t2
            profile.save(update_fields=['current_team'])
            self.away_athletes.append((u, profile))

        # GOAL events con player_name riconciliabile (un atleta dedicato per evento)
        events = []
        for i in range(HOME_GOALS):
            events.append({
                "type": "GOAL", "team": "home", "minute": i + 1,
                "player_name": f"T1Player{i} Test",
            })
        for i in range(AWAY_GOALS):
            events.append({
                "type": "GOAL", "team": "away", "minute": HOME_GOALS + i + 1,
                "player_name": f"T2Player{i} Test",
            })

        # Create minimal valid data that passes assess_publish_readiness
        valid_data = {
            'metadata': {'confidence': 0.9},
            'match_info': {'home_team': 'Soc A', 'away_team': 'Soc B', 'date': '2026-03-26'},
            'scores': {'final_score': '10-5', 'quarters': {}},
            'teams': {
                'home': {'name': 'Soc A', 'score': 10, 'players': [{'name': 'P1', 'number': 1}]},
                'away': {'name': 'Soc B', 'score': 5, 'players': [{'name': 'P2', 'number': 1}]}
            },
            'events': events,
            'reconciliation': {
                'home_team_id': self.t1.id,
                'away_team_id': self.t2.id,
                'home_players': {
                    f"T1Player{i} Test": self.home_athletes[i][0].id
                    for i in range(HOME_GOALS)
                },
                'away_players': {
                    f"T2Player{i} Test": self.away_athletes[i][0].id
                    for i in range(AWAY_GOALS)
                },
            },
        }
        self.r1 = MatchReport.objects.create(
            match=self.m1, status='VALIDATED',
            normalized_data=valid_data
        )
        self.league.needs_rebuild = True
        self.league.save(update_fields=['needs_rebuild'])

    def test_standings_updated_on_publish(self):
        # Initial: no persisted standings
        self.assertFalse(LeagueStanding.objects.filter(league=self.league).exists())
        
        # Publish report
        success, msg = PublishingService.publish_report(self.r1)
        self.assertTrue(success)
        
        # Now standings should exist
        self.assertTrue(LeagueStanding.objects.filter(league=self.league).exists())
        s1 = LeagueStanding.objects.get(league=self.league, team=self.t1)
        self.assertEqual(s1.points, 3)
        self.assertEqual(s1.rank, 1)
        
        s2 = LeagueStanding.objects.get(league=self.league, team=self.t2)
        self.assertEqual(s2.points, 0)
        self.assertEqual(s2.rank, 2)

    def test_rebuild_command(self):
        # Manually publish WITHOUT service (simulating legacy or sync issues)
        self.r1.status = 'PUBLISHED'
        self.r1.save()
        
        # We MUST also set the match as finished with scores, 
        # as the StandingsService only counts finished/published matches.
        self.m1.is_finished = True
        self.m1.home_score = 10
        self.m1.away_score = 5
        self.m1.save()
        
        out = StringIO()
        call_command('rebuild_standings', stdout=out)
        
        self.assertIn("Trovate 1 leghe con ricalcolo richiesto", out.getvalue())
        self.assertTrue(LeagueStanding.objects.filter(league=self.league).exists())
        s1 = LeagueStanding.objects.get(team=self.t1)
        self.assertEqual(s1.points, 3)

    def test_get_standings_uses_persisted(self):
        # Create a "fake" persisted standing to prove it uses it
        LeagueStanding.objects.create(
            league=self.league, team=self.t1, season=self.league.season,
            points=99, played=1, rank=1
        )
        
        standings = self.league.get_standings()
        self.assertEqual(standings[0]['points'], 99)
        self.assertEqual(standings[0]['team'], self.t1)
