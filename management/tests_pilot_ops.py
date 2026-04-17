"""
Tests for pilot operations models, services, and commands.
"""
from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from io import StringIO

from .models import PilotDailyLog, PilotBug, PilotFeedback, PilotReview, AuditLog
from .pilot_services import generate_daily_report_data, send_daily_report_email, check_and_send_urgent_alerts

User = get_user_model()


class PilotModelTestCase(TestCase):
    """Test all 4 pilot operations models."""

    def setUp(self):
        self.staff = User.objects.create_superuser('pilot_staff', 'staff@test.com', 'pass123')

    def test_pilot_daily_log_creation(self):
        log = PilotDailyLog.objects.create(
            date=date.today(),
            operator=self.staff,
            status='GREEN',
            blockers='None',
            notes='Day 1 pilot start',
            next_day_decision='Continue as planned',
        )
        self.assertEqual(str(log), f"{date.today()} — 🟢 Green — nominal")
        self.assertEqual(PilotDailyLog.objects.count(), 1)

    def test_pilot_daily_log_unique_date(self):
        PilotDailyLog.objects.create(date=date.today(), operator=self.staff, status='GREEN')
        with self.assertRaises(Exception):
            PilotDailyLog.objects.create(date=date.today(), operator=self.staff, status='YELLOW')

    def test_pilot_bug_creation(self):
        bug = PilotBug.objects.create(
            title='Login crash on empty email',
            severity='S1',
            reported_by=self.staff,
            role_context='Staff testing',
            observed_behavior='App crashes',
            expected_behavior='Validation error shown',
            reproducibility='ALWAYS',
            status='NEW',
        )
        self.assertIn('[S1]', str(bug))
        self.assertIn('NEW', str(bug))

    def test_pilot_feedback_creation(self):
        fb = PilotFeedback.objects.create(
            source='Coach Alberto',
            flow_step='Report Upload',
            summary='Upload button hard to find on mobile',
            impact='Delays report filing',
            category='UX_COPY',
        )
        self.assertIn('UX_COPY', str(fb))

    def test_pilot_review_creation(self):
        review = PilotReview.objects.create(
            review_date=date.today(),
            review_type='DAY_7',
            what_worked='Upload flow, OCR mock, standings update',
            blockers_summary='None critical',
            recommendation='CONTINUE',
            created_by=self.staff,
        )
        self.assertIn('Day 7', str(review))
        self.assertEqual(review.recommendation, 'CONTINUE')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PilotServicesTestCase(TestCase):
    """Test pilot email services."""

    def setUp(self):
        self.staff = User.objects.create_superuser('svc_staff', 'svc@test.com', 'pass123')

    def test_generate_daily_report_data_empty(self):
        """Report generation works even with no data."""
        data = generate_daily_report_data()
        self.assertEqual(data['overall_status'], 'NO_LOG')
        self.assertEqual(data['kpis']['new_bugs_count'], 0)

    def test_generate_daily_report_with_data(self):
        PilotDailyLog.objects.create(
            date=date.today(), operator=self.staff, status='YELLOW',
            blockers='OCR mock flaky', next_day_decision='Monitor closely',
        )
        PilotBug.objects.create(
            title='Test bug', severity='S2', reported_by=self.staff,
            observed_behavior='X', expected_behavior='Y',
        )
        data = generate_daily_report_data()
        self.assertEqual(data['overall_status'], 'YELLOW')
        self.assertEqual(data['kpis']['new_bugs_count'], 1)

    def test_send_daily_report_dry_run(self):
        """Dry run should NOT send email."""
        data, html = send_daily_report_email(dry_run=True)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn('2salti', html)

    def test_send_daily_report_real(self):
        """Real send should deliver email."""
        PilotDailyLog.objects.create(date=date.today(), operator=self.staff, status='GREEN')
        data, html = send_daily_report_email()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('[2salti Pilot]', mail.outbox[0].subject)

    def test_urgent_alerts_no_triggers(self):
        """No alerts when everything is green."""
        PilotDailyLog.objects.create(date=date.today(), operator=self.staff, status='GREEN')
        alerts = check_and_send_urgent_alerts()
        self.assertEqual(len(alerts), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_urgent_alerts_red_status(self):
        """Red daily log triggers alert."""
        PilotDailyLog.objects.create(
            date=date.today(), operator=self.staff, status='RED',
            blockers='System down',
        )
        alerts = check_and_send_urgent_alerts()
        self.assertTrue(any(a['trigger'] == 'PILOT_STATUS_RED' for a in alerts))
        self.assertEqual(len(mail.outbox), 1)

    def test_urgent_alerts_s1_no_workaround(self):
        """S1 bug without workaround triggers alert."""
        PilotBug.objects.create(
            title='Critical crash', severity='S1', reported_by=self.staff,
            observed_behavior='Crash', expected_behavior='No crash',
            workaround='',
        )
        alerts = check_and_send_urgent_alerts()
        self.assertTrue(any(a['trigger'] == 'S1_BUG_NO_WORKAROUND' for a in alerts))

    def test_urgent_alerts_dedup(self):
        """Second alert check on same day should not re-send."""
        PilotDailyLog.objects.create(date=date.today(), operator=self.staff, status='RED')
        check_and_send_urgent_alerts()
        self.assertEqual(len(mail.outbox), 1)
        # Second check — should not send again
        check_and_send_urgent_alerts()
        self.assertEqual(len(mail.outbox), 1)  # Still 1

    def test_urgent_alerts_blocker_accumulation(self):
        """3+ S1 bugs triggers accumulation alert."""
        for i in range(3):
            PilotBug.objects.create(
                title=f'Blocker {i}', severity='S1', reported_by=self.staff,
                observed_behavior='X', expected_behavior='Y', workaround='tmp fix',
            )
        alerts = check_and_send_urgent_alerts()
        self.assertTrue(any(a['trigger'] == 'BLOCKER_ACCUMULATION' for a in alerts))


class PilotCommandTestCase(TestCase):
    """Test management commands."""

    def setUp(self):
        self.staff = User.objects.create_superuser('cmd_staff', 'cmd@test.com', 'pass123')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_pilot_report_dry_run(self):
        out = StringIO()
        call_command('send_pilot_report', '--dry-run', stdout=out)
        output = out.getvalue()
        self.assertIn('DRY-RUN', output)
        self.assertIn('NOT sent', output)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_pilot_report_real(self):
        PilotDailyLog.objects.create(date=date.today(), operator=self.staff, status='GREEN')
        out = StringIO()
        call_command('send_pilot_report', stdout=out)
        output = out.getvalue()
        self.assertIn('successfully', output)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_check_pilot_alerts_command(self):
        out = StringIO()
        call_command('check_pilot_alerts', stdout=out)
        output = out.getvalue()
        self.assertIn('All clear', output)


class PilotAdminAccessTestCase(TestCase):
    """Test that pilot models are accessible only to staff."""

    def setUp(self):
        self.staff = User.objects.create_superuser('admin_test', 'admin@test.com', 'pass123')
        self.non_staff = User.objects.create_user('regular', 'regular@test.com', 'pass123')

    def test_staff_can_access_admin(self):
        self.client.login(username='admin_test', password='pass123')
        for model_name in ['pilotdailylog', 'pilotbug', 'pilotfeedback', 'pilotreview']:
            url = f'/admin/management/{model_name}/'
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f"Staff should access {model_name}")

    def test_non_staff_cannot_access_admin(self):
        self.client.login(username='regular', password='pass123')
        for model_name in ['pilotdailylog', 'pilotbug', 'pilotfeedback', 'pilotreview']:
            url = f'/admin/management/{model_name}/'
            response = self.client.get(url)
            self.assertIn(response.status_code, [302, 403], f"Non-staff should not access {model_name}")
