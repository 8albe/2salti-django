import os
import django
import sys
from django.utils import timezone

# Setup Django
sys.path.insert(0, '/home/alberto')
os.environ['DEBUG'] = 'True'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from management.models import Membership, Training, TrainingOccurrence
from core.models import Society, Team, Sport
from matches.models import Match
from django.conf import settings

settings.ALLOWED_HOSTS.append('testserver')
User = get_user_model()

def run_verify():
    print("Inizio verifica RBAC Finale...")
    client = Client()
    
    # 1. Setup
    sport = Sport.objects.get_or_create(name='WP', slug='wp')[0]
    soc_a = Society.objects.get_or_create(name='Society A', slug='soc-a', sport=sport)[0]
    soc_b = Society.objects.get_or_create(name='Society B', slug='soc-b', sport=sport)[0]
    
    user_a = User.objects.get_or_create(username='user_a')[0]
    user_a.identity_status = 'VERIFIED'
    user_a.subscription_status = 'ACTIVE'
    user_a.save()
    
    # Membership so user_a is in Soc A
    Membership.objects.filter(user=user_a).delete()
    mem_a = Membership.objects.create(user=user_a, society=soc_a, role='HEAD_COACH', is_active=True)
    team_a = Team.objects.get_or_create(society=soc_a, category='SENIOR', slug='team-a')[0]
    mem_a.team = team_a
    mem_a.save()
    
    client.force_login(user_a)
    
    # --- TEST 1: Society Isolation (Management) ---
    team_b = Team.objects.get_or_create(society=soc_b, category='SENIOR', slug='team-b')[0]
    now = timezone.now()
    tr_b = Training.objects.create(society=soc_b, team=team_b, title='B Training', start_time=now, end_time=now + timezone.timedelta(hours=1))
    occ_b = TrainingOccurrence.objects.create(training=tr_b, start_time=now, end_time=now + timezone.timedelta(hours=1))
    
    print(f"Test 1: User A (Soc A) tenta RSVP a Training di Soc B (Proprietario Soc B)...")
    response = client.get(f'/management/trainings/rsvp/{occ_b.id}/')
    if response.status_code == 404:
        print("SUCCESS: Isolamento Socità funzionante (404).")
    else:
        print(f"FAIL: Accesso consentito o errore errato! ({response.status_code})")

    # --- TEST 2: Usability Fix (Access without slug) ---
    tr_a = Training.objects.create(society=soc_a, team=team_a, title='A Training', start_time=now, end_time=now + timezone.timedelta(hours=1))
    occ_a = TrainingOccurrence.objects.create(training=tr_a, start_time=now, end_time=now + timezone.timedelta(hours=1))
    
    print(f"Test 2: User A (Soc A) tenta RSVP a proprio Training (ID {occ_a.id}) SENZA SLUG...")
    response = client.get(f'/management/trainings/rsvp/{occ_a.id}/')
    if response.status_code == 200:
        print("SUCCESS: Usability fix funzionante (fallback a membership context).")
    else:
        print(f"FAIL: Accesso negato a proprio oggetto senza slug! ({response.status_code})")

    # --- TEST 3: Onboarding Gating ---
    user_unv = User.objects.get_or_create(username='unverified')[0]
    user_unv.identity_status = 'PENDING'
    user_unv.save()
    client.force_login(user_unv)
    
    print(f"Test 3: Utente non verificato ({user_unv.identity_status}) tenta accesso a Trainings...")
    response = client.get('/management/trainings/')
    print(f"Risposta: {response.status_code}, Redirect a: {response.url if response.status_code == 302 else 'N/A'}")
    if response.status_code == 302 and 'verify-identity' in response.url:
        print("SUCCESS: Onboarding gating funzionante (Redirect a verifica).")
    else:
        print(f"FAIL: Gating non funzionante!")

    # --- TEST 4: Staff-only Review Flow ---
    client.force_login(user_a) # User A is not staff
    print("Test 4: Utente non-staff tenta accesso a Report Review...")
    response = client.get('/matches/report/999/review/') # ID mock
    if response.status_code == 403:
        print("SUCCESS: Review flow protetto (Solo Staff/Superuser).")
    else:
        print(f"FAIL: Review flow accessibile a non-staff! ({response.status_code})")

    # --- TEST 5: RBAC Team Contribution (Chat) ---
    print(f"Test 5: User A tenta post in Chat del proprio Team A (senza slug)...")
    response = client.post(f'/management/team-chat/{team_a.id}/add/', {'content': 'Hello Team'})
    if response.status_code == 302: # Redirect after success match
        print("SUCCESS: Post in chat personale funzionante (con fallback).")
    else:
        print(f"FAIL: Post in propria chat negato! ({response.status_code})")

    print(f"Test 6: User A tenta post in Chat di Team B...")
    response = client.post(f'/management/team-chat/{team_b.id}/add/', {'content': 'Hacker post'})
    if response.status_code == 403:
        print("SUCCESS: Post in chat altrui negato correctly.")
    else:
        print(f"FAIL: Post in chat altrui consentito! ({response.status_code})")

    print("\n=== VERIFICA RBAC FINALE COMPLETATA ===")

if __name__ == '__main__':
    run_verify()
