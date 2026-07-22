"""Check di coerenza fra eventi-gol per periodo e parziale del periodo (§8.5(b)-1).

Le fixture sono COPIE STATICHE derivate dai cinque referti reali del box dev
misurati nella recon del 2026-07-21. Non vengono lette dal DB a runtime: il DB
dev cambia (la riparazione dei `normalized_data` e' il giro successivo) e un
test che vi legge smetterebbe di misurare i casi che deve misurare.

Dei referti reali si conserva solo cio' che il check guarda — punteggio finale,
parziali per periodo, e per ogni evento-gol la coppia (squadra, periodo). Nessun
nome, nessun dato personale.
"""

from django.test import SimpleTestCase

from matches.services.ocr_quality_gate import OCRQualityGate
from matches.services.schema import (
    PERIOD_BLOCKER_PREFIX,
    OCRSchemaValidator,
    PERIOD_DEFICIT,
    PERIOD_EXCESS,
    PERIOD_NOT_APPLICABLE,
    PERIOD_OK,
)


def build_payload(final_score, quarters, goals_per_period, unassigned=None):
    """Payload minimo con la sola informazione che il check per-periodo legge.

    Args:
        final_score: stringa "X-Y".
        quarters: dict periodo -> [casa, ospite] (o None se illeggibile).
        goals_per_period: dict periodo -> (gol casa, gol ospite) negli eventi.
        unassigned: dict squadra -> numero di gol senza periodo.
    """
    events = []
    for q, (home_goals, away_goals) in goals_per_period.items():
        events += [{"type": "GOAL", "team": "home", "quarter": q}] * home_goals
        events += [{"type": "GOAL", "team": "away", "quarter": q}] * away_goals
    for side, count in (unassigned or {}).items():
        events += [{"type": "GOAL", "team": side, "quarter": None}] * count
    return {"scores": {"final_score": final_score, "quarters": quarters}, "events": events}


# --- Fixture dai referti reali di dev (misure del 2026-07-21) -----------------

#: Referto 7 — eccesso in tutti e 4 i periodi: 23 eventi-gol CASA contro 15.
REPORT_7 = build_payload(
    "15-9",
    {"1": [5, 2], "2": [4, 2], "3": [3, 1], "4": [3, 4]},
    {"1": (6, 2), "2": (5, 2), "3": (4, 1), "4": (8, 5)},
)

#: Referto 8 — CASA completa e perfettamente distribuita, OSPITE in difetto su 2
#: periodi con estrazione incompleta (8 gol estratti su 10).
REPORT_8 = build_payload(
    "12-10",
    {"1": [3, 2], "2": [2, 3], "3": [4, 3], "4": [3, 2]},
    {"1": (3, 2), "2": (2, 2), "3": (4, 3), "4": (3, 1)},
)

#: Referto 10 — difetto su 3 periodi su 4, entrambe le squadre incomplete.
REPORT_10 = build_payload(
    "11-19",
    {"1": [2, 2], "2": [4, 5], "3": [2, 4], "4": [3, 8]},
    {"1": (2, 2), "2": (4, 3), "3": (1, 4), "4": (2, 7)},
)

#: Referto 11 — difetto su 4 periodi su 4: 12 eventi-gol estratti su 21.
REPORT_11 = build_payload(
    "20-1",
    {"1": [5, 0], "2": [5, 0], "3": [5, 0], "4": [5, 1]},
    {"1": (3, 0), "2": (4, 0), "3": (2, 0), "4": (2, 1)},
)

#: Referto 16 — 4 periodi su 4 coerenti. Caso capitale: i parziali sono FALSI
#: (misurato sul cartaceo) e la cronologia e' stata estratta coerente con essi.
#: Il check passa. E' esattamente il limite del check, non una sua falla: misura
#: coerenza interna, non verita'. Vedi §8.11.
REPORT_16 = build_payload(
    "5-19",
    {"1": [1, 3], "2": [0, 5], "3": [3, 5], "4": [1, 6]},
    {"1": (1, 3), "2": (0, 5), "3": (3, 5), "4": (1, 6)},
)


