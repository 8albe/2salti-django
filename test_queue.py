import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from matches.admin import MatchReportAdmin
from matches.models import MatchReport
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
factory = RequestFactory()
request = factory.get('/admin/matches/matchreport/')
from django.contrib.auth import get_user_model
User = get_user_model()
try:
    admin_user = User.objects.filter(is_superuser=True).first()
except User.DoesNotExist:
    admin_user = User.objects.create_superuser('test_admin', 'admin@example.com', 'admin')
request.user = admin_user
site = AdminSite()
ma = MatchReportAdmin(MatchReport, site)
response = ma.changelist_view(request)
try:
    response.render()
    print("KPI keys inside context:", response.context_data.get('queue_kpi'))
    print("SUCCESS: changelist_view renders fine with the custom template!")
except Exception as e:
    print("ERROR rendering:", e)
