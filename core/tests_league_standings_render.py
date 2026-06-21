"""Content test della classifica pubblica (leagues/league_standings.html).

Regression del cosmetico "tag {{ }} spezzato su due righe": il widget capocannonieri
renderizza `{{ scorer.player__first_name }} {{ scorer.player__last_name }}`. Il test
asserisce che il valore reale compaia nell'HTML (non il letterale del tag), così la
ricomposizione del tag su una riga sola resta verificata. La view è pubblica.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import League, Society, Sport, Team
from matches.models import Match, MatchEvent

User = get_user_model()


class LeagueStandingsScorerRenderTests(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="ZZ Pallanuoto Test", slug="zz-pallanuoto")
        self.society = Society.objects.create(
            name="ZZ Recco", slug="zz-recco", sport=self.sport, city="Genova"
        )
        self.league = League.objects.create(
            name="ZZ Serie A1", sport=self.sport, slug="zz-serie-a1"
        )
        self.team = Team.objects.create(society=self.society, league=self.league)
        self.scorer = User.objects.create_user(
            username="zz-scorer", first_name="Alessandro", last_name="Velottozz",
            role="athlete",
        )
        self.match = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.team,
            match_date=timezone.now(),
        )
        MatchEvent.objects.create(
            match=self.match, event_type="GOAL", player=self.scorer,
            team=self.team, minute=1, quarter=1,
        )

    def test_scorer_last_name_is_rendered_not_literal(self):
        resp = self.client.get(reverse("league_standings", args=[self.league.id]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # Il valore reale del tag ricomposto deve comparire...
        self.assertIn("Velottozz", html)
        self.assertIn("Alessandro", html)
        # ...e nessun letterale del tag deve sopravvivere nel rendering.
        self.assertNotIn("scorer.player__last_name", html)
        self.assertNotIn("scorer.player__first_name", html)
