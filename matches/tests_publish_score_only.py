"""Publish "solo punteggio" (SCORE_ONLY) — Opzione A (2026-07-22).

Un referto puo' essere pubblicato a un livello esplicito "punteggio e parziali
verificati, eventi non disponibili": nessun `MatchEvent` creato, nessuna
statistica finta a zero. Questi test blindano:

  - SCORE_ONLY proietta i punteggi ma NON crea eventi, e cancella quelli
    esistenti (D1); l'audit riporta livello e conteggio eventi rimossi;
  - l'abort zero-eventi resta IDENTICO sul livello FULL (Policy A strict non
    indebolita) e NON scatta su SCORE_ONLY;
  - il default `level='FULL'` e' retrocompatibile;
  - `assess_publish_readiness` declassa i soli blocker event-scoped su
    SCORE_ONLY, lasciando invariato il FULL;
  - il guardrail dato-verificato vale anche su SCORE_ONLY;
  - D3: downgrade FULL->SCORE_ONLY senza reason fallisce, con reason passa;
    upgrade SCORE_ONLY->FULL e' libero;
  - il pubblico distingue "cronologia non disponibile" (SCORE_ONLY) da un FULL
    con 0 eventi (`Match.events_published`).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import AthleteProfile
from core.models import League, Season, Society, Sport, Team
from matches.models import Match, MatchEvent, MatchReport, MatchReportAuditLog
from matches.services.data_verification_service import set_data_verified
from matches.services.publishing_service import PublishingService
from matches.services.schema import (
    LEVEL_FULL,
    LEVEL_SCORE_ONLY,
    OUT_OF_LEVEL_PREFIX,
    OCRSchemaValidator,
)

User = get_user_model()

FINAL = "4-2"
QUARTERS = {'1': [2, 1], '2': [0, 0], '3': [1, 1], '4': [1, 0]}


class ScoreOnlyBaseTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn-so")
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.soc_home = Society.objects.create(name="SocHome SO", slug="soc-home-so", sport=self.sport)
        self.soc_away = Society.objects.create(name="SocAway SO", slug="soc-away-so", sport=self.sport)
        self.league = League.objects.create(name="Lega SO", sport=self.sport)
        self.home = Team.objects.create(society=self.soc_home, name="Home SO", league=self.league)
        self.away = Team.objects.create(society=self.soc_away, name="Away SO", league=self.league)
        self.match = Match.objects.create(
            league=self.league, home_team=self.home, away_team=self.away,
            match_date=timezone.now(),
        )
        self.user = User.objects.create_user(username="op-so", role="athlete")
        self.p_home = User.objects.create_user(username="ph-so", role="athlete")
        AthleteProfile.objects.update_or_create(user=self.p_home, defaults={'current_team': self.home})
        self.p_away = User.objects.create_user(username="pa-so", role="athlete")
        AthleteProfile.objects.update_or_create(user=self.p_away, defaults={'current_team': self.away})

    def _data_full(self):
        """`normalized_data` pubblicabile a livello FULL: eventi coerenti,
        distribuiti sui periodi secondo i parziali, riconciliati."""
        events = []
        for q, (qh, qa) in QUARTERS.items():
            events += [{"type": "GOAL", "team": "home", "player": "Giocatore Casa", "minute": 1, "quarter": int(q)}] * qh
            events += [{"type": "GOAL", "team": "away", "player": "Giocatore Ospite", "minute": 2, "quarter": int(q)}] * qa
        return {
            "metadata": {"confidence": 0.95},
            "match_info": {"home_team": "Home SO", "away_team": "Away SO"},
            "scores": {"final_score": FINAL, "quarters": dict(QUARTERS)},
            "teams": {
                "home": {"players": [{"name": "Giocatore Casa"}]},
                "away": {"players": [{"name": "Giocatore Ospite"}]},
            },
            "events": events,
            "reconciliation": {
                "home_team_id": self.home.id, "away_team_id": self.away.id,
                "home_players": {"Giocatore Casa": self.p_home.id},
                "away_players": {"Giocatore Ospite": self.p_away.id},
            },
        }

    def _data_score_clean_no_events(self):
        """Scores puliti (somma quarti == finale), nessun evento, roster vuoti.

        A livello FULL blocca (roster vuoti + zero eventi, entrambi event-scoped);
        a livello SCORE_ONLY e' pubblicabile: nessun blocker score-scoped.
        """
        return {
            "metadata": {"confidence": 0.9},
            "match_info": {"home_team": "Home SO", "away_team": "Away SO"},
            "scores": {"final_score": FINAL, "quarters": dict(QUARTERS)},
            "teams": {"home": {"players": []}, "away": {"players": []}},
            "events": [],
            "reconciliation": {},
        }

    def _report(self, data, status=MatchReport.Status.VALIDATED, level=LEVEL_FULL):
        return MatchReport.objects.create(
            match=self.match, status=status, normalized_data=data, publication_level=level,
        )


class AssessScopingTest(ScoreOnlyBaseTest):
    def test_full_blockers_invariati(self):
        """Il livello FULL (default) non cambia di un byte: stessi blocker che
        senza parametro."""
        data = self._data_score_clean_no_events()
        safe_default, blk_default, _ = OCRSchemaValidator.assess_publish_readiness(data)
        safe_full, blk_full, _ = OCRSchemaValidator.assess_publish_readiness(data, level=LEVEL_FULL)
        self.assertEqual(safe_default, safe_full)
        self.assertEqual(blk_default, blk_full)
        self.assertFalse(safe_full)
        # I due blocker event-scoped attesi.
        self.assertTrue(any("roster" in b for b in blk_full))
        self.assertTrue(any("Zero Eventi" in b for b in blk_full))

    def test_score_only_declassa_event_scoped(self):
        data = self._data_score_clean_no_events()
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(data, level=LEVEL_SCORE_ONLY)
        self.assertTrue(safe, f"score-only doveva essere safe, blockers={blockers}")
        self.assertEqual(blockers, [])
        # I blocker declassati compaiono come warning marcati [fuori livello].
        marked = [w for w in warnings if w.startswith(OUT_OF_LEVEL_PREFIX)]
        self.assertTrue(any("roster" in w for w in marked))
        self.assertTrue(any("Zero Eventi" in w for w in marked))

    def test_score_only_tiene_i_blocker_score_scoped(self):
        """Un blocker score-scoped (somma quarti != finale) resta blocker anche
        su SCORE_ONLY: il livello score-only non e' un bypass."""
        data = self._data_score_clean_no_events()
        data["scores"]["quarters"] = {'1': [9, 9], '2': [0, 0], '3': [0, 0], '4': [0, 0]}
        safe, blockers, _ = OCRSchemaValidator.assess_publish_readiness(data, level=LEVEL_SCORE_ONLY)
        self.assertFalse(safe)
        self.assertTrue(any("Incoerenza punteggio" in b for b in blockers))


