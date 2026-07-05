from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Society, Sport
from management.services.president_personification import (
    societies_for_personification,
)

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

    def test_superuser_without_society_passes_gate(self):
        User.objects.create_user(
            username='prez_super', password='pwd', role='president',
            is_superuser=True,
        )
        self.client.login(username='prez_super', password='pwd')

        response = self.client.get(reverse('create_society'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_refine'])

    def test_staff_create_does_not_attach_society_to_operator(self):
        """Consolidamento opzione A: il ramo CREATE è uno strumento staff
        side-effect-free sull'operatore — la società creata NON viene
        agganciata al suo president_profile e il suo setup_completed resta
        invariato (strumento riusabile dallo stesso account)."""
        staff = User.objects.create_user(
            username='prez_staff_post', password='pwd', role='president',
            is_staff=True,
        )
        self.client.login(username='prez_staff_post', password='pwd')

        response = self.client.post(reverse('create_society'), {
            'name': 'Società Onboardata',
            'sport': self.sport.pk,
            'city': 'Milano',
            'email': 'info@societaonboardata.it',
        })

        society = Society.objects.get(name='Società Onboardata')
        self.assertRedirects(
            response, reverse('society_detail', kwargs={'slug': society.slug}),
        )
        self.assertTrue(society.setup_completed)
        self.assertEqual(society.teams.count(), 1)

        staff.refresh_from_db()
        staff.president_profile.refresh_from_db()
        self.assertIsNone(staff.president_profile.managed_society)
        self.assertFalse(staff.setup_completed)

    def test_staff_created_society_is_personifiable(self):
        """La società creata dallo staff (ha una squadra) deve comparire nella
        lista di personificazione: è il canale con cui il presidente reale la
        rivendica via choose_society."""
        User.objects.create_user(
            username='prez_staff_pers', password='pwd', role='president',
            is_staff=True,
        )
        self.client.login(username='prez_staff_pers', password='pwd')

        self.client.post(reverse('create_society'), {
            'name': 'Società Personificabile',
            'sport': self.sport.pk,
            'city': 'Roma',
            'email': 'info@societapersonificabile.it',
        })

        society = Society.objects.get(name='Società Personificabile')
        self.assertIn(society, societies_for_personification())

    def test_redirect_to_choose_society_does_not_bounce_back(self):
        """Verifica assenza di redirect-loop: choose_society deve RENDERIZZARE
        (200), non rimbalzare di nuovo verso create_society."""
        User.objects.create_user(username='prez_loop', password='pwd', role='president')
        self.client.login(username='prez_loop', password='pwd')

        response = self.client.get(reverse('create_society'), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [(reverse('choose_society'), 302)])
