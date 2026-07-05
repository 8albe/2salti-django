import re

from django.core import mail
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import Season, Sport, Society, Team, League
from management.models import ActivationCode, Membership, MembershipRequest
import datetime
from django.utils import timezone

User = get_user_model()


def _extract_verify_link(email_body):
    """Estrae il path /accounts/verify-email/<token>/ dal corpo dell'email
    (stesso pattern usato per il link di certificazione genitore)."""
    match = re.search(r'(/accounts/verify-email/[^\s]+/)', email_body)
    return match.group(1) if match else None


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
            last_name='Athlete',
            email='test_athlete@example.com',
        )

    def test_onboarding_redirection_flow(self):
        """Verifica che l'utente venga rediretto correttamente attraverso i vari step"""
        self.client.login(username='test_athlete', password='password123')

        # 1. Accesso a dashboard -> Redirezione a Identity
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('verify_identity'))

        # 2. Reinvio email di conferma (verify_identity POST = reinvio, non più mock)
        response = self.client.post(reverse('verify_identity'))
        self.assertRedirects(response, reverse('verify_identity'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.user.email, mail.outbox[0].to)

        # 3. Click sul link ricevuto via email -> Identity verificata
        link = _extract_verify_link(mail.outbox[0].body)
        self.assertIsNotNone(link)
        response = self.client.get(link)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.identity_status, 'VERIFIED')

        # 4. Accesso a dashboard -> Redirezione a Setup Wizard (step pagamento
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

    def test_verify_email_link_not_redirected_by_middleware(self):
        # /accounts/verify-email/<token>/ è a path variabile: il match esatto
        # di allowed_urls non basta, serve l'esenzione per prefisso.
        from accounts.services.email_verification import make_token

        self.user.email = 'test_onb@example.com'
        self.user.save()
        token = make_token(self.user)

        response = self.client.get(reverse('verify_email', args=[token]))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Location', response)


class VerifyEmailViewTest(TestCase):
    """Copertura a livello view del click sul link di verifica: scaduto,
    manomesso, idempotente sul già-verificato."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='verify_target', password='password123', role='athlete',
            email='verify_target@example.com',
        )

    def test_valid_token_verifies_identity(self):
        from accounts.services.email_verification import make_token

        token = make_token(self.user)
        response = self.client.get(reverse('verify_email', args=[token]))
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.identity_status, 'VERIFIED')
        self.assertIsNotNone(self.user.identity_verified_at)

    def test_already_verified_is_idempotent(self):
        from accounts.services.email_verification import make_token
        from management.models import AuditLog

        token = make_token(self.user)
        self.client.get(reverse('verify_email', args=[token]))
        first_verified_at = User.objects.get(pk=self.user.pk).identity_verified_at

        # Secondo click sullo stesso link valido: nessun errore, nessun nuovo
        # audit log, il timestamp di verifica non si sposta.
        response = self.client.get(reverse('verify_email', args=[token]))
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.identity_status, 'VERIFIED')
        self.assertEqual(self.user.identity_verified_at, first_verified_at)
        self.assertEqual(
            AuditLog.objects.filter(action='ONBOARDING_IDENTITY_VERIFIED', user=self.user).count(), 1,
        )

    def test_expired_token_shows_error_page(self):
        # La scadenza è coperta a livello service (tests_email_verification,
        # max_age negativo). Qui si verifica solo che la view propaghi
        # correttamente l'esito 'expired' del service alla pagina d'errore.
        from unittest.mock import patch

        with patch('accounts.services.email_verification.verify_token', return_value=(False, None, 'expired')):
            response = self.client.get(reverse('verify_email', args=['whatever-token']))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "scaduto", status_code=400)

    def test_tampered_token_shows_error_page(self):
        from accounts.services.email_verification import make_token

        token = make_token(self.user)
        tampered = token[:-1] + ('a' if token[-1] != 'a' else 'b')
        response = self.client.get(reverse('verify_email', args=[tampered]))
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.identity_status, 'UNVERIFIED')


class SignupHoneypotTest(TestCase):
    """Honeypot anti-bot su SignUpForm (debito B3): un campo nascosto che un
    utente umano non compila mai."""

    def _signup_payload(self, **overrides):
        payload = {
            'username': 'honeypot_test_user',
            'email': 'honeypot_test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'role': 'athlete',
            'password1': 'S0me-Str0ng-Pass!',
            'password2': 'S0me-Str0ng-Pass!',
        }
        payload.update(overrides)
        return payload

    def test_signup_without_honeypot_succeeds(self):
        response = self.client.post(reverse('signup'), self._signup_payload())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='honeypot_test_user').exists())

    def test_signup_with_honeypot_filled_is_rejected(self):
        response = self.client.post(reverse('signup'), self._signup_payload(website='http://spam.example'))
        self.assertEqual(response.status_code, 200)  # form non valido, ri-renderizzato
        self.assertFalse(User.objects.filter(username='honeypot_test_user').exists())


class SignupEmailUniquenessTest(TestCase):
    """Constraint email unique case-insensitive su User (debito B1): il form
    deve rifiutare un duplicato con un errore di validazione, non un 500 da
    IntegrityError; i 58 seed a email vuota restano fuori dal vincolo."""

    def setUp(self):
        User.objects.create_user(
            username='existing_user',
            email='Existing@Example.com',
            password='password123',
            role='athlete',
        )

    def _signup_payload(self, **overrides):
        payload = {
            'username': 'new_user',
            'email': 'newuser@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'role': 'athlete',
            'password1': 'S0me-Str0ng-Pass!',
            'password2': 'S0me-Str0ng-Pass!',
        }
        payload.update(overrides)
        return payload

    def test_signup_with_new_email_succeeds(self):
        response = self.client.post(reverse('signup'), self._signup_payload())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='new_user').exists())

    def test_signup_with_duplicate_email_is_form_error_not_500(self):
        response = self.client.post(
            reverse('signup'), self._signup_payload(email='existing@example.com')
        )
        self.assertEqual(response.status_code, 200)  # form non valido, ri-renderizzato
        self.assertFalse(User.objects.filter(username='new_user').exists())
        self.assertFormError(
            response.context['form'], 'email', "Questa email è già registrata."
        )

    def test_signup_with_duplicate_email_different_case_is_rejected(self):
        response = self.client.post(
            reverse('signup'), self._signup_payload(email='EXISTING@EXAMPLE.COM')
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='new_user').exists())

    def test_multiple_empty_emails_do_not_violate_constraint(self):
        """I 58 seed a email vuota: il partial index li esclude dal vincolo."""
        User.objects.create_user(username='seed_a', email='', password='x', role='athlete')
        User.objects.create_user(username='seed_b', email='', password='x', role='athlete')
        self.assertTrue(User.objects.filter(username__in=['seed_a', 'seed_b']).count() == 2)