class ScoreOnlyPublishTest(ScoreOnlyBaseTest):
    def test_score_only_proietta_ma_non_crea_eventi(self):
        report = self._report(self._data_score_clean_no_events())
        success, msg = PublishingService.publish_report(report, user=self.user, level=LEVEL_SCORE_ONLY)
        self.assertTrue(success, msg)
        self.match.refresh_from_db()
        self.assertEqual((self.match.home_score, self.match.away_score), (4, 2))
        self.assertEqual(self.match.quarter_scores, QUARTERS)
        self.assertTrue(self.match.is_finished)
        # Nessun evento creato.
        self.assertEqual(MatchEvent.objects.filter(match=self.match).count(), 0)
        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.PUBLISHED)
        self.assertEqual(report.publication_level, LEVEL_SCORE_ONLY)

    def test_score_only_cancella_eventi_preesistenti_e_li_conta_in_audit(self):
        """D1 + D1a: eventi manuali preesistenti rimossi; conteggio nell'audit."""
        for _ in range(3):
            MatchEvent.objects.create(
                match=self.match, event_type="GOAL", team=self.home,
                player=self.p_home, minute=1, quarter=1,
            )
        report = self._report(self._data_score_clean_no_events())
        success, msg = PublishingService.publish_report(report, user=self.user, level=LEVEL_SCORE_ONLY)
        self.assertTrue(success, msg)
        self.assertEqual(MatchEvent.objects.filter(match=self.match).count(), 0)
        audit = MatchReportAuditLog.objects.filter(report=report, action='publish').first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.after.get('publication_level'), LEVEL_SCORE_ONLY)
        self.assertEqual(audit.after.get('events_deleted'), 3)
        self.assertEqual(audit.after.get('events_created'), 0)

    def test_score_only_non_aborta_con_zero_eventi_e_score_positivo(self):
        """L'abort zero-eventi NON si applica a SCORE_ONLY: zero eventi e' il
        contratto del livello, non un'anomalia."""
        report = self._report(self._data_score_clean_no_events())
        success, msg = PublishingService.publish_report(report, user=self.user, level=LEVEL_SCORE_ONLY)
        self.assertTrue(success, msg)
        self.assertEqual(
            MatchReportAuditLog.objects.filter(report=report, action='abort_zero_events').count(), 0
        )


class AbortUnchangedOnFullTest(ScoreOnlyBaseTest):
    def test_abort_zero_eventi_invariato_su_full(self):
        """Stesso caso del test storico: force bypassa l'assess, ma su FULL
        l'abort zero-eventi deve comunque scattare (Policy A strict intatta)."""
        data = self._data_full()
        data.pop('reconciliation', None)  # eventi senza player_id -> 0 creati
        report = self._report(data)
        success, msg = PublishingService.publish_report(
            report, user=self.user, force=True, reason='test', level=LEVEL_FULL,
        )
        self.assertFalse(success)
        self.assertIn('0 eventi creati', msg)
        self.assertEqual(
            MatchReportAuditLog.objects.filter(report=report, action='abort_zero_events').count(), 1
        )
        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.VALIDATED)

    def test_abort_zero_eventi_invariato_default_level(self):
        """Chiamata senza `level` (default FULL) mantiene l'abort."""
        data = self._data_full()
        data.pop('reconciliation', None)
        report = self._report(data)
        success, msg = PublishingService.publish_report(report, user=self.user, force=True, reason='test')
        self.assertFalse(success)
        self.assertIn('0 eventi creati', msg)


