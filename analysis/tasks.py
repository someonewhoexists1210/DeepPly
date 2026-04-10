from celery import shared_task
import os
import chess
from typing import Any
from main.models import Game
from classes import Position
from .utils import fetch_evals, analysis_pipeline, detect_50move_rule, detect_repitition
from .explanation import generate_explanations

MUSCLE_IP = os.getenv('MUSCLE_IP')
if not MUSCLE_IP:
    raise Exception("MUSCLE_IP not set in environment variables")

@shared_task(bind=True)
def analyse_game(self, game_id):
    try:
        game = Game.objects.filter(id=game_id).first()
        if not game:
            raise Exception(f'Game with id {game_id} not found')

        log_file = f'game_{game_id}_log.json'
        log_data = {'game_id': game.id, 'player': game.user.username}
    
        b = chess.Board()
        positions: list[Position] = []
        moves: list[str] = [move for move in game.moves.split() if move.strip()]
        for i, move in enumerate(moves):
            fen = b.fen()
            b.push_uci(move)
            pos = Position(fen=fen, index=i, move=move)
            positions.append(pos)

        positions.append(Position(fen=b.fen(), index=len(moves), move='')) # final position after all moves
        moverule, move_num = detect_50move_rule(positions)
        repetition, repitition_indices = detect_repitition(positions)

        if moverule:
            log_data['50move_rule'] = {'move_number': move_num, 'index': move_num}
            positions[move_num].notes['50move_rule'] = True
        if repetition:
            log_data['repetition'] = {'move_numbers': repitition_indices, 'indices': repitition_indices}
            for idx in repitition_indices:
                positions[idx].notes['repetition'] = True


        evals = fetch_evals(positions) # returns [{'fen': str, 'index': int,'eval': [{'pv': 'e2e4 e7e5', 'score': 20, 'mate': int, 'cp': int}, ...], ...}, ...]
        log_data['positions'] = evals  # pyright: ignore[reportArgumentType]
        for eval in evals:
            for pv in eval.eval:
                if not game.color:
                    pv.evaluation.score = -pv.evaluation.score
                    pv.evaluation.mate = -pv.evaluation.mate if pv.evaluation.mate is not None else None
                    pv.evaluation.cp = -pv.evaluation.cp if pv.evaluation.cp is not None else None

        analysis: list[dict[str, Any]] = []
        for i, a in enumerate(analysis_pipeline(evals, game.color)):
            if i == 0 or isinstance(a, list):
                log_data['critical_moments'] = a
                continue
            analysis.append(a)
        log_data['analysis'] = analysis

        explanations = generate_explanations(analysis)
        return explanations
    except Exception as e:
        raise e

    




            