from django.urls import path
from . import views

urlpatterns = [
    path('<int:match_id>/', views.match_detail, name='match_detail'),
]
