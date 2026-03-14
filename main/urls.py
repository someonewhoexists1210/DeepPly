from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import *

urlpatterns = [
    path('auth/token/', TokenObtainPairView.as_view(), name='token_get_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/register/', Register.as_view(), name='register'),
    path('auth', CheckAuth.as_view(), name='check_auth'),
    path('lichess/import', LichessImport.as_view(), name='lichess_import'),
    path('lichess/login', LichessLogin.as_view(), name='lichess_login'),
    path('lichess/callback', LichessCallback.as_view(), name='lichess_callback'),
    path('lichess/test', LichessTest.as_view(), name='lichess_test'),
    path('import_cancelled', ImportCancel.as_view(), name='import_cancelled'),
    path('upload_pgn/', UploadPGN.as_view(), name='upload_pgn'),
]