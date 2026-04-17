import os
import django
import sys
from django.utils import timezone

# Setup Django
sys.path.insert(0, '/home/alberto')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from core.models import Sport, Society, Team, League
from matches.models import Match, MatchReport

from django.conf import settings
settings.ALLOWED_HOSTS.append('testserver')
User = get_user_model()

def run_verify():
    print("Inizio verifica Admin Validation Queue...")
    client = Client()
    
    # Setup Data
    sport = Sport.objects.get_or_create(name='WP', slug='wp')[0]
    soc = Society.objects.get_or_create(name='Soc', slug='soc', sport=sport)[0]
    league = League.objects.get_or_create(name='L1', sport=sport, category='SENIOR', slug='l1')[0]
    team = Team.objects.get_or_create(society=soc, category='SENIOR', league=league)[0]
    match = Match.objects.create(league=league, home_team=team, away_team=team, match_date=timezone.now())
    
    staff = User.objects.get_or_create(username='staff_user', is_staff=True)[0]
    player = User.objects.get_or_create(username='player_user', is_staff=False)[0]
    
    # Create reports with different statuses
    MatchReport.objects.all().delete()
    r1 = MatchReport.objects.create(match=match, uploader=player, status='UPLOADED')
    r2 = MatchReport.objects.create(match=match, uploader=player, status='PUBLISHED')
    
    # 1. Non-staff access
    client.force_login(player)
    response = client.get('/matches/queue/')
    if response.status_code == 403:
        print("SUCCESS: Accesso negato a non-staff (403).")
    else:
        print(f"FAIL: Accesso consentito a non-staff! ({response.status_code})")
        
    # 2. Staff access
    client.force_login(staff)
    response = client.get('/matches/queue/')
    if response.status_code == 200:
        print("SUCCESS: Accesso consentito a staff (200).")
        if b'Soc vs Soc' in response.content:
            print("SUCCESS: I report appaiono nella lista.")
    else:
        print(f"FAIL: Accesso negato a staff! ({response.status_code})")
        
    # 3. Filtering
    response = client.get('/matches/queue/?status=UPLOADED')
    if response.status_code == 200:
        content = response.content.decode()
        if 'Caricato (In attesa)' in content and 'Pubblicato' not in content:
            # Note: "Pubblicato" might be in the filter buttons, so I should be careful.
            # Best check: only 1 <tr> in <tbody>
            if content.count('<tr class="hover:bg-white/5') == 1:
                print("SUCCESS: Filtro per stato funzionante.")
            else:
                print(f"FAIL: Il filtro non sembra funzionare (Trovati {content.count('<tr class=')} righe).")

    print("\n=== VERIFICA COMPLETATA ===")

if __name__ == '__main__':
    run_verify()
