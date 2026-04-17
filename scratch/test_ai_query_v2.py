import os
import sys
import django
import json
from dotenv import load_dotenv

# Load env variables from .env
load_dotenv()

# Setup Django
sys.path.append('/home/alberto')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from matches.models import Match, MatchEvent, MatchReport
from core.models import Team, League, Sport
from accounts.models import User, AthleteProfile

def setup_test_data():
    # 1. League
    sport, _ = Sport.objects.get_or_create(name='Pallanuoto', defaults={'slug': 'pallanuoto'})
    league, _ = League.objects.get_or_create(name='Serie A1', defaults={'sport': sport, 'season': '2025/2026', 'slug': 'serie-a1'})
    
    # 2. Team & Athlete
    team, _ = Team.objects.get_or_create(name='Pro Recco', defaults={'league': league})
    
    bianchi, created = User.objects.get_or_create(
        username='jbianchi',
        defaults={'first_name': 'Jacopo', 'last_name': 'Bianchi', 'role': 'athlete'}
    )
    profile, _ = AthleteProfile.objects.get_or_create(user=bianchi)
    profile.current_team = team
    profile.save()
    
    # 3. Match & Report
    match = Match.objects.create(
        league=league, home_team=team, away_team=team, 
        match_date=django.utils.timezone.now(), is_finished=True
    )
    MatchReport.objects.create(match=match, status='PUBLISHED')
    
    # 4. Events (2 goals for Bianchi)
    MatchEvent.objects.create(match=match, team=team, player=bianchi, event_type='GOAL', minute=5, quarter=1)
    MatchEvent.objects.create(match=match, team=team, player=bianchi, event_type='GOAL', minute=15, quarter=2)
    
    return league, bianchi

def test_queries():
    c = Client()
    
    test_cases = [
        "Mostrami la classifica della Serie A1",
        "Quanti gol ha segnato Bianchi nell'ultima partita?"
    ]
    
    for query in test_cases:
        print(f"\n>>> QUERY: {query}")
        response = c.post('/api/v1/ai-query/', 
                         data=json.dumps({'query': query}),
                         content_type='application/json')
        
        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"Type: {data.get('type')}")
        print(f"Text: {data.get('text')}")
        if data.get('target_url'):
            print(f"Target URL: {data.get('target_url')}")
        if data.get('data'):
            print(f"Data: {json.dumps(data.get('data'), indent=2)}")

if __name__ == "__main__":
    setup_test_data()
    test_queries()
