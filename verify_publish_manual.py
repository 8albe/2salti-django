import os
import django
from django.utils import timezone
from django.db import transaction

# Setup Django if needed (for external script usage)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
try:
    django.setup()
except Exception as e:
    print(f"Django setup fail: {e}")

from core.models import Sport, Society, League, Team
from matches.models import Match, MatchReport, MatchEvent
from matches.services.publishing_service import PublishingService
from management.models import AuditLog
from accounts.models import User, AthleteProfile

def verify():
    # 0. SETUP
    print("--- 0. SETUP ---")
    sport = Sport.objects.filter(name="Pallanuoto").first()
    if not sport:
        sport = Sport.objects.create(name="Pallanuoto", slug="pallanuotopallanuoto")
        
    league = League.objects.filter(name="Serie A1").first()
    if not league:
        league = League.objects.create(name="Serie A1", sport=sport, category="SENIOR", slug="serie-a1-test")
        
    team_h = Team.objects.filter(league=league).first()
    if not team_h:
        soc_h, _ = Society.objects.get_or_create(name="Pro Recco Test", sport=sport, slug="pro-recco-test")
        team_h = Team.objects.create(society=soc_h, category="SENIOR", league=league)
        
    team_a = Team.objects.filter(league=league).exclude(id=team_h.id).first()
    if not team_a:
        soc_a, _ = Society.objects.get_or_create(name="AN Brescia Test", sport=sport, slug="an-brescia-test")
        team_a = Team.objects.create(society=soc_a, category="SENIOR", league=league)
        
    user, _ = User.objects.get_or_create(username="admin_test", is_superuser=True)
    
    # Create an athlete for event tests
    player_user, _ = User.objects.get_or_create(username="player1", role='athlete')
    athlete_profile, _ = AthleteProfile.objects.get_or_create(user=player_user)
    athlete_profile.current_team = team_h
    athlete_profile.save()
    
    match = Match.objects.create(
        league=league, home_team=team_h, away_team=team_a,
        match_date=timezone.now(), home_score=0, away_score=0
    )
    
    report = MatchReport.objects.create(
        match=match, status=MatchReport.Status.VALIDATED,
        normalized_data={
            "match_info": {"home_team": "Pro Recco Test", "away_team": "AN Brescia Test"},
            "scores": {"final_score": "10-5", "quarters": {"1": [2,1]}},
            "events": [{"type": "GOAL", "player": "Player1", "team": "home", "minute": 5}],
            "reconciliation": {
                "home_players": {"Player1": player_user.id}
            },
            "metadata": {"extraction_warnings": []}
        }
    )

    # 1. TEST PUBLISH
    print("--- 1. TEST PUBLISH ---")
    success, msg = PublishingService.publish_report(report, user=user)
    print(f"Success: {success}, Message: {msg}")
    
    match.refresh_from_db()
    report.refresh_from_db()
    league.refresh_from_db()
    
    # Check results
    if not success:
        print(f"FAILED: {msg}")
        return

    assert match.home_score == 10
    assert match.is_finished == True
    assert report.status == MatchReport.Status.PUBLISHED
    assert league.needs_rebuild == True, "League needs_rebuild should be True"
    assert MatchEvent.objects.filter(match=match).count() == 1
    
    # Verify AuditLog
    audit = AuditLog.objects.filter(target_id=str(report.id), action="PUBLISH_REPORT").first()
    assert audit is not None
    assert audit.details["events_created"] == 1
    
    # Verify Athlete Stats
    athlete_profile.refresh_from_db()
    print(f"Athlete goals: {athlete_profile.total_goals}")
    assert athlete_profile.total_goals == 1, "Athlete goals should be updated"
    
    print("Publish tests Passed")

    # 2. TEST REPUBLISH (Idempotency)
    print("--- 2. TEST REPUBLISH (Idempotency) ---")
    # Change score in data to verify it updates
    report.normalized_data["scores"]["final_score"] = "11-5"
    report.save()
    
    success2, msg2 = PublishingService.publish_report(report, user=user)
    print(f"Success2: {success2}, Message2: {msg2}")
    
    match.refresh_from_db()
    assert match.home_score == 11
    assert MatchEvent.objects.filter(match=match).count() == 1, "Should still be only 1 event"
    
    audit2 = AuditLog.objects.filter(target_id=str(report.id), action="REPUBLISH_REPORT").first()
    assert audit2 is not None
    assert audit2.details["events_deleted"] == 1
    assert audit2.details["is_republish"] == True
    print("Republish tests Passed")

    # 3. CLEANUP
    print("--- 3. CLEANUP ---")
    # match.delete() # Let's not delete just to be safe if anything is useful
    print("Cleanup Passed")

    print("\nVERIFICATION COMPLETE")

if __name__ == "__main__":
    verify()
