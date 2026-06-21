"""Test Macro 7a: FanProfile (signal + backfill idempotente) e multi-follow."""
import importlib

from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import FanProfile

User = get_user_model()


class FanProfileSignalTest(TestCase):
    def test_signal_crea_fanprofile_per_nuovo_fan(self):
        user = User.objects.create_user(
            username='fan1', password='pw', role='fan',
            first_name='Mario', last_name='Rossi',
        )
        self.assertTrue(FanProfile.objects.filter(user=user).exists())
        self.assertEqual(user.fan_profile.user_id, user.pk)

    def test_signal_non_crea_fanprofile_per_altri_ruoli(self):
        athlete = User.objects.create_user(username='atl1', password='pw', role='athlete')
        self.assertFalse(FanProfile.objects.filter(user=athlete).exists())

    def test_signal_non_duplica_su_save_successivo(self):
        user = User.objects.create_user(username='fan2', password='pw', role='fan')
        user.city = 'Genova'
        user.save()  # save su utente esistente: created=False, nessun nuovo profilo
        self.assertEqual(FanProfile.objects.filter(user=user).count(), 1)


class FanProfileBackfillTest(TestCase):
    """Idempotenza del backfill: rilanciare la data-migration non duplica."""

    def _run_backfill(self):
        mig = importlib.import_module('accounts.migrations.0007_backfill_fanprofile')
        mig.backfill_fan_profiles(global_apps, None)

    def test_backfill_crea_per_fan_senza_profilo_ed_e_idempotente(self):
        fan = User.objects.create_user(username='fan3', password='pw', role='fan')
        # Simula uno stato pre-7a: il fan esiste senza FanProfile.
        FanProfile.objects.filter(user=fan).delete()
        self.assertFalse(FanProfile.objects.filter(user=fan).exists())

        self._run_backfill()
        self.assertEqual(FanProfile.objects.filter(user=fan).count(), 1)

        # Idempotenza: secondo giro, nessun duplicato.
        self._run_backfill()
        self.assertEqual(FanProfile.objects.filter(user=fan).count(), 1)


class MultiFollowTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.fan = User.objects.create_user(
            username='genitore', password='pw', role='fan',
            identity_status='VERIFIED',
        )
        self.a1 = User.objects.create_user(username='figlio1', password='pw', role='athlete')
        self.a2 = User.objects.create_user(username='figlio2', password='pw', role='athlete')
        self.a3 = User.objects.create_user(username='figlio3', password='pw', role='athlete')

    def test_setup_wizard_segue_piu_atleti(self):
        self.client.login(username='genitore', password='pw')
        resp = self.client.post(reverse('setup_wizard'), {
            'favorite_player_id': [str(self.a1.id), str(self.a2.id)],
        })
        self.assertEqual(resp.status_code, 302)
        self.fan.refresh_from_db()
        self.assertEqual(
            set(self.fan.favorite_players.values_list('id', flat=True)),
            {self.a1.id, self.a2.id},
        )

    def test_edit_profile_aggiorna_insieme_follow(self):
        # Parte da 2 follow, poi via edit ne tiene 1 e ne aggiunge un altro.
        self.fan.favorite_players.set([self.a1, self.a2])
        self.fan.setup_completed = True
        self.fan.save()
        self.client.login(username='genitore', password='pw')
        resp = self.client.post(reverse('edit_profile'), {
            'favorite_player_id': [str(self.a1.id), str(self.a3.id)],
        })
        self.assertEqual(resp.status_code, 302)
        self.fan.refresh_from_db()
        self.assertEqual(
            set(self.fan.favorite_players.values_list('id', flat=True)),
            {self.a1.id, self.a3.id},
        )

    def test_id_non_atleta_ignorato(self):
        other_fan = User.objects.create_user(username='altrofan', password='pw', role='fan')
        self.client.login(username='genitore', password='pw')
        self.client.post(reverse('setup_wizard'), {
            'favorite_player_id': [str(self.a1.id), str(other_fan.id)],
        })
        self.fan.refresh_from_db()
        self.assertEqual(
            set(self.fan.favorite_players.values_list('id', flat=True)),
            {self.a1.id},
        )

    def test_profilo_pubblico_mostra_atleti_seguiti(self):
        self.fan.favorite_players.set([self.a1, self.a2])
        resp = self.client.get(reverse('profile', args=[self.fan.username]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['fan_athletes']), 2)
