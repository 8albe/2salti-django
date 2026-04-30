from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.models import Sport, Society, Team
from management.models import Membership, Training, TrainingOccurrence
from django.core.exceptions import PermissionDenied

User = get_user_model()

class RBACTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="WP", slug="wp")
        self.soc_a = Society.objects.create(name="Soc A", slug="soc-a", sport=self.sport)
        self.soc_b = Society.objects.create(name="Soc B", slug="soc-b", sport=self.sport)
        
        # User in Soc A
        self.user_a = User.objects.create_user(username='user_a', role='athlete', identity_status='VERIFIED', subscription_status='ACTIVE', setup_completed=True)
        Membership.objects.create(user=self.user_a, society=self.soc_a, role='PLAYER', is_active=True)
        
        # Training in Soc B
        self.team_b = Team.objects.get_or_create(society=self.soc_b, category='SENIOR', slug='team-b')[0]
        now = timezone.now()
        self.tr_b = Training.objects.create(
            society=self.soc_b, team=self.team_b, title='B Training',
            start_time=now, end_time=now + timezone.timedelta(hours=1)
        )
        self.occ_b = TrainingOccurrence.objects.create(training=self.tr_b, start_time=now, end_time=now + timezone.timedelta(hours=1))

    def test_society_isolation_training_rsvp(self):
        self.client.force_login(self.user_a)
        # Try to RSVP to Soc B's training
        response = self.client.get(f'/management/trainings/rsvp/{self.occ_b.id}/')
        # Since it's filtered by user's society context (fallback), it should 404
        self.assertEqual(response.status_code, 404)

    def test_onboarding_gating_unverified(self):
        user_unv = User.objects.create_user(username='unv', identity_status='UNVERIFIED')
        self.client.force_login(user_unv)
        response = self.client.get('/management/trainings/')
        self.assertRedirects(response, '/accounts/verify-identity/')

    def test_society_isolation_chat_add(self):
        self.client.force_login(self.user_a)
        # Try to post to Team B's chat
        response = self.client.post(f'/management/team-chat/{self.team_b.id}/add/', {'content': 'Hacker'})
        self.assertEqual(response.status_code, 403)
