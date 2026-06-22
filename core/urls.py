from django.urls import path
from . import views
from .seo_views import robots_txt, sitemap_xml
from matches import views as match_views
from accounts import views as account_views

urlpatterns = [
    path('', views.home, name='home'),
    path('sport/<slug:slug>/', views.sport_detail, name='sport_detail'),
    path('society/choose/', views.choose_society, name='choose_society'),
    path('society/create/', views.create_society, name='create_society'),
    path('society/<slug:slug>/', views.society_detail, name='society_detail'),
    path('team/<slug:slug>/', views.team_detail, name='team_detail'),
    path('player/<str:username>/', account_views.profile, name='player_profile'),
    path('team/<int:team_id>/follow/', views.toggle_follow_team, name='toggle_follow_team'),
    path('league/<int:league_id>/standings/', views.league_standings, name='league_standings'),
    path('league/<slug:league_slug>/stats/', match_views.league_statistics, name='league_stats'),
    path('sport/<slug:sport_slug>/matches/', match_views.sport_matches, name='sport_matches'),
    path('robots.txt', robots_txt, name='robots_txt'),
    path('sitemap.xml', sitemap_xml, name='sitemap_xml'),
    
    # Dashboard API
    path('api/dashboard/me', views.dashboard_me, name='dashboard_me'),
]
