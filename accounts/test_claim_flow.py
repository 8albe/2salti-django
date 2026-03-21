from django.test import TestCase, Client
from django.contrib.auth import get_user_model

User = get_user_model()

class ClaimFlowTest(TestCase):
    def test_claim_flow_skip(self):
        print("\\n1. Creazione Utente")
        user = User.objects.create_user(
            username='test_claim_user',
            email='test_claim@example.com',
            password='Password123!',
            role='athlete',
            first_name='Test',
            last_name='Claim',
            identity_status='UNVERIFIED',
            subscription_status='INACTIVE'
        )
        self.client.force_login(user)
        
        print("2. Verify Identity")
        response_id = self.client.post('/accounts/verify-identity/', {'method': 'spid'})
        self.assertEqual(response_id.status_code, 302)
        
        print("3. Process Payment")
        response_pay = self.client.post('/accounts/payment/', {'action': 'pay'})
        self.assertEqual(response_pay.status_code, 302)
        
        print("4. Claim Profile (Skip)")
        response_claim = self.client.post('/accounts/claim-profile/', {'action': 'skip'})
        self.assertEqual(response_claim.status_code, 302)
        
        print("Verifica completata con successo!")
