from datetime import date, datetime, time

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import Sport, Society, Team, League, Season
from management.models import Membership
from matches.models import Match

User = get_user_model()


def _aware_dt_on(d):
    """Datetime aware in Europe/Rome con orario fisso (12:00) a partire da una date."""
    return timezone.make_aware(datetime.combine(d, time(12, 0)))


class PlayerMembershipsOrderingTests(TestCase):
    """§10.4 Step 3c (rivisto Fase 2): player_memberships ordinato per stagione
    più recente (-season__label, NULL in coda; tie -created_at)."""

    def setUp(self):
        self.client = Client()
        self.sport = Sport.objects.create(name='Pallanuoto', slug='pallanuoto')
        self.society = Society.objects.create(name='Pro Recco', slug='pro-recco', sport=self.sport)
        self.season_prev = Season.objects.create(sport=self.sport, label='2024/2025', is_current=False)
        self.season_curr = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.league = League.objects.create(
            name='Serie A1', sport=self.sport, season='2025-2026',
        )
        self.team_a = Team.objects.create(society=self.society, league=self.league, slug='tmp-team-a')
        self.team_b = Team.objects.create(society=self.society, league=self.league, slug='tmp-team-b')
        self.athlete = User.objects.create_user(
            username='atleta_test', password='pw', role='athlete',
            first_name='Mario', last_name='Rossi',
        )

    def test_player_memberships_ordered_by_season(self):
        """Membership della stagione più recente appare prima in player_memberships."""
        # Stagione precedente, chiusa
        Membership.objects.create(
            user=self.athlete, society=self.society, team=self.team_a, role='PLAYER',
            season=self.season_prev, is_active=False,
        )
        # Stagione corrente, attiva
        Membership.objects.create(
            user=self.athlete, society=self.society, team=self.team_b, role='PLAYER',
            season=self.season_curr, is_active=True,
        )

        response = self.client.get(reverse('profile', args=[self.athlete.username]))
        self.assertEqual(response.status_code, 200)
        memberships = list(response.context['player_memberships'])
        self.assertEqual(len(memberships), 2)
        self.assertEqual(memberships[0].team_id, self.team_b.id)  # 2025/2026 prima
        self.assertEqual(memberships[1].team_id, self.team_a.id)  # 2024/2025 dopo


class CoachedDirectMatchesTemporalTests(TestCase):
    """§16.3 fetta 2d-3: direct_matches attribuito col modello β-stagione/coach-finale.

    Il coach "della stagione" per una squadra è quello in carica a fine stagione; a
    lui sono attribuite TUTTE le partite della squadra in quella stagione, derivata
    via Match -> league -> league.season_fk, senza alcun bound start_date/end_date.
    """

    def setUp(self):
        self.client = Client()
        self.sport = Sport.objects.create(name='Pallanuoto', slug='pallanuoto')
        self.society = Society.objects.create(name='Pro Recco', slug='pro-recco', sport=self.sport)
        self.opponent_society = Society.objects.create(name='SC Quinto', slug='sc-quinto', sport=self.sport)

        # Due Season reali per lo sport; la lega corrente ha season_fk valorizzato
        # (senza questo, l'attribuzione β-stagione cadrebbe nel ramo difensivo).
        self.season_curr = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.season_prev = Season.objects.create(sport=self.sport, label='2024/2025', is_current=False)

        self.league = League.objects.create(
            name='Serie A1', sport=self.sport, season='2025-2026',
            season_fk=self.season_curr,
        )
        # Lega di un'altra stagione, stessa squadra/avversario: serve a provare che
        # l'attribuzione è per stagione, non per squadra in assoluto.
        self.league_prev = League.objects.create(
            name='Serie A1 (24/25)', sport=self.sport, season='2024-2025',
            season_fk=self.season_prev,
        )
        self.team_a = Team.objects.create(society=self.society, league=self.league)
        self.opponent = Team.objects.create(society=self.opponent_society, league=self.league)

        self.coach = User.objects.create_user(
            username='coach_test', password='pw', role='coach',
            first_name='Carlo', last_name='Bianchi',
        )
        # coach_profile esiste già via signals/setup_wizard? In test creiamolo esplicitamente
        # senza current_team per NON attivare il signal sync_coach_membership.
        from accounts.models import CoachProfile
        CoachProfile.objects.get_or_create(user=self.coach)

    def _make_match(self, match_d, home=None, away=None, league=None):
        return Match.objects.create(
            league=league or self.league,
            home_team=home or self.team_a,
            away_team=away or self.opponent,
            match_date=_aware_dt_on(match_d),
        )

    def _coach_membership(self, season, is_active=True):
        return Membership.objects.create(
            user=self.coach, society=self.society, team=self.team_a, role='HEAD_COACH',
            season=season, is_active=is_active,
        )

    def test_includes_match_same_season(self):
        """Match nella stagione della membership (league.season_fk == season) → incluso."""
        self._coach_membership(season=self.season_curr)
        match_same = self._make_match(date(2025, 6, 15))

        response = self.client.get(reverse('profile', args=[self.coach.username]))
        self.assertEqual(response.status_code, 200)
        direct = response.context.get('direct_matches')
        self.assertIsNotNone(direct)
        ids = [m.id for m in direct]
        self.assertIn(match_same.id, ids)

    def test_excludes_match_other_season(self):
        """Match della stessa squadra ma in un'altra stagione (diverso league.season_fk) → escluso."""
        self._coach_membership(season=self.season_curr)
        match_other_season = self._make_match(date(2025, 6, 15), league=self.league_prev)

        response = self.client.get(reverse('profile', args=[self.coach.username]))
        self.assertEqual(response.status_code, 200)
        direct = response.context.get('direct_matches')
        ids = [m.id for m in direct] if direct else []
        self.assertNotIn(match_other_season.id, ids)

    def test_includes_all_season_matches_for_final_coach(self):
        """Modello β-stagione/coach-finale: al coach della stagione sono attribuite
        TUTTE le partite della squadra in quella stagione, anche distanti nel tempo."""
        self._coach_membership(season=self.season_curr)
        match_early = self._make_match(date(2025, 9, 15))
        match_late = self._make_match(date(2026, 3, 1))

        response = self.client.get(reverse('profile', args=[self.coach.username]))
        self.assertEqual(response.status_code, 200)
        direct = response.context.get('direct_matches')
        self.assertIsNotNone(direct)
        ids = [m.id for m in direct]
        self.assertIn(match_early.id, ids)
        self.assertIn(match_late.id, ids)

    # Nota Fase 2 (2d-7): lo scenario "Membership con season=None" non esiste
    # piu' a livello di schema (NOT NULL), quindi il vecchio test del ramo
    # difensivo della view e' stato rimosso: il filtro season_id is not None
    # nella view resta come difesa morta ma innocua.
