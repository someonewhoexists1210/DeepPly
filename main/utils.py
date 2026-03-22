import chess
import chess.pgn
import io
from datetime import datetime

def parse_pgn(pgn_text, username=None, color=None):
    pgn_io = io.StringIO(pgn_text)
    num_games = 0
    game_list = [{
            'plies': 2,
            'moves': '',
            'color': 1,
            'result': 0.5,
            'date': datetime.now(),
            'time_control': ''
        }]
    game_list.pop()
    while chess.pgn.read_headers(pgn_io):
        num_games += 1

    if num_games == 0:
        return {'error': 'No valid games found in PGN.'}

    for _ in range(num_games):
        game = chess.pgn.read_game(pgn_io)
        if not game:
            return {'error': f'Invalid PGN in game {_ + 1}'}
        
        if not color:
            headers = game.headers
            if not headers:
                return {'error': f'Need to provide color if PGN headers are missing in game {_ + 1}'}
            
            if headers.get('White') == username:
                color = 0
            elif headers.get('Black') == username:
                color = 1
            else:
                return {'error': f'Username not found in PGN headers for game {_ + 1}. Please provide color.'}

        plies = sum(1 for _ in game.mainline_moves())
        moves = ' '.join(move.uci() for move in game.mainline_moves())
        if game.headers.get('Result') == '1-0':
            result = 1.0 if color == 0 else 0.0
        elif game.headers.get('Result') == '0-1':
            result = 1.0 if color == 1 else 0.0
        elif game.headers.get('Result') == '1/2-1/2':
            result = 0.5
        else:
            return {'error': f'Invalid game result in PGN headers for game {_ + 1}.'}
        
        date = game.headers.get('Date')
        if date and date != '????.??.??':
            try:
                date = datetime.strptime(date, '%Y.%m.%d')
            except ValueError:
                date = None

        timecontrolheader = game.headers.get('TimeControl')
        if timecontrolheader and timecontrolheader != '?':
            time_control = "/".join(timecontrolheader.split('+'))
        else:
            time_control = None

        game_list.append({
            'plies': plies,
            'moves': moves,
            'color': color,
            'result': result,
            'date': date,
            'time_control': time_control
        })

    return game_list

def calculate_result(result, color):
    if result == 0.5:
        return 0.5
    return (1.0 if result == 0.0 else 0.0) if color == 1 else result