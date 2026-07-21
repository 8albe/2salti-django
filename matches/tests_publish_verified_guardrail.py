"""Guardrail "dato verificato" in `publish_report` (prerequisito 1, 2026-07-21).

Contesto. Con l'opzione A (ratificata il 2026-07-21) `Match` e' una proiezione
del referto e `publish_report` ne e' l'unico scrittore. Ma su prod esistono
partite i cui punteggi sono stati verificati a mano contro il cartaceo mentre il
`normalized_data` del referto collegato e' ancora sbagliato: pubblicare quel
referto sovrascriverebbe il dato corretto e — danno peggiore — lascerebbe
`is_data_verified=True`, cioe' il dato sbagliato resterebbe pubblicamente
visibile *come verificato da un umano*.

Questi test blindano le due meta' del guardrail: il blocco delle pubblicazioni
distruttive, e il ritiro della verifica quando la sovrascrittura avviene
comunque via force.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import AthleteProfile
from core.models import League, Season, Society, Sport, Team
from management.models import AuditLog
from matches.models import Match, MatchReport, MatchReportAuditLog
from matches.services.data_verification_service import AUDIT_ACTION as DV_AUDIT_ACTION
from matches.services.data_verification_service import set_data_verified
from matches.services.publishing_service import (
    FORCED_OVERWRITE_AUDIT_ACTION,
    PublishingService,
)

User = get_user_model()

# Punteggio verificato a mano sul Match, e i parziali corrispondenti.
VERIFIED_SCORE = (4, 19)
VERIFIED_QUARTERS = {'1': [1, 3], '2': [0, 5], '3': [3, 6], '4': [0, 5]}

# Punteggio sbagliato che il referto proietterebbe: la situazione reale dei
# report 10/16 sul match 3 di prod.
WRONG_SCORE = "11-19"
WRONG_QUARTERS = {'1': [2, 2], '2': [4, 5], '3': [2, 4], '4': [3, 8]}


class VerifiedProjectionGuardrailTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn-guard")
        # Serve una stagione corrente: assegnare `current_team` a un atleta apre
        # una membership, che senza stagione derivabile solleva RuntimeError.
        self.season = Season.objects.create(
            sport=self.sport, label='2025/2026', is_current=True
        )
        self.soc_home = Society.objects.create(name="SocHome G", slug="soc-home-g", sport=self.sport)
        self.soc_away = Society.objects.create(name="SocAway G", slug="soc-away-g", sport=self.sport)
        self.league = League.objects.create(name="Lega Guardrail", sport=self.sport)
        self.home = Team.objects.create(society=self.soc_home, name="Home G", league=self.league)
        self.away = Team.objects.create(society=self.soc_away, name="Away G", league=self.league)

        self.match = Match.objects.create(
            league=self.league, home_team=self.home, away_team=self.away,
            match_date=timezone.now(),
            home_score=VERIFIED_SCORE[0], away_score=VERIFIED_SCORE[1],
            quarter_scores=dict(VERIFIED_QUARTERS),
        )
        self.operator = User.objects.create_user(username="operatore-guard", role="athlete")

        # Un atleta riconciliato per lato: serve a superare il guardrail
        # "zero eventi con punteggio positivo", che e' un'altra difesa e non
        # deve interferire con quella sotto test.
        self.p_home = User.objects.create_user(username="ph-guard", role="athlete")
        AthleteProfile.objects.update_or_create(
            user=self.p_home, defaults={'current_team': self.home}
        )
        self.p_away = User.objects.create_user(username="pa-guard", role="athlete")
        AthleteProfile.objects.update_or_create(
            user=self.p_away, defaults={'current_team': self.away}
        )

    # --- helper ------------------------------------------------------------

    def _data(self, final_score, quarters):
        """`normalized_data` pubblicabile: supera i guardrail preesistenti.

        I gol devono essere tanti quanti il punteggio finale, altrimenti scatta
        prima il blocker di coerenza ("Incoerenza eventi") e il guardrail sotto
        test non verrebbe nemmeno raggiunto.
        """
        home_goals, away_goals = (int(p) for p in final_score.split("-"))
        events = [
            {"type": "GOAL", "team": "home", "player": "Giocatore Casa", "minute": 1, "quarter": 1}
            for _ in range(home_goals)
        ] + [
            {"type": "GOAL", "team": "away", "player": "Giocatore Ospite", "minute": 2, "quarter": 1}
            for _ in range(away_goals)
        ]
        return {
            "metadata": {"confidence": 0.95},
            "match_info": {"home_team": "Home G", "away_team": "Away G"},
            "scores": {"final_score": final_score, "quarters": dict(quarters)},
            "teams": {
                "home": {"players": [{"name": "Giocatore Casa"}]},
                "away": {"players": [{"name": "Giocatore Ospite"}]},
            },
            "events": events,
            "reconciliation": {
                "home_team_id": self.home.id,
                "away_team_id": self.away.id,
                "home_players": {"Giocatore Casa": self.p_home.id},
                "away_players": {"Giocatore Ospite": self.p_away.id},
            },
        }

    def _report(self, final_score, quarters):
        return MatchReport.objects.create(
            match=self.match,
            status=MatchReport.Status.VALIDATED,
            normalized_data=self._data(final_score, quarters),
        )

    def _verify_match(self):
        set_data_verified(
            self.match, True, self.operator,
            "collazione sul cartaceo originale (setup di test)",
        )

    # --- blocco ------------------------------------------------------------

    def test_blocca_publish_su_match_verificato_con_dati_divergenti(self):
        self._verify_match()
        report = self._report(WRONG_SCORE, WRONG_QUARTERS)

        success, msg = PublishingService.publish_report(report, user=self.operator)

        self.assertFalse(success)
        self.assertIn("verificato a mano", msg)

        # Il Match non e' stato toccato: ne' punteggi, ne' flag.
        self.match.refresh_from_db()
        self.assertEqual(
            (self.match.home_score, self.match.away_score), VERIFIED_SCORE
        )
        self.assertEqual(self.match.quarter_scores, VERIFIED_QUARTERS)
        self.assertTrue(self.match.is_data_verified)

        # E il referto non e' passato a PUBLISHED.
        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.VALIDATED)

    def test_blocca_anche_quando_divergono_solo_i_parziali(self):
        """Il finale coincide, i parziali no: e' comunque una sovrascrittura."""
        self._verify_match()
        report = self._report("4-19", {'1': [1, 5], '2': [1, 5], '3': [1, 5], '4': [1, 4]})

        success, msg = PublishingService.publish_report(report, user=self.operator)

        self.assertFalse(success)
        self.assertIn("parziali", msg)
        self.match.refresh_from_db()
        self.assertEqual(self.match.quarter_scores, VERIFIED_QUARTERS)

    # --- non-blocco --------------------------------------------------------

    def test_permette_publish_su_match_verificato_con_dati_coincidenti(self):
        """Nessuna sovrascrittura, nessun blocco: non c'e' niente da difendere."""
        self._verify_match()
        report = self._report("4-19", VERIFIED_QUARTERS)

        success, msg = PublishingService.publish_report(report, user=self.operator)

        self.assertTrue(success, msg)
        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.PUBLISHED)

        # La verifica umana resta in piedi: i dati sono ancora quelli verificati.
        self.match.refresh_from_db()
        self.assertTrue(self.match.is_data_verified)
        self.assertEqual((self.match.home_score, self.match.away_score), VERIFIED_SCORE)

    def test_match_non_verificato_nessun_blocco_nuovo(self):
        """Caso di controllo: senza verifica umana il guardrail non esiste."""
        self.assertFalse(self.match.is_data_verified)
        report = self._report(WRONG_SCORE, WRONG_QUARTERS)

        success, msg = PublishingService.publish_report(report, user=self.operator)

        self.assertTrue(success, msg)
        self.match.refresh_from_db()
        self.assertEqual((self.match.home_score, self.match.away_score), (11, 19))
        self.assertFalse(self.match.is_data_verified)
        # Nessun audit di sovrascrittura: non c'era nulla di verificato.
        self.assertFalse(
            MatchReportAuditLog.objects.filter(action=FORCED_OVERWRITE_AUDIT_ACTION).exists()
        )

    # --- force -------------------------------------------------------------

    def test_force_senza_reason_e_rifiutato(self):
        self._verify_match()
        report = self._report(WRONG_SCORE, WRONG_QUARTERS)

        success, msg = PublishingService.publish_report(
            report, user=self.operator, force=True,
        )

        self.assertFalse(success)
        self.assertIn("motivazione", msg)
        self.match.refresh_from_db()
        self.assertEqual((self.match.home_score, self.match.away_score), VERIFIED_SCORE)
        self.assertTrue(self.match.is_data_verified)

    def test_force_con_reason_vuota_o_spazi_e_rifiutato(self):
        self._verify_match()
        report = self._report(WRONG_SCORE, WRONG_QUARTERS)

        success, msg = PublishingService.publish_report(
            report, user=self.operator, force=True, reason="   ",
        )

        self.assertFalse(success)
        self.assertIn("motivazione", msg)
        self.match.refresh_from_db()
        self.assertTrue(self.match.is_data_verified)

    def test_force_con_reason_esegue_e_ritira_la_verifica(self):
        self._verify_match()
        report = self._report(WRONG_SCORE, WRONG_QUARTERS)
        motivo = "referto ricontrollato: la correzione a mano del 19/07 era su un altro foglio"

        success, msg = PublishingService.publish_report(
            report, user=self.operator, force=True, reason=motivo,
        )

        self.assertTrue(success, msg)

        # I dati del referto sono stati proiettati...
        self.match.refresh_from_db()
        self.assertEqual((self.match.home_score, self.match.away_score), (11, 19))
        self.assertEqual(self.match.quarter_scores, WRONG_QUARTERS)

        # ...e la pretesa di verifica umana e' caduta: e' questo il punto.
        self.assertFalse(self.match.is_data_verified)
        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.PUBLISHED)

    def test_force_con_reason_scrive_audit_con_valori_prima_dopo(self):
        self._verify_match()
        report = self._report(WRONG_SCORE, WRONG_QUARTERS)
        motivo = "sovrascrittura autorizzata da Alberto, verbale del 21/07"

        success, msg = PublishingService.publish_report(
            report, user=self.operator, force=True, reason=motivo,
        )
        self.assertTrue(success, msg)

        log = MatchReportAuditLog.objects.get(action=FORCED_OVERWRITE_AUDIT_ACTION)
        self.assertEqual(log.report_id, report.id)
        self.assertEqual(log.user, self.operator)
        self.assertEqual(log.reason, motivo)

        self.assertEqual(log.before['home_score'], VERIFIED_SCORE[0])
        self.assertEqual(log.before['away_score'], VERIFIED_SCORE[1])
        self.assertEqual(log.before['quarter_scores'], VERIFIED_QUARTERS)
        self.assertTrue(log.before['is_data_verified'])

        self.assertEqual(log.after['home_score'], 11)
        self.assertEqual(log.after['quarter_scores'], WRONG_QUARTERS)
        self.assertFalse(log.after['is_data_verified'])
        self.assertCountEqual(
            log.after['diverging_fields'], ['final_score', 'quarter_scores']
        )

    def test_ritiro_della_verifica_passa_dal_seam(self):
        """Il flag non si scrive a mano: deve esserci l'audit del seam."""
        self._verify_match()
        report = self._report(WRONG_SCORE, WRONG_QUARTERS)

        success, msg = PublishingService.publish_report(
            report, user=self.operator, force=True, reason="motivo tracciato",
        )
        self.assertTrue(success, msg)

        logs = list(AuditLog.objects.filter(action=DV_AUDIT_ACTION).order_by('id'))
        # [0] e' il set_data_verified(True) del setup, [1] il ritiro.
        self.assertEqual(len(logs), 2)
        self.assertTrue(logs[0].details['to'])
        self.assertFalse(logs[1].details['to'])
        self.assertIn("pubblicazione forzata", logs[1].details['reason'])
        self.assertIn("motivo tracciato", logs[1].details['reason'])
