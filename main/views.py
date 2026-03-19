from rest_framework.views import APIView, Response
from rest_framework.permissions import IsAuthenticated
from .models import User

# Create your views here.
class UploadPGN(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        user = request.user
        pgn_file = request.FILES.get('pgn_file')
        color = request.data.get('color')
        if not pgn_file:
            return Response({"error": "No PGN file uploaded."}, status=400)
        
        # PGN proccessing
        # Parsing
        # pgn_text = pgn_file.read().decode('utf-8')
        # moves = regex.findall(r'\d+\.\s*([a-hKRQNB][^\s]+)(?:\s+([a-hKRQNB][^\s]+))?', pgn_text)
        # if len(moves) == 0:
        #     return Response({"error": "Invalid PGN file."}, status=400)
        
        # ply_count = 2 * (len(moves) - 1) + len(moves[-1])
        # if request.data.get('datetime'):
        #     date = request.data.get('datetime')
        # else:
        #     date_reg = regex.search(r'\[Date\s+"(\d{4}\.\d{2}\.\d{2})"\]', pgn_text)
        #     time_reg = regex.search(r'\[EndTime\s+"(\d{2}:\d{2}:\d{2})"\]', pgn_text)
        #     date = date_reg.group(1) if date_reg else None

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
    
        