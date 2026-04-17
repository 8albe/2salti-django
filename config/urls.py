from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from matches.admin import op_admin_site

urlpatterns = [
    path('admin/', op_admin_site.urls),
    path('', include('core.urls')),
    path('accounts/', include('accounts.urls')),
    path('matches/', include('matches.urls')),
    path('api/', include('matches.api_urls')),
    path('management/', include('management.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
