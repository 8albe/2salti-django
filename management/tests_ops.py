from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from core.models import Sport, Society, Team, League
from matches.models import Match, MatchReport

User = get_user_model()

class OpsDashboardTestCase(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="OpsSport", slug="opssport")
        self.society = Society.objects.create(name="Ops Society", slug="ops-soc", sport=self.sport)
        self.league = League.objects.create(name="Ops League", sport=self.sport, season="2023/24")
        self.team = Team.objects.create(society=self.society, league=self.league)
        
        # Staff user
        self.staff_user = User.objects.create_superuser('ops_admin', 'ops@2salti.com', 'pass123')
        
        # 1. Stuck Reports Setup
        now = timezone.now()
        # Not stuck (recent)
        self.report_recent = MatchReport.objects.create(
            match=Match.objects.create(home_team=self.team, away_team=self.team, league=self.league, match_date=now),
            status='UPLOADED',
            created_at=now
        )
        # Stuck (old)
        old_time = now - timedelta(hours=5)
        self.match_old = Match.objects.create(home_team=self.team, away_team=self.team, league=self.league, match_date=old_time)
        self.report_stuck = MatchReport.objects.create(
            match=self.match_old,
            status='EXTRACTED',
        )
        # Update created_at using .filter().update() because auto_now_add=True
        MatchReport.objects.filter(id=self.report_stuck.id).update(created_at=old_time)

        # 2. Blocked Users Setup
        # IDENTITY_PENDING
        User.objects.create(username="blocked_identity", role='athlete', identity_status='UNVERIFIED')
        # PAYMENT_PENDING
        User.objects.create(username="blocked_payment", role='athlete', identity_status='VERIFIED', onboarding_payment_done=False)
        # SETUP_PENDING
        User.objects.create(username="blocked_setup", role='athlete', identity_status='VERIFIED', onboarding_payment_done=True, setup_completed=False)

    def test_dashboard_metrics_logic(self):
        self.client.login(username='ops_admin', password='pass123')
        response = self.client.get(reverse('staff_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check Stuck Reports
        stuck_reports = response.context['stuck_reports']
        self.assertEqual(len(stuck_reports), 1)
        self.assertEqual(stuck_reports[0].id, self.report_stuck.id)
        
        # Check Onboarding Stats
        stats = response.context['onboarding_stats']
        self.assertEqual(stats['IDENTITY_PENDING'], 1)
        self.assertEqual(stats['PAYMENT_PENDING'], 1)
        self.assertEqual(stats['SETUP_PENDING'], 1)
        
        # Check Content
        self.assertContains(response, "PILOT MODE ACTIVE")
        self.assertContains(response, "SIMULATED")
