from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()


class LoginRedirectRegressionTest(TestCase):
    """Anti-regressione del fix ec83e34 (LOGIN_REDIRECT_URL).

    Prima del fix Django usava il default `/accounts/profile/`, che non matcha
    alcuna rotta (esiste solo `profile/<username>/`) e restituiva 404 subito dopo
    il login. Il fix imposta LOGIN_REDIRECT_URL='profile_redirect', il redirect
    role-aware che porta alla dashboard. Questi test bloccano quella regressione.
    """

    def setUp(self):
        self.client = Client()
        # Fan COMPLETED: identita' verificata + setup fatto -> onboarding_state
        # 'COMPLETED' (i fan sono esenti da pagamento e membership), cosi' il
        # middleware di onboarding non intercetta e la dashboard rende 200.
        self.user = User.objects.create_user(
            username='redirect_probe',
            password='password123',
            role='fan',
            identity_status='VERIFIED',
            setup_completed=True,
        )

    def test_login_redirect_url_points_to_role_aware_redirect(self):
        """LOGIN_REDIRECT_URL deve essere il redirect role-aware, non il default rotto."""
        self.assertEqual(settings.LOGIN_REDIRECT_URL, 'profile_redirect')

    def test_post_login_without_next_redirects_to_profile_redirect_not_profile_404(self):
        """Login senza ?next= -> 302 verso profile_redirect, mai verso /accounts/profile/."""
        response = self.client.post(
            reverse('login'),
            {'username': 'redirect_probe', 'password': 'password123'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('profile_redirect'))
        # Il default Django rotto non deve piu' comparire.
        self.assertNotEqual(response.url, '/accounts/profile/')

    def test_post_login_lands_on_dashboard(self):
        """Seguendo i redirect, l'utente atterra sulla dashboard (200), non su un 404."""
        response = self.client.post(
            reverse('login'),
            {'username': 'redirect_probe', 'password': 'password123'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        # La pagina finale e' la dashboard.
        self.assertEqual(response.request['PATH_INFO'], reverse('dashboard'))
        # Nessuna tappa della catena di redirect tocca il default rotto.
        chain_paths = [url for url, _status in response.redirect_chain]
        self.assertNotIn('/accounts/profile/', chain_paths)
        self.assertIn(reverse('profile_redirect'), chain_paths)
