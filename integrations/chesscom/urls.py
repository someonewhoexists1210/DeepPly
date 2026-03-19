from django.urls import path
from .views import *

urlpatterns = [
    path('import', ChessComImport.as_view(), name='import')
]