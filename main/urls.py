from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from .views import *

urlpatterns = [
    path('auth/login/', LoginView.as_view(), name='token_get_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/register/', Register.as_view(), name='register'),
    path('auth', CheckAuth.as_view(), name='check_auth'),
    path('games', GamesListView.as_view(), name='games_list'),
    path('game/<int:id>', GameDetailView.as_view(), name='game_detail'),
    path('import/pgn', UploadPGN.as_view(), name='upload_pgn'),
    path('import/lichess/', include('integrations.lichess.urls')),
    path('import/chesscom/', include('integrations.chesscom.urls')),
    path('analysis/', include('analysis.urls')),
    path('profile/', ProfileView.as_view(), name='profile'),
]