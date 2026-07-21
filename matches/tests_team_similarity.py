"""Discovery: dal fuzzy posizionale a difflib (fetta separata, 2026-07-21).

Il confronto posizionale (`simple_similarity`) confrontava i caratteri alla
stessa posizione: una sola inserzione all'inizio disallineava tutto il resto.
`Nautilus Roma` contro `Nautilus N. Roma` valeva 0.562 — sotto ogni soglia
utile — pur essendo la stessa squadra.

I test qui sotto fissano le due meta' del contratto:
  1. gli orfani storici per shift/inserzione ora risolvono;
  2. i non-match restano non-match — in particolare le allucinazioni del
     report 15 (`S.C. Tuscolano`, `Virtus Nuoto Roma`) NON devono agganciarsi
     a nulla di esistente.
"""
from django.test import TestCase

from core.models import League, Society, Sport, Team
from matches.services.ocr_service import (
    TEAM_FUZZY_THRESHOLD,
    normalize_team_name,
    resolve_team_entity,
    simple_similarity,
    team_similarity,
)

#: Le 13 squadre realmente a DB su dev e prod al 2026-07-21.
REAL_TEAMS = [
    'Pol. Delta', 'Villa York', 'Nautilus N. Roma', 'Unime', 'Bellator Frusino',
    'SS. Lazio Nuoto', 'Olimpic Roma P.N.', 'Libertas Roma Eur', 'De Akker',
    'Pro Recco Waterpolo', 'Onda Forte', 'S.S. Lazio Nuoto', 'Zero9',
]


class TeamSimilarityMetricTest(TestCase):
    """La metrica, isolata dal DB: prima/dopo sui casi che l'hanno motivata."""

    def _pair(self, a, b):
        return normalize_team_name(a), normalize_team_name(b)

    def test_insertion_used_to_break_positional_and_now_does_not(self):
        a, b = self._pair("Nautilus Roma", "Nautilus N. Roma")
        self.assertLess(simple_similarity(a, b), 0.6)      # prima: 0.562
        self.assertGreater(team_similarity(a, b), 0.85)    # dopo:  0.897

    def test_word_insertion_case(self):
        a, b = self._pair("Nautilus Nuoto Roma", "Nautilus N. Roma")
        self.assertLess(simple_similarity(a, b), 0.6)      # prima: 0.579
        self.assertGreater(team_similarity(a, b), 0.85)    # dopo:  0.857

    def test_appended_suffix_case(self):
        """`LIBERTAS ROMA EUR P.N`: suffisso inventato dal modello (§8.9)."""
        a, b = self._pair("LIBERTAS ROMA EUR P.N", "Libertas Roma Eur")
        self.assertGreater(team_similarity(a, b), 0.85)

    def test_single_letter_substitution_stays_high(self):
        """Il caso che gia' funzionava non deve peggiorare."""
        a, b = self._pair("Olympic Roma P.N.", "Olimpic Roma P.N.")
        self.assertGreater(team_similarity(a, b), 0.9)

    def test_metric_is_symmetric_and_bounded(self):
        a, b = self._pair("Nautilus Roma", "Nautilus N. Roma")
        self.assertAlmostEqual(team_similarity(a, b), team_similarity(b, a))
        self.assertAlmostEqual(team_similarity(a, a), 1.0)
        self.assertEqual(team_similarity("", b), 0.0)
        self.assertEqual(team_similarity(a, ""), 0.0)

    def test_threshold_sits_in_an_empty_band(self):
        """La soglia non e' ereditata: e' misurata, e sta in mezzo al vuoto.

        Veri positivi tutti >= 0.85, falsi positivi tutti <= 0.65. La soglia a
        0.80 cade dentro l'intervallo vuoto: nessun caso reale le sta vicino.
        """
        true_positives = [
            ("Olympic Roma P.N.", "Olimpic Roma P.N."),
            ("Nautilus Roma", "Nautilus N. Roma"),
            ("Nautilus Nuoto Roma", "Nautilus N. Roma"),
            ("LIBERTAS ROMA EUR P.N", "Libertas Roma Eur"),
        ]
        for probe, target in true_positives:
            with self.subTest(tp=probe):
                self.assertGreaterEqual(team_similarity(*self._pair(probe, target)), 0.85)

        # Il falso positivo piu' alto misurato su tutta la popolazione reale.
        worst_fp = team_similarity(*self._pair("Virtus Nuoto Roma", "Nautilus N. Roma"))
        self.assertLessEqual(worst_fp, 0.65)
        self.assertLess(worst_fp, TEAM_FUZZY_THRESHOLD)
        self.assertGreater(TEAM_FUZZY_THRESHOLD, 0.65)
        self.assertLess(TEAM_FUZZY_THRESHOLD, 0.85)

    def test_gate_threshold_would_be_too_permissive_here(self):
        """Perche' non allinearsi allo 0.6 del quality gate: aggancerebbe.

        A 0.6 la discovery collegherebbe `Virtus Nuoto Roma` — allucinazione del
        report 15 — a Nautilus N. Roma, sovrascrivendo il punteggio di una
        partita che non c'entra nulla.
        """
        self.assertGreater(team_similarity(*self._pair("Virtus Nuoto Roma", "Nautilus N. Roma")), 0.6)


