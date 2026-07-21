"""Criterio di aggiornamento della classifica — decisione di prodotto ratificata.

**Se un test di questo file fallisce, si sta toccando una decisione di prodotto,
non un dettaglio implementativo.** Prima di "aggiustare" l'asserzione, leggere
`docs/syllabus/8_ocr_affidabilita.md` §8.5 e `docs/BLUEPRINT.md` §14.

Ratifica del 2026-07-21 (Alberto), testualmente: *"la classifica si aggiorna solo
quando una partita è stata ufficialmente letta e confermata da un referto, e usando
i dati che stanno sul referto."*

Il corollario operativo è la parte che questi test proteggono: ``is_data_verified``
**non deve mai** entrare nel criterio delle classifiche. È stata rifiutata
esplicitamente la "doppia strada" del gate del risultato pubblico
(``matches/services/result_visibility.py``: ``is_data_verified=True`` **oppure**
referto ``PUBLISHED``). Le due cose divergono per disegno, e la divergenza è
accettata: ``is_data_verified`` è un **atto umano** — una dichiarazione — mentre la
classifica deve poggiare su un **artefatto verificabile**, il referto pubblicato.

Conseguenza visibile e accettata consapevolmente: una partita può mostrare il
risultato al pubblico (via ``is_data_verified``) e contemporaneamente pesare zero in
classifica (perché nessun referto è ``PUBLISHED``). Non è un bug da correggere in UI
aggirando il criterio. L'unica strada per popolare le classifiche è correggere i
``normalized_data`` dei referti e pubblicarli (OPS_RUNBOOK §10.22).

Questi test **fissano lo status quo**: alla data della ratifica il codice si comporta
già così. Non introducono un comportamento nuovo, gli impediscono di cambiare in
silenzio.
"""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import League, LeagueStanding, Season, Society, Sport, Team
from matches.models import Match, MatchReport
from matches.services.data_verification_service import set_data_verified
from matches.services.publishing_service import PublishingService
from matches.services.standings_service import StandingsService

User = get_user_model()

HOME_GOALS = 10
AWAY_GOALS = 5


