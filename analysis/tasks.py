from celery import shared_task
from pathlib import Path
import os
import chess
from main.models import Game
from .classes import *
from django.db import transaction
from .models import Position as PositionModel, AnalysisResult, TaskResult
from .utils import fetch_evals, analysis_pipeline, detect_50move_rule, detect_repetition
from .explanation import filter_analysis_for_explanation, generate_explanations
from django.conf import settings
from django.db.models.functions import Now
from django.db.models import F
import time


MUSCLE_IP = os.getenv('MUSCLE_IP')
if not MUSCLE_IP:
    raise Exception("MUSCLE_IP not set in environment variables")

@shared_task(bind=True)
def analyse_game(self, game_id):
    task_id = self.request.id
    task = TaskResult.objects.get_or_create(task_id=task_id)[0]
    task.status = "STARTED"
    self.update_state(state="STARTED", meta={'progress': 0.0})

    try:
        t = time.time()
        print(f"Starting analysis for game_id: {game_id}")
        game = Game.objects.filter(id=game_id).first()
        if not game:
            raise Exception(f'Game with id {game_id} not found')

        log_file: Path = settings.GAME_RESULT_DIR / f'full/game_{game_id}_log.json'
        log_file2: Path = settings.GAME_RESULT_DIR / f'filtered/game_{game_id}_filtered_log.json'
        log_data = {'game_id': game.id, 'player': game.user.username, "color": game.color}
    
        b = chess.Board()
        positions: list[Position] = []
        moves: list[str] = [move for move in game.moves.split() if move.strip()]
        for i, move in enumerate(moves):
            fen = b.fen()
            piece = chess.piece_name(b.piece_at(chess.parse_square(move[:2])).piece_type) # type:ignore
            b.push_uci(move)
            pos = Position(fen=fen, index=i, move=move, piece_moved=piece)
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
        log_data['positions'] = positions  # pyright: ignore[reportArgumentType]
        for position in positions:
            for pv in position.variations:
                if not game.color:
                    pv.evaluation.score = -pv.evaluation.score
                    pv.evaluation.mate = -pv.evaluation.mate if pv.evaluation.mate is not None else None
                    pv.evaluation.cp = -pv.evaluation.cp if pv.evaluation.cp is not None else None

        self.update_state(state="STARTED", meta={'progress': 40.0, 'message': 'Evaluations fetched'})
        task.progress = 40.0
        task.save()

        analysis: list[FullPositionResult] = analysis_pipeline(positions, game.color)
        self.update_state(state="STARTED", meta={'progress': 60.0, 'message': 'Analysis complete'})
        task.progress = 60.0
        task.save()

        log_data['analysis'] = analysis

        full_analysis = GameAnalysisResult.model_validate(log_data)
        with log_file.open('w', encoding='utf-8') as f:
            f.write(full_analysis.model_dump_json(indent=4))

        filtered_analysis = filter_analysis_for_explanation(full_analysis)
        with log_file2.open('w', encoding='utf-8') as f:
            f.write(filtered_analysis.model_dump_json(indent=4))

        game.analysed = True
        fen_list = [pos.fen for pos in positions]
        with transaction.atomic():
            objs = PositionModel.objects.select_for_update().filter(fen__in=fen_list, user=game.user)
            existing = {obj.fen: obj for obj in objs}
            missing = [PositionModel(fen=pos.fen, user=game.user, hits=0) for pos in positions if pos.fen not in existing]
            PositionModel.objects.bulk_create(missing)
            PositionModel.objects.filter(fen__in=fen_list, user=game.user).update(hits=F('hits') + 1, last_hit=Now())
            game.positions.add(*PositionModel.objects.filter(fen__in=fen_list, user=game.user))

        llm_start = time.time()
        explanation_output, input_tok, output_tok = generate_explanations(filtered_analysis)
        self.update_state(state="STARTED", meta={'progress': 100.0, 'message': 'Explanations generated'})
        end = time.time()

        task.status = "SUCCESS"
        task.progress = 100.0
        task.save()
        res = AnalysisResult.objects.create(
            model_input=filtered_analysis.model_dump(),
            tokens_input=input_tok,
            model_output=explanation_output.model_dump(),
            tokens_output=output_tok,
            llm_latency=end - llm_start,
            completion_time=end - t
        )
        game.analysed = True
        game.analysis = res  # pyright: ignore[reportAttributeAccessIssue]
        game.save()
        print("Time taken: ", end - t)
        return res.id

    except Exception as e:
        task.status = "FAILURE"
        task.error_message = str(e)
        task.retry_count += 1
        task.save()
        raise self.retry(countdown=1, exc=e)