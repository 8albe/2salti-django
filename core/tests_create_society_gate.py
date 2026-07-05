from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Society, Sport

User = get_user_model()


class CreateSocietyStaffOnlyGateTest(TestCase):
    """Gate ramo CREATE di create_society (debito B4): il self-service passa
    da /society/choose/ (personificazione); CREATE resta strumento operativo
    riservato allo staff."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")

    def test_non_staff_president_without_society_is_redirected_to_choose(self):
        User.objects.create_user(username='prez_no_soc', password='pwd', role='president')
        self.client.login(username='prez_no_soc', password='pwd')

        response = self.client.get(reverse('create_society'))

        self.assertRedirects(response, reverse('choose_society'))

    def test_president_with_managed_society_can_refine(self):
        society = Society.objects.create(name="Zero9", slug="zero9", sport=self.sport)
        prez = User.objects.create_user(username='prez_refine', password='pwd', role='president')
        prez.president_profile.managed_society = society
        prez.president_profile.save()
        self.client.login(username='prez_refine', password='pwd')

        response = self.client.get(reverse('create_society'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_refine'])

    def test_staff_president_without_society_can_create(self):
        User.objects.create_user(
            username='prez_staff', password='pwd', role='president', is_staff=True,
        )
        self.client.login(username='prez_staff', password='pwd')

        response = self.client.get(reverse('create_society'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_refine'])

    def test_redirect_to_choose_society_does_not_bounce_back(self):
        """Verifica assenza di redirect-loop: choose_society deve RENDERIZZARE
        (200), non rimbalzare di nuovo verso create_society."""
        User.objects.create_user(username='prez_loop', password='pwd', role='president')
        self.client.login(username='prez_loop', password='pwd')

        response = self.client.get(reverse('create_society'), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [(reverse('choose_society'), 302)])
