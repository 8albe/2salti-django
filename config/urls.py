from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.templatetags.static import static as static_url
from django.views.generic.base import RedirectView

from matches.admin import op_admin_site
from matches.api_views_jury import jury_link_landing


class FaviconRedirectView(RedirectView):
    """Redirect del probe legacy /favicon.ico all'asset statico (spegne il 404
    sul root). `static()` risolto a request-time: regge il nome con hash del
    ManifestStaticFilesStorage senza lookup del manifest all'import."""
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        try:
            return static_url('favicon.svg')
        except ValueError:
            # manifest non ancora aggiornato (collectstatic non eseguito):
            # ripiega sul path non-hashato servito da nginx, mai 500.
            return settings.STATIC_URL + 'favicon.svg'


urlpatterns = [
    path('admin/', op_admin_site.urls),
    path('favicon.ico', FaviconRedirectView.as_view()),
    # Landing pubblica del link giuria (Macro 14): risoluzione token, nessuna UI.
    path('r/<str:token>/', jury_link_landing, name='jury_link_landing'),
    path('', include('core.urls')),
    path('accounts/', include('accounts.urls')),
    path('matches/', include('matches.urls')),
    path('api/', include('matches.api_urls')),
    path('management/', include('management.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
