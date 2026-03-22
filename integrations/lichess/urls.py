from django.urls import path, include
from .views import *

app_name = 'lichess'
urlpatterns = [
    path('import', LichessImport.as_view(), name='import'),
    path('login', LichessLogin.as_view(), name='login'),
    path('callback', LichessCallback.as_view(), name='callback'),
    path('oauth_cancelled', OAuthCancel.as_view(), name='cancel'),
]