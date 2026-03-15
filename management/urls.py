from django.urls import path
from . import views

urlpatterns = [
    path('trainings/', views.training_list, name='training_list'),
    path('trainings/create/', views.training_create, name='training_create'),
    path('trainings/rsvp/<int:occurrence_id>/', views.training_rsvp, name='training_rsvp'),
    path('bacheca/', views.bacheca_view, name='bacheca_globale'),
    path('team/<slug:team_slug>/bacheca/', views.bacheca_view, name='bacheca_team'),
    path('team/<int:team_id>/post/create/', views.post_create, name='post_create'),
    path('team/<slug:team_slug>/chat/', views.chat_view, name='chat_team'),
    path('team/<int:team_id>/chat/add/', views.chat_message_add, name='chat_message_add'),
]
