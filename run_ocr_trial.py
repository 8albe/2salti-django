import sys, os
sys.path.append('/opt/2salti/backend')
from dotenv import load_dotenv
load_dotenv('/opt/2salti/backend/.env')

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from matches.models import MatchReport
from matches.services.ocr_service import OCRService
import logging

logging.basicConfig(level=logging.INFO)

report = MatchReport.objects.get(id=19)
report.status = 'NEEDS_REVIEW'
report.save()

print(f'Processing report {report.id} (Status: {report.status})...')
success = OCRService.process_and_update(report)
print(f'Success: {success}')

report.refresh_from_db()
data = report.raw_extracted_data
provider = data.get('metadata', {}).get('provider') if isinstance(data, dict) else 'Unknown'
print(f'Provider used: {provider}')
print(f'Normalized data present: {bool(report.normalized_data)}')
if isinstance(data, dict):
    print('Quality assessment quick view:')
    print(f'- Match info: {bool(data.get("match_info"))}')
    print(f'- Scores: {bool(data.get("scores"))}')
    print(f'- Teams: {bool(data.get("teams"))}')
    print(f'- Events: {len(data.get("events", []))} found')
