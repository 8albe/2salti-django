from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import Season, Sport, Society, Team, League, LeagueStanding
from matches.models import Match, MatchEvent, MatchReport
import json
from django.utils import timezone

User = get_user_model()

class PublicReadLayerTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.society = Society.objects.create(name="Pro Recco", slug="pro-recco", sport=self.sport)
        self.team = Team.objects.create(society=self.society)
        self.league = League.objects.create(name="Serie A1", sport=self.sport, season="2024-2025")
        self.team.league = self.league
        self.team.save()
        
        # Test Athlete
        self.athlete_user = User.objects.create_user(username="atleta1", role="athlete", first_name="Mario", last_name="Rossi")
        self.athlete_profile = self.athlete_user.athlete_profile
        self.athlete_profile.current_team = self.team
        self.athlete_profile.save()
        
        # Test Match
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team, # Just for testing
            match_date=timezone.now(),
            is_finished=True,
            home_score=10,
            away_score=8
        )
        
        # Create a published report to ensure data is "public"
        self.report = MatchReport.objects.create(
            match=self.match,
            status='PUBLISHED'
        )
        
        # Create a standing
        self.standing = LeagueStanding.objects.create(
            league=self.league,
            team=self.team,
            season="2024-2025",
            points=3,
            played=1,
            won=1,
            rank=1
        )

    def test_home_page_public(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pallanuoto")

    def test_league_standings_public(self):
        response = self.client.get(reverse('league_standings', args=[self.league.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.team.name)
        # The position is just a number in a td
        self.assertContains(response, '1') 

    def test_team_detail_public(self):
        response = self.client.get(reverse('team_detail', args=[self.team.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.team.name)
        self.assertContains(response, "Posizione #1")
        self.assertContains(response, self.athlete_user.get_full_name())

    def test_match_detail_public(self):
        response = self.client.get(reverse('match_detail', args=[self.match.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.match.home_score))
        self.assertContains(response, str(self.match.away_score))

    def test_athlete_profile_public(self):
        response = self.client.get(reverse('profile', args=[self.athlete_user.username]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.athlete_user.get_full_name())

    def test_athlete_alias_url(self):
        """Verifica che il nuovo alias /player/ funzioni."""
        response = self.client.get(reverse('player_profile', args=[self.athlete_user.username]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.athlete_user.get_full_name())

    def test_hardening_excludes_non_published_matches(self):
        """Verifica che i match NON pubblicati non appaiano nelle liste pubbliche."""
        # 1. Crea un match finito con un report VALIDATED (ma non PUBLISHED)
        draft_match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team,
            match_date=timezone.now() - timezone.timedelta(hours=5),
            is_finished=True,
            home_score=5,
            away_score=5
        )
        MatchReport.objects.create(match=draft_match, status='VALIDATED')
        
        # 2. Verifica pagina Team: non deve contenere il punteggio del draft match
        response = self.client.get(reverse('team_detail', args=[self.team.slug]))
        self.assertNotContains(response, "5-5")
        
        # 3. Verifica pagina Athlete: non deve contenere il punteggio del draft match
        response = self.client.get(reverse('player_profile', args=[self.athlete_user.username]))
        self.assertNotContains(response, "5-5")

    def test_empty_states_render_safely(self):
        """Verifica che stati vuoti non mandino in crash le pagine."""
        empty_team = Team.objects.create(society=self.society, slug="empty-team")
        response = self.client.get(reverse('team_detail', args=[empty_team.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nessuna partita recente")
        
        empty_user = User.objects.create_user(username="empty_atleta", role="athlete")
        response = self.client.get(reverse('player_profile', args=[empty_user.username]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nessuna prestazione recente registrata")

    def test_api_standings(self):
        response = self.client.get(reverse('api_league_standings', args=[self.league.id]))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['league']['id'], self.league.id)
        self.assertEqual(data['standings'][0]['team_name'], self.team.name)

    def test_api_match_detail(self):
        response = self.client.get(reverse('api_match_detail', args=[self.match.id]))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['home_team'], self.team.name)
        self.assertEqual(data['home_score'], 10)


class SportMatchesSeasonSelectorTest(TestCase):
    """Macro 3 fetta 2: selettore stagione sulla pagina pubblica Partite
    (sport_matches). Replica il pattern di sport_detail (fetta 1): default =
    stagione corrente, ?season= additivo, filtro su League.season. Il filtro
    data (?date=) resta come sotto-filtro per-giorno."""

    def setUp(self):
        import datetime
        self.client = Client()
        self.sport = Sport.objects.create(name="PM SelTest", slug="pm-seltest")
        self.society = Society.objects.create(name="Soc PM", slug="soc-pm", sport=self.sport)
        self.team = Team.objects.create(society=self.society)
        self.league_old = League.objects.create(
            name="L vecchia", sport=self.sport, season="2024/2025", slug="pm-old")
        self.league_new = League.objects.create(
            name="L nuova", sport=self.sport, season="2025/2026", slug="pm-new")
        # Stagione corrente = 2025/2026 (NON la richiesta nel caso (a)), cosi'
        # un ?season=2024/2025 prova che la querystring sovrascrive il default.
        Season.objects.create(sport=self.sport, label="2024/2025", is_current=False)
        Season.objects.create(sport=self.sport, label="2025/2026", is_current=True)
        # Una partita per stagione, stesso giorno (oggi): isola il filtro
        # stagione dal sotto-filtro data, che di default e' la giornata odierna.
        self.today = timezone.now()
        self.match_old = Match.objects.create(
            league=self.league_old, home_team=self.team, away_team=self.team,
            match_date=self.today, is_finished=True, home_score=1, away_score=0)
        self.match_new = Match.objects.create(
            league=self.league_new, home_team=self.team, away_team=self.team,
            match_date=self.today, is_finished=True, home_score=2, away_score=2)

    def test_available_seasons_distinct_desc(self):
        resp = self.client.get(reverse("sport_matches", args=[self.sport.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["available_seasons"], ["2025/2026", "2024/2025"])

    def test_default_is_current_season(self):
        # (b) ?season assente -> default = stagione corrente (2025/2026).
        resp = self.client.get(reverse("sport_matches", args=[self.sport.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["selected_season"], "2025/2026")
        seasons = {m.league.season for m in resp.context["matches"]}
        self.assertEqual(seasons, {"2025/2026"})

    def test_querystring_overrides_default(self):
        # (a) ?season valido restringe le partite a quella stagione.
        resp = self.client.get(
            reverse("sport_matches", args=[self.sport.slug]), {"season": "2024/2025"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["selected_season"], "2024/2025")
        seasons = {m.league.season for m in resp.context["matches"]}
        self.assertEqual(seasons, {"2024/2025"})

    def test_invalid_season_falls_back_without_error(self):
        # (c) ?season non in available_seasons -> fallback alla corrente, 200.
        resp = self.client.get(
            reverse("sport_matches", args=[self.sport.slug]), {"season": "1999/2000"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["selected_season"], "2025/2026")

    def test_selector_rendered_with_multiple_seasons(self):
        resp = self.client.get(reverse("sport_matches", args=[self.sport.slug]))
        self.assertContains(resp, 'id="season-select"')

    def test_season_form_preserves_date_hidden_input(self):
        # Il form stagione porta il giorno corrente come hidden -> cambiare
        # stagione non perde il sotto-filtro data.
        resp = self.client.get(
            reverse("sport_matches", args=[self.sport.slug]), {"date": "2026-01-15"})
        self.assertContains(resp, 'name="date" value="2026-01-15"')

    def test_no_selector_and_200_without_leagues(self):
        # (d) sport senza leghe/partite -> 200, nessun <select>, lista vuota.
        empty_sport = Sport.objects.create(name="PM Vuoto", slug="pm-vuoto")
        resp = self.client.get(reverse("sport_matches", args=[empty_sport.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["available_seasons"], [])
        self.assertEqual(list(resp.context["matches"]), [])
        self.assertNotContains(resp, 'id="season-select"')

    def test_date_subfilter_still_works(self):
        # (e) regressione: il sotto-filtro ?date= continua a restringere per
        # giorno, all'interno della stagione corrente di default.
        import datetime
        other_day = self.today + datetime.timedelta(days=3)
        match_future = Match.objects.create(
            league=self.league_new, home_team=self.team, away_team=self.team,
            match_date=other_day, is_finished=False)
        # Default (oggi): vede la partita di oggi, non quella futura.
        resp_today = self.client.get(reverse("sport_matches", args=[self.sport.slug]))
        ids_today = {m.id for m in resp_today.context["matches"]}
        self.assertIn(self.match_new.id, ids_today)
        self.assertNotIn(match_future.id, ids_today)
        # ?date=<giorno futuro>: vede solo la partita futura (stessa stagione).
        # La data del parametro va calcolata in Europe/Rome (`localtime`), coerente
        # col filtro `match_date__date` della view che opera in Europe/Rome: con
        # `other_day.date()` (data UTC del datetime aware) fra le 00:00 e le 02:00
        # di Roma il parametro cadeva sul giorno UTC sbagliato (bug lato-test,
        # OPS_RUNBOOK §10.29 sibling B).
        resp_future = self.client.get(
            reverse("sport_matches", args=[self.sport.slug]),
            {"date": timezone.localtime(other_day).date().strftime("%Y-%m-%d")})
        ids_future = {m.id for m in resp_future.context["matches"]}
        self.assertIn(match_future.id, ids_future)
        self.assertNotIn(self.match_new.id, ids_future)
