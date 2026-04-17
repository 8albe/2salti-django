import sys, os
sys.path.append('/opt/2salti/backend')
from dotenv import load_dotenv
load_dotenv('/opt/2salti/backend/.env')

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from matches.models import MatchReport

report = MatchReport.objects.get(id=19)
print(f"Current raw: {bool(report.raw_extracted_data)}")
print(f"Current normalized: {bool(report.normalized_data)}")

report.normalized_data = {"test": "data"}
report.save(update_fields=['normalized_data'])

report.refresh_from_db()
print(f"After update_fields normalized_data: {report.normalized_data}")
