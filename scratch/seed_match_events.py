import os
import sys
import django
import random
from datetime import datetime, timedelta

# Setup Django environment
sys.path.append('/opt/2salti/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Sport, League
from matches.models import Match, MatchEvent
from accounts.models import User

def seed_events():
    # 1. Get targets
    sport = Sport.objects.get(name="Pallanuoto")
    league = League.objects.get(name="Senior", sport=sport)
    
    # Teams
    teams = list(Team.objects.filter(league=league))
    if len(teams) < 2:
        print("Not enough teams to seed matches.")
        return
        
    # Athletes by team
    athletes_by_team = {}
    for team in teams:
        athletes = list(User.objects.filter(role='athlete', athlete_profile__current_team=team))
        athletes_by_team[team.id] = athletes
        print(f"Team {team.society.name} has {len(athletes)} athletes.")

    # 2. Create Matches
    match_dates = [datetime.now() - timedelta(days=i*5) for i in range(8)]
    
    matches = []
    for i in range(8):
        # Pick two different teams
        pair = random.sample(teams, 2)
        home, away = pair[0], pair[1]
        
        match = Match.objects.create(
            league=league,
            home_team=home,
            away_team=away,
            match_date=match_dates[i],
            is_finished=True,
            location="Piscina Comunale"
        )
        matches.append(match)
        print(f"Created Match: {home.society.name} vs {away.society.name} on {match.match_date.date()}")

    # 3. Create Goals
    for match in matches:
        # Home goals (5-10)
        h_score = 0
        h_athletes = athletes_by_team.get(match.home_team.id, [])
        if h_athletes:
            h_score = random.randint(5, 10)
            for _ in range(h_score):
                scorer = random.choice(h_athletes)
                MatchEvent.objects.create(
                    match=match,
                    player=scorer,
                    event_type='GOAL',
                    minute=random.randint(1, 32),
                    team=match.home_team,
                    quarter=random.randint(1, 4)
                )
        
        # Away goals (5-10)
        a_score = 0
        a_athletes = athletes_by_team.get(match.away_team.id, [])
        if a_athletes:
            a_score = random.randint(5, 10)
            for _ in range(a_score):
                scorer = random.choice(a_athletes)
                MatchEvent.objects.create(
                    match=match,
                    player=scorer,
                    event_type='GOAL',
                    minute=random.randint(1, 32),
                    team=match.away_team,
                    quarter=random.randint(1, 4)
                )
        
        # Update match scores
        match.home_score = h_score
        match.away_score = a_score
        match.save()
        print(f"Seeded goals for match {match.id}: {h_score}-{a_score}")

    print("MatchEvents seeding completed.")

if __name__ == "__main__":
    seed_events()
