import os
import requests
import time
import chess
from typing import Any
from .classes import *
from .scorers import generate_position_vector
from sklearn.metrics.pairwise import cosine_similarity
from scipy.special import softmax
import numpy as np
import numpy.typing as npt
from pydantic import TypeAdapter

MUSCLE_IP = os.getenv('MUSCLE_IP')
if not MUSCLE_IP:
    raise Exception("MUSCLE_IP not set in environment variables")

VECTOR_LENGTH = len(VECTOR_FORMAT['format']['features'])
WEIGHTS = json.load(open('analysis/vector_weights.json'))
PLAN_TEMP = 0.33

def zip_position_vector(position_vector: PositionVector | list[str], format: list[str] = VECTOR_FEATURES) -> dict[str, dt]:
    return dict(zip(format, position_vector))

def diff_vector_to_semantic(vector: DiffVector) -> list[str]:
    semantic = []
    for value in vector:
        if value < -0.1:
            semantic.append('user position has more')
        elif value > 0.1:
            semantic.append('engine position has more')
    return semantic

def detect_repetition(game: list[Position]) -> tuple[bool, list[int]]:
    all_positions: dict[str, list[int]] = {}
    for pos in game:
        pos.fen = ' '.join(pos.fen.split()[:4])
        exists = all_positions.get(pos.fen)
        if exists is not None:
            all_positions[pos.fen].append(pos.index)
        else:
            all_positions[pos.fen] = [pos.index]

    for fen, indices in all_positions.items():
        if len(indices) >= 3:
            return (True, indices)
    return (False, [])

def detect_50move_rule(game: list[Position]) -> tuple[bool, int]:
    for pos in game:
        half_move_clock = int(pos.fen.split()[4])        
        if half_move_clock >= 100:
            return (True, pos.index)
    return (False, -1)

def fetch_evals(positions: list[Position], progress_update_func=None, retry_counter=0) -> list[Position]: # returns [{'fen': str, 'eval': {'pv': 'e2e4 e7e5', 'score': 20}}]
    serialized = TypeAdapter(list[Position]).dump_python(positions)
    response = requests.post(f'http://{MUSCLE_IP}/evaluate', json=serialized)
    if response.status_code != 200:
        raise Exception(f'MUSCLE evaluation failed with status code {response.status_code}, response: {response.text}')
    
    data = response.json()
    job_id: str = data.get('job_id')
    evals: list[Position] = TypeAdapter(list[Position]).validate_python(data.get('cached', []))
    remaining: list = data.get('remaining', [])

    start_time = time.time()
    while True and len(remaining) > 0:
        current_time = time.time()
        if current_time - start_time > 180: # timeout after 180 seconds
            raise Exception('MUSCLE evaluation timed out after 180 seconds')
        
        status_res = requests.get(f'http://{MUSCLE_IP}/result/{job_id}')
        if status_res.status_code != 200:
            raise Exception(f'MUSCLE status check failed with status code {status_res.status_code}, response: {status_res.text}')
        
        st_data = status_res.json()
        status = st_data.get('status')
        if 'failed' in status.lower() or 'expired' in status.lower():
            if retry_counter >= 3:
                raise Exception(f'MUSCLE evaluation failed with status: {status}. Retried {retry_counter} times.')  
            evals = fetch_evals(positions, progress_update_func=progress_update_func, retry_counter=retry_counter+1)
            break
        elif 'pending' in status.lower() or 'processing' in status.lower():
            progress_update_func(40 * round(st_data.get('done', 0) / st_data.get('total', 1), 1), f"") if progress_update_func else None
            time.sleep(0.5)
        elif 'complete' in status.lower():
            results = st_data.get('result', [])
            evals.extend(TypeAdapter(list[Position]).validate_python([json.loads(r) for r in results]))
            if len(results) != len(remaining):
                raise Exception(f'MUSCLE returned complete but results count {len(results)} does not match expected {len(remaining)}')
            break
        else:
            raise Exception(f'Unexpected MUSCLE status: {status}')
        

    print(f"MUSCLE evaluated in {time.time() - start_time:.2f} seconds with {len(evals)} results")
    evals = sorted(evals, key=lambda x: x.index)
    return evals

def analysis_pipeline(positions: list[Position], color=1) -> list[FullPositionResult]: # yields either FullPositionResult for each position or a list of critical moment indices at the start
    for position in positions:
        if len(position.variations) == 0:
            raise Exception('Evaluation data missing for some positions')
        
    cms = [position for position in positions if position.index in flag_critical(positions, color)]
    criticals = [position.index for position in cms]
    
    results: list[FullPositionResult] = []
    for i in range(len(positions) - 1):
        if i % 2 == color:
            continue
        
        pos_log: dict[str, Any] = {}
        pos_log['strategic_analysis'] = positional_analysis(positions[i], positions[i+1].variations[0].evaluation)
        if positions[i].index in criticals:
            pos_log['tactical_analysis'] = tactical_analysis(positions[i].fen, retry_counter=0)
        else:
            pos_log['tactical_analysis'] = None

        if positions[i].index in criticals:
            pos_log['critical'] = True
        
        if pos_log['tactical_analysis']:
            pos_log['overall_mistake'] = True
            pos_log['mistake_type'] = 'tactical'
        elif pos_log['strategic_analysis'].strategic_mistake:
            pos_log['overall_mistake'] = True
            pos_log['mistake_type'] = 'strategic'

        pos_obj = FullPositionResult.model_validate(pos_log)
        results.append(pos_obj)

    return results

