from django.core import mail
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from accounts.services.email_verification import (
    make_token,
    verify_token,
    EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS,
)

User = get_user_model()


class EmailVerificationTokenTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='token_user', password='password123', role='athlete',
            email='token_user@example.com',
        )

    def test_valid_token_resolves_to_user(self):
        token = make_token(self.user)
        ok, user, error = verify_token(token)
        self.assertTrue(ok)
        self.assertEqual(user.pk, self.user.pk)
        self.assertIsNone(error)

    def test_expired_token_is_rejected(self):
        token = make_token(self.user)
        # max_age negativo forza la scadenza immediata, senza serve dormire.
        ok, user, error = verify_token(token, max_age=-1)
        self.assertFalse(ok)
        self.assertIsNone(user)
        self.assertEqual(error, 'expired')

    def test_tampered_token_is_rejected(self):
        token = make_token(self.user)
        tampered = token[:-1] + ('a' if token[-1] != 'a' else 'b')
        ok, user, error = verify_token(tampered)
        self.assertFalse(ok)
        self.assertIsNone(user)
        self.assertEqual(error, 'invalid')

    def test_token_invalid_after_email_change(self):
        token = make_token(self.user)
        self.user.email = 'changed@example.com'
        self.user.save()
        ok, user, error = verify_token(token)
        self.assertFalse(ok)
        self.assertIsNone(user)
        self.assertEqual(error, 'invalid')


class VerifyIdentityResendThrottleTest(TestCase):
    """Cooldown session-based sul reinvio POST di verify_identity (debito B2)."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='throttle_user', password='password123', role='athlete',
            email='throttle_user@example.com',
        )
        self.client.login(username='throttle_user', password='password123')

    def test_first_resend_sends_email(self):
        response = self.client.post(reverse('verify_identity'))
        self.assertRedirects(response, reverse('verify_identity'))
        self.assertEqual(len(mail.outbox), 1)

    def test_second_resend_within_cooldown_is_blocked(self):
        self.client.post(reverse('verify_identity'))
        self.assertEqual(len(mail.outbox), 1)

        response = self.client.post(reverse('verify_identity'), follow=True)
        self.assertEqual(len(mail.outbox), 1)  # nessuna nuova email inviata
        messages = list(response.context['messages'])
        self.assertTrue(any('secondi' in str(m) for m in messages))

    def test_resend_allowed_again_after_cooldown_elapses(self):
        self.client.post(reverse('verify_identity'))
        self.assertEqual(len(mail.outbox), 1)

        session = self.client.session
        session['verify_email_last_sent'] = (
            timezone.now().timestamp() - EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS - 1
        )
        session.save()

        response = self.client.post(reverse('verify_identity'))
        self.assertRedirects(response, reverse('verify_identity'))
        self.assertEqual(len(mail.outbox), 2)
