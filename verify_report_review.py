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
from matches.models import Match, MatchReport, League
from core.models import Team, Sport
from django.conf import settings

settings.ALLOWED_HOSTS.append('testserver')
User = get_user_model()

def run_verify():
    print("Inizio verifica flow Manual Match Report Review...")
    client = Client()
    
    # 1. Setup Admin
    admin_user = User.objects.filter(username='admin_reviewer').first()
    if not admin_user:
        admin_user = User.objects.create_superuser('admin_reviewer', 'admin@test.com', 'Admin123!')
    client.force_login(admin_user)
    
    # 2. Setup Match & Report
    from core.models import Society
    sport = Sport.objects.get_or_create(name='Pallanuoto', slug='pallanuoto')[0]
    league, _ = League.objects.get_or_create(
        name='Serie A1',
        season='2024-2025',
        category='SENIOR',
        sport=sport,
        defaults={'slug': 'a1-test-review'}
    )
    soc_h = Society.objects.get_or_create(name='Pro Recco', slug='pro-recco')[0]
    soc_a = Society.objects.get_or_create(name='AN Brescia', slug='an-brescia')[0]
    team_h, _ = Team.objects.get_or_create(society=soc_h, category='SENIOR', league=league)
    team_a, _ = Team.objects.get_or_create(society=soc_a, category='SENIOR', league=league)
    
    match = Match.objects.create(
        league=league,
        home_team=team_h,
        away_team=team_a,
        match_date=timezone.now(),
        home_score=0,
        away_score=0,
        is_finished=False
    )
    
    report = MatchReport.objects.create(
        match=match,
        status='UPLOADED',
        file='match_reports/test_report.pdf' # Mock file path
    )
    
    print(f"Creato Match ID: {match.id}, Report ID: {report.id}")
    
    # 3. Invio Revisione
    print("Inviando revisione manuale (Score: 10-8, Status: PUBLISHED)...")
    response = client.post(f'/matches/report/{report.id}/review/', {
        'home_score': 10,
        'away_score': 8,
        'is_finished': 'on', # Checkbox
        'report_status': 'PUBLISHED',
        'validation_notes': 'Verificato manualmente. Tutto OK.'
    })
    
    print(f"Status Code: {response.status_code}")
    if response.status_code == 302:
        print(f"Redirect a: {response.url}")
        
    # 4. Verifica nel DB
    match.refresh_from_db()
    report.refresh_from_db()
    
    success = True
    if match.home_score == 10 and match.away_score == 8 and match.is_finished:
        print("SUCCESS: Risultato Match aggiornato correttamente.")
    else:
        print(f"FAIL: Risultato Match NON aggiornato! ({match.home_score}-{match.away_score})")
        success = False
        
    if report.status == 'PUBLISHED':
        print("SUCCESS: Stato Report aggiornato a PUBLISHED.")
    else:
        print(f"FAIL: Stato Report è {report.status}")
        success = False
        
    if success:
        print("\n=== VERIFICA COMPLETATA CON SUCCESSO ===")
    else:
        print("\n=== VERIFICA FALLITA ===")

if __name__ == '__main__':
    run_verify()
