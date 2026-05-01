from rest_framework.views import APIView, Response
from rest_framework.generics import ListAPIView, RetrieveAPIView, RetrieveDestroyAPIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import MyTokenObtainPairSerializer, GameSerializer, GameDetailSerializer, ProfileSerializer
from rest_framework.permissions import IsAuthenticated
from .models import User, Game
from .utils import parse_pgn

# Create your views here.
class UploadPGN(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        user = request.user
        pgn_text = request.data.get('pgn')
        color = request.data.get('color')
        if not pgn_text:
            return Response({"error": "No PGN text provided."}, status=400)
        
        data = parse_pgn(pgn_text, username=user.username, color=color)
        if isinstance(data, dict) or 'error' in data:
            return Response(data, status=400)
        
        ids = []
        for game_data in data:
            g = Game.objects.create(user=user,**game_data)
            ids.append(g.id)
        return Response({'message': 'Game uploaded successfully', 'ids': ids}, status=200)

class Register(APIView):
    def post(self, request):
        username = request.data.get('username')
        email = request.data.get('email')
        password = request.data.get('password')
        
        if not username or not password:
            return Response({"error": "Username and password are required."}, status=400)
        
        if User.objects.filter(username=username).exists():
            return Response({"error": "Username already exists."}, status=400)
        
        if email and User.objects.filter(email=email).exists():
            return Response({"error": "Email already exists."}, status=400)
        
        user = User.objects.create_user(username=username, password=password, email=email)
        refresh = RefreshToken.for_user(user)

        user_data = ProfileSerializer(user).data
        return Response({"refresh": str(refresh), "access": str(refresh.access_token), "user": user_data}, status=201)

class LoginView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

class ProfileView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProfileSerializer

    def get_object(self): #type:ignore
        return self.request.user 
    
class GamesListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class =  GameSerializer
    queryset = Game.objects.all()

    def get_queryset(self): 
        return super().get_queryset().filter(user=self.request.user).order_by('-date')
    
class GameDetailView(RetrieveDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = GameDetailSerializer
    queryset = Game.objects.all()
    lookup_field = 'id'

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

class Health(APIView):
    def get(self, request):
        return Response({"status": "ok"}, status=200)