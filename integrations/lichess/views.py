from datetime import  timedelta
from django.utils import timezone
from django.shortcuts import redirect
from django.urls import reverse
from rest_framework.views import APIView, Response
from rest_framework.permissions import IsAuthenticated
from main.models import Game
from main.utils import calculate_result
from .models import LichessToken
from .utils import generate_oauth_url, get_access_token, get_profile, import_all_games, import_one_game, ms_epoch_to_datetime
import secrets
import regex as re

states = {} # USE REDIS IN FUTURE WHEN USING MULTIPLE WORKERS

# Create your views here.
class LichessImport(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        LToken = LichessToken.objects.filter(user=request.user).first()
        if not LToken or LToken.expires_at <= timezone.now():
            state = secrets.token_urlsafe(32)
            states[state] = request.user
            callback_url = reverse('lichess:import')
            return redirect(reverse('lichess:login') + f'?state={state}&callback={callback_url}')
        
        try:
            for game in import_all_games(LToken):
                ### MAKE THIS A CELERY TASK IN FUTURE
                color = game['players']['black']['user']['name'] == LToken.lichessUsername
                Game.objects.create(
                    lichess_id=game['id'],
                    user=request.user,
                    plies=len(game['moves'].split(' ')),
                    color=color,
                    moves=game['moves'],
                    middle_game_start=game['division'].get('middle'),
                    end_game_start=game['division'].get('end'),
                    result = calculate_result((0.0 if game['winner'] == 'black' else 1.0) if game.get('winner') else 0.5, color),
                    date=ms_epoch_to_datetime(game['createdAt']),
                    time_control=f'{game["clock"]["initial"]}/{game["clock"]["increment"]}'
                )
            return Response({'message': "Import successful"}, status=200)
        except Exception as e:
            return Response({"error": "Error occured: " + str(e)}, status=500)

class LichessLogin(APIView):
    def get(self, request): 
        state = request.query_params.get("state")
        callback_url = request.query_params.get("callback")
        data = generate_oauth_url('https://lichess.org/oauth?', state, request.build_absolute_uri(reverse('lichess:callback')))
        code_verifier, rd_url = data
        request.session['oauth_state'] = state
        request.session['code_verifier'] = code_verifier
        request.session['callback_url'] = callback_url

        return redirect(rd_url)
    
class LichessCallback(APIView):
    def get(self, request):
        state = request.query_params.get("state")
        if 'error' in request.query_params:
            error = request.query_params.get('error')
            print(error)
            if error == 'access_denied':
                return redirect(reverse('lichess:cancel'))
            print(request.query_params['error_description'])
            print(state)
            return Response({"error": "Authorization failed: " + error}, status=400)
        
        code = request.query_params.get("code")
        code_verifier = request.session.get('code_verifier')
        callback_url = request.session.get('callback_url')
        rd_url = request.build_absolute_uri(reverse('lichess:callback'))
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
                
            else:
                token = LichessToken(
                    user = states[state],
                    access_token = access_token,
                    expires_at = expire_date
                )
                

            data = get_profile(access_token)
            if not data:
                return Response({'error': "Failed to fetch user profile"}, status=400)
            token.lichessUserId = data.get('id')
            token.lichessUsername = data.get('username')
            seenAt = data.get('seenAt')
            if seenAt is not None:
                token.last_seen = ms_epoch_to_datetime(seenAt)

            token.save()
            states.pop(state, None)
            return redirect(callback_url)
        
class OAuthCancel(APIView):
    def get(self, request):
        return Response({"message": "womp womp"}, status=200)
    
class LichessUrl(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        url = request.body.get('url')
        if re.match(r'https://lichess\.org/[a-zA-Z0-9]{8,12}', url) is None: # Should be of format https://lichess.org/{gameId} where gameId is 12 characters or 8
            return Response({'error': 'Invalid URL format'}, status=400)
        lichess_id = url.split('/')[-1][:8]
        color = request.body.get('color')
        token = LichessToken.objects.filter(user=request.user).first()
        if Game.objects.filter(lichess_id=lichess_id, user=request.user).exists():
            return Response({'error': 'Game already imported'}, status=400)
        
        try:
            game = import_one_game(lichess_id, token)
            if not game:
                return Response({'error': 'Failed to import game'}, status=400)
            
            Game.objects.create(
                    lichess_id=game['id'],
                    user=request.user,
                    plies=len(game['moves'].split(' ')),
                    color=color == 'black',
                    moves=game['moves'],
                    middle_game_start=game['division'].get('middle'),
                    end_game_start=game['division'].get('end'),
                    result=calculate_result((1.0 if game['winner'] == 'white' else 0.0) if game.get('winner') else 0.5, color == 'black'),
                    date=ms_epoch_to_datetime(game['createdAt']),
                    time_control=f'{game["clock"]["initial"]}/{game["clock"]["increment"]}'
            )
            return Response({'message': 'Game imported successfully'}, status=200)
        except Exception as e:
            return Response({'error': 'Failed to import game: ' + str(e)}, status=400)
        
        
