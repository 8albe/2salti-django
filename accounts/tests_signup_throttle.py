"""Rate-limit IP-based sul signup (OPS_RUNBOOK §10.16).

Cap 5 tentativi POST / 10 minuti per IP, errore soft (messaggio + ri-render,
mai 500). Finestra sliding su lista timestamp in cache; con LocMemCache il
conteggio è per-process (best-effort, documentato nel service). La cache è
condivisa tra i test dello stesso run: setUp/tearDown la puliscono.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.services.signup_throttle import (
    SIGNUP_THROTTLE_CACHE_PREFIX,
    SIGNUP_THROTTLE_MAX_ATTEMPTS,
    SIGNUP_THROTTLE_WINDOW_SECONDS,
)

User = get_user_model()

# Il test client Django presenta REMOTE_ADDR=127.0.0.1 (nessun X-Forwarded-For)
THROTTLE_KEY = f'{SIGNUP_THROTTLE_CACHE_PREFIX}:127.0.0.1'


class SignupThrottleTest(TestCase):

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _signup_payload(self, n=0, **overrides):
        payload = {
            'username': f'throttle_signup_user_{n}',
            'email': f'throttle_signup_{n}@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'role': 'athlete',
            'password1': 'S0me-Str0ng-Pass!',
            'password2': 'S0me-Str0ng-Pass!',
        }
        payload.update(overrides)
        return payload

    def _burn_attempts(self, count):
        """Consuma tentativi con POST invalidi (password mismatch): contano
        come tentativi ma non creano utenti né sessioni loggate."""
        for i in range(count):
            self.client.post(
                reverse('signup'),
                self._signup_payload(n=i, password2='non-corrisponde'),
            )

    def test_sixth_attempt_within_window_is_blocked(self):
        self._burn_attempts(SIGNUP_THROTTLE_MAX_ATTEMPTS)

        response = self.client.post(reverse('signup'), self._signup_payload(n=99))
        self.assertEqual(response.status_code, 200)  # errore soft, mai 500
        self.assertFalse(
            User.objects.filter(username='throttle_signup_user_99').exists()
        )
        messages = list(response.context['messages'])
        self.assertTrue(any('Troppi tentativi' in str(m) for m in messages))

    def test_attempts_under_cap_are_not_blocked(self):
        self._burn_attempts(SIGNUP_THROTTLE_MAX_ATTEMPTS - 1)

        response = self.client.post(reverse('signup'), self._signup_payload(n=99))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            User.objects.filter(username='throttle_signup_user_99').exists()
        )

    def test_unblocked_after_window_expires(self):
        self._burn_attempts(SIGNUP_THROTTLE_MAX_ATTEMPTS)

        # Simula lo scorrere della finestra: tutti i tentativi registrati
        # risultano più vecchi di WINDOW_SECONDS (stesso stile del test
        # cooldown resend in tests_email_verification).
        expired_ts = timezone.now().timestamp() - SIGNUP_THROTTLE_WINDOW_SECONDS - 1
        cache.set(
            THROTTLE_KEY,
            [expired_ts] * SIGNUP_THROTTLE_MAX_ATTEMPTS,
            timeout=SIGNUP_THROTTLE_WINDOW_SECONDS,
        )

        response = self.client.post(reverse('signup'), self._signup_payload(n=99))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            User.objects.filter(username='throttle_signup_user_99').exists()
        )

    def test_honeypot_stays_independent_of_throttle(self):
        # Sotto cap: l'honeypot rifiuta comunque (form invalido, nessun utente)
        response = self.client.post(
            reverse('signup'),
            self._signup_payload(n=0, website='http://spam.example'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            User.objects.filter(username='throttle_signup_user_0').exists()
        )

        # E un utente legittimo dallo stesso IP, ancora sotto cap, passa
        response = self.client.post(reverse('signup'), self._signup_payload(n=1))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            User.objects.filter(username='throttle_signup_user_1').exists()
        )