def tactical_analysis(fen: str, retry_counter: int = 0) -> TacticalDetectionResult | None:
    board = chess.Board(fen)
    if not board.is_valid():
        raise Exception('Invalid FEN provided for tactical analysis')
    
    response = requests.post(f'https://chessgrammar.com/api/v1/extract', json={'fen': fen})
    if not response.ok:
        if response.status_code == 429:
            if retry_counter >= 3:
                raise Exception(f'Tactical detection API rate limit exceeded. Retried {retry_counter} times.')
            time.sleep(2 ** (retry_counter + 2)) # exponential backoff
            return tactical_analysis(fen, retry_counter=retry_counter+1)
        raise Exception(f'Tactical detection API call failed with status code {response.status_code}, response: {response.text}')

    data = response.json()
    count = data.get('count', 0)
    tactics_list = data.get('tactics', [])
    if count == 0: return None
    if len(tactics_list) != count:
        raise Exception(f'Tactical detection API returned count {count} but tactics list has length {len(tactics_list)}')
    
    ## FUTURE: log latencies
    main_tactic = tactics_list[0]
    tactic_result = TacticalDetectionResult.model_validate(main_tactic)
    return tactic_result

def flag_critical(positions: list[Position], color=1, threshold=50, mate_threshold=5, oneside=True) -> list[int]: # returns list of indices of critical moments
    critical_moments: list[int] = []
    index = 0
    for position in positions:
        if index == len(positions)-1:
            break

        if oneside and index % 2 == color:
            index += 1
            continue

        if len(position.variations) == 0:
            raise Exception('No evaluation data available for critical moment analysis')
        
        current_eval: PV = position.variations[0]
        next_eval: PV = positions[index + 1].variations[0]

        if current_eval.evaluation.mate is not None:
            if next_eval.evaluation.mate is not None:
                if current_eval.evaluation.mate < 0:
                    continue # if already losing, not necessarily critical (may need to revise in future)

                mate_delta = next_eval.evaluation.mate - current_eval.evaluation.mate
                if next_eval.evaluation.mate * current_eval.evaluation.mate < 0: # sign change indicates a blunder leading to a losing position from a winning one
                    critical_moments.append(index)
                elif mate_delta > mate_threshold and current_eval.evaluation.mate < 10: # Missed mate or significant increase in mate distance
                    critical_moments.append(index)

            elif next_eval.evaluation.cp is not None and next_eval.evaluation.cp < 500: # mate missed into a not as winning position, could be losing now
                critical_moments.append(index)
        
        elif next_eval.evaluation.mate is not None:
            if current_eval.evaluation.cp is not None and current_eval.evaluation.cp > 0 and next_eval.evaluation.mate < 0: # missed a winning position into a losing one
                critical_moments.append(index)
                continue

        elif current_eval.evaluation.cp is not None and next_eval.evaluation.cp is not None:
            cp_delta = next_eval.evaluation.cp - current_eval.evaluation.cp
            if next_eval.evaluation.cp * current_eval.evaluation.cp < 0 and current_eval.evaluation.cp > 0: # sign change indicates a blunder leading to a losing position from a winning one
                critical_moments.append(index)
            elif cp_delta < -threshold and current_eval.evaluation.cp < 300: # significant mistake
                critical_moments.append(index)

        index += 1

    return critical_moments
            
