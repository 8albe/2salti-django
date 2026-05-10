from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import Society, Sport, Team
from management.models import (
    ActivationCode,
    AuditLog,
    Membership,
    MembershipRequest,
)
from management.services.membership_enrollment import (
    redeem_activation_code,
    request_manual_membership,
)

User = get_user_model()


class MembershipEnrollmentServiceTests(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn")
        self.society = Society.objects.create(
            name="Pro Recco", slug="pro-recco", sport=self.sport, city="Recco"
        )
        self.team = Team.objects.create(
            society=self.society, category='SENIOR', slug='pro-recco-senior'
        )
        self.athlete = User.objects.create_user(
            username='athlete1', role='athlete'
        )
        self.coach = User.objects.create_user(
            username='coach1', role='coach'
        )

    def _make_code(self, **overrides):
        defaults = dict(
            code='ABC-123',
            society=self.society,
            team=self.team,
            role='PLAYER',
            max_uses=5,
            current_uses=0,
            is_active=True,
        )
        defaults.update(overrides)
        return ActivationCode.objects.create(**defaults)

    # ── redeem_activation_code ──────────────────────────────────

    def test_redeem_valid_code_creates_membership(self):
        code = self._make_code()

        ok, membership, err = redeem_activation_code(self.athlete, 'ABC-123')

        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, 'PLAYER')
        self.assertEqual(membership.user, self.athlete)
        self.assertEqual(membership.society, self.society)

        code.refresh_from_db()
        self.assertEqual(code.current_uses, 1)

        self.assertTrue(
            AuditLog.objects.filter(
                user=self.athlete, action='MEMBERSHIP_CODE_REDEEMED'
            ).exists()
        )

    def test_redeem_coach_assigns_head_coach_role(self):
        self._make_code()

        ok, membership, _ = redeem_activation_code(self.coach, 'ABC-123')

        self.assertTrue(ok)
        self.assertEqual(membership.role, 'HEAD_COACH')

    def test_redeem_expired_code(self):
        self._make_code(expires_at=timezone.now() - timedelta(days=1))

        ok, membership, err = redeem_activation_code(self.athlete, 'ABC-123')

        self.assertFalse(ok)
        self.assertIsNone(membership)
        self.assertIn('scaduto', err.lower())
        self.assertFalse(Membership.objects.exists())

    def test_redeem_exhausted_code(self):
        self._make_code(max_uses=2, current_uses=2)

        ok, membership, err = redeem_activation_code(self.athlete, 'ABC-123')

        self.assertFalse(ok)
        self.assertIsNone(membership)
        self.assertIn('esaurito', err.lower())
        self.assertFalse(Membership.objects.exists())

    def test_redeem_invalid_code(self):
        ok, membership, err = redeem_activation_code(self.athlete, 'NOPE')

        self.assertFalse(ok)
        self.assertIsNone(membership)
        self.assertIsNotNone(err)

    def test_redeem_idempotent_double_post(self):
        code = self._make_code()

        ok1, m1, _ = redeem_activation_code(self.athlete, 'ABC-123')
        ok2, m2, _ = redeem_activation_code(self.athlete, 'ABC-123')

        self.assertTrue(ok1 and ok2)
        self.assertEqual(m1.pk, m2.pk)
        self.assertEqual(Membership.objects.filter(user=self.athlete).count(), 1)

        code.refresh_from_db()
        self.assertEqual(code.current_uses, 1)

    # ── request_manual_membership ───────────────────────────────

    def test_request_manual_creates_pending(self):
        ok, req, err = request_manual_membership(self.athlete, self.team.id)

        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertEqual(req.status, 'PENDING')
        self.assertEqual(req.role, 'PLAYER')
        self.assertEqual(req.team, self.team)
        self.assertEqual(req.society, self.society)

        self.assertTrue(
            AuditLog.objects.filter(
                user=self.athlete, action='MEMBERSHIP_REQUESTED'
            ).exists()
        )

    def test_request_manual_unknown_team(self):
        ok, req, err = request_manual_membership(self.athlete, 999999)

        self.assertFalse(ok)
        self.assertIsNone(req)
        self.assertIsNotNone(err)

    def test_request_manual_idempotent_double_post(self):
        ok1, r1, _ = request_manual_membership(self.athlete, self.team.id)
        ok2, r2, _ = request_manual_membership(self.athlete, self.team.id)

        self.assertTrue(ok1 and ok2)
        self.assertEqual(r1.pk, r2.pk)
        self.assertEqual(
            MembershipRequest.objects.filter(user=self.athlete, team=self.team).count(),
            1,
        )

    def test_request_manual_coach_role(self):
        ok, req, _ = request_manual_membership(self.coach, self.team.id)

        self.assertTrue(ok)
        self.assertEqual(req.role, 'HEAD_COACH')
