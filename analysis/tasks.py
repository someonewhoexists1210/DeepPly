from celery import shared_task
from pathlib import Path
import os
import chess
from main.models import Game
from .classes import *
from .utils import fetch_evals, analysis_pipeline, detect_50move_rule, detect_repetition
from .explanation import generate_explanations
from django.conf import settings

MUSCLE_IP = os.getenv('MUSCLE_IP')
if not MUSCLE_IP:
    raise Exception("MUSCLE_IP not set in environment variables")

@shared_task(bind=True)
def analyse_game(self, game_id):
    try:
        print(f"Starting analysis for game_id: {game_id}")
        game = Game.objects.filter(id=game_id).first()
        if not game:
            raise Exception(f'Game with id {game_id} not found')

        log_file: Path = settings.GAME_RESULT_DIR / f'game_{game_id}_log.json'
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
        repetition, repetition_indices = detect_repetition(positions)

        if moverule:
            log_data['fifty_move_rule'] = move_num
            positions[move_num].notes['fifty_move_rule'] = True
        if repetition:
            log_data['repetition'] = repetition_indices
            for idx in repetition_indices:
                positions[idx].notes['repetition'] = True


        positions = fetch_evals(positions) # returns [{'fen': str, 'index': int,'eval': [{'pv': 'e2e4 e7e5', 'score': 20, 'mate': int, 'cp': int}, ...], ...}, ...]
        print(f"Fetched evaluations for game_id: {game_id}")
        log_data['positions'] = positions  # pyright: ignore[reportArgumentType]
        for position in positions:
            for pv in position.variations:
                if not game.color:
                    pv.evaluation.score = -pv.evaluation.score
                    pv.evaluation.mate = -pv.evaluation.mate if pv.evaluation.mate is not None else None
                    pv.evaluation.cp = -pv.evaluation.cp if pv.evaluation.cp is not None else None

        analysis: list[FullPositionResult] = analysis_pipeline(positions, game.color)
        log_data['analysis'] = analysis

        full_analysis = GameAnalysisResult.model_validate(log_data)
        with log_file.open('w', encoding='utf-8') as f:
            f.write(full_analysis.model_dump_json(indent=4))

        # explanations = generate_explanations(full_analysis)
        # return explanations
    except Exception as e:
        raise e

    




            