from django.urls import path
from . import views, api_views, api_views_digital

urlpatterns = [
    path('<int:match_id>/', views.match_detail, name='match_detail'),
    path('<int:match_id>/upload-report/', views.upload_report, name='upload_report'),
    path('upload-report/', views.upload_report, name='upload_report_standalone'),
    path('<int:match_id>/digital-report/', views.create_digital_report, name='create_digital_report'),
    path('report/<int:report_id>/review/', views.report_review, name='report_review'),
    path('queue/', views.report_queue, name='report_queue'),
    
    path('api/v1/ai-query/', api_views.api_ai_query, name='api_ai_query'),
]
