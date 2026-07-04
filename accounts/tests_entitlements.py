"""Test del gating premium (Macro gating premium).

Copre: property fonte-di-verità (is_premium / is_club_pro), il seam
entitlement_service (cambia campo + scrive AuditLog con source), e — nei
commit successivi — la data migration di decoupling e il gating di
api_ai_query. Nessuna chiamata di rete: il motore AI è mockato.
"""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase
from django.db.migrations.executor import MigrationExecutor
from django.db import connection

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


class EntitlementAdminActionTests(TestCase):
    """Le admin action instradano nel seam (cambio campo + audit), niente bypass."""

    def setUp(self):
        from django.test import RequestFactory
        from django.contrib.messages.storage.fallback import FallbackStorage
        self.admin_user = User.objects.create_superuser(username='admin_e', password='x')
        self.target = User.objects.create_user(username='target_e', role='athlete')
        self.request = RequestFactory().post('/admin/')
        self.request.user = self.admin_user
        # messages framework richiede uno storage sul request
        setattr(self.request, 'session', {})
        setattr(self.request, '_messages', FallbackStorage(self.request))

    def test_attiva_premium_action_uses_seam(self):
        from accounts.admin import CustomUserAdmin
        from django.contrib.admin.sites import AdminSite
        ma = CustomUserAdmin(User, AdminSite())
        ma.attiva_premium(self.request, User.objects.filter(pk=self.target.pk))
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_premium)
        log = AuditLog.objects.get(action='ENTITLEMENT_PLAN_GRANTED')
        self.assertEqual(log.details['source'], 'admin')
        self.assertEqual(log.user, self.admin_user)  # actor tracciato

    def test_disattiva_premium_action_uses_seam(self):
        from accounts.admin import CustomUserAdmin
        from django.contrib.admin.sites import AdminSite
        entitlement_service.grant_premium(self.target, source='admin')
        ma = CustomUserAdmin(User, AdminSite())
        ma.disattiva_premium(self.request, User.objects.filter(pk=self.target.pk))
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_premium)
        self.assertTrue(AuditLog.objects.filter(action='ENTITLEMENT_PLAN_REVOKED').exists())


class AiQueryGatingTests(TestCase):
    """Gating di api_ai_query: anonimo→login, freemium→403, premium→200.

    Usa utenti fan pienamente onboardati (identity VERIFIED + setup done → stato
    COMPLETED) così l'OnboardingMiddleware non intercetta. Nessuna rete: il motore
    AI è mockato per il caso premium.
    """

    # Entrambe le rotte montano la stessa view decorata (matches/urls + api_urls).
    ROUTES = ['/api/v1/ai-query/', '/matches/api/v1/ai-query/']

    def _fan(self, username, **kwargs):
        return User.objects.create_user(
            username=username, password='x', role='fan',
            identity_status='VERIFIED', setup_completed=True, **kwargs,
        )

    def test_anonymous_redirected_to_login(self):
        for route in self.ROUTES:
            resp = self.client.post(route, data='{"query":"x"}',
                                    content_type='application/json')
            self.assertEqual(resp.status_code, 302)
            self.assertIn('login', resp['Location'])

    def test_freemium_gets_403_premium_required_both_routes(self):
        self._fan('fan_free')
        self.client.login(username='fan_free', password='x')
        for route in self.ROUTES:
            resp = self.client.post(route, data='{"query":"x"}',
                                    content_type='application/json')
            self.assertEqual(resp.status_code, 403, route)
            self.assertEqual(resp.json()['error'], 'premium_required', route)

    def test_premium_reaches_engine_200(self):
        from unittest import mock
        self._fan('fan_premium', plan=User.Plan.PREMIUM)
        self.client.login(username='fan_premium', password='x')
        fake_engine = mock.Mock()
        fake_engine.process_query.return_value = {'text': 'ok', 'data': {}}
        with mock.patch('matches.api_views.AIStatsEngine', return_value=fake_engine):
            resp = self.client.post('/api/v1/ai-query/', data='{"query":"gol di Rossi"}',
                                    content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['text'], 'ok')
        fake_engine.process_query.assert_called_once()


class DecoupleDataMigrationTest(TransactionTestCase):
    """Data migration 0010: subscription_status ACTIVE -> onboarding_payment_done,
    plan resta FREEMIUM per tutti (nessun premium regalato). Reverse esplicito.

    Segue il pattern di management.tests_migrations_membership_season: rewind con
    MigrationExecutor, crea fixture con lo stato storico, poi migra forward.
    """

    migrate_from = [('accounts', '0009_plan_onboarding_db_default')]
    migrate_to = [('accounts', '0010_decouple_onboarding_payment')]

    def tearDown(self):
        # Riporta il DB di test condiviso allo stato head (le migration girano fuori
        # transazione su SQLite; TransactionTestCase non fa rollback dello schema).
        call_command('migrate', verbosity=0)

    def test_active_maps_to_payment_done_plan_stays_freemium(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        OldUser = old_apps.get_model('accounts', 'User')
        active = OldUser.objects.create(username='mig_active', role='athlete',
                                        subscription_status='ACTIVE')
        inactive = OldUser.objects.create(username='mig_inactive', role='athlete',
                                          subscription_status='INACTIVE')

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        NewUser = new_apps.get_model('accounts', 'User')
        a = NewUser.objects.get(pk=active.pk)
        i = NewUser.objects.get(pk=inactive.pk)
        self.assertTrue(a.onboarding_payment_done)
        self.assertFalse(i.onboarding_payment_done)
        # Nessun premium regalato dalla data migration.
        self.assertEqual(a.plan, 'FREEMIUM')
        self.assertEqual(i.plan, 'FREEMIUM')
