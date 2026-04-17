from django.test import TestCase
from django.utils import timezone
from core.models import Sport, Society, Team, League
from matches.models import Match, MatchReport

class StandingsTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="WP", slug="wp")
        self.soc1 = Society.objects.create(name="Soc 1", slug="soc1", sport=self.sport)
        self.soc2 = Society.objects.create(name="Soc 2", slug="soc2", sport=self.sport)
        self.league = League.objects.create(name="L1", sport=self.sport, category="SENIOR", slug="l1")
        self.t1 = Team.objects.create(society=self.soc1, category="SENIOR", league=self.league, name="T1")
        self.t2 = Team.objects.create(society=self.soc2, category="SENIOR", league=self.league, name="T2")

    def test_standings_calculation(self):
        # Initial: everyone 0
        standings = self.league.get_standings()
        self.assertEqual(len(standings), 2)
        self.assertEqual(standings[0]['points'], 0)
        
        # Match 1: T1 vs T2 -> 10-5
        m1 = Match.objects.create(
            league=self.league, home_team=self.t1, away_team=self.t2,
            home_score=10, away_score=5, is_finished=True, match_date=timezone.now()
        )
        MatchReport.objects.create(match=m1, status='PUBLISHED')
        
        standings = self.league.get_standings()
        t1_stats = next(s for s in standings if s['team'] == self.t1)
        t2_stats = next(s for s in standings if s['team'] == self.t2)
        
        self.assertEqual(t1_stats['points'], 3)
        self.assertEqual(t2_stats['points'], 0)
        
        # Match 2: T2 vs T1 -> 5-5 (Draw)
        m2 = Match.objects.create(
            league=self.league, home_team=self.t2, away_team=self.t1,
            home_score=5, away_score=5, is_finished=True, match_date=timezone.now()
        )
        MatchReport.objects.create(match=m2, status='PUBLISHED')
        
        standings = self.league.get_standings()
        t1_stats = next(s for s in standings if s['team'] == self.t1)
        t2_stats = next(s for s in standings if s['team'] == self.t2)
        
        self.assertEqual(t1_stats['points'], 4) # 3 + 1
        self.assertEqual(t2_stats['points'], 1) # 0 + 1
