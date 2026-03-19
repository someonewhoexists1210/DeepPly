from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import *

urlpatterns = [
    path('auth/token/', TokenObtainPairView.as_view(), name='token_get_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/register/', Register.as_view(), name='register'),
    path('auth', CheckAuth.as_view(), name='check_auth'),
    path('upload_pgn/', UploadPGN.as_view(), name='upload_pgn'),
    path('lichess/', include('integrations.lichess.urls')),
    path('chesscom/', include('integrations.chesscom.urls'))
]