"""
Copertura parametrica di TUTTI gli stati di MatchReport su TUTTE le superfici
che mostrano o contano referti (Macro 22, giro 2).

Origine (2026-07-19): l'introduzione dello stato `QUEUED` ha rotto 7 punti su
14 che enumeravano gli stati a mano, e la suite era verde. Nessun test forzava
un referto attraverso le pagine in ogni stato possibile, e ogni catena
`{% if status == '...' %}` aveva un ramo `{% else %}` che assorbiva in silenzio
lo stato nuovo: il badge diventava grigio, il KPI perdeva un referto, e nessuno
se ne accorgeva.

Il giro 1 aveva coperto cosi' solo la review page e il cockpit. Qui la stessa
tecnica copre ogni superficie rimasta: admin changelist e changeform, coda
referti, dashboard staff, filtri, endpoint di stato.

Due regole di costruzione, entrambe deliberate:

1. **La checklist si deriva da `Status.choices`, mai da una lista scritta qui.**
   Un decimo stato aggiunto domani entra in copertura da solo e fa fallire la
   suite finche' non e' classificato. Una lista scritta a mano avrebbe lo
   stesso difetto che questi test esistono per eliminare.

2. **Le mappe di presentazione si verificano per totalita', non per valore.**
   Non si asserisce che PUBLISHED sia verde — e' una scelta estetica che puo'
   cambiare — ma che *ogni* stato abbia un tono, un bucket e una classe in ogni
   tema. E' l'esaustivita' che si rompe da sola, non il colore.
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
from matches.status_presentation import (
    BUCKETS,
    OPEN_STATUSES,
    PALETTES,
    PIPELINE_STATUSES,
    SETTLED_STATUSES,
    TONE_BY_STATUS,
    TONES,
    bucket_for,
    classes_for,
    tone_for,
)

User = get_user_model()

# LA fonte di verita' di ogni test in questo modulo. Non sostituire con una
# lista letterale: e' il meccanismo che rende automatica la copertura futura.
ALL_STATUSES = [s for s, _ in MatchReport.Status.choices]


class StatusPresentationTotalityTest(TestCase):
    """
    Le mappe di presentazione coprono ogni stato dichiarato.

    Questi test sono il cuore della guardia: se qualcuno aggiunge uno stato al
    modello e non lo classifica, qui si accende un rosso immediato con un
    messaggio che dice esattamente cosa fare.
    """

    def test_every_status_has_a_tone(self):
        missing = [s for s in ALL_STATUSES if s not in TONE_BY_STATUS]
        self.assertEqual(
            missing, [],
            f"Stati senza tono in status_presentation.TONE_BY_STATUS: {missing}. "
            "Assegna un tono, altrimenti il badge cade sul grigio neutro in ogni pagina.",
        )

    def test_no_tone_mapping_for_a_status_that_no_longer_exists(self):
        """Guardia contro la ruggine opposta: uno stato rimosso dal modello."""
        stale = [s for s in TONE_BY_STATUS if s not in ALL_STATUSES]
        self.assertEqual(stale, [], f"Toni per stati inesistenti: {stale}")

    def test_every_tone_is_defined_in_every_palette(self):
        for theme, palette in PALETTES.items():
            for tone in TONES:
                with self.subTest(theme=theme, tone=tone):
                    self.assertIn(
                        tone, palette,
                        f"Il tema '{theme}' non definisce il tono '{tone}'.",
                    )

    def test_every_status_resolves_to_classes_in_every_theme(self):
        for status in ALL_STATUSES:
            for theme in PALETTES:
                with self.subTest(status=status, theme=theme):
                    self.assertTrue(classes_for(status, theme))

    def test_buckets_are_a_total_partition_of_the_statuses(self):
        """
        Ogni stato in esattamente un bucket: ne' perso, ne' contato due volte.

        E' l'invariante che rende i KPI del cockpit affidabili. Prima DRAFT non
        era in nessun bucket e i referti in bozza non comparivano in nessuna
        metrica.
        """
        assigned = [s for members in BUCKETS.values() for s in members]
        self.assertEqual(
            sorted(assigned), sorted(ALL_STATUSES),
            "I bucket operativi non partizionano gli stati: controlla BUCKETS. "
            f"Assegnati={sorted(assigned)} vs dichiarati={sorted(ALL_STATUSES)}",
        )
        self.assertEqual(len(assigned), len(set(assigned)), "Uno stato compare in piu' bucket")

    def test_bucket_for_resolves_every_status(self):
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                self.assertIn(bucket_for(status), BUCKETS)

    def test_open_statuses_is_the_exact_complement_of_settled(self):
        self.assertEqual(OPEN_STATUSES | SETTLED_STATUSES, set(ALL_STATUSES))
        self.assertEqual(OPEN_STATUSES & SETTLED_STATUSES, set())

    def test_pipeline_statuses_are_the_ones_the_worker_advances(self):
        """
        Gli stati "non finali" per il polling sono esattamente quelli in cui il
        worker fara' avanzare il referto da solo. Se un nuovo stato transitorio
        non finisce qui, il client smette di aggiornare la pagina su un referto
        ancora in lavorazione.
        """
        self.assertEqual(
            PIPELINE_STATUSES,
            {MatchReport.Status.QUEUED, MatchReport.Status.PROCESSING},
        )
        for status in PIPELINE_STATUSES:
            with self.subTest(status=status):
                self.assertIn(status, ALL_STATUSES)
                self.assertEqual(bucket_for(status), 'in_flight')


class ReportPagesAllStatusesTest(TestCase):
    """
    Ogni pagina che mostra referti risponde 200 con un referto in ogni stato.

    Un referto senza partita collegata e' il caso peggiore realistico (upload
    asincrono: il referto nasce prima che l'OCR trovi la partita), quindi ogni
    pagina viene esercitata in entrambe le configurazioni.
    """

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.league = League.objects.create(
            name="Serie A1", sport=self.sport, season="2024", slug="serie-a1"
        )
        soc_h = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco")
        soc_a = Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia")
        self.team_h = Team.objects.create(society=soc_h, league=self.league)
        self.team_a = Team.objects.create(society=soc_a, league=self.league)
        self.match = Match.objects.create(
            league=self.league, home_team=self.team_h, away_team=self.team_a,
            match_date=timezone.now(), location="Sori",
        )
        self.admin = User.objects.create_superuser(
            username='admin', password='password', email='admin@test.com'
        )
        self.admin.identity_status = 'VERIFIED'
        self.admin.save()
        self.client = Client()
        self.client.login(username='admin', password='password')

    # --- coda referti (front-office staff) --------------------------------

    def test_report_queue_renders_with_a_report_in_each_status(self):
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                report = MatchReport.objects.create(match=self.match, status=status)
                response = self.client.get(reverse('report_queue'))
                self.assertEqual(response.status_code, 200)
                report.delete()

    def test_report_queue_renders_without_match_in_each_status(self):
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                report = MatchReport.objects.create(match=None, status=status)
                response = self.client.get(reverse('report_queue'))
                self.assertEqual(response.status_code, 200)
                report.delete()

    def test_report_queue_status_filter_works_for_each_status(self):
        """
        Il filtro per stato e' esposto come pill nella pagina: ogni valore di
        `Status.choices` deve essere un filtro valido che ritorna il referto
        giusto e non esplode.
        """
        reports = {
            status: MatchReport.objects.create(match=self.match, status=status)
            for status in ALL_STATUSES
        }
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                response = self.client.get(reverse('report_queue'), {'status': status})
                self.assertEqual(response.status_code, 200)
                ids = [r.id for r in response.context['reports']]
                self.assertEqual(ids, [reports[status].id])

    def test_report_queue_shows_the_translated_label_not_the_raw_code(self):
        """Lo staff deve leggere 'Revisione Tecnica Necessaria', non 'NEEDS_REVIEW'."""
        MatchReport.objects.create(match=self.match, status=MatchReport.Status.NEEDS_REVIEW)
        response = self.client.get(reverse('report_queue'))
        self.assertContains(response, "Revisione Tecnica Necessaria")

    # --- dettaglio partita (pagina pubblica con pallino di stato) ---------

    def test_match_detail_renders_with_a_report_in_each_status(self):
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                report = MatchReport.objects.create(match=self.match, status=status)
                response = self.client.get(reverse('match_detail', args=[self.match.id]))
                self.assertEqual(response.status_code, 200)
                report.delete()

    # --- cockpit e dashboard staff ----------------------------------------

    def test_ops_cockpit_renders_with_a_report_in_each_status(self):
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                report = MatchReport.objects.create(match=self.match, status=status)
                response = self.client.get(reverse('ops_cockpit'))
                self.assertEqual(response.status_code, 200)
                report.delete()

    def test_ops_cockpit_counts_every_status_in_exactly_one_kpi(self):
        """
        Un referto per stato: la somma dei bucket deve fare il totale.

        E' il test che avrebbe intercettato sia il buco di QUEUED sia quello di
        DRAFT — entrambi referti reali che non comparivano in nessun KPI.
        """
        for status in ALL_STATUSES:
            MatchReport.objects.create(match=self.match, status=status)

        response = self.client.get(reverse('ops_cockpit'))
        self.assertEqual(response.status_code, 200)
        stats = response.context['stats']

        # published_24h e' una metrica temporale, non un bucket: si esclude dal
        # conteggio di partizione e si verifica a parte.
        counted = sum(stats[b] for b in BUCKETS)
        self.assertEqual(
            counted, len(ALL_STATUSES),
            f"I KPI del cockpit contano {counted} referti su {len(ALL_STATUSES)}: "
            "qualche stato non ricade in nessun bucket.",
        )

    def test_staff_dashboard_renders_with_a_report_in_each_status(self):
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                report = MatchReport.objects.create(match=self.match, status=status)
                response = self.client.get(reverse('staff_dashboard'))
                self.assertEqual(response.status_code, 200)
                report.delete()

    def test_staff_dashboard_funnel_lists_every_status(self):
        response = self.client.get(reverse('staff_dashboard'))
        self.assertEqual(response.status_code, 200)
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                self.assertIn(status, response.context['report_stats'])

    # --- admin: changelist e changeform ------------------------------------

    def test_admin_changelist_renders_with_a_report_in_each_status(self):
        url = reverse('admin:matches_matchreport_changelist')
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                report = MatchReport.objects.create(match=self.match, status=status)
                self.assertEqual(self.client.get(url).status_code, 200)
                report.delete()

    def test_admin_changelist_filters_by_each_status(self):
        url = reverse('admin:matches_matchreport_changelist')
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                report = MatchReport.objects.create(match=self.match, status=status)
                response = self.client.get(url, {'status__exact': status})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    [r.id for r in response.context['cl'].queryset], [report.id]
                )
                report.delete()

    def test_admin_changeform_renders_with_a_report_in_each_status(self):
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                report = MatchReport.objects.create(match=self.match, status=status)
                url = reverse('admin:matches_matchreport_change', args=[report.id])
                self.assertEqual(self.client.get(url).status_code, 200)
                report.delete()

    def test_admin_changeform_renders_without_match_in_each_status(self):
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                report = MatchReport.objects.create(match=None, status=status)
                url = reverse('admin:matches_matchreport_change', args=[report.id])
                self.assertEqual(self.client.get(url).status_code, 200)
                report.delete()

    def test_admin_status_colored_gives_a_distinct_color_to_draft(self):
        """
        Regressione puntuale: DRAFT mancava dal dizionario colori dell'admin e
        cadeva sul fallback, diventando indistinguibile da REJECTED.
        """
        self.assertNotEqual(
            classes_for(MatchReport.Status.DRAFT, 'admin'),
            classes_for(MatchReport.Status.REJECTED, 'admin'),
        )

    def test_admin_changelist_kpi_counts_open_reports_in_each_status(self):
        url = reverse('admin:matches_matchreport_changelist')
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                report = MatchReport.objects.create(match=self.match, status=status)
                response = self.client.get(url)
                expected = 0 if status in SETTLED_STATUSES else 1
                self.assertEqual(response.context_data['queue_kpi']['total'], expected)
                report.delete()

    # --- endpoint di stato (polling client) --------------------------------

    def test_status_endpoint_answers_for_each_status(self):
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                report = MatchReport.objects.create(
                    match=self.match, status=status, uploader=self.admin,
                )
                response = self.client.get(
                    reverse('api_report_status', args=[report.id])
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload['status'], status)
                # L'etichetta non deve mai essere vuota ne' il codice grezzo.
                self.assertTrue(payload['status_display'])
                self.assertEqual(
                    payload['is_final'], status not in PIPELINE_STATUSES,
                    f"is_final sbagliato per {status}: il client smetterebbe di "
                    "fare polling (o non smetterebbe mai).",
                )
                report.delete()


class TemplateStatusChainAuditTest(TestCase):
    """
    Audit sui template: nessuna catena `{% if %}` che enumeri stati a mano.

    Stessa tecnica dell'audit sul gate di visibilita' del risultato
    (`tests_result_visibility.TemplateScoreExposureAuditTest`): si scandisce il
    filesystem invece di tenere una lista scritta a mano, cosi' un template
    *nuovo* che reintroduce il pattern viene intercettato da solo — che e'
    esattamente il caso che una checklist umana non copre.

    Quello che si vieta e' il confronto inline con un codice di stato letterale.
    La via corretta e' `{{ report.status|status_classes:'tema' }}`, che passa
    dalla mappa unica in `matches.status_presentation`.
    """

    # Confronto con un letterale che assomiglia a un codice di stato referto:
    # {% if report.status == 'PUBLISHED' %} e varianti (elif, !=, doppi apici).
    STATUS_COMPARISON = re.compile(
        r"\.status\s*[!=]=\s*['\"](" + "|".join(ALL_STATUSES) + r")['\"]"
    )

    # Template autorizzati a mantenere una catena inline, con la ragione.
    # Ogni voce e' un debito dichiarato, non un'assoluzione implicita.
    ALLOWED = {
        # Changeform custom dell'admin: distingue un solo stato per evidenziare
        # il banner di revisione tecnica, non e' una tassonomia di colori.
        "admin/matches/matchreport/review.html",
        # Review page: i due `if` non colorano nulla, accendono il banner di
        # polling OCR e quello di supporto. Sono logica di flusso, non di
        # presentazione, e la lista corretta e' PIPELINE_STATUSES (vedi sotto).
        "matches/report_review.html",
    }

    def _template_root(self):
        return Path(settings.BASE_DIR) / "templates"

    def test_no_template_enumerates_report_statuses_inline(self):
        root = self._template_root()
        offenders = []
        for path in sorted(root.rglob("*.html")):
            rel = str(path.relative_to(root))
            if rel in self.ALLOWED:
                continue
            if self.STATUS_COMPARISON.search(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(rel)

        self.assertEqual(
            offenders, [],
            "Questi template confrontano lo stato di un referto con un codice "
            f"letterale: {offenders}. Usa {{{{ report.status|status_classes:'tema' }}}} "
            "(load report_status), oppure dichiara il template in ALLOWED "
            "spiegando perche'. Una catena inline non fallisce quando nasce uno "
            "stato nuovo: diventa semplicemente grigia.",
        )

    def test_the_audit_regex_still_matches_something(self):
        """
        Guardia anti-ruggine: se la regex smette di trovare anche solo i casi
        dichiarati in ALLOWED, non sta piu' controllando nulla e il test di
        sopra passerebbe per vuoto.
        """
        root = self._template_root()
        matched = [
            rel for rel in self.ALLOWED
            if (root / rel).exists()
            and self.STATUS_COMPARISON.search(
                (root / rel).read_text(encoding="utf-8", errors="ignore")
            )
        ]
        self.assertTrue(
            matched,
            "La regex dell'audit non trova piu' alcuna catena di stato, "
            "nemmeno nei template in ALLOWED: va rivista, non sta piu' guardando nulla.",
        )

    def test_allowlist_entries_still_exist(self):
        """Un template in ALLOWED che sparisce lascia un'eccezione fantasma."""
        root = self._template_root()
        missing = [rel for rel in sorted(self.ALLOWED) if not (root / rel).exists()]
        self.assertEqual(
            missing, [],
            f"Template in ALLOWED non piu' esistenti: {missing}. Rimuovili dalla lista.",
        )

    def test_templates_using_the_filter_load_the_tag_library(self):
        """
        `{{ x|status_classes }}` senza `{% load report_status %}` non e' un
        errore rumoroso in Django: il filtro non si applica e la stringa esce
        vuota, quindi il badge perde il colore in silenzio.
        """
        root = self._template_root()
        offenders = []
        for path in sorted(root.rglob("*.html")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            uses = "status_classes" in text or "status_label" in text
            if uses and "{% load report_status %}" not in text:
                offenders.append(str(path.relative_to(root)))
        self.assertEqual(
            offenders, [],
            f"Template che usano i filtri di stato senza caricarli: {offenders}",
        )
