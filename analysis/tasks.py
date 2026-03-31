from celery import shared_task
import os
import chess
from main.models import Game
from .models import Position
from .utils import fetch_evals, analysis_pipeline
from django.forms.models import model_to_dict

MUSCLE_IP = os.getenv('MUSCLE_IP')
if not MUSCLE_IP:
    raise Exception("MUSCLE_IP not set in environment variables")

@shared_task(bind=True)
def analyse_game(self, game_id):
    try:
        game = Game.objects.filter(id=game_id).first()
        if not game:
            raise Exception(f'Game with id {game_id} not found')

        self.update_state(state='EVALUATING', meta={'stage': 'Fetching positions', 'progress': 0})
        log_file = 'game_{game_id}_log.json'
        log_data = {'game_object': model_to_dict(game), 'player': model_to_dict(game.user)}
    
        b = chess.Board()
        positions = []
        moves = [move for move in game.moves.split() if move.strip()]
        for i, move in enumerate(moves):
            fen = b.fen()
            b.push_uci(move)
            positions.append({'fen': fen, 'index': i, 'move': move})
            if b.ply() % 2 != game.color: # only user moves
                p = Position.objects.get_or_create(fen=fen, user=game.user)[0]
        positions.append({'fen': b.fen(), 'index': len(moves), 'move': None}) # final position after all moves

        self.update_state(state='PROGRESS', meta={'stage': 'EVALUATING', 'progress': 5})
        evals = sorted(fetch_evals(positions, game.color), key=lambda x: x['index']) # returns [{'fen': str, 'index': int,'eval': [{'pv': 'e2e4 e7e5', 'score': 20, 'mate': int, 'cp': int}, ...], ...}, ...]
        log_data['positions'] = evals # type: ignore
        for eval in evals:
            for pv in eval['eval']:
                if game.color:
                    pv['score'] = -pv['score']
                    pv['mate'] = -pv['mate'] if pv['mate'] is not None else None
                    pv['cp'] = -pv['cp'] if pv['cp'] is not None else None

        for eval in evals:
            eval['eval'] = sorted(eval['eval'], key=lambda x: (x['mate'] is not None, x['mate'] if game.color else -x['mate'], x['cp'] if not game.color else -x['cp']), reverse=True)[:3] # keep top 3 lines, sorted by mate first then cp
            
        self.update_state(state='PROGRESS', meta={'stage': 'ANALYZING', 'progress': 25})
        analysis_pipeline(evals, game.color)
    except Exception as e:
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise e

    




            