class PeriodCheckRealReportsTest(SimpleTestCase):
    """I cinque referti reali di dev, con i conteggi misurati nella recon."""

    def test_report_7_eccesso_su_tutti_e_quattro_i_periodi(self):
        r = OCRSchemaValidator.check_goal_events_per_period(REPORT_7)
        self.assertTrue(r["applicable"])
        self.assertEqual(r["counts"]["periods"], 4)
        self.assertEqual(r["counts"]["periods_excess"], 4)
        self.assertEqual(r["counts"]["periods_deficit"], 0)
        # D1: l'eccesso e' sempre un errore, mai una mancata rilevazione.
        self.assertTrue(r["messages"]["excess"])
        self.assertEqual(r["messages"]["distribution"], [])

    def test_report_8_difetto_su_due_periodi_estrazione_incompleta(self):
        r = OCRSchemaValidator.check_goal_events_per_period(REPORT_8)
        self.assertEqual(r["counts"]["periods_deficit"], 2)
        self.assertEqual(r["counts"]["periods_excess"], 0)
        # CASA ha estratto tutti i suoi gol e li ha distribuiti bene: nessun rilievo.
        self.assertTrue(r["extraction_complete"]["home"])
        self.assertFalse(r["extraction_complete"]["away"])
        # D3: estrazione incompleta -> sola evidenza, mai blocco.
        self.assertEqual(r["messages"]["excess"], [])
        self.assertEqual(r["messages"]["distribution"], [])
        self.assertEqual(len(r["messages"]["evidence"]), 2)

    def test_report_10_difetto_su_tre_periodi(self):
        r = OCRSchemaValidator.check_goal_events_per_period(REPORT_10)
        self.assertEqual(r["counts"]["periods_deficit"], 3)
        self.assertEqual(r["counts"]["periods_excess"], 0)
        self.assertFalse(r["extraction_complete"]["home"])
        self.assertFalse(r["extraction_complete"]["away"])
        self.assertEqual(r["messages"]["distribution"], [])

    def test_report_11_difetto_su_tutti_i_periodi_dodici_gol_su_ventuno(self):
        r = OCRSchemaValidator.check_goal_events_per_period(REPORT_11)
        self.assertEqual(r["counts"]["periods_deficit"], 4)
        self.assertEqual(r["counts"]["periods_excess"], 0)
        goals = [e for e in REPORT_11["events"] if e["type"] == "GOAL"]
        self.assertEqual(len(goals), 12)
        self.assertFalse(r["extraction_complete"]["home"])
        self.assertTrue(r["extraction_complete"]["away"])
        self.assertEqual(r["messages"]["distribution"], [])

    def test_report_16_coerente_su_parziali_falsi(self):
        r = OCRSchemaValidator.check_goal_events_per_period(REPORT_16)
        self.assertEqual(r["counts"]["periods"], 4)
        self.assertEqual(r["counts"]["periods_excess"], 0)
        self.assertEqual(r["counts"]["periods_deficit"], 0)
        self.assertTrue(all(row["outcome"] == PERIOD_OK for row in r["rows"]))
        # Nessun messaggio: il check tace perche' la coerenza interna regge,
        # NON perche' i dati siano veri. La distinzione vive in §8.11 e nella UI.
        self.assertEqual(r["messages"]["excess"], [])
        self.assertEqual(r["messages"]["distribution"], [])
        self.assertEqual(r["messages"]["evidence"], [])


