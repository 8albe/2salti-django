import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Sport, League, Team
from matches.models import Match, MatchReport
from matches.services.schema import OCRSchemaValidator
from matches.services.publishing_service import PublishingService
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

def setup_db():
    sport, _ = Sport.objects.get_or_create(name='Pallanuoto', defaults={'slug': 'pallanuoto'})
    league, _ = League.objects.get_or_create(name='Serie A1', defaults={'sport': sport})
    team_a, _ = Team.objects.get_or_create(name='Pro Recco', defaults={'society_id': 1})
    team_b, _ = Team.objects.get_or_create(name='AN Brescia', defaults={'society_id': 2})
    return league, team_a, team_b

def test_guardrails_logic():
    print("Testing OCRSchemaValidator Guardrails...")
    
    # CASE 1: Zero Events with positive score
    data_zero_events = {
        "metadata": {"confidence": 0.9},
        "match_info": {"home_team": "Team A", "away_team": "Team B"},
        "scores": {"final_score": "5-0"},
        "teams": {"home": {"players": []}, "away": {"players": []}},
        "events": [], # Zero events
        "reconciliation": {"home_players": {}, "away_players": {}}
    }
    
    safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(data_zero_events)
    print(f"  [Zero Events] Score 5-0 / Events 0 -> Safe: {safe} | Blockers: {blockers}")
    
    # CASE 2: Score Inconsistency
    data_inconsistent = {
        "metadata": {"confidence": 0.9},
        "match_info": {"home_team": "Team A", "away_team": "Team B"},
        "scores": {"final_score": "5-0"},
        "teams": {"home": {"players": []}, "away": {"players": []}},
        "events": [{"type": "GOAL", "team": "home"}], # Only 1 goal for 5-0 score
        "reconciliation": {"home_players": {}, "away_players": {}}
    }
    safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(data_inconsistent)
    print(f"  [Inconsistency] Score 5-0 / Events 1 -> Safe: {safe} | Blockers: {blockers}")

    # CASE 3: Incomplete Reconciliation
    data_incomplete = {
        "metadata": {"confidence": 0.9},
        "match_info": {"home_team": "Team A", "away_team": "Team B"},
        "scores": {"final_score": "0-0"},
        "teams": {
            "home": {"players": [{"name": "P1"}, {"name": "P2"}, {"name": "P3"}]}, # 3 players
            "away": {"players": []}
        },
        "events": [],
        "reconciliation": {"home_players": {"P1": 1}, "away_players": {}} # Only 1/3 reconciled
    }
    safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(data_incomplete)
    print(f"  [Incomplete] 1/3 players reconciled -> Safe: {safe} | Warnings: {warnings}")

def test_publishing_override():
    print("\nTesting PublishingService Override...")
    
    league, team_a, team_b = setup_db()
    admin_user = User.objects.filter(is_staff=True).first()
    if not admin_user:
        admin_user = User.objects.create_superuser('admin_test', 'admin@test.com', 'pass')
        
    match = Match.objects.create(home_team=team_a, away_team=team_b, league=league, match_date=timezone.now().date())
    
    report = MatchReport.objects.create(
        match=match,
        status=MatchReport.Status.VALIDATED,
        normalized_data={
            "metadata": {"confidence": 0.9},
            "match_info": {"home_team": team_a.name, "away_team": team_b.name},
            "scores": {"final_score": "10-0"},
            "teams": {"home": {"players": []}, "away": {"players": []}},
            "events": [], # Zero events blocker
            "reconciliation": {"home_players": {}, "away_players": {}}
        }
    )
    
    # 1. Standard Publish (should fail)
    success, msg = PublishingService.publish_report(report, user=admin_user, force=False)
    print(f"  Standard Publish -> Success: {success} | Msg: {msg}")
    
    # 2. Forced Publish (should succeed)
    success, msg = PublishingService.publish_report(report, user=admin_user, force=True)
    print(f"  Forced Publish -> Success: {success} | Msg: {msg}")
    
    # Verify Audit Log
    from management.models import AuditLog
    last_log = AuditLog.objects.filter(target_id=str(report.id), action="PUBLISH_REPORT").latest('timestamp')
    print(f"  Audit Log -> Forced: {last_log.details.get('forced')} | Overridden: {last_log.details.get('overridden_blockers')}")

if __name__ == "__main__":
    test_guardrails_logic()
    try:
        test_publishing_override()
    except Exception as e:
        print(f"Error in publishing test: {e}")
        import traceback
        traceback.print_exc()
