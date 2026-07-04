from django.urls import path
from . import views

urlpatterns = [
    path('trainings/', views.training_list, name='training_list'),
    path('trainings/create/', views.training_create, name='training_create'),
    path('trainings/rsvp/<int:occurrence_id>/', views.training_rsvp, name='training_rsvp'),
    path('bacheca/', views.bacheca_view, name='bacheca_globale'),
    path('team/<slug:team_slug>/bacheca/', views.bacheca_view, name='bacheca_team'),
    path('team/<int:team_id>/post/create/', views.post_create, name='post_create'),
    path('team-chat/<slug:team_slug>/', views.chat_view, name='chat_view'),
    path('team-chat/<int:team_id>/add/', views.chat_message_add, name='chat_message_add'),

    # Convocazioni
    path('convocation/create/<int:match_id>/', views.convocation_create, name='convocation_create'),

    # Nuovo Onboarding & Club Admin (Blueprint v3)
    path('team-access/', views.team_access, name='team_access'),
    path('club-admin/', views.club_admin_dashboard, name='club_admin_dashboard'),
    path('club-admin/request/<int:request_id>/approve/', views.approve_membership, name='approve_membership'),
    path('club-admin/generate-code/', views.generate_code, name='generate_code'),
    path('staff-dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('ops-cockpit/', views.ops_cockpit, name='ops_cockpit'),

    # Certificazione genitore (Macro 7b)
    path('club-admin/certifications/', views.parent_certifications_list, name='parent_certifications_list'),
    path('club-admin/certification/<int:cert_id>/confirm/', views.confirm_parent_certification, name='confirm_parent_certification'),
    path('club-admin/certification/<int:cert_id>/reject/', views.reject_parent_certification, name='reject_parent_certification'),
    path('certify/<str:token>/', views.certify_parent, name='certify_parent'),
]
