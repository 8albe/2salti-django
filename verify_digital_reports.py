import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

import json
from django.test import Client
from django.contrib.auth import get_user_model
from matches.models import Match, MatchReport, MatchReportAuditLog
from core.models import Team, League, Sport
from django.utils import timezone

User = get_user_model()

def run_test():
    client = Client()
    
    # 1. Setup Data
    sport, _ = Sport.objects.get_or_create(name="Pallanuoto", defaults={'slug': 'pallanuoto'})
    league, _ = League.objects.get_or_create(name="Serie A", season="2025/2026", defaults={'sport': sport})
    team_h, _ = Team.objects.get_or_create(name="Pro Recco", defaults={'city': 'Recco'})
    team_a, _ = Team.objects.get_or_create(name="AN Brescia", defaults={'city': 'Brescia'})
    
    match = Match.objects.create(
        league=league,
        home_team=team_h,
        away_team=team_a,
        match_date=timezone.now(),
        location="Piscina Comunale"
    )
    
    # 2. Setup User (Referee)
    referee_user, _ = User.objects.get_or_create(
        username="referee_api_test",
        defaults={
            "role": "referee",
            "first_name": "Marco",
            "last_name": "Arbitro",
            "identity_status": "VERIFIED",
            "subscription_status": "ACTIVE",
            "setup_completed": True
        }
    )
    if not referee_user.check_password("testpass123"):
        referee_user.set_password("testpass123")
        referee_user.save()
    
    # Also ensure there's a membership or claim if needed by onboarding_state
    # (Referees are exempt from some membership checks sometimes, let's double check)
    
    client.login(username="referee_api_test", password="testpass123")
    
    print(f"--- Testing Digital Report Workflow for Match {match.id} ---")
    
    # 3. START
    print("\n1. Calling /api/referti/digital/start/...")
    response = client.post(
        '/api/referti/digital/start/',
        data=json.dumps({'match_id': match.id}),
        content_type='application/json'
    )
    
    if response.status_code != 201:
        print(f"FAILED: Status {response.status_code}")
        print(response.content.decode())
        return

    report_id = response.json()['id']
    print(f"SUCCESS: Created Report ID {report_id}")
    
    # Check status
    report = MatchReport.objects.get(id=report_id)
    print(f"Model Status: {report.status} (Expected: DRAFT)")
    
    # 4. UPDATE
    print("\n2. Calling /api/referti/digital/{id} update...")
    print("\n2. Calling /api/referti/digital/{id}/ update...")
    update_payload = {
        "metadata": {"version": "2.0", "confidence": 1.0},
        "match_info": {"home_team": "Pro Recco", "away_team": "AN Brescia"},
        "scores": {"final_score": "5-3", "quarters": {"1": [2,1], "2": [3,2]}},
        "teams": {"home": {"players": []}, "away": {"players": []}},
        "events": [
            {"type": "GOAL", "team": "home", "player_name": "Rossi", "minute": 2, "quarter": 1}
        ]
    }
    
    response = client.put(
        f'/api/referti/digital/{report_id}/',
        data=json.dumps({'data': update_payload}),
        content_type='application/json'
    )
    
    if response.status_code != 200:
        print(f"FAILED: Status {response.status_code}")
        print(response.content.decode())
        return
    
    print("SUCCESS: Draft updated")
    
    # 5. CLOSE
    print("\n3. Calling /api/referti/digital/{id}/close/...")
    response = client.post(
        f'/api/referti/digital/{report_id}/close/'
    )
    
    if response.status_code != 200:
        print(f"FAILED: Status {response.status_code}")
        print(response.content.decode())
        return
    
    print(f"SUCCESS: Report closed. Message: {response.json()['message']}")
    
    # verify final state
    report.refresh_from_db()
    print(f"Final Model Status: {report.status} (Expected: NEEDS_REVIEW)")
    
    # Check Audit Log
    logs = MatchReportAuditLog.objects.filter(report=report)
    print(f"\nAudit Logs found: {logs.count()}")
    for log in logs:
        print(f"- {log.action}: {log.old_status} -> {log.new_status}")

    print("\n--- TEST COMPLETED SUCCESSFULLY ---")

if __name__ == "__main__":
    run_test()
