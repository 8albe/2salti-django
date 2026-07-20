"""
Gate di visibilita' pubblica del risultato (BLUEPRINT cap. 1 + cap. 14).

Un match e' "mostrabile" se `is_data_verified=True` OPPURE ha almeno un report
PUBLISHED. Altrimenti il pubblico vede la partita ma NON il risultato.

Lezione dallo stato QUEUED (7 punti rotti su 14 perche' nessuno aveva enumerato
i punti di visualizzazione): dove possibile la lista dei punti da controllare e'
DERIVATA dal codice, non scritta a mano — vedi
`TemplateScoreExposureAuditTest`, che fallisce da sola quando qualcuno aggiunge
un nuovo template che stampa un punteggio senza passare dal gate.
"""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import League, Season, Society, Sport, Team
from matches.models import Match, MatchReport
from matches.services.result_visibility import (
    UNVERIFIED_RESULT_LABEL,
    can_see_result,
    is_result_public,
    result_public_q,
)

User = get_user_model()


class ResultVisibilityGateTest(TestCase):
    """Semantica del gate. Nessun terzo criterio: solo verified OR published."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.league = League.objects.create(name="Serie B", sport=self.sport)
        soc_h = Society.objects.create(name="Pol Delta", sport=self.sport, slug="pol-delta")
        soc_a = Society.objects.create(name="Villa York", sport=self.sport, slug="villa-york")
        self.team_h = Team.objects.create(society=soc_h, league=self.league)
        self.team_a = Team.objects.create(society=soc_a, league=self.league)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_h,
            away_team=self.team_a,
            match_date=timezone.now(),
            home_score=15,
            away_score=9,
            quarter_scores={"1": [6, 2], "2": [1, 2], "3": [3, 4], "4": [5, 1]},
            is_finished=True,
        )

    def test_unverified_and_unpublished_is_not_public(self):
        self.assertFalse(is_result_public(self.match))
        self.assertFalse(self.match.is_result_public)

    def test_is_data_verified_alone_makes_it_public(self):
        self.match.is_data_verified = True
        self.match.save(update_fields=["is_data_verified"])
        self.assertTrue(is_result_public(self.match))

    def test_published_report_alone_makes_it_public(self):
        MatchReport.objects.create(match=self.match, status=MatchReport.Status.PUBLISHED)
        self.assertTrue(is_result_public(self.match))

    def test_non_published_report_does_not_make_it_public(self):
        for status in (
            MatchReport.Status.UPLOADED,
            MatchReport.Status.EXTRACTED,
            MatchReport.Status.NEEDS_REVIEW,
            MatchReport.Status.VALIDATED,
        ):
            MatchReport.objects.all().delete()
            MatchReport.objects.create(match=self.match, status=status)
            self.assertFalse(
                is_result_public(self.match),
                f"lo stato {status} non deve rendere pubblico il risultato",
            )

    def test_gate_is_wider_than_is_public_only_via_verification(self):
        """`is_result_public` differisce da `is_public` solo per la verifica umana."""
        self.match.is_data_verified = True
        self.match.save(update_fields=["is_data_verified"])
        self.assertTrue(self.match.is_result_public)
        self.assertFalse(self.match.is_public)  # is_public resta il gate degli EVENTI

    def test_staff_and_superuser_always_see_the_result(self):
        staff = User.objects.create_user(username="staff_v", role="coach", is_staff=True)
        admin = User.objects.create_superuser(username="admin_v", email="a@b.it", password="x")
        anon = User.objects.create_user(username="tifoso", role="fan")
        self.assertTrue(can_see_result(self.match, staff))
        self.assertTrue(can_see_result(self.match, admin))
        self.assertFalse(can_see_result(self.match, anon))
        self.assertFalse(can_see_result(self.match, None))

    def test_queryset_q_matches_the_instance_helper(self):
        """`result_public_q()` e `is_result_public()` devono dire la stessa cosa."""
        other = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_h,
            match_date=timezone.now(),
            is_finished=True,
            is_data_verified=True,
        )
        visible = set(Match.objects.filter(result_public_q()).distinct().values_list("id", flat=True))
        expected = {m.id for m in Match.objects.all() if is_result_public(m)}
        self.assertEqual(visible, expected)
        self.assertIn(other.id, visible)
        self.assertNotIn(self.match.id, visible)

    def test_q_with_prefix_traverses_the_relation(self):
        from matches.models import MatchEvent

        q = result_public_q("match__")
        self.assertEqual(
            set(MatchEvent.objects.filter(q).values_list("id", flat=True)),
            set(),
        )


class TemplateScoreExposureAuditTest(TestCase):
    """
    Censimento DERIVATO, non scritto a mano.

    Scansiona tutti i template alla ricerca di un punteggio stampato: ogni file
    che ne stampa uno deve passare dal gate (`result_visible_to`) oppure essere
    esplicitamente in `STAFF_ONLY` — cioe' raggiungibile solo da staff/admin.
    Un nuovo template che stampa un punteggio senza gate fa fallire questo test
    senza che nessuno debba ricordarsi di aggiornare una lista.
    """

    # Template serviti solo a staff/admin: il gate NON si applica, e' il loro
    # strumento di verifica. Ogni voce cita la view e il controllo di accesso.
    STAFF_ONLY = {
        # management/views.py:ops_cockpit — @login_required + is_staff/is_superuser
        "management/ops_cockpit.html",
        # matches/views.py:report_review — @login_required + is_staff/is_superuser
        "matches/report_review.html",
        # OpAdminSite (is_active + is_staff)
        "admin/matches/matchreport/review.html",
    }

    SCORE_TOKENS = re.compile(
        r"\{\{\s*[\w.]*\.(home_score|away_score)\s*[|}]"
        r"|\{\{\s*[\w.]*quarter_scores"
    )

    def test_every_template_printing_a_score_goes_through_the_gate(self):
        template_root = Path(settings.BASE_DIR) / "templates"
        offenders = []
        audited = []
        for path in sorted(template_root.rglob("*.html")):
            text = path.read_text(encoding="utf-8")
            if not self.SCORE_TOKENS.search(text):
                continue
            rel = str(path.relative_to(template_root))
            audited.append(rel)
            if rel in self.STAFF_ONLY:
                continue
            if "result_visible_to" not in text:
                offenders.append(rel)

        self.assertTrue(audited, "l'audit non ha trovato alcun template: regex da rivedere")
        self.assertEqual(
            offenders,
            [],
            "Questi template stampano un punteggio senza passare dal gate "
            "`match|result_visible_to:request.user`. Aggiungi il gate, oppure "
            "dichiarali in STAFF_ONLY se sono raggiungibili solo da staff:\n  "
            + "\n  ".join(offenders),
        )

    def test_staff_only_allowlist_entries_still_exist(self):
        """L'allowlist non deve marcire: se un file sparisce, va tolto di qui."""
        template_root = Path(settings.BASE_DIR) / "templates"
        for rel in self.STAFF_ONLY:
            self.assertTrue((template_root / rel).exists(), f"{rel} non esiste piu'")


