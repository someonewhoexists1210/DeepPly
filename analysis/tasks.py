from celery import shared_task
from pathlib import Path
import os
import chess
from main.models import Game
from main.utils import calculate_result
from .classes import *
from django.db import transaction
from .models import Position as PositionModel, AnalysisResult, TaskResult
from .utils import fetch_evals, analysis_pipeline, detect_50move_rule, detect_repetition
from .explanation import filter_analysis_for_explanation, generate_explanations
from django.conf import settings
from django.db.models.functions import Now
from django.db.models import F
import time
from django.db.utils import IntegrityError


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
        game = Game.objects.get(id=game_id)

        log_file: Path = settings.GAME_RESULT_DIR / f'full/game_{game_id}_log.json'
        log_file2: Path = settings.GAME_RESULT_DIR / f'filtered/game_{game_id}_filtered_log.json'
        log_data = {'game_id': game.id, 'player': game.user.username, "color": game.color, "result": "win" if game.result == 1 else ("loss" if game.result == 0 else "draw"), 'time_control': game.time_control}
    
        b = chess.Board()
        positions: list[Position] = []
        moves: list[str] = [move for move in game.moves_uci.split() if move.strip()]
        for i, move in enumerate(moves):
            fen = b.fen()
            piece = chess.piece_name(b.piece_at(chess.parse_square(move[:2])).piece_type) # type:ignore
            capture = b.is_capture(chess.Move.from_uci(move))
            captured_piece = chess.piece_name(b.piece_at(chess.parse_square(move[2:4])).piece_type) if capture else None # type:ignore
            b.push_uci(move)
            pos = Position(fen=fen, index=i, move=move, piece_moved=piece, capture=capture, captured_piece=captured_piece)
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

        positions = fetch_evals(positions, progress_update_func=lambda progress, message: self.update_state(state="STARTED", meta={'progress': progress, 'message': message})) # returns [{'fen': str, 'index': int,'eval': [{'pv': 'e2e4 e7e5', 'score': 20, 'mate': int, 'cp': int}, ...], ...}, ...]
        log_data['positions'] = positions  # pyright: ignore[reportArgumentType]
        temp_b = chess.Board()
        positions = [p for p in positions if len(p.variations[0].line.split()) > 0]

        for position in positions:
            temp_b.set_fen(position.fen)
            position.variations = [v for v in position.variations if v.line.strip() != '']
            position.engine_move = position.variations[0].line.split()[0]
            position.engine_piece_moved = chess.piece_name(temp_b.piece_at(chess.parse_square(position.engine_move[:2])).piece_type) if position.engine_move else None # type:ignore
            position.engine_capture = temp_b.is_capture(chess.Move.from_uci(position.engine_move)) if position.engine_move else False
            position.engine_captured_piece = chess.piece_name(temp_b.piece_at(chess.parse_square(position.engine_move[2:4])).piece_type) if position.engine_capture else None# type:ignore
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

        fen_list = [pos.fen for pos in positions]
        try:
            with transaction.atomic():
                objs = PositionModel.objects.select_for_update().filter(fen__in=fen_list, user=game.user)
                existing = {obj.fen: obj for obj in objs}
                missing = set([pos.fen for pos in positions if pos.fen not in existing])
                missing_objs = [PositionModel(fen=fen, user=game.user, hits=0) for fen in missing]
                PositionModel.objects.bulk_create(missing_objs)
                PositionModel.objects.filter(fen__in=fen_list, user=game.user).update(hits=F('hits') + 1, last_hit=Now())
                game.positions.add(*PositionModel.objects.filter(fen__in=fen_list, user=game.user))
        except IntegrityError as e:
            print(f"IntegrityError during position update: {e}")

        llm_start = time.time()
        explanation_output, input_tok, output_tok = generate_explanations(filtered_analysis)
        self.update_state(state="STARTED", meta={'progress': 100.0, 'message': 'Explanations generated'})
        end = time.time()

        task.status = "SUCCESS"
        task.progress = 100.0
        task.save()
        res = AnalysisResult.objects.create(
            game=game,
            model_input=filtered_analysis.model_dump(),
            tokens_input=input_tok,
            model_output=explanation_output.model_dump(),
            tokens_output=output_tok,
            llm_latency=end - llm_start,
            completion_time=end - t
        )
        print(res.game.id)
        game.analysed = True
        game.save()
        print("Time taken: ", end - t)
        return res.id

    except Game.DoesNotExist as e:
        task.status = "FAILURE"
        task.error_message = str(e)
        task.retry_count += 1
        task.save(update_fields=["status", "error_message", "retry_count", "updated_at"])
        raise
    except Exception as e:
        task.retry_count += 1
        if task.retry_count >= 3:
            task.status = "FAILURE"
            task.error_message = str(e)
            task.save(update_fields=["status", "error_message", "retry_count", "updated_at"])
            raise

        task.status = "RETRY"
        task.error_message = str(e)
        task.save(update_fields=["status", "error_message", "retry_count", "updated_at"])
        raise self.retry(countdown=1, exc=e)