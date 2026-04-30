from django.urls import path, include
from .views import *

app_name = 'lichess'
urlpatterns = [
    path('login', LichessLogin.as_view(), name='login'),
    path('set_session', LichessSetSession.as_view(), name='set_session'),
    path('callback', LichessCallback.as_view(), name='callback'),
    path('oauth_cancelled', OAuthCancel.as_view(), name='cancel'),
    path('url', LichessUrl.as_view(), name='url')
]