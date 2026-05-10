import os
import django
import sys

# Setup Django environment
sys.path.append('/home/alberto')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from matches.models import Match, MatchEvent, MatchReport
from core.models import League
import json

def verify_all():
    print("=== STARTING END-TO-END COHERENCE AUDIT ===")
    
    # 1. Check all PUBLISHED matches
    published_matches = Match.objects.filter(reports__status='PUBLISHED').distinct()
    print(f"Auditing {published_matches.count()} published matches...")
    
    for match in published_matches:
        print(f"\nMatch ID: {match.id} - {match}")
        
        # A. Goal Sum Consistency
        home_goals = match.events.filter(team=match.home_team, event_type='GOAL').count()
        away_goals = match.events.filter(team=match.away_team, event_type='GOAL').count()
        
        if home_goals != match.home_score or away_goals != match.away_score:
            print(f"  [FAIL] Score mismatch! DB: {match.home_score}-{match.away_score} | EventsSum: {home_goals}-{away_goals}")
        else:
            print(f"  [OK] Score/Events coherence.")
            
        # B. Quarter Score Consistency
        total_q_h = sum(scores[0] for scores in match.quarter_scores.values())
        total_q_a = sum(scores[1] for scores in match.quarter_scores.values())
        if total_q_h != match.home_score or total_q_a != match.away_score:
            print(f"  [FAIL] Quarter sum mismatch! QSum: {total_q_h}-{total_q_a}")
        else:
            print(f"  [OK] Quarters/Total coherence.")

    # 2. Check Standings Coherence
    for league in League.objects.all():
        print(f"\nLeague: {league.name}")
        standings = league.get_standings()
        if not standings:
            print("  No published standings yet.")
            continue
            
        for entry in standings:
            team_name = entry['team'].name
            points = entry['points']
            print(f"  {entry['rank']}. {team_name:20} | Pts: {points} | P:{entry['played']} W:{entry['won']} D:{entry['drawn']} L:{entry['lost']}")

    print("\n=== AUDIT COMPLETE ===")

if __name__ == "__main__":
    verify_all()
