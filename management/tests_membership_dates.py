from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import Society, Sport, Team
from management.models import Membership

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
