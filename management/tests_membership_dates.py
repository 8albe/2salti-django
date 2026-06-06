from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Society, Sport, Team
from management.models import ActivationCode, Membership, MembershipRequest
from management.services.membership_enrollment import redeem_activation_code

User = get_user_model()


class MembershipActiveAtTests(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn")
        self.society = Society.objects.create(
            name="Pro Recco", slug="pro-recco", sport=self.sport, city="Recco"
        )
        self.team = Team.objects.create(
            society=self.society, category='SENIOR', slug='pro-recco-senior'
        )
        self.user = User.objects.create_user(username='athlete1', role='athlete')
        self.today = timezone.localdate()
        self.yesterday = self.today - timedelta(days=1)
        self.tomorrow = self.today + timedelta(days=1)

    def _make_membership(self, **overrides):
        defaults = dict(
            user=self.user,
            society=self.society,
            team=self.team,
            role='PLAYER',
        )
        defaults.update(overrides)
        return Membership.objects.create(**defaults)

    def test_active_at_default_today(self):
        m = self._make_membership(start_date=self.yesterday, end_date=None)

        active = Membership.objects.active_at()

        self.assertIn(m, active)

    def test_active_at_future_date(self):
        m = self._make_membership(start_date=self.tomorrow, end_date=None)

        self.assertNotIn(m, Membership.objects.active_at())
        self.assertIn(m, Membership.objects.active_at(self.tomorrow))

    def test_active_at_closed(self):
        m = self._make_membership(start_date=self.yesterday, end_date=self.yesterday)

        self.assertNotIn(m, Membership.objects.active_at())
        self.assertIn(m, Membership.objects.active_at(self.yesterday))

    def test_active_at_null_start(self):
        m = self._make_membership(start_date=None, end_date=None)

        self.assertNotIn(m, Membership.objects.active_at())
        self.assertNotIn(m, Membership.objects.active_at(self.today))
        self.assertNotIn(m, Membership.objects.active_at(self.tomorrow))

    def test_active_at_explicit_date(self):
        past_member = self._make_membership(
            start_date=self.today - timedelta(days=30),
            end_date=self.today - timedelta(days=10),
        )
        other_user = User.objects.create_user(username='athlete2', role='athlete')
        current_member = Membership.objects.create(
            user=other_user,
            society=self.society,
            team=self.team,
            role='PLAYER',
            start_date=self.yesterday,
            end_date=None,
        )

        snapshot = Membership.objects.active_at(self.today - timedelta(days=20))

        self.assertIn(past_member, snapshot)
        self.assertNotIn(current_member, snapshot)

    def test_default_manager_chainable(self):
        player = self._make_membership(start_date=self.yesterday, role='PLAYER')
        other_user = User.objects.create_user(username='coach1', role='coach')
        Membership.objects.create(
            user=other_user,
            society=self.society,
            team=self.team,
            role='HEAD_COACH',
            start_date=self.yesterday,
        )

        chained = Membership.objects.active_at().filter(role='PLAYER')

        self.assertIn(player, chained)
        self.assertEqual(chained.count(), 1)


class MembershipSignalCleanupTests(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn")
        self.society = Society.objects.create(
            name="Pro Recco", slug="pro-recco", sport=self.sport, city="Recco"
        )
        self.team_a = Team.objects.create(
            society=self.society, category='SENIOR', slug='team-a'
        )
        self.team_b = Team.objects.create(
            society=self.society, category='U20', slug='team-b'
        )
        self.user = User.objects.create_user(username='athlete1', role='athlete')
        self.today = timezone.localdate()

    def test_signal_closes_old_membership_on_team_change(self):
        profile = self.user.athlete_profile
        profile.current_team = self.team_a
        profile.save()
        old = Membership.objects.get(
            user=self.user, society=self.society, team=self.team_a, role='PLAYER'
        )
        self.assertEqual(old.start_date, self.today)
        self.assertIsNone(old.end_date)

        profile.current_team = self.team_b
        profile.save()

        old.refresh_from_db()
        self.assertEqual(old.end_date, self.today)
        self.assertFalse(old.is_active)

        new = Membership.objects.get(
            user=self.user, society=self.society, team=self.team_b, role='PLAYER'
        )
        self.assertEqual(new.start_date, self.today)
        self.assertIsNone(new.end_date)
        self.assertTrue(new.is_active)

    def test_signal_no_close_on_same_team(self):
        profile = self.user.athlete_profile
        profile.current_team = self.team_a
        profile.save()
        m = Membership.objects.get(
            user=self.user, society=self.society, team=self.team_a, role='PLAYER'
        )
        original_start = m.start_date

        m.start_date = self.today - timedelta(days=30)
        m.save(update_fields=['start_date'])
        original_start = m.start_date

        profile.save()

        m.refresh_from_db()
        self.assertEqual(m.start_date, original_start)
        self.assertIsNone(m.end_date)
        self.assertTrue(m.is_active)
        self.assertEqual(
            Membership.objects.filter(user=self.user, role='PLAYER').count(), 1,
        )

    def test_signal_create_first_membership_sets_start_date(self):
        self.assertFalse(Membership.objects.filter(user=self.user).exists())

        profile = self.user.athlete_profile
        profile.current_team = self.team_a
        profile.save()

        m = Membership.objects.get(user=self.user, role='PLAYER')
        self.assertEqual(m.start_date, self.today)
        self.assertIsNone(m.end_date)
        self.assertTrue(m.is_active)

    def test_signal_close_when_team_set_to_none(self):
        profile = self.user.athlete_profile
        profile.current_team = self.team_a
        profile.save()
        m = Membership.objects.get(user=self.user, role='PLAYER')
        self.assertIsNone(m.end_date)

        profile.current_team = None
        profile.save()

        m.refresh_from_db()
        self.assertEqual(m.end_date, self.today)
        self.assertFalse(m.is_active)
        self.assertFalse(
            Membership.objects.filter(
                user=self.user, role='PLAYER', end_date__isnull=True,
            ).exists()
        )

    def test_enrollment_service_sets_start_date(self):
        code = ActivationCode.objects.create(
            code='ABC-123',
            society=self.society,
            team=self.team_a,
            role='PLAYER',
            max_uses=5,
            current_uses=0,
            is_active=True,
        )

        ok, membership, err = redeem_activation_code(self.user, 'ABC-123')

        self.assertTrue(ok)
        self.assertIsNotNone(membership)
        self.assertEqual(membership.start_date, self.today)
        self.assertIsNone(membership.end_date)

    def test_membership_request_approve_sets_start_date(self):
        president_user = User.objects.create_user(
            username='prez', password='pwd', role='president',
            identity_status='VERIFIED', subscription_status='ACTIVE',
            setup_completed=True,
        )
        president_profile = president_user.president_profile
        president_profile.managed_society = self.society
        president_profile.save()
        req = MembershipRequest.objects.create(
            user=self.user,
            society=self.society,
            team=self.team_a,
            role='PLAYER',
            status='PENDING',
        )
        client = self.client
        client.login(username='prez', password='pwd')

        response = client.post(
            reverse('approve_membership', args=[req.id]), {'action': 'approve'},
        )

        self.assertEqual(response.status_code, 302)
        m = Membership.objects.get(
            user=self.user, society=self.society, team=self.team_a, role='PLAYER'
        )
        self.assertEqual(m.start_date, self.today)
        self.assertIsNone(m.end_date)

    # ── Fix rischio #1: servizi aggiornano profile.current_team ───────────

    def test_redeem_updates_profile_current_team(self):
        self.assertIsNone(self.user.athlete_profile.current_team)
        code = ActivationCode.objects.create(
            code='UPD-001',
            society=self.society,
            team=self.team_a,
            role='PLAYER',
            max_uses=5,
            current_uses=0,
            is_active=True,
        )

        ok, _, _ = redeem_activation_code(self.user, 'UPD-001')

        self.assertTrue(ok)
        self.user.athlete_profile.refresh_from_db()
        self.assertEqual(self.user.athlete_profile.current_team, self.team_a)

    def test_redeem_then_profile_save_does_not_close_membership(self):
        code = ActivationCode.objects.create(
            code='STAY-001',
            society=self.society,
            team=self.team_a,
            role='PLAYER',
            max_uses=5,
            current_uses=0,
            is_active=True,
        )
        ok, membership, _ = redeem_activation_code(self.user, 'STAY-001')
        self.assertTrue(ok)
        self.assertIsNone(membership.end_date)

        profile = self.user.athlete_profile
        profile.refresh_from_db()
        profile.birth_date = self.today - timedelta(days=30 * 365)
        profile.save()

        membership.refresh_from_db()
        self.assertIsNone(membership.end_date)
        self.assertTrue(membership.is_active)
        self.assertEqual(
            Membership.objects.filter(
                user=self.user, role='PLAYER', end_date__isnull=True,
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
        self.assertIsNone(old.end_date)

        profile.current_team = team_other_society
        profile.save()

        old.refresh_from_db()
        self.assertEqual(old.end_date, self.today)
        self.assertFalse(old.is_active)

        new = Membership.objects.get(
            user=self.user, society=other_society, team=team_other_society, role='PLAYER'
        )
        self.assertIsNone(new.end_date)
        self.assertTrue(new.is_active)

    def test_signal_does_not_close_other_role_memberships(self):
        profile = self.user.athlete_profile
        profile.current_team = self.team_a
        profile.save()

        coach_membership = Membership.objects.create(
            user=self.user,
            society=self.society,
            team=self.team_b,
            role='HEAD_COACH',
            start_date=self.today - timedelta(days=5),
            end_date=None,
            is_active=True,
        )

        team_c = Team.objects.create(
            society=self.society, category='U18', slug='team-c'
        )
        profile.current_team = team_c
        profile.save()

        old_player = Membership.objects.get(
            user=self.user, team=self.team_a, role='PLAYER'
        )
        self.assertEqual(old_player.end_date, self.today)

        coach_membership.refresh_from_db()
        self.assertIsNone(coach_membership.end_date)
        self.assertTrue(coach_membership.is_active)


class MembershipEndDateConstraintTests(TestCase):
    """DEBT-003: end_date < start_date deve essere impedito a livello DB
    (CheckConstraint) e segnalato pulito a livello validazione (clean())."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn")
        self.society = Society.objects.create(
            name="Pro Recco", slug="pro-recco", sport=self.sport, city="Recco"
        )
        self.team = Team.objects.create(
            society=self.society, category='SENIOR', slug='pro-recco-senior'
        )
        self.user = User.objects.create_user(username='athlete1', role='athlete')
        self.today = timezone.localdate()
        self.yesterday = self.today - timedelta(days=1)

    def _membership(self, **overrides):
        defaults = dict(
            user=self.user,
            society=self.society,
            team=self.team,
            role='PLAYER',
        )
        defaults.update(overrides)
        return Membership(**defaults)

    def test_db_rejects_end_before_start(self):
        from django.db import IntegrityError, transaction

        m = self._membership(start_date=self.today, end_date=self.yesterday)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                m.save()

    def test_clean_rejects_end_before_start(self):
        from django.core.exceptions import ValidationError

        m = self._membership(start_date=self.today, end_date=self.yesterday)
        with self.assertRaises(ValidationError):
            m.full_clean()

    def test_allows_equal_dates(self):
        m = self._membership(start_date=self.today, end_date=self.today)
        m.full_clean()
        m.save()
        self.assertEqual(Membership.objects.filter(pk=m.pk).count(), 1)

    def test_allows_null_start_with_end(self):
        m = self._membership(start_date=None, end_date=self.today)
        m.full_clean()
        m.save()
        self.assertEqual(Membership.objects.filter(pk=m.pk).count(), 1)
