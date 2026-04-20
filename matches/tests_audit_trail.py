from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from core.models import Sport, Society, League, Team
from matches.models import Match, MatchReport, MatchReportAuditLog

User = get_user_model()


class AuditTrailTestCase(TestCase):
    def setUp(self):
        self.sport   = Sport.objects.create(name="Test Sport", slug="test-sport-audit")
        self.society = Society.objects.create(name="Test Society", sport=self.sport, slug="test-soc-audit")
        self.league  = League.objects.create(name="Test League", sport=self.sport)
        self.team    = Team.objects.create(society=self.society, league=self.league)
        self.match   = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.team,
            match_date=timezone.now()
        )
        self.report  = MatchReport.objects.create(
            match=self.match, status=MatchReport.Status.UPLOADED
        )
        self.user    = User.objects.create_superuser(
            username="audit_admin", email="audit@test.com", password="pass"
        )

    def test_model_fields_exist(self):
        field_names = [f.name for f in MatchReportAuditLog._meta.get_fields()]
        self.assertIn('old_status', field_names)
        self.assertIn('new_status', field_names)
        self.assertIn('reason', field_names)

    def test_create_full_audit_log(self):
        log = MatchReportAuditLog.objects.create(
            report=self.report,
            user=self.user,
            action='validate',
            old_status='UPLOADED',
            new_status='VALIDATED',
            reason='Dati verificati manualmente',
            before={'teams': {'home': {'score': 4}}},
            after={'teams': {'home': {'score': 5}}},
        )
        self.assertIsNotNone(log.pk)
        self.assertEqual(log.old_status, 'UPLOADED')
        self.assertEqual(log.new_status, 'VALIDATED')
        self.assertIn('manualmente', log.reason)
        self.assertIsNotNone(log.before)
        self.assertIsNotNone(log.after)

    def test_str_includes_status_change(self):
        log = MatchReportAuditLog.objects.create(
            report=self.report,
            user=self.user,
            action='validate',
            old_status='UPLOADED',
            new_status='VALIDATED',
        )
        self.assertIn('(UPLOADED -> VALIDATED)', str(log))

    def test_str_omits_transition_when_no_statuses(self):
        # old_status e new_status omessi → None nel DB → condizione falsy nel __str__
        log = MatchReportAuditLog.objects.create(report=self.report, action='edit')
        self.assertNotIn('->', str(log))

    def test_save_draft_log(self):
        log = MatchReportAuditLog.objects.create(
            report=self.report,
            user=self.user,
            action='save_draft',
            old_status='UPLOADED',
            new_status='UPLOADED',
            reason='',
            before={'teams': {'home': {'score': 5}}},
            after={'teams': {'home': {'score': 6}}},
        )
        self.assertIsNotNone(log.pk)
        self.assertEqual(log.old_status, log.new_status)
        self.assertEqual(log.reason, '')

    def test_publish_log(self):
        log = MatchReportAuditLog.objects.create(
            report=self.report,
            user=self.user,
            action='publish',
            old_status='VALIDATED',
            new_status='PUBLISHED',
            reason='Dati corretti, pronto per il pubblico',
        )
        self.assertIsNotNone(log.pk)
        self.assertEqual(log.old_status, 'VALIDATED')
        self.assertEqual(log.new_status, 'PUBLISHED')
        self.assertGreater(len(log.reason), 0)

    def test_depublish_log(self):
        log = MatchReportAuditLog.objects.create(
            report=self.report,
            user=self.user,
            action='depublish',
            old_status='PUBLISHED',
            new_status='VALIDATED',
            reason='Superato da nuova versione (Report ID 999)',
        )
        self.assertIsNotNone(log.pk)
        self.assertEqual(log.old_status, 'PUBLISHED')
        self.assertEqual(log.new_status, 'VALIDATED')
        self.assertIn('Report ID 999', log.reason)

    def test_publish_force_log(self):
        log = MatchReportAuditLog.objects.create(
            report=self.report,
            user=self.user,
            action='publish_force',
            old_status='NEEDS_REVIEW',
            new_status='PUBLISHED',
            reason='Override: blocchi ignorati per urgenza operativa',
        )
        self.assertIsNotNone(log.pk)
        self.assertEqual(log.action, 'publish_force')
        self.assertIn('Override', log.reason)

    def test_query_audit_trail_counts(self):
        # Crea i 5 log dello scenario originale in modo indipendente
        base = {'report': self.report, 'user': self.user}
        MatchReportAuditLog.objects.create(**base, action='validate',
            old_status='UPLOADED', new_status='VALIDATED', reason='Verifica manuale')
        MatchReportAuditLog.objects.create(**base, action='save_draft',
            old_status='UPLOADED', new_status='UPLOADED', reason='')
        MatchReportAuditLog.objects.create(**base, action='publish',
            old_status='VALIDATED', new_status='PUBLISHED', reason='Pronto per il pubblico')
        MatchReportAuditLog.objects.create(**base, action='depublish',
            old_status='PUBLISHED', new_status='VALIDATED', reason='Superato da Report ID 999')
        MatchReportAuditLog.objects.create(**base, action='publish_force',
            old_status='NEEDS_REVIEW', new_status='PUBLISHED', reason='Override urgenza')

        all_logs = MatchReportAuditLog.objects.filter(report=self.report)
        self.assertEqual(all_logs.count(), 5)

        logs_with_reason = all_logs.exclude(reason='')
        self.assertEqual(logs_with_reason.count(), 4)  # save_draft non ha reason
