"""Test del management command comp_society (wiring comped a regime, Opzione 1).

Il command identifica la società per nome + sport e passa dal seam
``set_society_comped`` (audit ``ENTITLEMENT_SOCIETY_COMPED_CHANGED`` con
``source='comp_society_command'``). Copre: grant, revoke, idempotenza,
lookup fallito (0 match) e ambiguo (>1 match) senza effetti collaterali.
"""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from core.models import Sport, Society
from management.models import AuditLog


class CompSocietyCommandTests(TestCase):

    def setUp(self):
        self.sport = Sport.objects.create(name='Pallanuoto Cmd')
        self.society = Society.objects.create(
            name='CmdSoc', sport=self.sport, city='Roma')

    def _run(self, *args, **kwargs):
        out = StringIO()
        call_command('comp_society', *args, stdout=out, **kwargs)
        return out.getvalue()

    def test_grant_sets_comped_via_seam_and_logs(self):
        out = self._run('CmdSoc', sport='Pallanuoto Cmd')
        self.society.refresh_from_db()
        self.assertTrue(self.society.is_comped)
        self.assertTrue(self.society.is_club_pro)
        log = AuditLog.objects.get(action='ENTITLEMENT_SOCIETY_COMPED_CHANGED')
        self.assertEqual(log.details['source'], 'comp_society_command')
        self.assertEqual(log.details['from'], False)
        self.assertEqual(log.details['to'], True)
        self.assertIn('False -> True', out)

    def test_revoke_resets_comped_and_logs(self):
        self._run('CmdSoc', sport='Pallanuoto Cmd')
        out = self._run('CmdSoc', sport='Pallanuoto Cmd', revoke=True)
        self.society.refresh_from_db()
        self.assertFalse(self.society.is_comped)
        revoked = AuditLog.objects.filter(
            action='ENTITLEMENT_SOCIETY_COMPED_CHANGED',
            details__to=False)
        self.assertEqual(revoked.count(), 1)
        self.assertIn('True -> False', out)

    def test_rerun_is_idempotent_no_extra_audit(self):
        self._run('CmdSoc', sport='Pallanuoto Cmd')
        out = self._run('CmdSoc', sport='Pallanuoto Cmd')
        self.society.refresh_from_db()
        self.assertTrue(self.society.is_comped)
        self.assertEqual(
            AuditLog.objects.filter(action='ENTITLEMENT_SOCIETY_COMPED_CHANGED').count(), 1)
        self.assertIn('Nessun cambiamento', out)

    def test_lookup_case_insensitive(self):
        self._run('cmdsoc', sport='pallanuoto cmd')
        self.society.refresh_from_db()
        self.assertTrue(self.society.is_comped)

    def test_zero_matches_errors_without_action(self):
        with self.assertRaises(CommandError) as ctx:
            self._run('Inesistente', sport='Pallanuoto Cmd')
        self.assertIn('Nessuna società trovata', str(ctx.exception))
        self.society.refresh_from_db()
        self.assertFalse(self.society.is_comped)
        self.assertFalse(AuditLog.objects.filter(
            action='ENTITLEMENT_SOCIETY_COMPED_CHANGED').exists())

    def test_multiple_matches_errors_without_action(self):
        # Slug esplicito: l'auto-slug da name collide sull'unique con l'omonima.
        Society.objects.create(name='CmdSoc', slug='cmdsoc-milano',
                               sport=self.sport, city='Milano')
        with self.assertRaises(CommandError) as ctx:
            self._run('CmdSoc', sport='Pallanuoto Cmd')
        self.assertIn('Lookup ambiguo', str(ctx.exception))
        self.assertFalse(Society.objects.filter(is_comped=True).exists())
        self.assertFalse(AuditLog.objects.filter(
            action='ENTITLEMENT_SOCIETY_COMPED_CHANGED').exists())
