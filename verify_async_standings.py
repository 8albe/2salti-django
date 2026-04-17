import os
import django
import sys
from django.utils import timezone
from unittest.mock import MagicMock, patch

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from matches.models import MatchReport, Match
from core.models import Sport, League, Society, Team, LeagueStanding
from matches.services.publishing_service import PublishingService
from django.core.management import call_command

def run_test():
    # 1. Setup
    import uuid
    uid = str(uuid.uuid4())[:8]
    sport = Sport.objects.create(name=f"Test Async {uid}", slug=f"test-async-{uid}")
    society = Society.objects.create(name=f"Test Soc {uid}", sport=sport, slug=f"test-soc-{uid}")
    league = League.objects.create(name=f"Test League {uid}", sport=sport, category='SENIOR')
    team = Team.objects.create(society=society, league=league, category='SENIOR')
    match = Match.objects.create(league=league, home_team=team, away_team=team, match_date=timezone.now())
    report = MatchReport.objects.create(
        match=match,
        status=MatchReport.Status.VALIDATED,
        normalized_data={
            'scores': {'final_score': '10-8'},
            'match_info': {'home_team': 'Test Home', 'away_team': 'Test Away'},
            'teams': {'home': {'players': []}, 'away': {'players': []}},
            'events': []
        }
    )

    print(f"Initial needs_rebuild: {league.needs_rebuild}")

    # 2. Publish
    # Note: Using Patch for the actual underlying service call if we don't want real DB side effects on standings,
    # but since this is a test env, we can let it run too.
    # Actually, we WANT to check if the flag is SET.
    
    success, msg = PublishingService.publish_report(report)
    print(f"Publish success: {success}, msg: {msg}")
    
    league.refresh_from_db()
    print(f"Needs rebuild after publish: {league.needs_rebuild}")

    if not league.needs_rebuild:
        print("ERROR: needs_rebuild flag not set!")
        sys.exit(1)

    # 3. Run Command
    print("Running rebuild_standings command...")
    call_command('rebuild_standings')
    
    league.refresh_from_db()
    print(f"Needs rebuild after command: {league.needs_rebuild}")
    print(f"Last rebuild at: {league.last_rebuild_at}")

    if league.needs_rebuild:
        print("ERROR: needs_rebuild flag still True!")
        sys.exit(1)

    print("VERIFICATION SUCCESSFUL")

if __name__ == "__main__":
    run_test()
