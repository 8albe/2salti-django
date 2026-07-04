from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.models import Season, Sport, Society, Team, League
from matches.models import Match, MatchReport

User = get_user_model()

class ManualReviewTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Water Polo", slug="wp")
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.soc_a = Society.objects.create(name="Soc A", slug="soc-a", sport=self.sport)
        self.soc_b = Society.objects.create(name="Soc B", slug="soc-b", sport=self.sport)
        self.league = League.objects.create(name="League 1", sport=self.sport, slug="l1")
        
        self.team_a = Team.objects.create(society=self.soc_a, league=self.league, name="Team A")
        self.team_b = Team.objects.create(society=self.soc_b, league=self.league, name="Team B")
        
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=timezone.now()
        )
        
        self.report = MatchReport.objects.create(
            match=self.match,
            file='referto.pdf', # Dummy path
            status='UPLOADED'
        )
        
        self.staff_user = User.objects.create_user(username='staff', is_staff=True, identity_status='VERIFIED', onboarding_payment_done=True)
        self.player_user = User.objects.create_user(username='player', role='fan', identity_status='VERIFIED', onboarding_payment_done=True, setup_completed=True)

        # Create athletes for rosters to avoid "Empty roster" errors in form
        from accounts.models import AthleteProfile
        self.athlete_a = User.objects.create_user(username='athlete_a', last_name='A', identity_status='VERIFIED', onboarding_payment_done=True)
        self.prof_a = AthleteProfile.objects.create(user=self.athlete_a, current_team=self.team_a)
        
        self.athlete_b = User.objects.create_user(username='athlete_b', last_name='B', identity_status='VERIFIED', onboarding_payment_done=True)
        self.prof_b = AthleteProfile.objects.create(user=self.athlete_b, current_team=self.team_b)

    def test_staff_can_review(self):
        self.client.force_login(self.staff_user)
        from django.urls import reverse
        url = reverse('report_review', args=[self.report.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'matches/report_review.html')

    def test_non_staff_cannot_review(self):
        self.client.force_login(self.player_user)
        from django.urls import reverse
        url = reverse('report_review', args=[self.report.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_manual_review_submission_updates_standings(self):
        self.client.force_login(self.staff_user)
        
        # Verify initial standings
        standings = self.league.get_standings()
        for s in standings:
            self.assertEqual(s['points'], 0)
            
        # Submit review
        post_data = {
            'home_score': 10,
            'away_score': 8,
            'home_q1': 3, 'home_q2': 2, 'home_q3': 3, 'home_q4': 2,
            'away_q1': 2, 'away_q2': 2, 'away_q3': 2, 'away_q4': 2,
            'report_status': 'PUBLISHED',
            'is_finished': True,
            f'player_goals_home_{self.athlete_a.id}': 10,
            f'player_goals_away_{self.athlete_b.id}': 8,
        }
        from django.urls import reverse
        url = reverse('report_review', args=[self.report.id])
        response = self.client.post(url, post_data)
        
        self.assertEqual(response.status_code, 302) # Redirect to match detail
        
        # Verify match is finished and scores updated
        self.match.refresh_from_db()
        self.assertTrue(self.match.is_finished)
        self.assertEqual(self.match.home_score, 10)
        self.assertEqual(self.match.away_score, 8)
        
        # Verify report status
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, 'PUBLISHED')
        
        # Verify standings
        standings = self.league.get_standings()
        team_a_stats = next(s for s in standings if s['team'] == self.team_a)
        self.assertEqual(team_a_stats['points'], 3)
        self.assertEqual(team_a_stats['goals_for'], 10)
        
        team_b_stats = next(s for s in standings if s['team'] == self.team_b)
        self.assertEqual(team_b_stats['points'], 0)
        self.assertEqual(team_b_stats['goals_for'], 8)
