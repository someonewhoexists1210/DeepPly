from django.urls import path, include
from .views import *

urlpatterns = [
    path('import', LichessImport.as_view(), name='import'),
    path('login', LichessLogin.as_view(), name='login'),
    path('callback', LichessCallback.as_view(), name='lichess_callback'),
    path('oauth_cancelled', OAuthCancel.as_view(), name='import_cancelled'),
]