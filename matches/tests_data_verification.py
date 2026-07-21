"""Test del seam `set_data_verified` (fetta B1, 2026-07-21).

`Match.is_data_verified` decide, insieme ai referti PUBLISHED, se il risultato di
una partita e' pubblico. Ogni sua scrittura deve passare da qui e lasciare traccia.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import League, Society, Sport, Team
from management.models import AuditLog
from matches.models import Match
from matches.services.data_verification_service import AUDIT_ACTION, set_data_verified

User = get_user_model()


class SetDataVerifiedTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn-dv")
        self.soc_home = Society.objects.create(name="SocHome", slug="soc-home-dv", sport=self.sport)
        self.soc_away = Society.objects.create(name="SocAway", slug="soc-away-dv", sport=self.sport)
        self.league = League.objects.create(name="Lega DV", sport=self.sport)
        self.home = Team.objects.create(society=self.soc_home, name="Home DV", league=self.league)
        self.away = Team.objects.create(society=self.soc_away, name="Away DV", league=self.league)
        self.match = Match.objects.create(
            league=self.league, home_team=self.home, away_team=self.away,
            match_date=timezone.now(),
        )
        self.user = User.objects.create_user(username="verificatore", role="athlete")

    # --- comportamento base ---

    def test_set_true_writes_flag_and_audit(self):
        changed = set_data_verified(self.match, True, self.user, "collazione sul cartaceo")
        self.assertTrue(changed)

        self.match.refresh_from_db()
        self.assertTrue(self.match.is_data_verified)

        log = AuditLog.objects.get(action=AUDIT_ACTION)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.target_id, str(self.match.pk))
        self.assertEqual(log.target_type, 'Match')
        self.assertEqual(log.details['from'], False)
        self.assertEqual(log.details['to'], True)
        self.assertEqual(log.details['reason'], "collazione sul cartaceo")
        self.assertEqual(log.details['match_id'], self.match.pk)

    def test_set_false_is_audited_too(self):
        """Anche togliere la verifica e' un atto: va tracciato come metterla."""
        set_data_verified(self.match, True, self.user, "prima collazione")
        set_data_verified(self.match, False, self.user, "collazione smentita dal cartaceo")

        logs = list(AuditLog.objects.filter(action=AUDIT_ACTION).order_by('id'))
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[-1].details['from'], True)
        self.assertEqual(logs[-1].details['to'], False)

    def test_idempotent_no_op_writes_no_audit(self):
        set_data_verified(self.match, True, self.user, "prima volta")
        AuditLog.objects.all().delete()

        changed = set_data_verified(self.match, True, self.user, "seconda volta, stesso valore")
        self.assertFalse(changed)
        self.assertEqual(AuditLog.objects.filter(action=AUDIT_ACTION).count(), 0)

    def test_society_is_attached_to_the_audit_row(self):
        set_data_verified(self.match, True, self.user, "collazione")
        log = AuditLog.objects.get(action=AUDIT_ACTION)
        self.assertEqual(log.society, self.soc_home)

    # --- contratto: reason obbligatoria ---

    def test_empty_reason_is_rejected(self):
        for bad in ("", "   ", None):
            with self.subTest(reason=bad):
                with self.assertRaises(ValueError):
                    set_data_verified(self.match, True, self.user, bad)
        self.match.refresh_from_db()
        self.assertFalse(self.match.is_data_verified)
        self.assertEqual(AuditLog.objects.filter(action=AUDIT_ACTION).count(), 0)

    def test_non_boolean_value_is_rejected(self):
        for bad in (1, "True", None):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    set_data_verified(self.match, bad, self.user, "motivo valido")
        self.match.refresh_from_db()
        self.assertFalse(self.match.is_data_verified)

    def test_system_actor_is_allowed(self):
        """user=None e' ammesso per data migration e comandi, con reason esplicita."""
        changed = set_data_verified(self.match, True, None, "data migration 0021, sistema")
        self.assertTrue(changed)
        log = AuditLog.objects.get(action=AUDIT_ACTION)
        self.assertIsNone(log.user)

    # --- effetto osservabile: il gate del risultato pubblico ---

    def test_seam_drives_public_result_visibility(self):
        from matches.services.result_visibility import is_result_public

        self.assertFalse(is_result_public(self.match))
        set_data_verified(self.match, True, self.user, "collazione sul cartaceo")
        self.match.refresh_from_db()
        self.assertTrue(is_result_public(self.match))

    # --- guardia anti-ruggine: nessuna scrittura diretta fuori dal seam ---

    def test_no_direct_writes_outside_the_seam(self):
        """Scandisce il codice applicativo: `is_data_verified = ...` solo nel seam.

        Deriva la lista dai file invece di elencarla a mano, come l'audit dei
        template di §8.5(h): un nuovo punto di scrittura fa fallire la suite da
        solo, invece di passare inosservato.
        """
        import re
        from pathlib import Path
        from django.conf import settings

        base = Path(settings.BASE_DIR)
        allowed = {
            'matches/services/data_verification_service.py',  # il seam stesso
        }
        # Assegnazione ad ATTRIBUTO: prende `x.is_data_verified = ...` e non i
        # kwarg tipo `Match.objects.filter(is_data_verified=True)`, che sono letture.
        pattern = re.compile(r'\.is_data_verified\s*=\s*(?!=)')
        offenders = []

        for app in ('accounts', 'core', 'management', 'matches', 'seasons', 'config'):
            for path in (base / app).rglob('*.py'):
                rel = path.relative_to(base).as_posix()
                if rel in allowed:
                    continue
                if '/migrations/' in rel or '/tests' in rel or rel.startswith('tests'):
                    continue
                text = path.read_text(encoding='utf-8')
                for i, line in enumerate(text.splitlines(), 1):
                    stripped = line.strip()
                    if stripped.startswith('#'):
                        continue
                    if pattern.search(line):
                        offenders.append(f"{rel}:{i}: {stripped}")

        self.assertEqual(
            offenders, [],
            "Scrittura diretta di is_data_verified fuori dal seam. Usare "
            "matches.services.data_verification_service.set_data_verified():\n"
            + "\n".join(offenders)
        )

    def test_the_audit_guard_can_actually_fail(self):
        """Guardia anti-ruggine della guardia: la regex deve riconoscere il caso."""
        import re
        pattern = re.compile(r'\.is_data_verified\s*=\s*(?!=)')
        self.assertTrue(pattern.search("        match.is_data_verified = True"))
        self.assertTrue(pattern.search("obj.is_data_verified=False"))
        self.assertFalse(pattern.search("if match.is_data_verified == True:"))
        self.assertFalse(pattern.search("Match.objects.filter(is_data_verified=True)"))
