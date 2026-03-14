from datetime import datetime, timedelta
from django.utils import timezone
from django.shortcuts import redirect
from rest_framework.views import APIView, Response
from rest_framework.permissions import IsAuthenticated
from .models import User, Game, LichessToken
from .utils import generate_oauth_url, get_access_token, get_email
from django.conf import settings
import secrets


states = {}

# Create your views here.
class LichessTest(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        token = LichessToken.objects.filter(user=user).first()

        if token and token.expires_at > timezone.now():
            res = get_email(token.access_token)
            if res:
                return Response(res, status=200)
            return Response({"error": "Failed to fetch email"}, status=400)
        return Response({"error": "No valid token found"}, status=400)


class LichessImport(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        state = secrets.token_urlsafe(32)
        states[state] = request.user
        return redirect(f'/api/lichess/login?state={state}')

class LichessLogin(APIView):
    def get(self, request):
        state = request.query_params.get("state")
        data = generate_oauth_url('https://lichess.org/oauth?', state, settings.HOSTED_URL + '/api/lichess/callback')
        code_verifier, rd_url = data
        request.session['oauth_state'] = state
        request.session['code_verifier'] = code_verifier

        return redirect(rd_url)
    
class LichessCallback(APIView):
    def get(self, request):
        state = request.query_params.get("state")
        if 'error' in request.query_params:
            error = request.query_params.get('error')
            print(error)
            if error == 'access_denied':
                return redirect('/api/import_cancelled')  # Redirect to a cancellation page or back to the import page
            print(request.query_params['error_description'])
            print(state)
            return Response({"error": "Authorization failed: " + error}, status=400)
        
        code = request.query_params.get("code")
        code_verifier = request.session.get('code_verifier')
        rd_url = settings.HOSTED_URL + '/api/lichess/callback'
        if state != request.session.get('oauth_state'):
            return Response({"error": "State mismatch"}, status=400)
        
        tokens = get_access_token(code, code_verifier, rd_url)
        if tokens:
            access_token = tokens.get('access_token')
            expires_in = tokens.get('expires_in')
            expire_date = timezone.now() + timedelta(seconds=expires_in - 60)
            if LichessToken.objects.filter(user=states[state]).exists():
                token = LichessToken.objects.get(user=states[state])
                token.access_token = access_token
                token.expires_at = expire_date
                token.save()
            else:
                token = LichessToken(
                    user = states[state],
                    access_token = access_token,
                    expires_at = expire_date
                )
                token.save()
            return Response({"message": "Lichess import successful"}, status=200)
        
class ImportCancel(APIView):
    def get(self, request):
        return Response({"message": "womp womp"}, status=200)
    
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
    
        