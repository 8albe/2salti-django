"""Test dell'arricchimento eventi al converter/publish (DEBITI §10.35, §10.37).

Coprono:
- mappatura EXCLUSION_DEF -> RED_CARD al converter;
- RED_CARD con articolo null (forma V3 di produzione) e con articolo (forma V3.4);
- invarianza del conteggio fouled-out (opera solo su EXCLUSION_20);
- persistenza di un TIMEOUT senza giocatore (team-level, player null);
- warning su un evento player-level non riconciliato (non un blocker).
"""
from django.test import TestCase
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model

from core.models import Season, Sport, Society, League, Team
from matches.models import Match, MatchReport, MatchEvent
from matches.services.converters import MatchDataConverter
from matches.services.publishing_service import PublishingService
from matches.stats_services import get_fouled_out_stats
from matches.event_types import (
    EVENT_TYPE_RED_CARD,
    EVENT_TYPE_EXCLUSION_20,
    EVENT_TYPE_TIMEOUT,
    is_team_level_event,
)

User = get_user_model()


class ConverterExclusionDefMappingTest(TestCase):
    """Mappatura EXCLUSION_DEF -> RED_CARD e passaggio dei metadati sanzione (§10.35)."""

    def test_exclusion_def_mapped_to_red_card(self):
        """Un EXCLUSION_DEF diventa RED_CARD (stesso evento reale in pallanuoto)."""
        data = {"events": [{"type": "EXCLUSION_DEF", "player_name": "Mario Rossi",
                            "team": "home", "minute": 12, "regulation_article": "9.13",
                            "sanction_sigla": "EDCS"}]}
        events = MatchDataConverter.get_events_data(data)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], EVENT_TYPE_RED_CARD)

    def test_sanction_metadata_carried_v34_form(self):
        """Forma V3.4: articolo e sigla arrivano a valle verbatim, non scartati."""
        data = {"events": [{"type": "EXCLUSION_DEF", "player_name": "Mario Rossi",
                            "team": "home", "minute": 12, "regulation_article": "9.14",
                            "sanction_sigla": "EDCS"}]}
        ev = MatchDataConverter.get_events_data(data)[0]
        self.assertEqual(ev["regulation_article"], "9.14")
        self.assertEqual(ev["sanction_sigla"], "EDCS")

    def test_red_card_null_article_v3_form(self):
        """Forma V3 di produzione: RED_CARD senza articolo resta valido (metadati null)."""
        data = {"events": [{"type": "RED_CARD", "player_name": "Mario Rossi",
                            "team": "home", "minute": 20}]}
        ev = MatchDataConverter.get_events_data(data)[0]
        self.assertEqual(ev["event_type"], EVENT_TYPE_RED_CARD)
        self.assertIsNone(ev["regulation_article"])
        self.assertIsNone(ev["sanction_sigla"])

    def test_exclusion_def_never_becomes_exclusion_20(self):
        """Invarianza fouled-out: un EXCLUSION_DEF non diventa mai un EXCLUSION_20."""
        data = {"events": [
            {"type": "EXCLUSION_DEF", "player_name": "A", "team": "home", "minute": 5,
             "regulation_article": "9.13"},
            {"type": "EXCLUSION_20", "player_name": "B", "team": "home", "minute": 6},
        ]}
        events = MatchDataConverter.get_events_data(data)
        types = [e["event_type"] for e in events]
        # La definitiva -> RED_CARD; l'esclusione di 20s resta EXCLUSION_20 (una sola).
        self.assertEqual(types.count(EVENT_TYPE_EXCLUSION_20), 1)
        self.assertIn(EVENT_TYPE_RED_CARD, types)


class EventTypeStructuralTest(TestCase):
    """La distinzione team-level/player-level e' strutturale, non un elenco di stringhe."""

    def test_timeout_is_team_level(self):
        self.assertTrue(is_team_level_event(EVENT_TYPE_TIMEOUT))

    def test_player_events_are_not_team_level(self):
        for code in (EVENT_TYPE_RED_CARD, EVENT_TYPE_EXCLUSION_20):
            self.assertFalse(is_team_level_event(code))


