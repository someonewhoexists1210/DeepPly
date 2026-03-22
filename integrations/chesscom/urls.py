from django.urls import path
from .views import *

app_name = 'chesscom'
urlpatterns = [
    path('import', ChessComImport.as_view(), name='import')
]