from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from .models import User, Game
from typing import Dict, Any

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data: Dict[str, Any] = super().validate(attrs)

        user: User = self.user # type: ignore
        user_data = {
            'username': user.username,
            'date_joined': user.date_joined,
            'lichessUsername': getattr(user, "lichess_token.lichessUsername", None), # pyright: ignore[reportAttributeAccessIssue]
            'chessComUsername': getattr(user, "chesscom_username", None), # pyright: ignore[reportAttributeAccessIssue]
        }
        data['user'] = user_data
        return data
    
class ProfileSerializer(serializers.ModelSerializer):
    lichessUsername = serializers.CharField(source='lichess_token.lichessUsername', read_only=True) # pyright: ignore[reportAttributeAccessIssue]
    chesscom_username = serializers.CharField(read_only=True)
    class Meta:
        model = User
        fields = ['username', 'date_joined', 'lichessUsername', 'chesscom_username']
    
class GameSerializer(serializers.ModelSerializer):
    moves = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = ['id', 'opponent', 'analysed', 'color', 'date', 'result', 'time_control', 'moves']

    def get_moves(self, object: Game):
        return object.moves.split() if object.moves else []
    
class GameDetailSerializer(serializers.ModelSerializer):    
    analysis = serializers.JSONField(source='analysis.model_output', read_only=True)
    moves = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = ['id', 'opponent', 'analysed', 'color', 'date', 'result', 'time_control', 'moves', 'analysis', 'middle_game_start', 'end_game_start', 'plies']

    def get_moves(self, object: Game):
        return object.moves.split() if object.moves else []