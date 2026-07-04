"""Macro 18 — Personificazione società da parte del presidente.

Copre: lista società personificabili, creazione richiesta PRESIDENT, guard
1:1 (no IntegrityError), side-effect managed_society senza Membership, email
obbligatoria nel form di rifinitura, isolamento del ramo PRESIDENT dal consumer
president-gated, e no-loop della landing in stato PENDING.
"""
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase
from django.urls import reverse

from core.forms import SocietySetupForm
from core.models import Society, Sport, Team
from core.views import choose_society
from management.models import Membership, MembershipRequest
from management.services.president_personification import (
    approve_president_request,
    request_president_personification,
    societies_for_personification,
)

User = get_user_model()


def _president(username):
    return User.objects.create_user(
        username=username, password="pwd", role="president",
        email=f"{username}@example.com",
        identity_status="VERIFIED", onboarding_payment_done=True,
        setup_completed=False,
    )


class PersonificationServiceTests(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="ZZ Polo Test", slug="zz-polo")
        self.with_team = Society.objects.create(
            name="ZZ Con Squadra", slug="zz-con", sport=self.sport, city="Roma",
        )
        Team.objects.create(society=self.with_team, slug="zz-con-c")
        self.no_team = Society.objects.create(
            name="ZZ Senza Squadra", slug="zz-senza", sport=self.sport, city="Roma",
        )
        self.prez = _president("zz-prez1")

    def test_societies_list_only_with_teams(self):
        qs = societies_for_personification()
        self.assertIn(self.with_team, qs)
        self.assertNotIn(self.no_team, qs)

    def test_societies_list_distinct(self):
        # Seconda squadra sulla stessa società non deve duplicare la riga.
        Team.objects.create(society=self.with_team, slug="zz-con-d")
        qs = list(societies_for_personification())
        self.assertEqual(qs.count(self.with_team), 1)

    def test_request_creates_pending_president(self):
        ok, req, err = request_president_personification(self.prez, self.with_team)
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertEqual(req.role, "PRESIDENT")
        self.assertEqual(req.status, "PENDING")
        self.assertEqual(req.society, self.with_team)

    def test_request_idempotent_when_pending(self):
        request_president_personification(self.prez, self.with_team)
        ok, req, err = request_president_personification(self.prez, self.with_team)
        self.assertTrue(ok)
        self.assertEqual(
            MembershipRequest.objects.filter(
                user=self.prez, role="PRESIDENT").count(), 1)

    def test_request_blocked_if_already_managing(self):
        self.prez.president_profile.managed_society = self.with_team
        self.prez.president_profile.save()
        ok, req, err = request_president_personification(self.prez, self.with_team)
        self.assertFalse(ok)
        self.assertIsNotNone(err)

    def test_approve_sets_managed_society_no_membership(self):
        ok, req, _ = request_president_personification(self.prez, self.with_team)
        ok, err = approve_president_request(req)
        self.assertTrue(ok)
        self.assertIsNone(err)
        req.refresh_from_db()
        self.assertEqual(req.status, "APPROVED")
        self.prez.president_profile.refresh_from_db()
        self.assertEqual(self.prez.president_profile.managed_society, self.with_team)
        # Decisione #2: NESSUNA Membership PRESIDENT creata.
        self.assertEqual(
            Membership.objects.filter(user=self.prez).count(), 0)

    def test_approve_one_to_one_guard_clean_reject(self):
        # La società ha già un presidente: il secondo deve essere respinto
        # pulito, SENZA IntegrityError sul OneToOne.
        first = _president("zz-prez-first")
        first.president_profile.managed_society = self.with_team
        first.president_profile.save()

        _, req, _ = request_president_personification(self.prez, self.with_team)
        ok, err = approve_president_request(req)
        self.assertFalse(ok)
        self.assertIn("già un presidente", err)
        req.refresh_from_db()
        self.assertEqual(req.status, "PENDING")
        self.prez.president_profile.refresh_from_db()
        self.assertIsNone(self.prez.president_profile.managed_society)


class SocietySetupFormEmailTests(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="ZZ Nuoto Test", slug="zz-nuoto")

    def _data(self, **over):
        data = {
            "name": "ZZ Form Soc", "sport": self.sport.id, "city": "Roma",
        }
        data.update(over)
        return data

    def test_email_required(self):
        form = SocietySetupForm(data=self._data())
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_email_present_valid(self):
        form = SocietySetupForm(data=self._data(email="soc@example.com"))
        self.assertTrue(form.is_valid(), form.errors)


class IsolationFromPresidentConsumerTests(TestCase):
    """Il ramo PRESIDENT non deve transitare dal consumer president-gated."""

    def setUp(self):
        self.sport = Sport.objects.create(name="ZZ Iso Test", slug="zz-iso")
        self.society = Society.objects.create(
            name="ZZ Iso Soc", slug="zz-iso-soc", sport=self.sport, city="Roma",
        )
        Team.objects.create(society=self.society, slug="zz-iso-c")
        self.president = _president("zz-iso-prez")
        self.president.setup_completed = True
        self.president.save()
        self.president.president_profile.managed_society = self.society
        self.president.president_profile.save()
        # Richiesta PRESIDENT di un ALTRO utente sulla stessa società.
        self.other = _president("zz-iso-other")
        self.pres_req = MembershipRequest.objects.create(
            user=self.other, society=self.society, role="PRESIDENT", status="PENDING",
        )

    def test_dashboard_excludes_president_requests(self):
        self.client.force_login(self.president)
        resp = self.client.get(reverse("club_admin_dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(self.pres_req, resp.context["membership_requests"])

    def test_approve_membership_404_on_president_request(self):
        self.client.force_login(self.president)
        resp = self.client.post(
            reverse("approve_membership", args=[self.pres_req.id]),
            {"action": "approve"},
        )
        self.assertEqual(resp.status_code, 404)
        # Il guard 1:1 NON è scattato perché la richiesta è inaccessibile:
        # nessun secondo managed_society tentato.
        self.other.president_profile.refresh_from_db()
        self.assertIsNone(self.other.president_profile.managed_society)


class ChooseSocietyNoLoopTests(TestCase):
    """La landing PENDING renderizza (200), non redirige: non alimenta loop."""

    def setUp(self):
        self.rf = RequestFactory()
        self.sport = Sport.objects.create(name="ZZ Loop Test", slug="zz-loop")
        self.society = Society.objects.create(
            name="ZZ Loop Soc", slug="zz-loop-soc", sport=self.sport, city="Roma",
        )
        Team.objects.create(society=self.society, slug="zz-loop-c")
        self.prez = _president("zz-loop-prez")

    def _request(self):
        req = self.rf.get(reverse("choose_society"))
        req.user = self.prez
        req.session = SessionStore()
        req._messages = FallbackStorage(req)
        return req

    def test_pending_renders_status_not_redirect(self):
        request_president_personification(self.prez, self.society)
        resp = choose_society(self._request())
        self.assertEqual(resp.status_code, 200)

    def test_list_renders_when_no_request(self):
        resp = choose_society(self._request())
        self.assertEqual(resp.status_code, 200)
