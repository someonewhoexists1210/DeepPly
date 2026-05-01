import chess
import chess.pgn
import io
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Any

class GameData(BaseModel):
    plies: int
    moves: str
    moves_uci: str
    color: int
    result: float
    opponent: str = "Unknown"
    date: Optional[datetime] = None
    time_control: Optional[str] = None

def parse_pgn(pgn_text, username=None, color=None):
    pgn_io = io.StringIO(pgn_text)
    num_games = 0
    game_list: list[dict[str, Any]] = []
    
    while chess.pgn.read_game(pgn_io):
        num_games += 1

    if num_games == 0:
        if pgn_text.strip():
            return {'error': 'Need valid headers for analysis'}
        return {'error': 'No valid games found in PGN.'}

    for _ in range(num_games):
        game = chess.pgn.read_game(pgn_io)
        if not game:
            return {'error': f'Invalid PGN in game {_ + 1}'}
        
        board = chess.Board()
        moves = []
        moves_uci = []
        for move in game.mainline_moves():
            moves.append(board.san(move))
            moves_uci.append(move.uci())
            board.push(move)

        plies = len(moves)
        
        if not color:
            headers = game.headers
            if not headers:
                color = 1
            elif headers.get('White') == username:
                color = 1
            elif headers.get('Black') == username:
                color = 0
            else:
                return {'error': f'Username not found in PGN headers for game {_ + 1}. Please provide color.'}
        
        if game.headers.get('Result') == '1-0':
            result = 1.0 if color == 1 else 0.0
        elif game.headers.get('Result') == '0-1':
            result = 1.0 if color == 0 else 0.0
        elif game.headers.get('Result') == '1/2-1/2':
            result = 0.5
        else:
            return {'error': f'Invalid game result in PGN headers for game {_ + 1}.'}
        
        date_str = game.headers.get('Date')
        date = None
        if date_str and date_str != '????.??.??':
            try:
                date = datetime.strptime(date_str, '%Y.%m.%d')
            except ValueError:
                date = None

        timecontrolheader = game.headers.get('TimeControl')
        if timecontrolheader and timecontrolheader != '?':
            time_control = "/".join(timecontrolheader.split('+'))
        else:
            time_control = None

        game_data = GameData(
            plies=plies,
            opponent=game.headers.get('Black', "Unknown") if color == 1 else game.headers.get('White', "Unknown"),
            moves=' '.join(moves),
            moves_uci=' '.join(moves_uci),
            color=color,
            result=result,
            date=date,
            time_control=time_control
        )
        game_list.append(game_data.model_dump())

    return game_list

def calculate_result(result, color):
    if result == 0.5:
        return 0.5
    return (1.0 if result == 0.0 else 0.0) if color == 0 else result