def positional_analysis(position: Position, next_position_eval: Evaluation) -> PositionalPipelineResult:
    if len(position.variations) == 0 or position.move.strip() == '':
        raise Exception('No evaluation or move data available for positional analysis')
    log_data = {}
    board = chess.Board(position.fen)
    board.push_uci(position.move)
    user_vector_full = generate_position_vector(board, not board.turn)
    user_vector = user_vector_full[0]
    board.pop()

    engine_vectors: list[PositionVector] = []
    engine_vectors_full: list[tuple[PositionVector, PositionVector | None]] = []
    for variation in position.variations:
        board.push_uci(variation.line.split()[0])
        engine_vector_full = generate_position_vector(board, not board.turn)
        engine_vector = engine_vector_full[0]
        engine_vectors_full.append(engine_vector_full)
        engine_vectors.append(engine_vector)
        board.pop()

    log_data['vectors_full'] = [user_vector_full] + engine_vectors_full
    log_data['user_vector'] = user_vector
    log_data['engine_vectors'] = engine_vectors
    clusters: list[list[int]] = []
    for v_ind, vect in enumerate(engine_vectors):
        added = False
        for cluster in clusters:
            cluster_vecs = [engine_vectors[i] for i in cluster]
            sim_matrix = cosine_similarity(np.array([vect]), cluster_vecs) # type:ignore
            if np.mean(sim_matrix) > 0.85:
                cluster.append(v_ind)
                added = True
                break
        
        if not added:
            clusters.append([v_ind])
    
    log_data['clusters'] = clusters
    cluster_data: list[Cluster] = []
    for ind, cluster in enumerate(clusters):
        representative = engine_vectors[cluster[0]]
        representative_eval = position.variations[cluster[0]].evaluation
        cluster_data.append(Cluster(V=representative, E=representative_eval, idx=ind))

    cluster_data = sorted(cluster_data, key=lambda x: x.E.score, reverse=True)
    log_data['cluster_data'] = cluster_data

    plan_distances: npt.NDArray = np.array([np.linalg.norm(WEIGHTS * (user_vector - cluster.V)) for cluster in cluster_data])
    log_data['plan_distances'] = plan_distances

    plan_probabilities: npt.NDArray= softmax(-plan_distances / PLAN_TEMP)
    log_data['plan_probabilities'] = plan_probabilities

    user_plan = cluster_data[np.argmax(plan_probabilities)]
    log_data['user_plan'] = user_plan

    user_plan_confidence = np.max(plan_probabilities)
    log_data['user_plan_confidence'] = user_plan_confidence

    plan_match = 1
    if user_plan_confidence < 1 / len(plan_probabilities) + 0.1: # if all plans are very close in distance, no clear plan followed
        plan_match = -1
    elif user_plan_confidence < 1 / len(plan_probabilities) + 0.25:
        plan_match = 0

    log_data['plan_match'] = plan_match

    eval_diff = -np.diff([cluster.E.score for cluster in cluster_data]) 

    domination = False
    current_eval = cluster_data[0].E
    if (len(cluster_data) > 1):
        next_eval = cluster_data[1].E
    
        curr_mate = current_eval.mate
        next_mate = next_eval.mate

        curr_is_mate = curr_mate is not None
        next_is_mate = next_mate is not None

        if curr_is_mate and next_is_mate:
            if curr_mate < 6 and abs(eval_diff[0]) > 3:
                domination = True
        elif curr_is_mate:
            if next_eval.cp is not None and next_eval.cp < 500:
                domination = True
        elif next_eval.mate is not None and next_eval.mate < 0:
            if current_eval.cp is not None and current_eval.cp > -500:
                domination = True
        else:
            if abs(eval_diff[0]) > 50:
                domination = True
    else:
        domination = True
    log_data['domination'] = domination

    if domination:
        V_ref = cluster_data[0].V
        E_ref = cluster_data[0].E
    else:
        V_ref = user_plan.V
        E_ref = user_plan.E

    log_data['V_ref'] = V_ref
    log_data['E_ref'] = E_ref
    V_gap: DiffVector = WEIGHTS * (V_ref - user_vector)
    log_data['V_gap'] = V_gap
    log_data['next_position_eval'] = next_position_eval

    is_acceptable_move = cluster_data[0].E - next_position_eval <= 20
    log_data['is_acceptable_move'] = is_acceptable_move

    if plan_match == 0:
        if domination:
            result = f'User move does not follow any clear engine plan and there is a dominating plan with evaluation {cluster_data[0].E}, indicating a strategic mistake of not following the main plan of the position'
        elif is_acceptable_move:
            result = f'User move is reasonable and keeps the position within acceptable range, but does not follow any clear engine plan'
        else:
            result = "No clear plan detected, didn't match any engine plans clearly"
        log_data['strategic_mistake'] = True
        log_data['result'] = result
        res = PositionalPipelineResult.model_validate(log_data)
        return res
    
    if is_acceptable_move:
        result = f'User move is strong, follows engine plans closely with similar evaluation to the representative move, no clear mistakes'
        log_data['strategic_mistake'] = False
        log_data['result'] = result
        res = PositionalPipelineResult.model_validate(log_data)
        return res
    
    if domination:
        if user_plan.idx != cluster_data[0].idx:
            result = f"User is not following the main plan of the position"
            log_data['strategic_mistake'] = True
            log_data['result'] = result
            res = PositionalPipelineResult.model_validate(log_data)
            return res
        
        result = f'User follows main plan of position, but there is a strategic gap'
        log_data['strategic_mistake'] = True
        log_data['result'] = result
        res = PositionalPipelineResult.model_validate(log_data)
        return res


    result = f"User follows a clear plan with confidence {user_plan_confidence:.2f}, but there is a strategic gap"
    log_data['strategic_mistake'] = True
    log_data['result'] = result


    res = PositionalPipelineResult.model_validate(log_data)
    return res
                              