class PublicPagesResultGateTest(TestCase):
    """
    Punti di esposizione pubblici, percorsi con match non verificato e verificato.

    La lista delle pagine sta in un unico dizionario: aggiungerne una e'
    una riga, non un metodo di test.
    """

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.season = Season.objects.create(sport=self.sport, label="2025/2026", is_current=True)
        self.league = League.objects.create(name="Serie B", sport=self.sport, season_fk=self.season)
        soc_h = Society.objects.create(name="Pol Delta", sport=self.sport, slug="pol-delta")
        soc_a = Society.objects.create(name="Villa York", sport=self.sport, slug="villa-york")
        self.team_h = Team.objects.create(society=soc_h, league=self.league)
        self.team_a = Team.objects.create(society=soc_a, league=self.league)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_h,
            away_team=self.team_a,
            match_date=timezone.now() - timezone.timedelta(days=3),
            home_score=15,
            away_score=9,
            quarter_scores={"1": [6, 2], "2": [1, 2], "3": [3, 4], "4": [5, 1]},
            is_finished=True,
        )
        self.client = Client()

    def _public_urls(self):
        return {
            "match_detail": reverse("match_detail", args=[self.match.id]),
            "home": reverse("home"),
            "sport_detail": reverse("sport_detail", args=[self.sport.slug]),
            "sport_matches": reverse("sport_matches", args=[self.sport.slug]),
            "team_detail": reverse("team_detail", args=[self.team_h.slug]),
        }

    def _assert_no_score(self, name, url, client=None):
        response = (client or self.client).get(url)
        self.assertIn(response.status_code, (200, 301, 302), f"{name}: {url} -> {response.status_code}")
        if response.status_code != 200:
            return
        body = response.content.decode()
        self.assertNotIn(
            ">15</span>", body, f"{name}: punteggio casa non verificato esposto"
        )
        self.assertNotIn("15-9", body, f"{name}: punteggio non verificato esposto")
        self.assertNotIn("15 - 9", body, f"{name}: punteggio non verificato esposto")

    def test_no_public_page_shows_an_unverified_score(self):
        for name, url in self._public_urls().items():
            with self.subTest(page=name):
                self._assert_no_score(name, url)

    def test_match_detail_shows_the_placeholder_not_the_score(self):
        body = self.client.get(reverse("match_detail", args=[self.match.id])).content.decode()
        self.assertIn(UNVERIFIED_RESULT_LABEL, body)
        # la partita NON e' nascosta: squadre e competizione restano pubbliche
        self.assertIn(self.team_h.name, body)
        self.assertIn(self.team_a.name, body)
        self.assertIn(self.league.name, body)
        # nessun parziale
        self.assertNotIn("6</span>", body.split("Breakdown")[0][-200:] if "Breakdown" in body else "")
        self.assertNotIn("Breakdown", body)

    def test_match_detail_shows_the_score_once_verified(self):
        self.match.is_data_verified = True
        self.match.save(update_fields=["is_data_verified"])
        body = self.client.get(reverse("match_detail", args=[self.match.id])).content.decode()
        self.assertIn("15", body)
        self.assertIn("Breakdown", body)  # griglia parziali di nuovo visibile
        self.assertNotIn(UNVERIFIED_RESULT_LABEL, body)

    def test_match_detail_shows_the_score_once_a_report_is_published(self):
        MatchReport.objects.create(match=self.match, status=MatchReport.Status.PUBLISHED)
        body = self.client.get(reverse("match_detail", args=[self.match.id])).content.decode()
        self.assertIn("Breakdown", body)
        self.assertNotIn(UNVERIFIED_RESULT_LABEL, body)

    def test_staff_sees_the_unverified_score_on_the_public_page(self):
        staff = User.objects.create_user(
            username="staff_pub", role="coach", is_staff=True, password="x"
        )
        client = Client()
        client.force_login(staff)
        body = client.get(reverse("match_detail", args=[self.match.id])).content.decode()
        self.assertIn("Breakdown", body)
        self.assertIn("Visibile solo allo staff", body)

    def test_athlete_and_coach_and_referee_profiles_hide_the_score(self):
        athlete = User.objects.create_user(
            username="atleta_pub", first_name="Mario", last_name="Rossi", role="athlete"
        )
        profile = athlete.athlete_profile
        profile.current_team = self.team_h
        profile.save()
        referee = User.objects.create_user(username="arbitro_pub", role="referee")
        self.match.referees.add(referee)

        for user in (athlete, referee):
            with self.subTest(profilo=user.role):
                self._assert_no_score(f"profile:{user.role}", reverse("profile", args=[user.username]))


