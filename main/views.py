from rest_framework.views import APIView, Response
from rest_framework.permissions import IsAuthenticated
from .models import User, Game
from .utils import parse_pgn


# Create your views here.
class UploadPGN(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        user = request.user
        pgn_file = request.FILES.get('pgn_file')
        color = request.data.get('color')
        if not pgn_file:
            return Response({"error": "No PGN file uploaded."}, status=400)
        
        pgn_text = pgn_file.read().decode('utf-8')
        data = parse_pgn(pgn_text, username=user.username, color=color)
        if 'error' in data:
            return Response(data, status=400)
        
        for game_data in data:
            Game.objects.create(user=user,**game_data) # type:ignore
        return Response({'message': 'Game uploaded successfully'}, status=200)

class Register(APIView):
    def post(self, request):
        username = request.data.get('username')
        # email = request.data.get('email')
        password = request.data.get('password')
        
        if not username or not password:
            return Response({"error": "Username and password are required."}, status=400)
        
        if User.objects.filter(username=username).exists():
            # if email:
            #     username = f"{username}_{email.split('@')[0]}"
            #     if User.objects.filter(username=username).exists():
            #         return Response({"error": "Username already exists."}, status=400)
            # else:
                return Response({"error": "Username already exists."}, status=400)
        
        # if User.objects.filter(email=email).exists():
        #     return Response({"error": "Email already exists."}, status=400)
        
        user = User.objects.create_user(username=username, password=password)
        return Response({"message": "User registered successfully."}, status=201)
        
class CheckAuth(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"message": "Authenticated", "user": request.user.username}, status=200)
    
        