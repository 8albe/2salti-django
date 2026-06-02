from datetime import date, datetime, time

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import Sport, Society, Team, League
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
    """§10.4 Step 3c: direct_matches filtrato dalla tenure HEAD_COACH (Opzione C)."""

    def setUp(self):
        self.client = Client()
        self.sport = Sport.objects.create(name='Pallanuoto', slug='pallanuoto')
        self.society = Society.objects.create(name='Pro Recco', slug='pro-recco', sport=self.sport)
        self.opponent_society = Society.objects.create(name='SC Quinto', slug='sc-quinto', sport=self.sport)
        self.league = League.objects.create(
            name='Serie A1', sport=self.sport, category='SENIOR', season='2025-2026',
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

    def _make_match(self, match_d, home=None, away=None):
        return Match.objects.create(
            league=self.league,
            home_team=home or self.team_a,
            away_team=away or self.opponent,
            match_date=_aware_dt_on(match_d),
        )

    def test_coached_team_filter_excludes_match_outside_tenure(self):
        """Match fuori dalla finestra start–end NON appare in direct_matches."""
        Membership.objects.create(
            user=self.coach, society=self.society, team=self.team_a, role='HEAD_COACH',
            start_date=date(2025, 1, 1), end_date=date(2025, 12, 31), is_active=False,
        )
        match_outside = self._make_match(date(2026, 3, 1))

        response = self.client.get(reverse('profile', args=[self.coach.username]))
        self.assertEqual(response.status_code, 200)
        direct = response.context.get('direct_matches')
        ids = [m.id for m in direct] if direct else []
        self.assertNotIn(match_outside.id, ids)

    def test_coached_team_includes_match_during_tenure(self):
        """Tenure aperta (end_date=None): match dentro la finestra appare."""
        Membership.objects.create(
            user=self.coach, society=self.society, team=self.team_a, role='HEAD_COACH',
            start_date=date(2025, 1, 1), end_date=None, is_active=True,
        )
        match_inside = self._make_match(date(2025, 6, 15))

        response = self.client.get(reverse('profile', args=[self.coach.username]))
        self.assertEqual(response.status_code, 200)
        direct = response.context.get('direct_matches')
        self.assertIsNotNone(direct)
        ids = [m.id for m in direct]
        self.assertIn(match_inside.id, ids)

    def test_coached_team_includes_match_on_start_date(self):
        """Boundary: Match datato esattamente start_date → incluso."""
        start = date(2025, 1, 1)
        Membership.objects.create(
            user=self.coach, society=self.society, team=self.team_a, role='HEAD_COACH',
            start_date=start, end_date=date(2025, 12, 31), is_active=False,
        )
        match_boundary = self._make_match(start)

        response = self.client.get(reverse('profile', args=[self.coach.username]))
        self.assertEqual(response.status_code, 200)
        direct = response.context.get('direct_matches')
        self.assertIsNotNone(direct)
        ids = [m.id for m in direct]
        self.assertIn(match_boundary.id, ids)

    def test_coached_team_includes_match_on_end_date(self):
        """Boundary: Match datato esattamente end_date → incluso."""
        end = date(2025, 12, 31)
        Membership.objects.create(
            user=self.coach, society=self.society, team=self.team_a, role='HEAD_COACH',
            start_date=date(2025, 1, 1), end_date=end, is_active=False,
        )
        match_boundary = self._make_match(end)

        response = self.client.get(reverse('profile', args=[self.coach.username]))
        self.assertEqual(response.status_code, 200)
        direct = response.context.get('direct_matches')
        self.assertIsNotNone(direct)
        ids = [m.id for m in direct]
        self.assertIn(match_boundary.id, ids)

    def test_coach_with_no_start_date_membership_does_not_match(self):
        """
        Membership HEAD_COACH con start_date=None: APPARE in coached_memberships
        (storico completo) ma NON genera direct_matches (record anomalo, saltato in tenure_q).
        """
        legacy = Membership.objects.create(
            user=self.coach, society=self.society, team=self.team_a, role='HEAD_COACH',
            start_date=None, end_date=None, is_active=True,
        )
        match = self._make_match(date(2025, 6, 15))

        response = self.client.get(reverse('profile', args=[self.coach.username]))
        self.assertEqual(response.status_code, 200)

        coached_ids = [m.id for m in response.context['coached_memberships']]
        self.assertIn(legacy.id, coached_ids)  # storico mostra il record

        direct = response.context.get('direct_matches')
        if direct is not None:
            ids = [m.id for m in direct]
            self.assertNotIn(match.id, ids)
        # direct=None è anche corretto: nessuna tenure valida → niente direct_matches.
