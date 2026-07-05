from django.test import TestCase
from django.contrib.auth import get_user_model

from accounts.services.email_verification import make_token, verify_token

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
