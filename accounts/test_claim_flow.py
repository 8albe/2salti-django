from django.test import TestCase, Client
from django.contrib.auth import get_user_model

User = get_user_model()

class ClaimFlowTest(TestCase):
    def test_claim_profile_success(self):
        # 1. Setup User and Onboarding
        user = User.objects.create_user(
            username='real_user',
            email='real@example.com',
            password='Password123!',
            role='athlete',
            identity_status='VERIFIED',
            subscription_status='ACTIVE'
        )
        self.client.force_login(user)
        
        # 2. Setup a "Ghost" Profile to claim
        ghost_user = User.objects.create_user(username='ghost_player', role='athlete')
        ghost_profile = ghost_user.athlete_profile # Created by signal
        
        # 3. POST Claim
        response = self.client.post('/accounts/claim-profile/', {
            'action': 'claim',
            'profile_id': ghost_profile.id,
            'role': 'athlete'
        })
        
        # 4. Verify
        self.assertRedirects(response, '/management/team-access/')
        from .models import AccountProfileLink
        link = AccountProfileLink.objects.filter(user=user, athlete_profile=ghost_profile).first()
        self.assertIsNotNone(link)
        self.assertEqual(link.status, 'PENDING')