class FullRetrocompatTest(ScoreOnlyBaseTest):
    def test_publish_full_default_crea_eventi_e_livello_full(self):
        report = self._report(self._data_full())
        success, msg = PublishingService.publish_report(report, user=self.user)
        self.assertTrue(success, msg)
        self.assertEqual(MatchEvent.objects.filter(match=self.match).count(), 6)
        report.refresh_from_db()
        self.assertEqual(report.publication_level, LEVEL_FULL)

    def test_publication_level_default_full_su_referto_nuovo(self):
        report = self._report(self._data_full())
        self.assertEqual(report.publication_level, LEVEL_FULL)


class VerifiedGuardrailOnScoreOnlyTest(ScoreOnlyBaseTest):
    def test_guardrail_dato_verificato_attivo_anche_su_score_only(self):
        """Un Match verificato a mano con punteggio divergente blocca anche il
        publish SCORE_ONLY (sovrascrive comunque i punteggi)."""
        self.match.home_score, self.match.away_score = 9, 9
        self.match.quarter_scores = {'1': [9, 9]}
        self.match.save()
        set_data_verified(self.match, True, self.user, "collazione cartaceo (setup)")
        report = self._report(self._data_score_clean_no_events())
        success, msg = PublishingService.publish_report(report, user=self.user, level=LEVEL_SCORE_ONLY)
        self.assertFalse(success)
        self.assertIn("verificato a mano", msg)
        self.match.refresh_from_db()
        self.assertEqual((self.match.home_score, self.match.away_score), (9, 9))


class LevelChangeOnRepublishTest(ScoreOnlyBaseTest):
    def test_downgrade_full_to_score_only_senza_reason_fallisce(self):
        report = self._report(self._data_full())
        ok, _ = PublishingService.publish_report(report, user=self.user, level=LEVEL_FULL)
        self.assertTrue(ok)
        report.refresh_from_db()
        self.assertEqual(report.publication_level, LEVEL_FULL)
        # Downgrade senza reason -> rifiutato.
        ok2, msg2 = PublishingService.publish_report(report, user=self.user, level=LEVEL_SCORE_ONLY)
        self.assertFalse(ok2)
        self.assertIn("Downgrade", msg2)
        report.refresh_from_db()
        self.assertEqual(report.publication_level, LEVEL_FULL)  # invariato
        # Gli eventi FULL non sono stati toccati.
        self.assertEqual(MatchEvent.objects.filter(match=self.match).count(), 6)

    def test_downgrade_full_to_score_only_con_reason_passa(self):
        report = self._report(self._data_full())
        PublishingService.publish_report(report, user=self.user, level=LEVEL_FULL)
        ok, msg = PublishingService.publish_report(
            report, user=self.user, level=LEVEL_SCORE_ONLY,
            reason="referto ristampato senza cronologia",
        )
        self.assertTrue(ok, msg)
        report.refresh_from_db()
        self.assertEqual(report.publication_level, LEVEL_SCORE_ONLY)
        self.assertEqual(MatchEvent.objects.filter(match=self.match).count(), 0)

    def test_upgrade_score_only_to_full_libero(self):
        report = self._report(self._data_full())
        PublishingService.publish_report(report, user=self.user, level=LEVEL_SCORE_ONLY)
        report.refresh_from_db()
        self.assertEqual(report.publication_level, LEVEL_SCORE_ONLY)
        # Upgrade senza reason -> consentito.
        ok, msg = PublishingService.publish_report(report, user=self.user, level=LEVEL_FULL)
        self.assertTrue(ok, msg)
        report.refresh_from_db()
        self.assertEqual(report.publication_level, LEVEL_FULL)
        self.assertEqual(MatchEvent.objects.filter(match=self.match).count(), 6)


class PublicEventsGateTest(ScoreOnlyBaseTest):
    def test_events_published_true_solo_su_full(self):
        report = self._report(self._data_full())
        PublishingService.publish_report(report, user=self.user, level=LEVEL_FULL)
        self.match.refresh_from_db()
        self.assertTrue(self.match.is_public)
        self.assertTrue(self.match.events_published)

    def test_events_published_false_su_score_only(self):
        report = self._report(self._data_score_clean_no_events())
        PublishingService.publish_report(report, user=self.user, level=LEVEL_SCORE_ONLY)
        self.match.refresh_from_db()
        self.assertTrue(self.match.is_public)          # risultato pubblico
        self.assertFalse(self.match.events_published)  # ma eventi no
        self.assertEqual(self.match.published_report.publication_level, LEVEL_SCORE_ONLY)
