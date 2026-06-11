"""Ciclo di vita Membership su base stagione (Macro 16 Fase 2).

Eredita il perimetro di tests_membership_dates.py (rimosso con start_date/
end_date): queryset attivi, lifecycle via signal profili, creation-site
servizi/view. Il predicato di attivita' e' is_active (2d-5); l'asse temporale
e' la Season (niente finestre di date).
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Season, Society, Sport, Team
from management.models import ActivationCode, Membership, MembershipRequest
from management.services.membership_enrollment import redeem_activation_code

User = get_user_model()


class MembershipActiveQuerySetTests(TestCase):
    """active() / active_in_season(): sostituiscono il vecchio active_at(date)."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn")
        self.society = Society.objects.create(
            name="Pro Recco", slug="pro-recco", sport=self.sport, city="Recco"
        )
        self.team = Team.objects.create(
            society=self.society, category='SENIOR', slug='pro-recco-senior'
        )
        self.season_prev = Season.objects.create(
            sport=self.sport, label='2024/2025', is_current=False
        )
        self.season_curr = Season.objects.create(
            sport=self.sport, label='2025/2026', is_current=True
        )
        self.user = User.objects.create_user(username='athlete1', role='athlete')

    def _make_membership(self, **overrides):
        defaults = dict(
            user=self.user,
            society=self.society,
            team=self.team,
            role='PLAYER',
            season=self.season_curr,
        )
        defaults.update(overrides)
        return Membership.objects.create(**defaults)

    def test_active_includes_only_is_active(self):
        active = self._make_membership(is_active=True)
        other_user = User.objects.create_user(username='athlete2', role='athlete')
        closed = self._make_membership(user=other_user, is_active=False)

        qs = Membership.objects.active()

        self.assertIn(active, qs)
        self.assertNotIn(closed, qs)

    def test_active_in_season_filters_by_season(self):
        curr = self._make_membership(season=self.season_curr, is_active=True)
        prev = self._make_membership(season=self.season_prev, is_active=True)

        qs = Membership.objects.active_in_season(self.season_curr)

        self.assertIn(curr, qs)
        self.assertNotIn(prev, qs)

    def test_active_in_season_excludes_closed_row_same_season(self):
        closed = self._make_membership(season=self.season_curr, is_active=False)

        self.assertNotIn(
            closed, Membership.objects.active_in_season(self.season_curr)
        )

    def test_default_manager_chainable(self):
        player = self._make_membership(role='PLAYER')
        other_user = User.objects.create_user(username='coach1', role='coach')
        Membership.objects.create(
            user=other_user, society=self.society, team=self.team,
            role='HEAD_COACH', season=self.season_curr,
        )

        chained = Membership.objects.active().filter(role='PLAYER')

        self.assertIn(player, chained)
        self.assertEqual(chained.count(), 1)