class ResolveTeamEntityAgainstRealPopulationTest(TestCase):
    """Risoluzione contro le 13 squadre realmente a DB, senza alcun alias."""

    @classmethod
    def setUpTestData(cls):
        cls.sport = Sport.objects.create(name="Pallanuoto", slug="pn-sim")
        cls.league = League.objects.create(name="Lega Sim", sport=cls.sport)
        cls.teams = {}
        for i, name in enumerate(REAL_TEAMS):
            soc = Society.objects.create(name=name, slug=f"soc-sim-{i}", sport=cls.sport)
            cls.teams[name] = Team.objects.create(society=soc, name=name, league=cls.league)

    def setUp(self):
        self.all_teams = Team.objects.all()

    # --- orfani storici da shift/inserzione: ora risolvono ---

    def test_nautilus_short_spelling_now_resolves(self):
        """Referto del 28/03, dove la parola "Nuoto" non c'e' proprio (§8.6(a))."""
        self.assertEqual(
            resolve_team_entity("Nautilus Roma", self.all_teams),
            self.teams['Nautilus N. Roma'],
        )

    def test_nautilus_long_spelling_now_resolves(self):
        """Referti del 18/04 e del 25/04, dove "Nuoto" c'e' (§8.6(a))."""
        self.assertEqual(
            resolve_team_entity("Nautilus Nuoto Roma", self.all_teams),
            self.teams['Nautilus N. Roma'],
        )

    def test_invented_suffix_still_resolves(self):
        self.assertEqual(
            resolve_team_entity("LIBERTAS ROMA EUR P.N", self.all_teams),
            self.teams['Libertas Roma Eur'],
        )

    def test_olympic_spelling_keeps_resolving(self):
        """Non-regressione: cio' che il posizionale gia' risolveva resta risolto."""
        self.assertEqual(
            resolve_team_entity("Olympic Roma P.N.", self.all_teams),
            self.teams['Olimpic Roma P.N.'],
        )

    def test_exact_names_keep_resolving(self):
        for name, team in self.teams.items():
            with self.subTest(team=name):
                self.assertEqual(resolve_team_entity(name, self.all_teams), team)

    # --- i non-match devono restare non-match ---

    def test_tuscolano_hallucination_resolves_to_nothing(self):
        """Vincolo esplicito della fetta: nessun aggancio spurio.

        `S.C. Tuscolano` e' l'allucinazione con cui l'OCR ha letto S.C. Salerno
        sul report 15 in produzione. Il collaudo su prod ha visto la discovery
        NON agganciarla: il passaggio a difflib non deve cambiarlo.
        """
        self.assertIsNone(resolve_team_entity("S.C. Tuscolano", self.all_teams))

    def test_virtus_hallucination_resolves_to_nothing(self):
        """L'altra meta' del report 15: `Virtus Nuoto Roma` per Nautilus.

        E' il falso positivo piu' vicino alla soglia dell'intera popolazione
        (0.606) — il caso di confine che giustifica lo 0.80.
        """
        self.assertIsNone(resolve_team_entity("Virtus Nuoto Roma", self.all_teams))

    def test_other_gold_hallucinations_resolve_to_nothing(self):
        """Le altre allucinazioni sui nomi viste nella baseline §8.9."""
        for probe in ("S.C. SACCENGO", "Asd Tus Novara Nuoto Roma", "S.C. Spresiano",
                      "Invictus Nuoto Roma", "CONI", "TRISKELION ETNA SPORT"):
            with self.subTest(probe=probe):
                self.assertIsNone(resolve_team_entity(probe, self.all_teams))

    def test_absent_societies_resolve_to_nothing(self):
        """`S.C. Salerno` e `Triscelon Etna Sport` non sono a DB (§8.2).

        Un loro referto deve restare orfano per ASSENZA REALE, non agganciarsi
        a un omonimo approssimativo.
        """
        for probe in ("S.C. Salerno", "Triscelon Etna Sport"):
            with self.subTest(probe=probe):
                self.assertIsNone(resolve_team_entity(probe, self.all_teams))

    def test_empty_and_garbage_input(self):
        for probe in ("", None, "   ", "???", "unknown"):
            with self.subTest(probe=probe):
                self.assertIsNone(resolve_team_entity(probe, self.all_teams))

    # --- ambiguita': meglio nessuna risposta che quella sbagliata ---

    def test_lazio_duplicate_is_decided_by_a_razor_thin_margin(self):
        """RISCHIO NOTO, non un comportamento desiderato — motiva D1.

        Le due anagrafiche Lazio (§8.7) sono quasi identiche fra loro. Il
        posizionale non le raggiungeva affatto (referto orfano); difflib le
        raggiunge entrambe, e sceglie per uno scarto di ~0.03:

            'SS Lazio Nuoto' -> 'ss. lazio nuoto'  0.846   <- vince
                             -> 's.s. lazio nuoto' 0.815

        Cioe' su un referto Lazio la discovery ora RISPONDE, e la risposta e'
        decisa da un punto e mezzo di rumore fra due anagrafiche che
        rappresentano la stessa societa' reale. Non e' un aggancio spurio verso
        una squadra estranea — e' l'ambiguita' anagrafica di §8.7 che si
        manifesta. La cura e' il merge (fetta D1), non alzare la soglia: a
        qualunque soglia le due restano indistinguibili.

        Questo test fissa il fatto misurato. Dopo D1 andra' riscritto: con una
        sola anagrafica Lazio la risposta diventa univoca e legittima.
        """
        resolved = resolve_team_entity("SS Lazio Nuoto", self.all_teams)
        self.assertIn(resolved, (self.teams['SS. Lazio Nuoto'], self.teams['S.S. Lazio Nuoto']))

        a = team_similarity(normalize_team_name("SS Lazio Nuoto"), normalize_team_name("SS. Lazio Nuoto"))
        b = team_similarity(normalize_team_name("SS Lazio Nuoto"), normalize_team_name("S.S. Lazio Nuoto"))
        self.assertLess(abs(a - b), 0.05, "il margine fra le due Lazio e' rumore, non segnale")
