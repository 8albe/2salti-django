"""Test del gating premium (Macro gating premium).

Copre: property fonte-di-verità (is_premium / is_club_pro), il seam
entitlement_service (cambia campo + scrive AuditLog con source), e — nei
commit successivi — la data migration di decoupling e il gating di
api_ai_query. Nessuna chiamata di rete: il motore AI è mockato.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import Sport, Society
from core.services import entitlement_service
from management.models import AuditLog

User = get_user_model()


class EntitlementPropertyTests(TestCase):
    """Property fonte-di-verità unica per gli entitlement."""

    def test_user_is_premium_default_false(self):
        u = User.objects.create_user(username='u1', role='athlete')
        self.assertEqual(u.plan, User.Plan.FREEMIUM)
        self.assertFalse(u.is_premium)

    def test_user_is_premium_true_when_plan_premium(self):
        u = User.objects.create_user(username='u2', role='athlete', plan=User.Plan.PREMIUM)
        self.assertTrue(u.is_premium)

    def _society(self, **kwargs):
        sport = Sport.objects.create(name='Pallanuoto Test')
        return Society.objects.create(name='S', sport=sport, city='Roma', **kwargs)

    def test_society_is_club_pro_default_false(self):
        s = self._society()
        self.assertEqual(s.tier, Society.Tier.FREE)
        self.assertFalse(s.is_comped)
        self.assertFalse(s.is_club_pro)

    def test_society_is_club_pro_true_when_tier_club_pro(self):
        s = self._society(tier=Society.Tier.CLUB_PRO)
        self.assertTrue(s.is_club_pro)

    def test_society_is_club_pro_true_when_comped_even_if_tier_free(self):
        """is_comped ha precedenza: Club Pro anche con tier=FREE (caso Zero9)."""
        s = self._society(tier=Society.Tier.FREE, is_comped=True)
        self.assertTrue(s.is_club_pro)


class EntitlementSeamTests(TestCase):
    """Il seam cambia il campo e scrive una riga di audit con il source."""

    def setUp(self):
        self.user = User.objects.create_user(username='seam_u', role='athlete')
        self.sport = Sport.objects.create(name='Pallanuoto Seam')
        self.society = Society.objects.create(name='SeamSoc', sport=self.sport, city='Roma')

    def test_grant_premium_sets_plan_and_logs(self):
        entitlement_service.grant_premium(self.user, source='admin')
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_premium)
        log = AuditLog.objects.get(action='ENTITLEMENT_PLAN_GRANTED')
        self.assertEqual(log.details['source'], 'admin')
        self.assertEqual(log.details['from'], 'FREEMIUM')
        self.assertEqual(log.details['to'], 'PREMIUM')

    def test_grant_premium_is_idempotent(self):
        entitlement_service.grant_premium(self.user, source='admin')
        entitlement_service.grant_premium(self.user, source='admin')
        self.assertEqual(AuditLog.objects.filter(action='ENTITLEMENT_PLAN_GRANTED').count(), 1)

    def test_revoke_premium_sets_freemium_and_logs(self):
        entitlement_service.grant_premium(self.user, source='admin')
        entitlement_service.revoke_premium(self.user, source='admin')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_premium)
        self.assertTrue(AuditLog.objects.filter(action='ENTITLEMENT_PLAN_REVOKED').exists())

    def test_set_society_tier_changes_and_logs(self):
        entitlement_service.set_society_tier(self.society, Society.Tier.CLUB_PRO, source='admin')
        self.society.refresh_from_db()
        self.assertEqual(self.society.tier, Society.Tier.CLUB_PRO)
        self.assertTrue(self.society.is_club_pro)
        log = AuditLog.objects.get(action='ENTITLEMENT_SOCIETY_TIER_CHANGED')
        self.assertEqual(log.details['source'], 'admin')

    def test_set_society_comped_changes_and_logs(self):
        entitlement_service.set_society_comped(self.society, True, source='seed_zero9')
        self.society.refresh_from_db()
        self.assertTrue(self.society.is_comped)
        self.assertTrue(self.society.is_club_pro)
        log = AuditLog.objects.get(action='ENTITLEMENT_SOCIETY_COMPED_CHANGED')
        self.assertEqual(log.details['source'], 'seed_zero9')
