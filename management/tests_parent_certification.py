"""Test Macro 7b: ParentCertification — macchina a stati, service email,
endpoint click pubblico, gate helper is_certified_parent_of."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Season, Society, Sport, Team
from management.models import Membership, ParentCertification
from management.services import certification_service as svc

User = get_user_model()


class CertBase(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.society = Society.objects.create(
            name="Pro Recco", slug="pro-recco", sport=self.sport,
            city="Recco", email="club@prorecco.example",
        )
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.team = Team.objects.create(society=self.society)
        # Utenti onboardati (COMPLETED) così il middleware onboarding non
        # redirige le richieste client nei test di vista.
        self.parent = User.objects.create_user(
            username='genitore', password='pw', role='fan',
            first_name='Mario', last_name='Rossi', email='mario@example.com',
            identity_status='VERIFIED', setup_completed=True,
        )
        self.child = User.objects.create_user(
            username='figlio', password='pw', role='athlete',
            first_name='Luca', last_name='Rossi',
            identity_status='VERIFIED', subscription_status='ACTIVE',
            setup_completed=True,
        )
        # Tesseramento PLAYER del figlio nella stagione corrente.
        self.membership = Membership.objects.create(
            user=self.child, society=self.society, team=self.team,
            role='PLAYER', season=self.season, is_active=True,
        )


class RequestCertificationTest(CertBase):
    def test_richiesta_crea_cert_e_invia_email_societa(self):
        ok, cert, err = svc.request_certification(self.parent, self.child)
        self.assertTrue(ok, err)
        self.assertEqual(cert.status, ParentCertification.Status.IN_ATTESA_SOCIETA)
        self.assertEqual(cert.society, self.society)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('club@prorecco.example', mail.outbox[0].to)

    def test_richiesta_figlio_non_atleta_rifiutata(self):
        other = User.objects.create_user(username='nofan', password='pw', role='fan')
        ok, cert, err = svc.request_certification(self.parent, other)
        self.assertFalse(ok)
        self.assertIsNone(cert)

    def test_richiesta_senza_tesseramento_corrente_rifiutata(self):
        self.membership.is_active = False
        self.membership.save()
        ok, cert, err = svc.request_certification(self.parent, self.child)
        self.assertFalse(ok)
        self.assertIsNone(cert)
        self.assertEqual(len(mail.outbox), 0)

    def test_richiesta_duplicata_aperta_rifiutata(self):
        svc.request_certification(self.parent, self.child)
        ok, cert, err = svc.request_certification(self.parent, self.child)
        self.assertFalse(ok)
        self.assertEqual(ParentCertification.objects.filter(
            parent=self.parent, child=self.child).count(), 1)


class StateMachineTest(CertBase):
    def _fresh(self):
        return ParentCertification.objects.create(
            parent=self.parent, child=self.child, society=self.society,
            status=ParentCertification.Status.RICHIESTA_INVIATA,
        )

    def test_percorso_felice_completo(self):
        c = self._fresh()
        c.mark_in_attesa_societa()
        self.assertEqual(c.status, ParentCertification.Status.IN_ATTESA_SOCIETA)
        c.conferma_societa()
        self.assertEqual(c.status, ParentCertification.Status.CONFERMATA_SOCIETA)
        self.assertTrue(c.token)
        self.assertIsNotNone(c.token_expires_at)
        c.mark_in_attesa_click()
        self.assertEqual(c.status, ParentCertification.Status.IN_ATTESA_CLICK_GENITORE)
        c.certifica_via_click()
        self.assertEqual(c.status, ParentCertification.Status.CERTIFICATA)
        self.assertIsNotNone(c.certified_at)

    def test_rifiuto_societa(self):
        c = self._fresh()
        c.mark_in_attesa_societa()
        c.rifiuta_societa()
        self.assertEqual(c.status, ParentCertification.Status.RIFIUTATA)
        self.assertTrue(c.is_final)

    def test_scadenza(self):
        c = self._fresh()
        c.mark_in_attesa_societa()
        c.conferma_societa()
        c.mark_in_attesa_click()
        c.scadi()
        self.assertEqual(c.status, ParentCertification.Status.SCADUTA)
        self.assertTrue(c.is_final)

    def test_transizione_invalida_alza_valueerror(self):
        c = self._fresh()
        with self.assertRaises(ValueError):
            c.conferma_societa()  # da RICHIESTA_INVIATA non si può confermare
        with self.assertRaises(ValueError):
            c.certifica_via_click()  # idem

    def test_click_su_link_scaduto_alza_valueerror(self):
        c = self._fresh()
        c.mark_in_attesa_societa()
        c.conferma_societa()
        c.mark_in_attesa_click()
        c.token_expires_at = timezone.now() - timedelta(hours=1)
        c.save(update_fields=['token_expires_at'])
        with self.assertRaises(ValueError):
            c.certifica_via_click()


class ServiceConfirmRejectTest(CertBase):
    def test_confirm_invia_link_e_porta_in_attesa_click(self):
        _, cert, _ = svc.request_certification(self.parent, self.child)
        mail.outbox.clear()
        ok, cert, err = svc.confirm_certification(cert)
        self.assertTrue(ok, err)
        self.assertEqual(cert.status, ParentCertification.Status.IN_ATTESA_CLICK_GENITORE)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('mario@example.com', mail.outbox[0].to)
        self.assertIn(cert.token, mail.outbox[0].body)

    def test_certify_by_token_valido(self):
        _, cert, _ = svc.request_certification(self.parent, self.child)
        svc.confirm_certification(cert)
        ok, cert, err = svc.certify_by_token(cert.token)
        self.assertTrue(ok, err)
        self.assertEqual(cert.status, ParentCertification.Status.CERTIFICATA)

    def test_certify_by_token_scaduto(self):
        _, cert, _ = svc.request_certification(self.parent, self.child)
        svc.confirm_certification(cert)
        cert.token_expires_at = timezone.now() - timedelta(hours=1)
        cert.save(update_fields=['token_expires_at'])
        ok, cert, err = svc.certify_by_token(cert.token)
        self.assertFalse(ok)
        self.assertEqual(cert.status, ParentCertification.Status.SCADUTA)

    def test_certify_by_token_invalido(self):
        ok, cert, err = svc.certify_by_token('inesistente')
        self.assertFalse(ok)
        self.assertIsNone(cert)


class GateHelperTest(CertBase):
    def test_is_certified_parent_of(self):
        self.assertFalse(self.parent.is_certified_parent_of(self.child))
        _, cert, _ = svc.request_certification(self.parent, self.child)
        svc.confirm_certification(cert)
        svc.certify_by_token(cert.token)
        self.assertTrue(self.parent.is_certified_parent_of(self.child))

    def test_gate_falso_per_altri_atleti(self):
        other = User.objects.create_user(username='altro', password='pw', role='athlete')
        self.assertFalse(self.parent.is_certified_parent_of(other))
        self.assertFalse(self.parent.is_certified_parent_of(None))


class PublicEndpointTest(CertBase):
    def setUp(self):
        super().setUp()
        self.client = Client()

    def _cert_in_attesa_click(self):
        _, cert, _ = svc.request_certification(self.parent, self.child)
        svc.confirm_certification(cert)
        return cert

    def test_endpoint_click_valido_certifica(self):
        cert = self._cert_in_attesa_click()
        resp = self.client.get(reverse('certify_parent', args=[cert.token]))
        self.assertEqual(resp.status_code, 200)
        cert.refresh_from_db()
        self.assertEqual(cert.status, ParentCertification.Status.CERTIFICATA)

    def test_endpoint_click_scaduto(self):
        cert = self._cert_in_attesa_click()
        cert.token_expires_at = timezone.now() - timedelta(hours=1)
        cert.save(update_fields=['token_expires_at'])
        resp = self.client.get(reverse('certify_parent', args=[cert.token]))
        self.assertEqual(resp.status_code, 400)
        cert.refresh_from_db()
        self.assertEqual(cert.status, ParentCertification.Status.SCADUTA)

    def test_endpoint_token_invalido(self):
        resp = self.client.get(reverse('certify_parent', args=['xxx']))
        self.assertEqual(resp.status_code, 400)


class SocietyViewTest(CertBase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.president = User.objects.create_user(
            username='presidente', password='pw', role='president',
            identity_status='VERIFIED', subscription_status='ACTIVE',
            setup_completed=True,
        )
        # President COMPLETED richiede una società gestita.
        pp = self.president.president_profile
        pp.managed_society = self.society
        pp.save()
        Membership.objects.create(
            user=self.president, society=self.society, team=None,
            role='PRESIDENT', season=self.season, is_active=True,
        )

    def test_lista_e_conferma_da_societa(self):
        _, cert, _ = svc.request_certification(self.parent, self.child)
        mail.outbox.clear()
        self.client.login(username='presidente', password='pw')

        resp = self.client.get(reverse('parent_certifications_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(cert, list(resp.context['pending_certifications']))

        resp = self.client.post(reverse('confirm_parent_certification', args=[cert.id]))
        self.assertEqual(resp.status_code, 302)
        cert.refresh_from_db()
        self.assertEqual(cert.status, ParentCertification.Status.IN_ATTESA_CLICK_GENITORE)

    def test_rifiuto_da_societa(self):
        _, cert, _ = svc.request_certification(self.parent, self.child)
        self.client.login(username='presidente', password='pw')
        resp = self.client.post(reverse('reject_parent_certification', args=[cert.id]))
        self.assertEqual(resp.status_code, 302)
        cert.refresh_from_db()
        self.assertEqual(cert.status, ParentCertification.Status.RIFIUTATA)


class ParentRequestViewTest(CertBase):
    def setUp(self):
        super().setUp()
        self.client = Client()

    def test_genitore_invia_richiesta_via_vista(self):
        self.client.login(username='genitore', password='pw')
        resp = self.client.post(reverse('request_certification'), {'child_id': self.child.id})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ParentCertification.objects.filter(
            parent=self.parent, child=self.child).exists())

    def test_non_fan_negato(self):
        self.client.login(username='figlio', password='pw')
        resp = self.client.get(reverse('request_certification'))
        self.assertEqual(resp.status_code, 403)
