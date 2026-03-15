from django.urls import path
from . import views
from matches import views as match_views

urlpatterns = [
    path('', views.home, name='home'),
    path('sport/<slug:slug>/', views.sport_detail, name='sport_detail'),
    path('society/create/', views.create_society, name='create_society'),
    path('society/<slug:slug>/', views.society_detail, name='society_detail'),
    path('team/<slug:slug>/', views.team_detail, name='team_detail'),
    path('team/<int:team_id>/follow/', views.toggle_follow_team, name='toggle_follow_team'),
    path('league/<int:league_id>/standings/', views.league_standings, name='league_standings'),
    path('league/<slug:league_slug>/stats/', match_views.league_statistics, name='league_stats'),
    path('sport/<slug:sport_slug>/matches/', match_views.sport_matches, name='sport_matches'),
]
