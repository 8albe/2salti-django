import sys, os
sys.path.append('/opt/2salti/backend')
from dotenv import load_dotenv
load_dotenv('/opt/2salti/backend/.env')

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from matches.models import MatchReport

report = MatchReport.objects.get(id=19)
my_data = {"some_key": "some_value"}
report.raw_extracted_data = my_data
report.normalized_data = my_data
report.save(update_fields=['raw_extracted_data', 'normalized_data'])

report.refresh_from_db()
print(f"raw_extracted_data: {report.raw_extracted_data}")
print(f"normalized_data: {report.normalized_data}")