class PeriodCheckSemanticsTest(SimpleTestCase):
    """Casi costruiti per le regole che i referti reali non coprono."""

    def test_distribuzione_sbagliata_con_estrazione_completa_e_blocco(self):
        """D2: totale di squadra giusto, distribuzione fra i periodi no."""
        payload = build_payload(
            "12-12",
            {"1": [3, 3], "2": [3, 3], "3": [3, 3], "4": [3, 3]},
            {"1": (4, 3), "2": (2, 3), "3": (3, 3), "4": (3, 3)},
        )
        r = OCRSchemaValidator.check_goal_events_per_period(payload)
        self.assertTrue(r["extraction_complete"]["home"])
        self.assertTrue(r["messages"]["excess"])       # il periodo 1 e' in eccesso
        self.assertTrue(r["messages"]["distribution"])  # il periodo 2 e' in difetto "pesante"

    def test_gol_senza_periodo_sospende_il_difetto_ma_non_l_eccesso(self):
        payload = build_payload(
            "8-0",
            {"1": [4, 0], "2": [4, 0]},
            {"1": (5, 0), "2": (1, 0)},
            unassigned={"home": 2},
        )
        r = OCRSchemaValidator.check_goal_events_per_period(payload)
        self.assertEqual(r["unassigned_goals"]["home"], 2)
        # L'eccesso del periodo 1 resta: assegnare i gol mancanti puo' solo aumentarlo.
        self.assertEqual(r["rows"][0]["home_outcome"], PERIOD_EXCESS)
        self.assertTrue(r["messages"]["excess"])
        # Il difetto del periodo 2 non e' valutabile: potrebbe essere uno dei due
        # gol senza periodo. L'impossibilita' e' dichiarata, non taciuta.
        self.assertEqual(r["rows"][1]["home_outcome"], PERIOD_NOT_APPLICABLE)
        self.assertEqual(r["deficit"], [])
        self.assertIsNotNone(r["deficit_not_applicable"]["home"])
        self.assertTrue(any("senza periodo" in m for m in r["messages"]["evidence"]))

    def test_parziale_nullo_rende_il_periodo_non_applicabile_in_modo_visibile(self):
        payload = build_payload(
            "5-5",
            {"1": [3, 3], "2": None},
            {"1": (3, 3), "2": (2, 2)},
        )
        r = OCRSchemaValidator.check_goal_events_per_period(payload)
        self.assertTrue(r["applicable"])
        self.assertEqual(r["counts"]["periods"], 1)
        self.assertEqual(r["counts"]["periods_not_applicable"], 1)
        row = r["rows"][1]
        self.assertEqual(row["outcome"], PERIOD_NOT_APPLICABLE)
        self.assertIsNotNone(row["not_applicable_reason"])

    def test_nessun_parziale_il_check_dichiara_di_non_essere_eseguibile(self):
        payload = {"scores": {"final_score": "5-5", "quarters": {}}, "events": []}
        r = OCRSchemaValidator.check_goal_events_per_period(payload)
        self.assertFalse(r["applicable"])
        self.assertIsNotNone(r["not_applicable_reason"])
        self.assertTrue(r["messages"]["evidence"])
        self.assertEqual(r["messages"]["excess"], [])
        self.assertEqual(r["messages"]["distribution"], [])

    def test_payload_vuoto_non_esplode(self):
        for payload in ({}, None, {"scores": {"quarters": {"1": [1, 1]}}, "events": "x"}):
            r = OCRSchemaValidator.check_goal_events_per_period(payload)
            self.assertFalse(r["applicable"])
            self.assertIsNotNone(r["not_applicable_reason"])

    def test_periodi_in_forma_non_confrontabile_sono_dichiarati(self):
        payload = build_payload(
            "3-3",
            {"1": [3, 3], "2": "illeggibile"},
            {"1": (3, 3)},
        )
        r = OCRSchemaValidator.check_goal_events_per_period(payload)
        self.assertEqual(r["counts"]["periods_not_applicable"], 1)
        self.assertEqual(r["rows"][1]["outcome"], PERIOD_NOT_APPLICABLE)
        self.assertIsNotNone(r["rows"][1]["not_applicable_reason"])

    def test_tabella_riporta_conteggi_e_direzione_per_ogni_periodo(self):
        r = OCRSchemaValidator.check_goal_events_per_period(REPORT_8)
        self.assertEqual([row["quarter"] for row in r["rows"]], ["1", "2", "3", "4"])
        row2 = r["rows"][1]
        self.assertEqual((row2["home_partial"], row2["away_partial"]), (2, 3))
        self.assertEqual((row2["home_goals"], row2["away_goals"]), (2, 2))
        self.assertEqual(row2["home_outcome"], PERIOD_OK)
        self.assertEqual(row2["away_outcome"], PERIOD_DEFICIT)
        self.assertEqual(row2["outcome"], PERIOD_DEFICIT)


def wrap(payload, home="Pro Recco", away="AN Brescia"):
    """Completa un payload di periodo fino a farlo passare per referto estratto.

    Serve ai test dei due call site: gate e publish readiness guardano anche
    squadre, roster e riconciliazione, che al check per-periodo non interessano.
    """
    roster = [{"number": i, "name": f"Giocatore {i}"} for i in range(1, 14)]
    return {
        "metadata": {"confidence": 0.95, "confidence_fields": {}, "extraction_warnings": []},
        "match_info": {"home_team": home, "away_team": away, "date": "2026-01-15"},
        "scores": payload["scores"],
        "teams": {"home": {"name": home, "players": roster},
                  "away": {"name": away, "players": roster}},
        "events": payload["events"],
    }


