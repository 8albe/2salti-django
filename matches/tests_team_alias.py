"""Test del modello TeamAlias e della sua consultazione in discovery (fetta C1, 2026-07-21).

Gli alias coprono le divergenze di grafia REALI foglio↔DB (syllabus §8.6(a)):
`Olympic Roma P.N.` sul referto vs `Olimpic Roma P.N.` a DB, le due grafie di
Nautilus su fogli compilati da segretari diversi. NON coprono le allucinazioni
dell'OCR (§8.6(b)) — e i test lo verificano esplicitamente.
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import League, Society, Sport, Team, TeamAlias
from matches.services.ocr_service import resolve_team_entity

User = get_user_model()


class TeamAliasModelTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn-alias")
        self.league = League.objects.create(name="Lega Alias", sport=self.sport)
        self.soc_a = Society.objects.create(name="Olimpic Roma P.N.", slug="olimpic-alias", sport=self.sport)
        self.soc_b = Society.objects.create(name="Nautilus N. Roma", slug="nautilus-alias", sport=self.sport)
        self.team_a = Team.objects.create(society=self.soc_a, name="Olimpic Roma P.N.", league=self.league)
        self.team_b = Team.objects.create(society=self.soc_b, name="Nautilus N. Roma", league=self.league)

    def test_normalized_column_is_derived_on_save(self):
        alias = TeamAlias.objects.create(team=self.team_a, alias="  Olympic Roma P.N.  ")
        self.assertEqual(alias.alias, "Olympic Roma P.N.")
        self.assertEqual(alias.alias_normalized, "olympic roma p.n.")

    def test_uniqueness_is_case_insensitive(self):
        TeamAlias.objects.create(team=self.team_a, alias="Olympic Roma P.N.")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TeamAlias.objects.create(team=self.team_a, alias="OLYMPIC ROMA P.N.")

    def test_uniqueness_is_enforced_across_teams(self):
        """Lo stesso alias non puo' puntare a due squadre diverse: sarebbe ambiguo."""
        TeamAlias.objects.create(team=self.team_a, alias="Olympic Roma P.N.")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TeamAlias.objects.create(team=self.team_b, alias="olympic roma p.n.")

    def test_same_team_can_have_several_aliases(self):
        """E' il caso Nautilus: grafie diverse su fogli diversi, stessa squadra."""
        TeamAlias.objects.create(team=self.team_b, alias="Nautilus Roma")
        TeamAlias.objects.create(team=self.team_b, alias="Nautilus Nuoto Roma")
        self.assertEqual(self.team_b.aliases.count(), 2)

    def test_empty_alias_is_rejected_by_clean(self):
        for bad in ("", "   "):
            with self.subTest(alias=bad):
                with self.assertRaises(ValidationError):
                    TeamAlias(team=self.team_a, alias=bad).clean()

    def test_created_by_and_origin_are_recorded(self):
        user = User.objects.create_user(username="curatore", role="athlete")
        alias = TeamAlias.objects.create(
            team=self.team_a, alias="Olympic Roma P.N.", created_by=user,
            origin=TeamAlias.Origin.REFERTO, note="referto del 12/04/2026",
        )
        self.assertEqual(alias.created_by, user)
        self.assertEqual(alias.origin, TeamAlias.Origin.REFERTO)
        self.assertIsNotNone(alias.created_at)


class ResolveTeamEntityWithAliasTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn-alias-res")
        self.league = League.objects.create(name="Lega Alias Res", sport=self.sport)
        self.soc_olimpic = Society.objects.create(name="Olimpic Roma P.N.", slug="olimpic-res", sport=self.sport)
        self.soc_nautilus = Society.objects.create(name="Nautilus N. Roma", slug="nautilus-res", sport=self.sport)
        self.soc_bellator = Society.objects.create(name="Bellator Frusino", slug="bellator-res", sport=self.sport)
        self.olimpic = Team.objects.create(society=self.soc_olimpic, name="Olimpic Roma P.N.", league=self.league)
        self.nautilus = Team.objects.create(society=self.soc_nautilus, name="Nautilus N. Roma", league=self.league)
        self.bellator = Team.objects.create(society=self.soc_bellator, name="Bellator Frusino", league=self.league)
        self.all_teams = Team.objects.all()

    # --- i due casi fondativi di §8.6(a) ---

    def test_olympic_resolves_through_alias(self):
        """La grafia con la Y risolve verso il Team a DB, e lo fa PER ALIAS.

        Nota: su questo fixture il fuzzy posizionale ci arriverebbe comunque —
        `olympic` e `olimpic` differiscono di un carattere. Il punto dell'alias
        non e' rendere possibile cio' che era impossibile, e' rendere
        DETERMINISTICO cio' che dipendeva da una soglia: con l'alias la
        risoluzione non e' piu' esposta a un cambio di soglia, all'arrivo di una
        squadra dal nome simile, o al passaggio a un altro algoritmo di fuzzy.
        """
        TeamAlias.objects.create(team=self.olimpic, alias="Olympic Roma P.N.")
        self.assertEqual(resolve_team_entity("Olympic Roma P.N.", self.all_teams), self.olimpic)
        # e ci arriva davvero per alias, non per fuzzy:
        from matches.services.ocr_service import resolve_team_alias
        self.assertEqual(
            resolve_team_alias("olympic roma p.n.", self.all_teams), self.olimpic
        )

    def test_both_nautilus_spellings_resolve_through_aliases(self):
        TeamAlias.objects.create(team=self.nautilus, alias="Nautilus Roma")
        TeamAlias.objects.create(team=self.nautilus, alias="Nautilus Nuoto Roma")
        self.assertEqual(resolve_team_entity("Nautilus Roma", self.all_teams), self.nautilus)
        self.assertEqual(resolve_team_entity("NAUTILUS NUOTO ROMA", self.all_teams), self.nautilus)

    def test_alias_lookup_is_case_and_space_insensitive(self):
        TeamAlias.objects.create(team=self.olimpic, alias="Olympic Roma P.N.")
        self.assertEqual(resolve_team_entity("  olympic   roma   p.n.  ", self.all_teams), self.olimpic)

    # --- l'alias viene PRIMA del fuzzy, e vince ---

    def test_alias_takes_precedence_over_fuzzy(self):
        """Se un alias esiste, decide lui: e' verificato, il fuzzy indovina."""
        TeamAlias.objects.create(team=self.nautilus, alias="Olimpic Roma P.N.")
        self.assertEqual(resolve_team_entity("Olimpic Roma P.N.", self.all_teams), self.nautilus)

    def test_alias_is_restricted_to_the_given_queryset(self):
        """Un chiamante che restringe l'insieme non se lo vede aggirare dall'alias."""
        TeamAlias.objects.create(team=self.olimpic, alias="Olympic Roma P.N.")
        only_nautilus = Team.objects.filter(pk=self.nautilus.pk)
        self.assertIsNone(resolve_team_entity("Olympic Roma P.N.", only_nautilus))

    def test_alias_works_when_the_scope_is_a_plain_list(self):
        """`ocr_service` passa liste (`[match.home_team]`), non solo QuerySet."""
        TeamAlias.objects.create(team=self.olimpic, alias="Olympic Roma P.N.")
        self.assertEqual(resolve_team_entity("Olympic Roma P.N.", [self.olimpic]), self.olimpic)
        self.assertIsNone(resolve_team_entity("Olympic Roma P.N.", [self.nautilus]))

    # --- il fuzzy resta intatto come fallback ---

    def test_exact_match_still_works_without_any_alias(self):
        self.assertEqual(resolve_team_entity("Olimpic Roma P.N.", self.all_teams), self.olimpic)

    def test_fuzzy_fallback_is_unchanged_when_no_alias_matches(self):
        TeamAlias.objects.create(team=self.nautilus, alias="Nautilus Roma")
        self.assertEqual(resolve_team_entity("Bellator Frusino", self.all_teams), self.bellator)

    def test_unknown_name_still_resolves_to_nothing(self):
        self.assertIsNone(resolve_team_entity("Societa' Inesistente XYZ", self.all_teams))

    # --- cio' che gli alias NON devono fare ---

    def test_hallucinated_name_is_not_covered_by_the_alias_table(self):
        """§8.6(b): `BELLATOR FROSINONE` e' un'allucinazione, non una grafia.

        La tabella alias non la copre e non deve coprirla: non impara dagli
        output del modello. Che poi il fuzzy ci arrivi o no e' una questione
        separata, del fallback — qui si asserisce solo che l'alias non c'entra.
        """
        from matches.services.ocr_service import resolve_team_alias
        self.assertEqual(TeamAlias.objects.count(), 0)
        self.assertIsNone(resolve_team_alias("bellator frosinone", self.all_teams))

    def test_no_automatic_alias_creation_from_resolution(self):
        """Nessun percorso di risoluzione scrive alias: popolamento solo umano."""
        resolve_team_entity("Olympic Roma P.N.", self.all_teams)
        resolve_team_entity("BELLATOR FROSINONE", self.all_teams)
        resolve_team_entity("Nautilus Nuoto Roma", self.all_teams)
        self.assertEqual(TeamAlias.objects.count(), 0)


class NoAutomaticAliasSeedingAuditTest(TestCase):
    """Guardia anti-ruggine: nessun modulo non-admin crea TeamAlias.

    Deriva la lista dai file invece di elencarla a mano. Se un giro futuro
    aggiungesse un "impariamo gli alias dall'OCR", questo test lo fa emergere
    invece di lasciarlo passare in silenzio.
    """

    def test_teamalias_is_created_only_from_admin_or_tests(self):
        import re
        from pathlib import Path
        from django.conf import settings

        base = Path(settings.BASE_DIR)
        allowed_prefixes = ('core/admin.py', 'core/models.py')
        pattern = re.compile(r'TeamAlias(\.objects\.(create|get_or_create|bulk_create)|\s*\()')
        offenders = []

        for app in ('accounts', 'core', 'management', 'matches', 'seasons', 'config'):
            for path in (base / app).rglob('*.py'):
                rel = path.relative_to(base).as_posix()
                if rel.startswith(allowed_prefixes) or '/migrations/' in rel or '/tests' in rel:
                    continue
                for i, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                    if line.strip().startswith('#'):
                        continue
                    if pattern.search(line):
                        offenders.append(f"{rel}:{i}: {line.strip()}")

        self.assertEqual(
            offenders, [],
            "Creazione automatica di TeamAlias fuori dall'admin. Il popolamento "
            "degli alias e' un atto umano verificato sul cartaceo (C1):\n" + "\n".join(offenders)
        )
