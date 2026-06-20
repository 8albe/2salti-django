"""Regression test della bacheca (§10.10).

Copre il caso reale del presidente "de-vincolato": role='president' con
president_profile.managed_society valorizzata e NESSUNA Membership PRESIDENT
stagionale (lo stato prodotto dal flusso reale dal Macro 7). I test esistenti
esercitavano solo presidenti con Membership fixture, quindi la bacheca era a
copertura zero: due bug pre-esistenti (TemplateSyntaxError nel template,
NameError nel ramo team della view) erano latenti.

- test_bacheca_globale_*  → copre la compilazione/rendering del template.
- test_bacheca_team_*      → copre il ramo `if team_slug:` della view.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Society, Sport, Team
from management.models import Membership

User = get_user_model()


class BachecaPresidentNoMembershipTests(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="ZZ Basket Test", slug="zz-basket")
        self.society = Society.objects.create(
            name="ZZ Hoops", slug="zz-hoops", sport=self.sport, city="Milano"
        )
        self.team = Team.objects.create(society=self.society, slug="zz-hoops-senior")
        self.president = User.objects.create_user(
            username="zz-prez", password="pwd", role="president",
            identity_status="VERIFIED", subscription_status="ACTIVE",
            setup_completed=True,
        )
        # Presidente de-vincolato: managed_society senza Membership PRESIDENT.
        self.president.president_profile.managed_society = self.society
        self.president.president_profile.save()
        self.client.login(username="zz-prez", password="pwd")

    def test_president_has_no_membership(self):
        # Guard del presupposto: lo stato reale è zero membership.
        self.assertEqual(
            Membership.objects.filter(user=self.president, is_active=True).count(), 0
        )

    def test_bacheca_globale_renders_for_managed_society_president(self):
        # Regression del TemplateSyntaxError (endif multi-riga in bacheca.html):
        # il template deve compilare e renderizzare → 200.
        resp = self.client.get(reverse("bacheca_globale"))
        self.assertEqual(resp.status_code, 200)

    def test_bacheca_team_no_longer_raises_nameerror(self):
        # Regression del NameError nel ramo `if team_slug:` di bacheca_view:
        # `society` ora viene assegnata da team.society prima dell'uso.
        # NB: il rendering completo della bacheca di team resta bloccato da un
        # TERZO bug pre-esistente, fuori dal perimetro C+D e registrato nel
        # report ({% url 'chat_team' %} in bacheca.html:14 → URL inesistente,
        # il nome reale è 'chat_view' → NoReverseMatch). Tolleriamo quella sola
        # eccezione; un NameError tornerebbe a propagarsi e a far fallire il
        # test. Quando il bug 3 sarà chiuso, questo GET tornerà 200.
        from django.urls import NoReverseMatch
        try:
            resp = self.client.get(reverse("bacheca_team", args=[self.team.slug]))
        except NoReverseMatch:
            return
        self.assertEqual(resp.status_code, 200)
