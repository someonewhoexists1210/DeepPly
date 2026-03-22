from celery import shared_task
import os
import chess
from main.models import Game
from .models import Position
from .utils import fetch_evals, analysis_pipeline

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

        b = chess.Board()
        positions = []
        for move in game.moves.split():
            b.push_uci(move)
            fen = b.fen()
            p = Position.objects.get_or_create(fen=fen, user=game.user)[0]
            p.number_of_hits += 1
            p.save()
            positions.append(p.fen)

        self.update_state(state='PROGRESS', meta={'stage': 'EVALUATING', 'progress': 5})
        evals = fetch_evals(positions)
        self.update_state(state='PROGRESS', meta={'stage': 'ANALYZING', 'progress': 25})
        analysis_pipeline(evals)
    except Exception as e:
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise e

    




            