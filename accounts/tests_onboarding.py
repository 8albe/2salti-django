from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import Season, Sport, Society, Team, League
from management.models import ActivationCode, Membership, MembershipRequest
import datetime
from django.utils import timezone

User = get_user_model()

class OnboardingFlowTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.society = Society.objects.create(name="Pro Recco", slug="pro-recco", sport=self.sport)
        # Season corrente: dal flip NOT NULL (2d-7) i creation-site la esigono.
        self.season = Season.objects.create(
            sport=self.sport, label='2025/2026', is_current=True
        )
        self.league = League.objects.create(name="Serie A1", sport=self.sport, season='2024-2025')
        self.team = Team.objects.create(society=self.society, league=self.league)
        
        # Utente Atleta da onboardare
        self.user = User.objects.create_user(
            username='test_athlete',
            password='password123',
            role='athlete',
            first_name='Test',
            last_name='Athlete'
        )

    def test_onboarding_redirection_flow(self):
        """Verifica che l'utente venga rediretto correttamente attraverso i vari step"""
        self.client.login(username='test_athlete', password='password123')
        
        # 1. Accesso a dashboard -> Redirezione a Identity
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('verify_identity'))
        
        # 2. Completa Identity
        response = self.client.post(reverse('verify_identity'))
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.identity_status, 'VERIFIED')
        
        # 3. Accesso a dashboard -> Redirezione a Setup Wizard (step pagamento
        # onboarding: differito a Macro 10 pagamenti reali, non blocca più il funnel)
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('setup_wizard'))

    def test_process_payment_redirects_unconditionally(self):
        """/accounts/payment/ non è più uno step: redirige sempre a setup_wizard
        senza mostrare il mock, anche per link/bookmark diretti."""
        self.client.login(username='test_athlete', password='password123')
        self.user.identity_status = 'VERIFIED'
        self.user.save()

        response = self.client.get(reverse('process_payment'))
        self.assertRedirects(response, reverse('setup_wizard'))

    def test_membership_activation_code(self):
        """Verifica l'onboarding con codice di attivazione"""
        self.user.identity_status = 'VERIFIED'
        self.user.onboarding_payment_done = True
        self.user.setup_completed = True
        self.user.save()
        
        self.client.login(username='test_athlete', password='password123')
        
        # Crea codice di attivazione
        code = ActivationCode.objects.create(
            code="RECC-PRO-123",
            society=self.society,
            team=self.team,
            role='PLAYER',
            max_uses=10
        )
        
        # Accesso a dashboard -> Redirezione a Membership
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('onboarding_membership'))
        
        # Usa il codice
        response = self.client.post(reverse('onboarding_membership'), {'activation_code': 'RECC-PRO-123'})
        self.assertRedirects(response, reverse('dashboard'))
        
        # Verifica Membership creata
        self.assertTrue(Membership.objects.filter(user=self.user, society=self.society, team=self.team).exists())
        code.refresh_from_db()
        self.assertEqual(code.current_uses, 1)

    def test_membership_manual_request(self):
        """Verifica l'invio di una richiesta manuale di membership"""
        self.user.identity_status = 'VERIFIED'
        self.user.onboarding_payment_done = True
        self.user.setup_completed = True
        self.user.save()
        
        self.client.login(username='test_athlete', password='password123')
        
        # Invia richiesta manuale per il team
        response = self.client.post(reverse('onboarding_membership'), {'team_id': self.team.id})
        self.assertRedirects(response, reverse('dashboard'))
        
        # Verifica richiesta creata
        self.assertTrue(MembershipRequest.objects.filter(user=self.user, team=self.team, status='PENDING').exists())
        
        # L'utente è in stato COMPLETED perché ha una richiesta pendente (Fase 5.3 spec)
        self.user.refresh_from_db()
        self.assertEqual(self.user.onboarding_state, 'COMPLETED')

    def test_fan_onboarding_skips_payment_and_membership(self):
        """Verifica che un Fan possa saltare pagamento e membership"""
        fan_user = User.objects.create_user(
            username='test_fan',
            password='password123',
            role='fan'
        )
        self.client.login(username='test_fan', password='password123')
        
        # 1. Identity è obbligatoria
        self.assertEqual(fan_user.onboarding_state, 'IDENTITY_PENDING')
        
        # 2. Completa Identity -> Salta a Setup (non Payment)
        fan_user.identity_status = 'VERIFIED'
        fan_user.save()
        self.assertEqual(fan_user.onboarding_state, 'SETUP_PENDING')
        
        # 3. Completa Setup -> Salta a COMPLETED (non Membership)
        fan_user.setup_completed = True
        fan_user.save()
        self.assertEqual(fan_user.onboarding_state, 'COMPLETED')
        
        # Verifica che la dashboard sia accessibile
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)


class OnboardingMiddlewareApiExemptionTest(TestCase):
    """§10.13: le API AJAX sotto /accounts/api/ non devono essere redirette dal
    middleware onboarding, anche senza header XMLHttpRequest. La sentinella
    anti-loop (le pagine protette restano redirette) deve restare intatta."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='test_onb', password='password123', role='athlete',
            first_name='Test', last_name='Onb',
        )
        self.client.login(username='test_onb', password='password123')

    def test_user_is_in_onboarding(self):
        # Presupposto: utente nuovo = onboarding pendente (sentinella attiva).
        self.assertEqual(self.user.onboarding_state, 'IDENTITY_PENDING')

    def test_protected_page_still_redirects(self):
        # Sentinella anti-loop: una pagina protetta resta redirette al funnel.
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('verify_identity'))

    def test_accounts_api_not_redirected_without_ajax_header(self):
        # /accounts/api/ esentato dal prefisso, SENZA header XMLHttpRequest:
        # deve servire la view (200 JSON), non un redirect al funnel.
        response = self.client.get(reverse('api_teams_by_league'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Location', response)
