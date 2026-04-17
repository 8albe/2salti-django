import os
import django
import sys

# Setup Django
sys.path.insert(0, '/home/alberto')
os.environ['DEBUG'] = 'True'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from accounts.models import AthleteProfile, AccountProfileLink
from django.conf import settings

settings.ALLOWED_HOSTS.append('testserver')

User = get_user_model()

def run_verify():
    print("Inizio verifica finale del flow Claim Profile...")
    client = Client()
    
    # 1. Setup Dati
    username = 'verify_user'
    User.objects.filter(username=username).delete()
    user = User.objects.create_user(
        username=username,
        email='verify@example.com',
        password='Password123!',
        role='athlete',
        identity_status='VERIFIED',
        subscription_status='ACTIVE'
    )
    client.force_login(user)
    
    # Creamo un profilo atleta da "claimare"
    target_user_name = 'target_athlete'
    User.objects.filter(username=target_user_name).delete()
    target_user = User.objects.create_user(
        username=target_user_name,
        first_name='Mario',
        last_name='Rossi',
        role='athlete'
    )
    target_profile = target_user.athlete_profile # Creato dal signal
    
    print(f"2. Invio richiesta di claim per il profilo {target_profile}")
    response = client.post('/accounts/claim-profile/', {
        'profile_id': target_profile.id,
        'role': 'athlete'
    })
    
    print(f"Status Code: {response.status_code}")
    if response.status_code != 302:
        print(f"Response Content: {response.content.decode()[:500]}")
    if response.status_code == 302:
        print(f"Redirect a: {response.url}")
        
    # 3. Verifica nel DB
    link = AccountProfileLink.objects.filter(user=user, athlete_profile=target_profile).first()
    if link:
        print(f"SUCCESS: Record AccountProfileLink trovato! Status: {link.status}")
    else:
        print("FAIL: Record AccountProfileLink NON trovato!")
        
    # Cleanup
    # User.objects.filter(username__in=[username, target_user_name]).delete()
    print("\nVerifica completata.")

if __name__ == '__main__':
    run_verify()
