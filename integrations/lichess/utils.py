import secrets
import string
import base64
import hashlib
from urllib.parse import urlencode
import requests
from .models import LichessToken
from datetime import datetime, timedelta
from django.utils import timezone
import json
import chess
import chess.pgn
import io

CLIENT_ID = "deepply.com"
import_session = requests.Session()

ms_epoch_to_datetime = lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.get_current_timezone())

def generate_oauth_url(provider_url, state, redirect_url):
    char_set = string.ascii_letters + string.digits
    code_verifier = ''.join(secrets.choice(char_set) for _ in range(128))
    bytes_verifier = code_verifier.encode()
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(bytes_verifier).digest()).rstrip(b'=').decode()

    params = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'redirect_uri': redirect_url,
        'code_challenge_method': 'S256',
        'code_challenge': code_challenge,
        'scope': 'email:read',
        'state': state
    }
    redirect = provider_url + urlencode(params)

    return code_verifier, redirect

def get_access_token(code, code_verifier, redirect_url):
    body = {
        'client_id': CLIENT_ID,
        'grant_type': 'authorization_code',
        'code': code,
        'code_verifier': code_verifier,
        'redirect_uri': redirect_url
    }

    response = requests.post("https://lichess.org/api/token", data=body)
    if response.status_code == 200:
        return response.json()
    else:
        print("Error fetching access token:", response.text)
        return None
    
def get_profile(access_token):
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    response = requests.get("https://lichess.org/api/account", headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print("Error fetching profile:", response.text)
        return None
    
def parse_game_json(game_data: dict):
    pgn_io = io.StringIO(game_data['pgn'])
    game = chess.pgn.read_game(pgn_io)
    if not game:
        return None
    moves = " ".join(move.uci() for move in game.mainline_moves())
    game_data['moves'] = moves
    return game_data


def import_all_games(token: LichessToken):
    headers = {
        'Authorization': f'Bearer {token.access_token}',
        'Accept': 'application/x-ndjson'
    }
    params = {
        'since': int((datetime.now(timezone.get_current_timezone()) - timedelta(days=365)).timestamp() * 1000),
        'max': 100, # USE LIMITING STRATEGY IN DOCS AFTER HACKCLUB
        'rated': True,
        'perfType': 'rapid,classical',
        'pgnInJson': True, 
        'evals': False,
        'clocks': False, ## ADD CLOCK TAGS FOR PAID USERS IN FUTURE
        'tags': False,
        'division': True,
        'opening': True,
    }
    url = f'https://lichess.org/api/games/user/{token.lichessUsername}?' + urlencode(params)
    response = requests.get(url, stream=True, headers=headers)
    response.raise_for_status()
    
    for line in response.iter_lines(decode_unicode=True):
        if line:
            game_data = json.loads(line)
            parsed = parse_game_json(game_data)
            if parsed:
                yield parsed
            
def import_one_game(game_id: str, token):

    headers = {
        'Accept': 'application/json'
    }
    if isinstance(token, LichessToken):
        headers['Authorization'] = f'Bearer {token.access_token}'

    params = {
        'pgnInJson': True, 
        'evals': False,
        'clocks': False, ## ADD CLOCK TAGS FOR PAID USERS IN FUTURE
        'tags': False,
        'division': True,
        'opening': True,
    }
    url = f'https://lichess.org/game/export/{game_id}?' + urlencode(params)
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    return parse_game_json(response.json())
    