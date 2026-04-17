import sys, os
sys.path.append('/opt/2salti/backend')
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from matches.models import MatchReport, Match
from django.core.files import File

# Copy reliable image to media
os.system('cp /home/alberto/dataset/ocr_referti_reali/r001/raw/reale_01.jpeg /opt/2salti/backend/media/match_reports/reale_01.jpeg')

match = Match.objects.first()
report = MatchReport.objects.create(
    match=match,
    status='NEEDS_REVIEW'
)
report.file.name = 'match_reports/reale_01.jpeg'
report.save()

print(f"Created report {report.id} with file {report.file.name}")