class PublicApiResultGateTest(TestCase):
    """API pubbliche: stesso gate, nessun criterio locale."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.league = League.objects.create(name="Serie B", sport=self.sport)
        soc_h = Society.objects.create(name="Pol Delta", sport=self.sport, slug="pol-delta")
        soc_a = Society.objects.create(name="Villa York", sport=self.sport, slug="villa-york")
        self.team_h = Team.objects.create(society=soc_h, league=self.league)
        self.team_a = Team.objects.create(society=soc_a, league=self.league)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_h,
            away_team=self.team_a,
            match_date=timezone.now(),
            home_score=15,
            away_score=9,
            quarter_scores={"1": [6, 2]},
            is_finished=True,
        )
        self.client = Client()

    def test_match_detail_api_404s_when_unverified(self):
        r = self.client.get(f"/api/v1/match/{self.match.id}/")
        self.assertEqual(r.status_code, 404)

    def test_match_detail_api_serves_a_verified_match(self):
        self.match.is_data_verified = True
        self.match.save(update_fields=["is_data_verified"])
        r = self.client.get(f"/api/v1/match/{self.match.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["home_score"], 15)

    def test_league_matches_api_omits_unverified_matches(self):
        r = self.client.get(f"/api/v1/league/{self.league.id}/matches/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["matches"], [])

    def test_league_matches_api_includes_verified_matches_once(self):
        self.match.is_data_verified = True
        self.match.save(update_fields=["is_data_verified"])
        MatchReport.objects.create(match=self.match, status=MatchReport.Status.PUBLISHED)
        payload = self.client.get(f"/api/v1/league/{self.league.id}/matches/").json()["matches"]
        self.assertEqual(len(payload), 1, "il join sui report non deve duplicare le righe")
        self.assertEqual(payload[0]["home_score"], 15)


class AiStatsEngineResultGateTest(TestCase):
    """
    L'AI non e' una porta di servizio: i conteggi derivano solo da match il cui
    risultato e' pubblico, con lo stesso criterio del gate.
    """

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.season = Season.objects.create(sport=self.sport, label="2025/2026", is_current=True)
        self.league = League.objects.create(name="Serie B", sport=self.sport, season_fk=self.season)
        soc_h = Society.objects.create(name="Pol Delta", sport=self.sport, slug="pol-delta")
        soc_a = Society.objects.create(name="Villa York", sport=self.sport, slug="villa-york")
        self.team_h = Team.objects.create(society=soc_h, league=self.league)
        self.team_a = Team.objects.create(society=soc_a, league=self.league)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_h,
            away_team=self.team_a,
            match_date=timezone.now(),
            home_score=15,
            away_score=9,
            is_finished=True,
        )
        self.athlete = User.objects.create_user(
            username="bomber", first_name="Ugo", last_name="Rossi", role="athlete"
        )
        profile = self.athlete.athlete_profile
        profile.current_team = self.team_h
        profile.save()

        from matches.models import MatchEvent

        for minute in (3, 12, 21):
            MatchEvent.objects.create(
                match=self.match,
                team=self.team_h,
                player=self.athlete,
                event_type="GOAL",
                minute=minute,
                quarter=1,
            )

    def _goals(self):
        from matches.services.ai_services import AIStatsEngine

        engine = AIStatsEngine.__new__(AIStatsEngine)  # niente client OpenAI nei test
        return engine._get_player_goals(self.athlete, {})["value"]

    def test_goals_from_an_unverified_match_are_not_counted(self):
        self.assertEqual(self._goals(), 0)

    def test_goals_are_counted_once_the_match_is_verified(self):
        self.match.is_data_verified = True
        self.match.save(update_fields=["is_data_verified"])
        self.assertEqual(self._goals(), 3)

    def test_goals_are_counted_once_a_report_is_published(self):
        MatchReport.objects.create(match=self.match, status=MatchReport.Status.PUBLISHED)
        self.assertEqual(self._goals(), 3)

    def test_no_double_counting_when_both_conditions_hold(self):
        self.match.is_data_verified = True
        self.match.save(update_fields=["is_data_verified"])
        MatchReport.objects.create(match=self.match, status=MatchReport.Status.PUBLISHED)
        MatchReport.objects.create(match=self.match, status=MatchReport.Status.PUBLISHED)
        self.assertEqual(self._goals(), 3, "il join sui report non deve moltiplicare i gol")
