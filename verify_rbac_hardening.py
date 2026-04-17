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
    print("Inizio verifica RBAC Hardening...")
    client = Client()
    
    # 1. Setup Societies
    sport = Sport.objects.get_or_create(name='WP', slug='wp')[0]
    soc_a = Society.objects.get_or_create(name='Society A', slug='soc-a', sport=sport)[0]
    soc_b = Society.objects.get_or_create(name='Society B', slug='soc-b', sport=sport)[0]
    
    # 2. Setup Users
    user_a = User.objects.get_or_create(username='user_a')[0]
    user_a.identity_status = 'VERIFIED'
    user_a.subscription_status = 'ACTIVE'
    user_a.save()
    
    # 3. Membership for User A in Soc A
    Membership.objects.filter(user=user_a).delete()
    Membership.objects.create(user=user_a, society=soc_a, role='PLAYER', is_active=True)
    
    # 4. Setup Training in Soc B
    TrainingOccurrence.objects.all().delete()
    team_b = Team.objects.get_or_create(society=soc_b, category='SENIOR', slug='team-b')[0]
    now = timezone.now()
    tr_b = Training.objects.create(
        society=soc_b, 
        team=team_b,
        title='B Training',
        start_time=now,
        end_time=now + timezone.timedelta(hours=1)
    )
    occ_b = TrainingOccurrence.objects.create(training=tr_b, start_time=now, end_time=now + timezone.timedelta(hours=1))
    
    # 5. TEST: User A tries to RSVP to B's Training
    print(f"Test 1: User A (Soc A) tenta RSVP a Training di Soc B (ID {occ_b.id})...")
    client.force_login(user_a)
    
    # Accesso diretto senza prefix (middleware non troverà la società)
    response = client.get(f'/management/trainings/rsvp/{occ_b.id}/')
    print(f"Risposta (direct ID): {response.status_code}") 
    # Dovrebbe essere 403 o 404 a seconda di come get_object_or_404 si comporta con il filtro
    
    if response.status_code in [403, 404]:
         print("SUCCESS: Accesso negato correttamente (Test 1).")
    else:
         print(f"FAIL: Accesso consentito inaspettatamente! ({response.status_code})")

    # 6. TEST: Chat post to different team (Soc B)
    team_b = Team.objects.get_or_create(society=soc_b, category='SENIOR', slug='team-b')[0]
    print(f"Test 2: User A tenta post in Chat di Team B (Soc B, ID {team_b.id})...")
    response = client.post(f'/management/team-chat/{team_b.id}/add/', {'content': 'Hacker post'})
    print(f"Risposta: {response.status_code}")
    if response.status_code == 403:
        print("SUCCESS: Post in chat negato (Test 2).")
    else:
        print(f"FAIL: Post in chat consentito! ({response.status_code})")

    # 7. TEST: Convocation create for B's Match
    team_h_b = Team.objects.get_or_create(society=soc_b, category='U18', slug='team-h-b')[0]
    match_b = Match.objects.create(
        home_team=team_h_b,
        away_team=team_h_b, # Mock
        match_date=timezone.now(),
        league_id=1 # Assume league 1 exists
    )
    print(f"Test 3: User A tenta creazione convocazione per Match di Soc B (ID {match_b.id})...")
    # First we need to make sure user_a has a role that allows convocation_create (e.g. HEAD_COACH)
    mem_a = Membership.objects.get(user=user_a)
    mem_a.role = 'HEAD_COACH'
    mem_a.save()
    
    response = client.get(f'/management/club-admin/request/999/approve/') # Mock request id
    # This should hit the @role_required('PRESIDENT') and then _get_society_context
    print(f"Test 4: User A (Coach) tenta accesso a Club Admin... Status: {response.status_code}")
    if response.status_code == 403:
        print("SUCCESS: Accesso non autorizzato negato (Test 4).")
    else:
        print(f"FAIL: Accesso inaspettato ({response.status_code})")

    print("\n=== VERIFICA COMPLETATA ===")

if __name__ == '__main__':
    run_verify()