class StandingsCriterionTest(TestCase):
    """Il criterio è la PUBBLICAZIONE del referto, non il flag ``is_data_verified``."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.season = Season.objects.create(sport=self.sport, label='2025/2026', is_current=True)
        self.soc_a = Society.objects.create(name="Soc A", slug="soc-a", sport=self.sport)
        self.soc_b = Society.objects.create(name="Soc B", slug="soc-b", sport=self.sport)
        self.league = League.objects.create(name="A1", sport=self.sport, slug="a1")

        self.t1 = Team.objects.create(society=self.soc_a, league=self.league, name="T1")
        self.t2 = Team.objects.create(society=self.soc_b, league=self.league, name="T2")

        self.staff = User.objects.create_user(username='staff_verifier', role='admin')

        # La partita è CONCLUSA e col punteggio già a DB: è lo scenario reale di
        # prod al 2026-07-21 (match corretti a mano, referti mai pubblicati).
        self.match = Match.objects.create(
            league=self.league, home_team=self.t1, away_team=self.t2,
            home_score=HOME_GOALS, away_score=AWAY_GOALS,
            is_finished=True, match_date=timezone.now(),
        )

        # Roster riconciliabile: serve al guardrail "0 eventi con score positivo"
        # di PublishingService, non al criterio in sé.
        self.home_athletes = self._make_athletes(self.t1, 'T1Player', HOME_GOALS)
        self.away_athletes = self._make_athletes(self.t2, 'T2Player', AWAY_GOALS)

        self.report = MatchReport.objects.create(
            match=self.match, status='VALIDATED',
            normalized_data=self._normalized_data(),
        )

    def _make_athletes(self, team, prefix, count):
        athletes = []
        for i in range(count):
            u = User.objects.create_user(
                username=f'{prefix}_{i}', first_name=f'{prefix}{i}', last_name='Test',
                role='athlete', identity_status='VERIFIED',
                onboarding_payment_done=True, setup_completed=True,
            )
            profile = u.athlete_profile
            profile.current_team = team
            profile.save(update_fields=['current_team'])
            athletes.append(u)
        return athletes

    def _normalized_data(self):
        events = []
        for i in range(HOME_GOALS):
            events.append({"type": "GOAL", "team": "home", "minute": i + 1,
                           "player_name": f"T1Player{i} Test"})
        for i in range(AWAY_GOALS):
            events.append({"type": "GOAL", "team": "away", "minute": HOME_GOALS + i + 1,
                           "player_name": f"T2Player{i} Test"})
        return {
            'metadata': {'confidence': 0.9},
            'match_info': {'home_team': 'Soc A', 'away_team': 'Soc B', 'date': '2026-03-26'},
            'scores': {'final_score': f'{HOME_GOALS}-{AWAY_GOALS}', 'quarters': {}},
            'teams': {
                'home': {'name': 'Soc A', 'score': HOME_GOALS, 'players': [{'name': 'P1', 'number': 1}]},
                'away': {'name': 'Soc B', 'score': AWAY_GOALS, 'players': [{'name': 'P2', 'number': 1}]},
            },
            'events': events,
            'reconciliation': {
                'home_team_id': self.t1.id,
                'away_team_id': self.t2.id,
                'home_players': {f"T1Player{i} Test": self.home_athletes[i].id
                                 for i in range(HOME_GOALS)},
                'away_players': {f"T2Player{i} Test": self.away_athletes[i].id
                                 for i in range(AWAY_GOALS)},
            },
        }

    def _standing(self, team):
        return LeagueStanding.objects.get(league=self.league, team=team)

    # --- il test comportamentale che vale per tutti gli altri ---

    def test_publication_decides_the_standings_not_the_verified_flag(self):
        """`is_data_verified=True` non popola la classifica; il publish sì.

        I due assert vanno letti **insieme**: sono la stessa partita, con lo stesso
        punteggio a DB, nello stesso stato `is_finished`. L'unica variabile che
        cambia fra la prima metà e la seconda è l'esistenza di un referto
        `PUBLISHED`. Se la classifica si popolasse già nella prima metà, la
        ratifica del 2026-07-21 (syllabus §8.5) sarebbe violata.
        """
        # (1) Dato dichiarato verificato da un umano, nessun referto pubblicato.
        changed = set_data_verified(
            self.match, True, self.staff,
            "collazione sul cartaceo — test del criterio classifica",
        )
        self.assertTrue(changed)
        self.match.refresh_from_db()
        self.assertTrue(self.match.is_data_verified)
        self.assertFalse(
            MatchReport.objects.filter(match=self.match, status='PUBLISHED').exists()
        )

        StandingsService.rebuild_for_league(self.league)

        # Le righe esistono come placeholder, ma sono a ZERO: la partita non conta.
        for team in (self.t1, self.t2):
            s = self._standing(team)
            self.assertEqual(s.played, 0, f"{team}: `is_data_verified` non deve far contare la partita")
            self.assertEqual(s.won, 0)
            self.assertEqual(s.lost, 0)
            self.assertEqual(s.drawn, 0)
            self.assertEqual(s.points, 0)
            self.assertEqual(s.goals_for, 0)
            self.assertEqual(s.goals_against, 0)
            self.assertEqual(s.goal_diff, 0)

        # (2) Stessa partita, stesso flag: cambia solo che ora il referto è pubblicato.
        success, msg = PublishingService.publish_report(self.report, user=self.staff)
        self.assertTrue(success, msg)

        s1, s2 = self._standing(self.t1), self._standing(self.t2)
        self.assertEqual(s1.played, 1)
        self.assertEqual(s1.won, 1)
        self.assertEqual(s1.points, 3)
        self.assertEqual(s1.goals_for, HOME_GOALS)
        self.assertEqual(s1.goals_against, AWAY_GOALS)
        self.assertEqual(s2.played, 1)
        self.assertEqual(s2.lost, 1)
        self.assertEqual(s2.points, 0)

    def test_verified_flag_alone_never_reaches_the_standings_queryset(self):
        """Controprova diretta sul criterio, senza passare dal publish.

        Un match `is_finished=True` e `is_data_verified=True` con referto in uno
        stato **qualsiasi tranne** `PUBLISHED` non deve mai entrare nel conteggio.
        Copre gli stati intermedi in cui vive oggi la popolazione di prod
        (`NEEDS_REVIEW`) e quelli da cui si passa per pubblicare (`VALIDATED`).
        """
        set_data_verified(self.match, True, self.staff, "controprova criterio classifica")

        for status in ('DRAFT', 'UPLOADED', 'PROCESSING', 'EXTRACTED',
                       'NEEDS_REVIEW', 'VALIDATED', 'REJECTED'):
            with self.subTest(report_status=status):
                MatchReport.objects.filter(pk=self.report.pk).update(status=status)
                StandingsService.rebuild_for_league(self.league)
                self.assertEqual(
                    self._standing(self.t1).played, 0,
                    f"stato referto {status}: solo PUBLISHED deve far contare la partita",
                )
                self.assertEqual(self._standing(self.t1).points, 0)

    def test_public_result_gate_and_standings_criterion_diverge_by_design(self):
        """L'asimmetria accettata: risultato pubblico visibile, classifica a zero.

        È lo scenario osservato su prod il 2026-07-21 (lega 4) e la ragione per cui
        la decisione è stata portata alla ratifica. Il test lo fissa **come atteso**:
        se un giorno i due criteri tornassero a coincidere, è una scelta di prodotto
        da rifare, non un allineamento tecnico da dare per scontato.
        """
        from matches.services.result_visibility import is_result_public

        set_data_verified(self.match, True, self.staff, "asimmetria gate/classifica")
        self.match.refresh_from_db()
        StandingsService.rebuild_for_league(self.league)

        self.assertTrue(is_result_public(self.match), "il gate pubblico usa is_data_verified")
        self.assertEqual(self._standing(self.t1).played, 0, "la classifica no")


class StandingsCriterionSourceGuardTest(TestCase):
    """Guardia anti-ruggine sul sorgente, stessa forma di quella di `set_data_verified`.

    Il test comportamentale sopra prova cosa fa il codice **oggi**; questa guardia
    intercetta l'accoppiamento **appena viene scritto**, anche se qualcuno lo
    introducesse in un ramo non coperto dai test. Le due cose sono complementari:
    la ratifica del 2026-07-21 (syllabus §8.5) riguarda il criterio, non una riga.
    """

    #: Unico punto di verità delle classifiche (CLAUDE.md, protected file).
    STANDINGS_SERVICE = 'matches/services/standings_service.py'

    #: `is_data_verified` in qualunque forma: lettura, filtro, kwarg, attributo.
    #: Qui non si distingue lettura da scrittura — nel servizio delle classifiche
    #: anche solo **leggerlo** significherebbe averlo messo nel criterio.
    PATTERN = re.compile(r'is_data_verified')

    @classmethod
    def _significant_lines(cls, text):
        """Righe di codice vero: niente commenti, niente righe vuote.

        Un commento che *cita* la decisione ("qui NON si usa is_data_verified")
        è documentazione desiderabile, non una violazione.
        """
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            yield i, stripped

    def test_standings_service_never_mentions_the_verified_flag(self):
        path = Path(settings.BASE_DIR) / self.STANDINGS_SERVICE
        self.assertTrue(path.exists(), f"{self.STANDINGS_SERVICE} non trovato: percorso da aggiornare")

        offenders = [
            f"{self.STANDINGS_SERVICE}:{i}: {line}"
            for i, line in self._significant_lines(path.read_text(encoding='utf-8'))
            if self.PATTERN.search(line)
        ]

        self.assertEqual(
            offenders, [],
            "`is_data_verified` è comparso in StandingsService. Questo contraddice la "
            "decisione di prodotto ratificata il 2026-07-21 (docs/syllabus/"
            "8_ocr_affidabilita.md §8.5, docs/BLUEPRINT.md §14): la classifica si "
            "aggiorna SOLO al publish di un referto. Se la decisione è cambiata, "
            "aggiornare prima la documentazione e poi questo test.\n"
            + "\n".join(offenders)
        )

    def test_the_guard_can_actually_fail(self):
        """Guardia della guardia: la scansione deve riconoscere il caso che cerca.

        Senza questo, un refactor che rompesse `_significant_lines` o il pattern
        renderebbe il test sopra verde per sempre — la stessa classe di problema
        del test `REAL_TEAMS` hardcoded di §8.7.
        """
        offending_source = (
            "def _calculate_expected_standings(league):\n"
            "    matches = Match.objects.filter(is_data_verified=True)\n"
        )
        found = [line for _, line in self._significant_lines(offending_source)
                 if self.PATTERN.search(line)]
        self.assertEqual(len(found), 1, "la guardia non riconosce l'accoppiamento che deve vietare")

        commented_source = (
            "# NOTA: is_data_verified NON entra qui — ratifica 2026-07-21.\n"
            "matches = Match.objects.filter(reports__status='PUBLISHED')\n"
        )
        self.assertEqual(
            [line for _, line in self._significant_lines(commented_source)
             if self.PATTERN.search(line)],
            [],
            "un commento che cita la decisione non è una violazione",
        )
