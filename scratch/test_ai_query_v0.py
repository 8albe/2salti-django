import os
import sys
import django
import json
import re

# Add the project root to sys.path
sys.path.append('/home/alberto')

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

from django.test import Client
from matches.models import Match, MatchEvent, MatchReport
from core.models import Team, League, Sport
from accounts.models import AthleteProfile

def setup_test_data():
    # 1. Sport & League
    sport = Sport.objects.filter(name='Pallanuoto').first()
    if not sport:
        sport = Sport.objects.create(name='Pallanuoto', slug='pallanuoto')
    
    league = League.objects.filter(name='Serie A1').first()
    if not league:
        league = League.objects.create(name='Serie A1', sport=sport, season='2025/2026', slug='serie-a1')
    
    # 2. Teams
    team_a = Team.objects.filter(name='Pro Recco').first()
    if not team_a:
        team_a = Team.objects.create(name='Pro Recco', society_name='Pro Recco', league=league)
    
    # 3. Athlete: Marco Rossi
    rossi, created = User.objects.get_or_create(
        username='mrossi', 
        defaults={'first_name': 'Marco', 'last_name': 'Rossi', 'role': 'athlete'}
    )
    if not created:
        rossi.first_name = 'Marco'
        rossi.last_name = 'Rossi'
        rossi.role = 'athlete'
        rossi.save()
    
    # Ensure profile exists and has goals
    profile = rossi.athlete_profile
    profile.total_goals = 12
    profile.current_team = team_a
    profile.save()
    
    # 4. Matches & Events (for "last 5 matches" test)
    # Clear existing matches for Rossi to isolate test
    MatchEvent.objects.filter(player=rossi).delete()
    
    # Create 5 matches
    for i in range(5):
        m = Match.objects.create(
            league=league,
            home_team=team_a,
            away_team=team_a,
            match_date=django.utils.timezone.now() - django.utils.timezone.timedelta(days=i),
            is_finished=True,
            home_score=10,
            away_score=5
        )
        MatchReport.objects.create(match=m, status='PUBLISHED')
        # Each match has 2 goals for Rossi
        MatchEvent.objects.create(match=m, team=team_a, player=rossi, event_type='GOAL', minute=10, quarter=1)
        MatchEvent.objects.create(match=m, team=team_a, player=rossi, event_type='GOAL', minute=20, quarter=2)

    return rossi

def test_endpoint():
    c = Client()
    
    test_cases = [
        ("gol Rossi stagione", 200),
        ("quanti gol ha fatto Rossi", 200),
        ("gol Rossi ultime 3 partite", 200),
        ("gol Inesistente stagione", 200),
        ("quanti anni ha Rossi", 200),
    ]
    
    for query, expected_status in test_cases:
        print(f"\n--- Testing query: '{query}' ---")
        response = c.post('/matches/api/v1/ai/query/', 
                         data=json.dumps({'query': query}),
                         content_type='application/json')
        
        print(f"Status: {response.status_code}")
        try:
            print(f"Response: {json.dumps(response.json(), indent=2)}")
        except Exception as e:
            print(f"Error parsing JSON: {e}")
            print(f"Raw body: {response.content}")

if __name__ == "__main__":
    setup_test_data()
    test_endpoint()
