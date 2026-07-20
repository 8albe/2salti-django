from django.urls import path
from . import api_views, api_views_digital, api_views_jury, api_views_reports

urlpatterns = [
    # Legacy API v1 (mapped under /api/)
    path('v1/league/<int:league_id>/standings/', api_views.api_league_standings, name='api_league_standings'),
    path('v1/league/<int:league_id>/matches/', api_views.api_league_matches, name='api_league_matches'),
    path('v1/match/<int:match_id>/', api_views.api_match_detail, name='api_match_detail'),
    path('v1/athlete/<int:athlete_id>/', api_views.api_athlete_detail, name='api_athlete_detail'),
    path('v1/ai-query/', api_views.api_ai_query, name='api_ai_query'),

    # Stato workflow referto (polling post-upload asincrono, Macro 22)
    path('referti/<int:report_id>/status/', api_views_reports.api_report_status, name='api_report_status'),

    # Digital Report API
    path('referti/digital/start/', api_views_digital.api_digital_report_start, name='api_digital_report_start'),
    path('referti/digital/<int:report_id>/', api_views_digital.api_digital_report_update, name='api_digital_report_update'),
    path('referti/digital/<int:report_id>/close/', api_views_digital.api_digital_report_close, name='api_digital_report_close'),

    # Link giuria (Macro 14): emissione/revoca riservate a staff digitale/admin.
    path('matches/<int:match_id>/jury-link/', api_views_jury.api_jury_link_issue, name='api_jury_link_issue'),
    path('matches/<int:match_id>/jury-link/revoke/', api_views_jury.api_jury_link_revoke, name='api_jury_link_revoke'),
]
