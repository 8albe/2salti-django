from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import Sport, Society, Team, League
from matches.models import Match, MatchReport, MatchEvent
from matches.event_types import EVENT_TYPE_GOAL

User = get_user_model()


class AthleteStatsPublishedFilterTest(TestCase):
    """Regression: update_stats() deve contare solo MatchEvent di report PUBLISHED."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Water Polo", slug="wp-stats")
        self.soc_h = Society.objects.create(name="Home", slug="home-soc-stats", sport=self.sport)
        self.soc_a = Society.objects.create(name="Away", slug="away-soc-stats", sport=self.sport)
        self.league = League.objects.create(
            name="League Stats", sport=self.sport, category="SENIOR", slug="l-stats"
        )
        self.team_h = Team.objects.create(
            society=self.soc_h, category="SENIOR", league=self.league, name="H"
        )
        self.team_a = Team.objects.create(
            society=self.soc_a, category="SENIOR", league=self.league, name="A"
        )

        self.athlete = User.objects.create_user(
            username='athlete-stats', role='athlete',
            first_name='Test', last_name='Athlete'
        )
        self.profile = self.athlete.athlete_profile
        self.profile.current_team = self.team_h
        self.profile.save()

        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_h,
            away_team=self.team_a,
            match_date=timezone.now(),
        )

    def _create_goal(self):
        MatchEvent.objects.create(
            match=self.match,
            event_type=EVENT_TYPE_GOAL,
            player=self.athlete,
            team=self.team_h,
            minute=10,
            quarter=1,
        )

    def test_draft_report_goals_not_counted(self):
        MatchReport.objects.create(match=self.match, status=MatchReport.Status.DRAFT)
        self._create_goal()

        self.profile.update_stats()

        self.assertEqual(
            self.profile.total_goals, 0,
            "Gol su report DRAFT non devono incrementare total_goals",
        )
        self.assertEqual(
            self.profile.total_matches, 0,
            "Match con solo report DRAFT non deve essere contato in total_matches",
        )

    def test_published_report_goals_counted(self):
        MatchReport.objects.create(match=self.match, status=MatchReport.Status.PUBLISHED)
        self._create_goal()

        self.profile.update_stats()

        self.assertEqual(
            self.profile.total_goals, 1,
            "Gol su report PUBLISHED devono incrementare total_goals",
        )
        self.assertEqual(
            self.profile.total_matches, 1,
            "Match con report PUBLISHED deve essere contato in total_matches",
        )
