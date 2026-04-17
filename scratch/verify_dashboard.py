import os
import django
import sys
import json
from django.utils import timezone

# Setup
sys.path.insert(0, '/home/alberto')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from core.models import Sport, Society, Team, League
from matches.models import Match
from accounts.models import AthleteProfile, CoachProfile, PresidentProfile, AccountProfileLink

User = get_user_model()

def verify():
    c = Client()
    
    # 1. Setup Test Data
    print("--- Setting up test data ---")
    sport = Sport.objects.filter(name='Pallanuoto').first()
    if not sport:
        sport = Sport.objects.create(name='Pallanuoto', slug='pallanuoto-test')
    
    society = Society.objects.filter(name='Pro Recco Test').first()
    if not society:
        society = Society.objects.create(name='Pro Recco Test', slug='pro-recco-test', sport=sport)
        
    team = Team.objects.filter(society=society, category='SENIOR').first()
    if not team:
        team = Team.objects.create(society=society, category='SENIOR')
    
    # Club Admin
    admin_user = User.objects.filter(username='admin_test_v2').first()
    if not admin_user:
        admin_user = User.objects.create(username='admin_test_v2', email='admin2@test.com', role='president')
        admin_user.set_password('pass')
        admin_user.save()
    
    # Ensure profile exists
    pres_profile, _ = PresidentProfile.objects.get_or_create(user=admin_user)
    pres_profile.managed_society = society
    pres_profile.save()
    
    # Athlete (for claim)
    athl_user = User.objects.filter(username='athl_test_v2').first()
    if not athl_user:
        athl_user = User.objects.create(username='athl_test_v2', email='athl2@test.com', role='athlete')
    
    athl_profile, _ = AthleteProfile.objects.get_or_create(user=athl_user)
    athl_profile.current_team = team
    athl_profile.save()
    
    # Create a pending claim for the admin to see
    AccountProfileLink.objects.get_or_create(
        user=athl_user,
        athlete_profile=athl_profile,
        status='PENDING'
    )
    
    # Create a match without report for the alert
    league = League.objects.filter(sport=sport).first()
    if not league:
        league = League.objects.create(name='Serie A1 Test', sport=sport)
        
    Match.objects.get_or_create(
        league=league,
        home_team=team,
        away_team=team, 
        match_date=timezone.now() - timezone.timedelta(days=1),
        has_report=False
    )

    # 2. Test Club Admin Dashboard
    print("\n--- Testing Club Admin Dashboard ---")
    c.force_login(admin_user)
    resp = c.get('/api/dashboard/me')
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(json.dumps(data, indent=2))
    
    # 3. Test Athlete Dashboard
    print("\n--- Testing Athlete Dashboard ---")
    athl_user.identity_status = 'VERIFIED'
    athl_user.save()
    c.force_login(athl_user)
    resp = c.get('/api/dashboard/me')
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(json.dumps(data, indent=2))

if __name__ == '__main__':
    verify()
