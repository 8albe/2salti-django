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

from core.models import League, Society, Sport, Team, TeamAlias
from matches.services.ocr_service import (
    TEAM_FUZZY_THRESHOLD,
    normalize_team_name,
    resolve_team_entity,
    simple_similarity,
    team_similarity,
)

#: Le 13 squadre realmente a DB su dev al 2026-07-21, DOPO il merge D1 (§8.7).
#:
#: Prima di D1 le voci Lazio erano ``'SS. Lazio Nuoto'`` (Allievi, societa' 6) e
#: ``'S.S. Lazio Nuoto'`` (Serie C, societa' 12): due anagrafiche per un ente
#: solo. Il merge ha eliminato la societa' 6 e ri-puntato la sua squadra sulla
#: 12, rinominandola ``'S.S. Lazio Nuoto Allievi'``. Le SQUADRE restano due —
#: sono in due leghe diverse, ed e' legittimo — ma ora hanno un solo genitore.
REAL_TEAMS = [
    'Pol. Delta', 'Villa York', 'Nautilus N. Roma', 'Unime', 'Bellator Frusino',
    'S.S. Lazio Nuoto Allievi', 'Olimpic Roma P.N.', 'Libertas Roma Eur', 'De Akker',
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

    # --- ambiguita' anagrafica Lazio: com'era, e cosa il merge D1 ha cambiato ---

    def test_lazio_ambiguity_removed_by_the_merge(self):
        """Il merge D1 (§8.7) ha reso univoca la discovery sui nomi Lazio.

        Sostituisce ``test_lazio_duplicate_is_decided_by_a_razor_thin_margin``,
        che fissava il RISCHIO che motivava D1: con due anagrafiche quasi
        identiche a DB, difflib le raggiungeva entrambe e sceglieva per rumore.

            PRIMA (due anagrafiche)      'SS Lazio Nuoto'
                -> 'ss. lazio nuoto'      0.8462   <- vinceva, Allievi
                -> 's.s. lazio nuoto'     0.8148
                scarto 0.0314

            DOPO (una anagrafica, D1)    'SS Lazio Nuoto'
                -> 's.s. lazio nuoto allievi'  0.6286
                -> 's.s. lazio nuoto'          0.8148   <- vince, Serie C
                scarto 0.1862

        Due cose da non confondere. La prima e' l'irrobustimento: lo scarto
        passa da 0.03 a 0.19, cioe' da rumore a segnale, e la risposta smette di
        dipendere da un punto e mezzo di differenza. La seconda e' che **il
        vincitore cambia**: la stessa grafia che prima andava agli Allievi ora
        va alla Serie C. E' l'effetto voluto — la scelta di prima era un
        accidente, non un giudizio — ma resta un cambiamento di SEMANTICA, non
        solo di robustezza, ed e' il motivo per cui i referti storici hanno
        bisogno dell'alias verificato dal test successivo.
        """
        allievi = self.teams['S.S. Lazio Nuoto Allievi']
        serie_c = self.teams['S.S. Lazio Nuoto']

        self.assertEqual(resolve_team_entity("SS Lazio Nuoto", self.all_teams), serie_c)

        probe = normalize_team_name("SS Lazio Nuoto")
        s_allievi = team_similarity(probe, normalize_team_name(allievi.name))
        s_serie_c = team_similarity(probe, normalize_team_name(serie_c.name))

        self.assertGreater(s_serie_c, s_allievi, "vince la Serie C, non gli Allievi")
        self.assertGreaterEqual(
            s_serie_c - s_allievi, 0.10,
            f"scarto {s_serie_c - s_allievi:.4f}: prima di D1 era 0.0314 (rumore), "
            f"dopo deve essere segnale",
        )
        self.assertGreaterEqual(s_serie_c, TEAM_FUZZY_THRESHOLD)

    def test_losing_spelling_still_resolves_through_the_alias(self):
        """I referti storici col nome vecchio non sono diventati orfani.

        ``SS. Lazio Nuoto`` era il nome della societa' eliminata da D1 e della
        sua squadra: prima del merge risolveva per exact match sugli Allievi.
        Il merge lo preserva come ``TeamAlias`` di origine ``ANAGRAFICA``, cosi'
        un referto gia' compilato con quella grafia continua a risolvere dove
        risolveva.

        Il test verifica che a decidere sia l'ALIAS e non il fuzzy, e lo fa
        mostrando che i due darebbero risposte DIVERSE: senza alias la grafia
        vecchia finirebbe sulla Serie C (0.9677 contro 0.7692), cioe' sulla
        squadra sbagliata. E' esattamente il danno che l'alias previene.
        """
        allievi = self.teams['S.S. Lazio Nuoto Allievi']
        serie_c = self.teams['S.S. Lazio Nuoto']
        grafia = "SS. Lazio Nuoto"

        # 1. Senza alias il fuzzy sbaglia squadra: e' la premessa del test.
        self.assertEqual(
            resolve_team_entity(grafia, self.all_teams), serie_c,
            "premessa: senza alias questa grafia finisce sulla Serie C",
        )

        # 2. Con l'alias creato da D1 la risposta cambia e torna corretta.
        TeamAlias.objects.create(
            team=allievi, alias=grafia, alias_normalized=TeamAlias.normalize(grafia),
            origin=TeamAlias.Origin.ANAGRAFICA,
            note="Grafia della Society eliminata dal merge D1 (§8.7).",
        )
        self.assertEqual(resolve_team_entity(grafia, self.all_teams), allievi)

        # 3. E' l'alias a decidere, non un cambio di punteggi: il fuzzy da solo
        #    continuerebbe a preferire la Serie C.
        probe = normalize_team_name(grafia)
        self.assertGreater(
            team_similarity(probe, normalize_team_name(serie_c.name)),
            team_similarity(probe, normalize_team_name(allievi.name)),
            "il fuzzy preferisce ancora la Serie C: a scavalcarlo e' l'alias",
        )
