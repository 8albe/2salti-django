import os
import sys
import django

# Setup Django
sys.path.append('/opt/2salti/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from matches.models import AIQueryLog
from accounts.models import User
from django.db.models import Count

def analyze():
    print("=== SYSTEM STATUS ===")
    user_count = User.objects.count()
    athlete_count = User.objects.filter(role='athlete').count()
    print(f"Total Users: {user_count}")
    print(f"Total Athletes: {athlete_count}")
    
    logs = AIQueryLog.objects.all()
    count = logs.count()
    print(f"Total AI Logs: {count}")
    
    if count == 0:
        print("No pilot logs found yet.")
        return

    print("\n=== LOG ANALYSIS ===")
    
    print("\nResponse Type Distribution:")
    dist = logs.values('response_type').annotate(count=Count('id')).order_by('-count')
    for item in dist:
        pct = (item['count'] / count) * 100
        print(f" - {item['response_type']}: {item['count']} ({pct:.1f}%)")

    print("\nTop Raw Queries (Pilot Patterns):")
    top = logs.values('raw_query').annotate(count=Count('id')).order_by('-count')[:20]
    for item in top:
        print(f" - [{item['count']}x] {item['raw_query']}")

    print("\nTop Failed Artist/Athlete Lookups (no_match):")
    failed = logs.filter(response_type='no_match').values('raw_query').annotate(count=Count('id')).order_by('-count')[:15]
    for item in failed:
        # Extract potential names from query string if possible, or just show raw
        print(f" - [{item['count']}x] {item['raw_query']}")

    print("\nTop Out-of-Scope Requests (insufficient_data):")
    other = logs.filter(response_type='insufficient_data').values('raw_query').annotate(count=Count('id')).order_by('-count')[:15]
    for item in other:
        print(f" - [{item['count']}x] {item['raw_query']}")

    print("\nTime Range Usage:")
    ranges = logs.values('time_range').annotate(count=Count('id')).order_by('-count')
    for item in ranges:
        if item['time_range']:
            print(f" - {item['time_range']}: {item['count']}")

if __name__ == "__main__":
    analyze()