class PublishEventEnrichmentTest(TestCase):
    """Persistenza timeout team-level, warning non riconciliato, invarianza fouled-out."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.soc_home = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco")
        self.soc_away = Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia")
        self.league = League.objects.create(name="Serie A1", sport=self.sport, slug="serie-a1")
        self.team_home = Team.objects.create(society=self.soc_home, league=self.league)
        self.team_away = Team.objects.create(society=self.soc_away, league=self.league)
        self.user = User.objects.create_superuser(username="admin", email="admin@test.com", password="pw")

        self.match = Match.objects.create(
            league=self.league, home_team=self.team_home, away_team=self.team_away,
            match_date=timezone.now(), home_score=0, away_score=0, is_finished=False,
        )

        # Due atleti casa riconciliati: uno segna, uno prende un'espulsione definitiva.
        self.scorer = self._make_athlete("Bomber Casa", self.team_home)
        self.excluded = self._make_athlete("Duro Casa", self.team_home)

        events = [
            # Gol riconciliato: alimenta il guardrail zero-eventi (score 1-0).
            {"type": "GOAL", "team": "home", "minute": 3, "player_name": "Bomber Casa"},
            # Timeout team-level: player_name null per contratto -> persiste con player None.
            {"type": "TIMEOUT", "team": "home", "minute": 8},
            # Espulsione definitiva riconciliata -> RED_CARD con metadati sanzione.
            {"type": "EXCLUSION_DEF", "team": "home", "minute": 15,
             "player_name": "Duro Casa", "regulation_article": "9.14", "sanction_sigla": "EDCS"},
            # Rosso con nome che NON aggancia nessun atleta -> warning, non persistito.
            {"type": "RED_CARD", "team": "away", "minute": 22, "player_name": "Fantasma Ospite"},
        ]

        self.report = MatchReport.objects.create(
            match=self.match, uploader=self.user, status=MatchReport.Status.VALIDATED,
            file=SimpleUploadedFile("referto.pdf", b"pdf", content_type="application/pdf"),
            normalized_data={
                "metadata": {"confidence": 0.95, "confidence_fields": {}, "extraction_warnings": []},
                "match_info": {"home_team": "Pro Recco", "away_team": "AN Brescia", "date": "2026-01-15"},
                "scores": {"final_score": "1-0", "quarters": {"1": [1, 0]}},
                "teams": {
                    "home": {"name": "Pro Recco", "players": [{"number": i, "name": f"H{i}"} for i in range(1, 14)]},
                    "away": {"name": "AN Brescia", "players": [{"number": i, "name": f"A{i}"} for i in range(1, 14)]},
                },
                "events": events,
                "reconciliation": {
                    "home_team_id": self.team_home.id, "away_team_id": self.team_away.id,
                    "home_players": {"Bomber Casa": self.scorer.id, "Duro Casa": self.excluded.id},
                    "away_players": {},
                },
            },
        )

    def _make_athlete(self, full_name, team):
        first, last = full_name.split(" ", 1)
        u = User.objects.create_user(
            username=full_name.replace(" ", "_").lower(), first_name=first, last_name=last,
            role='athlete', identity_status='VERIFIED', onboarding_payment_done=True, setup_completed=True,
        )
        p = u.athlete_profile
        p.current_team = team
        p.save(update_fields=['current_team'])
        return u

    def _publish(self):
        # force=True: isoliamo la logica di creazione eventi dai guardrail di readiness,
        # che qui non sono l'oggetto del test.
        return PublishingService.publish_report(self.report, user=self.user, force=True)

    def test_timeout_persisted_without_player(self):
        """Il TIMEOUT (team-level) viene persistito con player null."""
        success, msg = self._publish()
        self.assertTrue(success, msg)
        to = MatchEvent.objects.filter(match=self.match, event_type=EVENT_TYPE_TIMEOUT)
        self.assertEqual(to.count(), 1)
        self.assertIsNone(to.first().player)
        self.assertEqual(to.first().team, self.team_home)

    def test_exclusion_def_persisted_as_red_card_with_metadata(self):
        """L'espulsione definitiva riconciliata diventa RED_CARD con articolo e sigla."""
        success, msg = self._publish()
        self.assertTrue(success, msg)
        rc = MatchEvent.objects.filter(match=self.match, event_type=EVENT_TYPE_RED_CARD, player=self.excluded)
        self.assertEqual(rc.count(), 1)
        self.assertEqual(rc.first().regulation_article, "9.14")
        self.assertEqual(rc.first().sanction_sigla, "EDCS")

    def test_fouled_out_count_invariant(self):
        """Dopo la mappatura, nessun EXCLUSION_20 e' stato creato: fouled-out invariato."""
        success, msg = self._publish()
        self.assertTrue(success, msg)
        self.assertEqual(
            MatchEvent.objects.filter(match=self.match, event_type=EVENT_TYPE_EXCLUSION_20).count(), 0
        )
        self.report.refresh_from_db()
        self.assertEqual(list(get_fouled_out_stats(self.league.id)), [])

    def test_unreconciled_player_event_warns_and_is_not_persisted(self):
        """Il rosso non riconciliato non si persiste e produce un warning col nome."""
        success, msg = self._publish()
        self.assertTrue(success, msg)
        # Non persistito: l'unico RED_CARD e' quello riconciliato (l'EDCS di casa).
        self.assertFalse(
            MatchEvent.objects.filter(match=self.match, event_type=EVENT_TYPE_RED_CARD, team=self.team_away).exists()
        )
        # Warning visibile in review, col nome che non ha agganciato il roster.
        self.assertIn("Fantasma Ospite", msg)
