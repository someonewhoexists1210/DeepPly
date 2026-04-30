from datetime import  timedelta
import os
from django.utils import timezone
from django.shortcuts import redirect
from django.urls import reverse
from django.core.cache import cache
from django.conf import settings
from rest_framework.views import APIView, Response
from rest_framework.permissions import IsAuthenticated
from main.models import Game
from main.utils import calculate_result
from .models import LichessToken
from main.models import User
from .utils import generate_oauth_url, get_access_token, get_profile, import_all_games, import_one_game, ms_epoch_to_datetime
import secrets
import regex as re
import redis


r_url = os.getenv('REDIS_URL')
if not r_url:
    raise Exception("REDIS_URL not set in environment variables")
r = redis.from_url(r_url, decode_responses=True)
FRONTEND_URL = settings.FRONTEND_URL
# Create your views here.


class LichessSetSession(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        state = secrets.token_urlsafe(32)
        r.set(state, request.user.id, ex=300) # 5 mins
        return Response({'state': state}, status=200)

class LichessLogin(APIView):
    def get(self, request): 
        state = request.query_params.get('state')
        if not state or r.get(state) is None:
            return Response({'error': 'Invalid state parameter'}, status=400)
        data = generate_oauth_url('https://lichess.org/oauth?', state, request.build_absolute_uri(reverse('lichess:callback')))
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
                return redirect(reverse('lichess:cancel'))
            print(request.query_params['error_description'])
            print(state)
            return redirect(FRONTEND_URL + '/dashboard?message=lichessoauthfail')
        
        code = request.query_params.get("code")
        code_verifier = request.session.get('code_verifier')
        rd_url = request.build_absolute_uri(reverse('lichess:callback'))
        if state != request.session.get('oauth_state'):
            print('State mismatch: expected', request.session.get('oauth_state'), 'got', state)
            return redirect(FRONTEND_URL + '/dashboard?message=lichessoauthfail')
        
        tokens = get_access_token(code, code_verifier, rd_url)
        if tokens:
            access_token = tokens.get('access_token')
            expires_in = tokens.get('expires_in')
            expire_date = timezone.now() + timedelta(seconds=expires_in - 60)
            user = r.get(state)
            if not user:
                print('No user in session')
                return redirect(FRONTEND_URL + '/dashboard?message=lichessoauthfail')
            UserObj = User.objects.filter(id=user).first()
            if not UserObj:
                print('User not found:', user)
                return redirect(FRONTEND_URL + '/dashboard?message=lichessoauthfail')
            request.session.flush()
            if LichessToken.objects.filter(user=UserObj).exists():
                token = LichessToken.objects.get(user=UserObj)
                token.access_token = access_token
                token.expires_at = expire_date  
            else:
                token = LichessToken(
                    user = UserObj,
                    access_token = access_token,
                    expires_at = expire_date
                )
                
            data = get_profile(access_token)
            if not data:
                print('Failed to fetch profile with access token:', access_token)
                return redirect(FRONTEND_URL + '/dashboard?message=lichessoauthfail')
            token.lichessUserId = data.get('id')
            token.lichessUsername = data.get('username')
            seenAt = data.get('seenAt')
            if seenAt is not None:
                token.last_seen = ms_epoch_to_datetime(seenAt)

            token.save()
            try:
                for game in import_all_games(token):
                    ### MAKE THIS A CELERY TASK IN FUTURE
                    color = game['players']['white']['user']['name'] == token.lichessUsername
                    opponent = game['players']['black']['user']['name'] if color else game['players']['white']['user']['name']
                    Game.objects.create(
                        lichess_id=game['id'],
                        user=UserObj,
                        plies=len(game['moves']),
                        color=color,
                        opponent=opponent,
                        moves=' '.join(game['moves']),
                        moves_uci=' '.join(game['moves_uci']),
                        middle_game_start=game['division'].get('middle'),
                        end_game_start=game['division'].get('end'),
                        result = calculate_result((1.0 if game['winner'] == 'white' else 0.0) if game.get('winner') else 0.5, color),
                        date=ms_epoch_to_datetime(game['createdAt']),
                        time_control=f'{game["clock"]["initial"]}+{game["clock"]["increment"]}'
                    )
            
            except Exception as e:
                print(e)
                return redirect(FRONTEND_URL + '/dashboard?message=importfail')

            r.delete(state)
            return redirect(FRONTEND_URL + '/dashboard?message=importsuccess')
        
class OAuthCancel(APIView):
    def get(self, request):
        return redirect(FRONTEND_URL + '/dashboard?message=lichesscancel')
    
class LichessUrl(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        url = request.data.get('lichessUrl')
        if re.match(r'https://lichess\.org/[a-zA-Z0-9]{8,12}', url) is None: # Should be of format https://lichess.org/{gameId} where gameId is 12 characters or 8
            return Response({'error': 'Invalid URL format'}, status=400)
        lichess_id = url.split('/')[-1][:8]
        color = request.data.get('color')
        
        token = LichessToken.objects.filter(user=request.user).first()
        if Game.objects.filter(lichess_id=lichess_id, user=request.user).exists():
            return Response({'error': 'Game already imported'}, status=400)
        
        try:
            game = import_one_game(lichess_id, token)
            if not game:
                return Response({'error': 'Failed to import game'}, status=400)
            
            if color is None and token is not None:
                color = 'white' if game['players']['white']['user']['name'] == token.lichessUsername else 'black'
            g = Game.objects.create(
                    lichess_id=game['id'],
                    user=request.user,
                    opponent=game['players']['black']['user']['name'] if color == 'white' else game['players']['white']['user']['name'],
                    plies=len(game['moves']),
                    color=color == 'white',
                    moves=' '.join(game['moves']),
                    moves_uci=' '.join(game['moves_uci']),
                    middle_game_start=game['division'].get('middle'),
                    end_game_start=game['division'].get('end'),
                    result=calculate_result((1.0 if game['winner'] == 'white' else 0.0) if game.get('winner') else 0.5, color == 'white'),
                    date=ms_epoch_to_datetime(game['createdAt']),
                    time_control=f'{game["clock"]["initial"]}+{game["clock"]["increment"]}'
            )
            return Response({'message': 'Game imported successfully', 'ids': [g.id]}, status=200)
        except Exception as e:
            return Response({'error': 'Failed to import game: ' + str(e)}, status=400)
        
        