class MembershipSignalCleanupTests(TestCase):
    """Lifecycle via signal profili: chiusura = is_active=False, riga conservata."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn")
        self.society = Society.objects.create(
            name="Pro Recco", slug="pro-recco", sport=self.sport, city="Recco"
        )
        self.season = Season.objects.create(
            sport=self.sport, label='2025/2026', is_current=True
        )
        self.team_a = Team.objects.create(
            society=self.society, category='SENIOR', slug='team-a'
        )
        self.team_b = Team.objects.create(
            society=self.society, category='U20', slug='team-b'
        )
        self.user = User.objects.create_user(username='athlete1', role='athlete')

    def test_signal_closes_old_membership_on_team_change(self):
        profile = self.user.athlete_profile
        profile.current_team = self.team_a
        profile.save()
        old = Membership.objects.get(
            user=self.user, society=self.society, team=self.team_a, role='PLAYER'
        )
        self.assertTrue(old.is_active)

        profile.current_team = self.team_b
        profile.save()

        # Successione: la riga d'origine resta (storico), solo chiusa.
        old.refresh_from_db()
        self.assertFalse(old.is_active)

        new = Membership.objects.get(
            user=self.user, society=self.society, team=self.team_b, role='PLAYER'
        )
        self.assertTrue(new.is_active)

    def test_signal_no_op_on_same_team(self):
        profile = self.user.athlete_profile
        profile.current_team = self.team_a
        profile.save()
        m = Membership.objects.get(
            user=self.user, society=self.society, team=self.team_a, role='PLAYER'
        )
        original_updated_at = m.updated_at

        profile.save()

        m.refresh_from_db()
        self.assertTrue(m.is_active)
        # No-op: nessuna riscrittura della riga gia' attiva.
        self.assertEqual(m.updated_at, original_updated_at)
        self.assertEqual(
            Membership.objects.filter(user=self.user, role='PLAYER').count(), 1,
        )

    def test_signal_create_first_membership_active_with_season(self):
        self.assertFalse(Membership.objects.filter(user=self.user).exists())

        profile = self.user.athlete_profile
        profile.current_team = self.team_a
        profile.save()

        m = Membership.objects.get(user=self.user, role='PLAYER')
        self.assertTrue(m.is_active)
        self.assertEqual(m.season, self.season)

    def test_signal_close_when_team_set_to_none(self):
        profile = self.user.athlete_profile
        profile.current_team = self.team_a
        profile.save()
        m = Membership.objects.get(user=self.user, role='PLAYER')
        self.assertTrue(m.is_active)

        profile.current_team = None
        profile.save()

        m.refresh_from_db()
        self.assertFalse(m.is_active)
        self.assertFalse(
            Membership.objects.filter(
                user=self.user, role='PLAYER', is_active=True,
            ).exists()
        )

    def test_signal_reopen_inactive_membership(self):
        profile = self.user.athlete_profile
        profile.current_team = self.team_a
        profile.save()
        m = Membership.objects.get(user=self.user, role='PLAYER')
        profile.current_team = None
        profile.save()
        m.refresh_from_db()
        self.assertFalse(m.is_active)

        profile.current_team = self.team_a
        profile.save()

        m.refresh_from_db()
        self.assertTrue(m.is_active)
        self.assertEqual(
            Membership.objects.filter(user=self.user, role='PLAYER').count(), 1,
        )

    def test_enrollment_service_creates_active_with_season(self):
        ActivationCode.objects.create(
            code='ABC-123', society=self.society, team=self.team_a,
            role='PLAYER', max_uses=5, current_uses=0, is_active=True,
        )

        ok, membership, err = redeem_activation_code(self.user, 'ABC-123')

        self.assertTrue(ok)
        self.assertIsNotNone(membership)
        self.assertTrue(membership.is_active)
        self.assertEqual(membership.season, self.season)

    def test_membership_request_approve_creates_active_with_season(self):
        president_user = User.objects.create_user(
            username='prez', password='pwd', role='president',
            identity_status='VERIFIED', subscription_status='ACTIVE',
            setup_completed=True,
        )
        president_profile = president_user.president_profile
        president_profile.managed_society = self.society
        president_profile.save()
        req = MembershipRequest.objects.create(
            user=self.user, society=self.society, team=self.team_a,
            role='PLAYER', status='PENDING',
        )
        self.client.login(username='prez', password='pwd')

        response = self.client.post(
            reverse('approve_membership', args=[req.id]), {'action': 'approve'},
        )

        self.assertEqual(response.status_code, 302)
        m = Membership.objects.get(
            user=self.user, society=self.society, team=self.team_a, role='PLAYER'
        )
        self.assertTrue(m.is_active)
        self.assertEqual(m.season, self.season)

    # ── Fix rischio #1: servizi aggiornano profile.current_team ───────────

    def test_redeem_updates_profile_current_team(self):
        self.assertIsNone(self.user.athlete_profile.current_team)
        ActivationCode.objects.create(
            code='UPD-001', society=self.society, team=self.team_a,
            role='PLAYER', max_uses=5, current_uses=0, is_active=True,
        )

        ok, _, _ = redeem_activation_code(self.user, 'UPD-001')

        self.assertTrue(ok)
        self.user.athlete_profile.refresh_from_db()
        self.assertEqual(self.user.athlete_profile.current_team, self.team_a)

    def test_redeem_then_profile_save_does_not_close_membership(self):
        ActivationCode.objects.create(
            code='STAY-001', society=self.society, team=self.team_a,
            role='PLAYER', max_uses=5, current_uses=0, is_active=True,
        )
        ok, membership, _ = redeem_activation_code(self.user, 'STAY-001')
        self.assertTrue(ok)
        self.assertTrue(membership.is_active)

        profile = self.user.athlete_profile
        profile.refresh_from_db()
        profile.birth_date = timezone.localdate() - timedelta(days=30 * 365)
        profile.save()

        membership.refresh_from_db()
        self.assertTrue(membership.is_active)
        self.assertEqual(
            Membership.objects.filter(
                user=self.user, role='PLAYER', is_active=True,
            ).count(),
            1,
        )

    # ── Fix rischio #2: cross-society cleanup nel signal ──────────────────

    def test_signal_closes_cross_society_on_team_change(self):
        other_society = Society.objects.create(
            name="Brescia", slug="brescia", sport=self.sport, city="Brescia"
        )
        team_other_society = Team.objects.create(
            society=other_society, category='SENIOR', slug='brescia-senior'
        )

        profile = self.user.athlete_profile
        profile.current_team = self.team_a
        profile.save()
        old = Membership.objects.get(
            user=self.user, society=self.society, team=self.team_a, role='PLAYER'
        )
        self.assertTrue(old.is_active)

        profile.current_team = team_other_society
        profile.save()

        old.refresh_from_db()
        self.assertFalse(old.is_active)

        new = Membership.objects.get(
            user=self.user, society=other_society, team=team_other_society,
            role='PLAYER',
        )
        self.assertTrue(new.is_active)

    def test_signal_does_not_close_other_role_memberships(self):
        profile = self.user.athlete_profile
        profile.current_team = self.team_a
        profile.save()

        coach_membership = Membership.objects.create(
            user=self.user, society=self.society, team=self.team_b,
            role='HEAD_COACH', season=self.season, is_active=True,
        )

        team_c = Team.objects.create(
            society=self.society, category='U18', slug='team-c'
        )
        profile.current_team = team_c
        profile.save()

        old_player = Membership.objects.get(
            user=self.user, team=self.team_a, role='PLAYER'
        )
        self.assertFalse(old_player.is_active)

        coach_membership.refresh_from_db()
        self.assertTrue(coach_membership.is_active)