class PeriodCheckAtGateTest(SimpleTestCase):
    """Consumo in `OCRQualityGate.evaluate` — severita' D1/D2/D3 al gate."""

    def test_eccesso_declassa_il_referto_a_needs_review(self):
        """D1: l'eccesso e' impossibile per costruzione, quindi blocca il gate."""
        is_valid, blockers, warnings, info = OCRQualityGate.evaluate(wrap(REPORT_7))
        self.assertFalse(is_valid)
        self.assertTrue(any(PERIOD_BLOCKER_PREFIX in b for b in blockers))

    def test_difetto_con_estrazione_incompleta_e_sola_evidenza(self):
        """D3: mancata rilevazione non e' errore — niente blocco, niente warning."""
        for payload in (REPORT_8, REPORT_10, REPORT_11):
            with self.subTest(payload=payload["scores"]["final_score"]):
                is_valid, blockers, warnings, info = OCRQualityGate.evaluate(wrap(payload))
                self.assertFalse(any(PERIOD_BLOCKER_PREFIX in b for b in blockers))
                self.assertFalse(any(PERIOD_BLOCKER_PREFIX in w for w in warnings))
                self.assertTrue(any("Evidenza per-periodo" in i for i in info))

    def test_distribuzione_sbagliata_avvisa_ma_non_declassa(self):
        """D2: warning al gate, non blocco. Il blocco arriva al publish."""
        payload = build_payload(
            "12-12",
            {"1": [3, 3], "2": [3, 3], "3": [3, 3], "4": [3, 3]},
            {"1": (3, 4), "2": (3, 2), "3": (3, 3), "4": (3, 3)},
        )
        is_valid, blockers, warnings, info = OCRQualityGate.evaluate(wrap(payload))
        self.assertTrue(any(PERIOD_BLOCKER_PREFIX in w for w in warnings))

    def test_referto_16_passa_il_gate_pur_avendo_parziali_falsi(self):
        """Il gate non puo' vedere la falsita' dei parziali: e' il limite, §8.11."""
        is_valid, blockers, warnings, info = OCRQualityGate.evaluate(wrap(REPORT_16))
        self.assertFalse(any(PERIOD_BLOCKER_PREFIX in b for b in blockers))


class PeriodCheckAtPublishTest(SimpleTestCase):
    """Consumo in `validate_coherence` / `assess_publish_readiness`."""

    def test_eccesso_blocca_il_publish(self):
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(wrap(REPORT_7))
        self.assertFalse(safe)
        self.assertTrue(any(PERIOD_BLOCKER_PREFIX in b for b in blockers))

    def test_distribuzione_sbagliata_blocca_il_publish(self):
        payload = build_payload(
            "12-12",
            {"1": [3, 3], "2": [3, 3], "3": [3, 3], "4": [3, 3]},
            {"1": (3, 4), "2": (3, 2), "3": (3, 3), "4": (3, 3)},
        )
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(wrap(payload))
        self.assertFalse(safe)
        self.assertTrue(any(PERIOD_BLOCKER_PREFIX in b for b in blockers))

    def test_difetto_con_estrazione_incompleta_non_blocca_mai(self):
        """D3 non deve produrre blocchi al publish nemmeno qui.

        Questi referti restano non pubblicabili per l'incoerenza AGGREGATA
        (gol estratti != finale), che e' un requisito a se': cio' che si blinda
        qui e' che nessun blocco arrivi dalla direzione "difetto per-periodo".
        """
        for payload in (REPORT_8, REPORT_10, REPORT_11):
            with self.subTest(payload=payload["scores"]["final_score"]):
                safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(wrap(payload))
                self.assertFalse(any(PERIOD_BLOCKER_PREFIX in b for b in blockers))

    def test_l_aggregato_resta_al_publish_accanto_al_per_periodo(self):
        """D6: al publish l'uguaglianza stretta gol-eventi/finale non e' sostituita."""
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(wrap(REPORT_11))
        self.assertFalse(safe)
        self.assertTrue(any("Incoerenza eventi" in b for b in blockers))
