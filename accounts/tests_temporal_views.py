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
    """§10.4 Step 3c: player_memberships ordinato per -start_date (tie -created_at)."""

    def setUp(self):
        self.client = Client()
        self.sport = Sport.objects.create(name='Pallanuoto', slug='pallanuoto')
        self.society = Society.objects.create(name='Pro Recco', slug='pro-recco', sport=self.sport)
        self.league = League.objects.create(
            name='Serie A1', sport=self.sport, category='SENIOR', season='2025-2026',
        )
        self.team_a = Team.objects.create(society=self.society, category='SENIOR', league=self.league)
        self.team_b = Team.objects.create(society=self.society, category='UNDER_20', league=self.league)
        self.athlete = User.objects.create_user(
            username='atleta_test', password='pw', role='athlete',
            first_name='Mario', last_name='Rossi',
        )

    def test_player_memberships_ordered_by_start_date(self):
        """Membership più recente per start_date appare prima in coached_memberships."""
        # Più vecchia, chiusa
        Membership.objects.create(
            user=self.athlete, society=self.society, team=self.team_a, role='PLAYER',
            start_date=date(2024, 9, 1), end_date=date(2025, 6, 30), is_active=False,
        )
        # Più recente, attiva
        Membership.objects.create(
            user=self.athlete, society=self.society, team=self.team_b, role='PLAYER',
            start_date=date(2025, 9, 1), end_date=None, is_active=True,
        )

        response = self.client.get(reverse('profile', args=[self.athlete.username]))
        self.assertEqual(response.status_code, 200)
        memberships = list(response.context['player_memberships'])
        self.assertEqual(len(memberships), 2)
        self.assertEqual(memberships[0].team_id, self.team_b.id)  # start_date 2025-09 prima
        self.assertEqual(memberships[1].team_id, self.team_a.id)  # start_date 2024-09 dopo


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
            name='Serie A1', sport=self.sport, category='SENIOR', season='2025-2026',
            season_fk=self.season_curr,
        )
        # Lega di un'altra stagione, stessa squadra/avversario: serve a provare che
        # l'attribuzione è per stagione, non per squadra in assoluto.
        self.league_prev = League.objects.create(
            name='Serie A1 (24/25)', sport=self.sport, category='SENIOR', season='2024-2025',
            season_fk=self.season_prev,
        )
        self.team_a = Team.objects.create(society=self.society, category='SENIOR', league=self.league)
        self.opponent = Team.objects.create(society=self.opponent_society, category='SENIOR', league=self.league)

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

    def _coach_membership(self, season=None, start_date=None, end_date=None, is_active=True):
        return Membership.objects.create(
            user=self.coach, society=self.society, team=self.team_a, role='HEAD_COACH',
            season=season, start_date=start_date, end_date=end_date, is_active=is_active,
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

    def test_includes_match_regardless_of_date_window(self):
        """Cambio semantico β-stagione: anche un match fuori dall'ex-finestra-data,
        purché nella stessa stagione, ora è attribuito (le date non contano più)."""
        # Ex-finestra stretta che sotto il vecchio modello AVREBBE escluso il match.
        self._coach_membership(
            season=self.season_curr,
            start_date=date(2025, 9, 1), end_date=date(2025, 9, 30),
        )
        match_outside_old_window = self._make_match(date(2026, 3, 1))  # fuori [set,set], stessa season

        response = self.client.get(reverse('profile', args=[self.coach.username]))
        self.assertEqual(response.status_code, 200)
        direct = response.context.get('direct_matches')
        self.assertIsNotNone(direct)
        ids = [m.id for m in direct]
        self.assertIn(match_outside_old_window.id, ids)

    def test_season_none_membership_no_direct_matches(self):
        """Ramo difensivo: Membership HEAD_COACH con season=None APPARE nello storico
        ma NON genera attribuzione (coerente con resolve_membership_season → None)."""
        legacy = self._coach_membership(season=None, start_date=date(2025, 1, 1))
        match = self._make_match(date(2025, 6, 15))

        response = self.client.get(reverse('profile', args=[self.coach.username]))
        self.assertEqual(response.status_code, 200)

        coached_ids = [m.id for m in response.context['coached_memberships']]
        self.assertIn(legacy.id, coached_ids)  # storico mostra comunque il record

        direct = response.context.get('direct_matches')
        if direct is not None:
            ids = [m.id for m in direct]
            self.assertNotIn(match.id, ids)
        # direct=None è anche corretto: nessuna season nota → niente direct_matches.

    def test_no_start_date_but_season_set_includes_match(self):
        """Le date non contano più: start_date=None con season valorizzata → match incluso."""
        self._coach_membership(season=self.season_curr, start_date=None, end_date=None)
        match = self._make_match(date(2025, 6, 15))

        response = self.client.get(reverse('profile', args=[self.coach.username]))
        self.assertEqual(response.status_code, 200)
        direct = response.context.get('direct_matches')
        self.assertIsNotNone(direct)
        ids = [m.id for m in direct]
        self.assertIn(match.id, ids)
