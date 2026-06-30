"""Test per il modulo Sponsor relazionale (Macro 9).

Copre: modello, targeting per stagione (solo stagione corrente), filtro
is_active, ordinamento, degradazione a zero, render scheda società e profilo
atleta del club, attributi rel del link esterno.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import League, Season, Society, Sponsor, Sport, Team
from core.services.sponsor_service import get_society_sponsors

User = get_user_model()


class SponsorModelAndServiceTests(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto SponsorSvc")
        self.current = Season.objects.create(
            sport=self.sport, label="2025/2026", is_current=True)
        self.other = Season.objects.create(
            sport=self.sport, label="2024/2025", is_current=False)
        self.society = Society.objects.create(name="Zero9 Svc", sport=self.sport, city="Roma")

    def test_str(self):
        s = Sponsor.objects.create(
            society=self.society, season=self.current, name="ACME")
        self.assertIn("ACME", str(s))
        self.assertIn(self.society.name, str(s))

    def test_targeting_only_current_season(self):
        cur = Sponsor.objects.create(
            society=self.society, season=self.current, name="Corrente")
        Sponsor.objects.create(
            society=self.society, season=self.other, name="Vecchio")
        result = list(get_society_sponsors(self.society))
        self.assertEqual(result, [cur])

    def test_inactive_excluded(self):
        Sponsor.objects.create(
            society=self.society, season=self.current, name="Spento", is_active=False)
        self.assertEqual(list(get_society_sponsors(self.society)), [])

    def test_ordering_by_order_then_name(self):
        b = Sponsor.objects.create(
            society=self.society, season=self.current, name="B", order=2)
        a = Sponsor.objects.create(
            society=self.society, season=self.current, name="A", order=1)
        self.assertEqual(list(get_society_sponsors(self.society)), [a, b])

    def test_degradation_no_current_season(self):
        sport2 = Sport.objects.create(name="Volley NoCurrent")
        soc2 = Society.objects.create(name="SocNoSeason", sport=sport2, city="Milano")
        Season.objects.create(sport=sport2, label="2025/2026", is_current=False)
        Sponsor.objects.create(
            society=soc2,
            season=Season.objects.get(sport=sport2),
            name="Invisibile",
        )
        self.assertEqual(list(get_society_sponsors(soc2)), [])

    def test_degradation_no_sponsors(self):
        self.assertEqual(list(get_society_sponsors(self.society)), [])

    def test_defensive_none_society(self):
        self.assertEqual(list(get_society_sponsors(None)), [])

    def test_other_society_isolated(self):
        other_soc = Society.objects.create(name="Altra", sport=self.sport, city="Genova")
        Sponsor.objects.create(
            society=other_soc, season=self.current, name="AltroSponsor")
        self.assertEqual(list(get_society_sponsors(self.society)), [])


class SponsorSocietyRenderTests(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto SponsorRender")
        self.season = Season.objects.create(
            sport=self.sport, label="2025/2026", is_current=True)
        self.society = Society.objects.create(
            name="Zero9 Render", sport=self.sport, city="Roma")

    def _get(self):
        return self.client.get(reverse('society_detail', args=[self.society.slug]))

    def test_zero_sponsors_block_hidden(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Partner")

    def test_sponsor_rendered_with_external_link_rel(self):
        Sponsor.objects.create(
            society=self.society, season=self.season,
            name="Sponsor Visibile", url="https://example.com/x",
            logo_url="https://example.com/logo.png",
        )
        resp = self._get()
        self.assertContains(resp, "Partner")
        self.assertContains(resp, "Sponsor Visibile")
        self.assertContains(resp, 'href="https://example.com/x"')
        self.assertContains(resp, 'rel="sponsored noopener nofollow"')
        self.assertContains(resp, 'target="_blank"')

    def test_sponsor_without_url_no_anchor(self):
        Sponsor.objects.create(
            society=self.society, season=self.season, name="Senza Link")
        resp = self._get()
        self.assertContains(resp, "Senza Link")
        self.assertNotContains(resp, 'rel="sponsored noopener nofollow"')

    def test_noncurrent_season_sponsor_hidden(self):
        old = Season.objects.create(
            sport=self.sport, label="2024/2025", is_current=False)
        Sponsor.objects.create(
            society=self.society, season=old, name="Stagione Vecchia",
            url="https://example.com/old")
        resp = self._get()
        self.assertNotContains(resp, "Stagione Vecchia")


class SponsorAthleteProfileRenderTests(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto SponsorAtleta")
        self.season = Season.objects.create(
            sport=self.sport, label="2025/2026", is_current=True)
        self.society = Society.objects.create(
            name="Zero9 Atleta", sport=self.sport, city="Roma")
        self.league = League.objects.create(
            name="Serie Test Atleta", sport=self.sport, season="2025/2026")
        self.team = Team.objects.create(society=self.society, league=self.league)
        self.user = User.objects.create_user(
            username="atleta9", password="pw", role="athlete",
            first_name="Mario", last_name="Rossi")
        # AthleteProfile è creato da un post_save signal su User: lo aggiorniamo.
        profile = self.user.athlete_profile
        profile.current_team = self.team
        profile.save()

    def _get(self):
        return self.client.get(reverse('profile', args=[self.user.username]))

    def test_club_sponsor_shown_reduced(self):
        Sponsor.objects.create(
            society=self.society, season=self.season,
            name="Club Partner", url="https://example.com/club",
            logo_url="https://example.com/club.png")
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Partner del Club")
        self.assertContains(resp, "Club Partner")
        self.assertContains(resp, 'rel="sponsored noopener nofollow"')

    def test_club_sponsor_degradation_zero(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Partner del Club")
