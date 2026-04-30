import requests
import chess
import chess.pgn
import io
from datetime import datetime
from django.utils import timezone

s_epoch_to_datetime = lambda epoch: datetime.fromtimestamp(epoch, tz=timezone.get_current_timezone())


### USE CELERY IN FUTURE
def import_games(username, months=1):
    url = f'https://api.chess.com/pub/player/{username}/games/archives'
    headers = {'Content-Type': 'application/json', 'User-Agent': 'DeepPly/1.0 (darshjindal537@gmail.com)'}
    response = requests.get(url, headers=headers)
    if not response.ok:
        if response.status_code == 404:
            return {"error": "Username not found", "status_code": 404}
        if response.status_code == 429:
            return {"error": "Rate limit exceeded. Please try again later", "status_code": 429}

        return {"error": "Error fetching archives: " + response.text, "status_code": response.status_code}
    monthly_archive_list = response.json().get('archives', [])
    if len(monthly_archive_list) == 0:
        return {'error': "No games found", "status_code": 404}
    
    months = months if months < len(monthly_archive_list) else len(monthly_archive_list)

    games = {'games': []}
    for i in monthly_archive_list[-months:]:
        games_response = requests.get(i, headers=headers)
        if not games_response.ok:
            continue


        games_json = games_response.json().get('games', [])
        for game in games_json:
            pgn_io = io.StringIO(game['pgn'])
            b = chess.pgn.read_game(pgn_io)
            board = chess.Board()
            if not b:
                continue

            moves_uci = []
            moves = []
            for move in b.mainline_moves():
                moves.append(board.san(move))
                moves.append(move.uci())
                board.push(move)

            move_count = sum(1 for _ in b.mainline_moves())
            game['plies'] = move_count
            
            game['moves'] = moves
            game['moves_uci'] = moves_uci
            games['games'].append(game)

    print(f'Fetched {len(games["games"])} games for user {username}')
    return games
        
