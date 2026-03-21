from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('signup/', views.signup, name='signup'),
    path('setup/', views.setup_wizard, name='setup_wizard'),
    path('profile-setup/', views.setup_wizard, name='setup_wizard'),
    path('verify-identity/', views.verify_identity, name='verify_identity'),
    path('payment/', views.process_payment, name='process_payment'),
    path('profile-redirect/', views.profile_redirect, name='profile_redirect'),
    path('profile/<str:username>/', views.profile, name='profile'),
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    # AJAX endpoints
    path('api/teams-by-league/', views.api_teams_by_league, name='api_teams_by_league'),
    path('api/search-athlete/', views.api_search_athlete, name='api_search_athlete'),
    path('claim-profile/', views.claim_profile, name='claim_profile'),
    path('api/search-profile-claim/', views.api_search_profile_claim, name='api_search_profile_claim'),
]
