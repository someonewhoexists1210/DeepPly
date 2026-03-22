from django.urls import path
from .views import * 

app_name = 'analysis'
urlpatterns = [
    path('', AnalysisView.as_view(), name='analysis'),
    path('status/<str:task_id>/', AnalysisStatusView.as_view(), name='status'),
]