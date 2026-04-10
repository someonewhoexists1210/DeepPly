import os
import requests
import time
import json
import chess
from typing import Any
from classes import *
from scorers import *
from sklearn.metrics.pairwise import cosine_similarity
from scipy.special import softmax
import numpy as np
import numpy.typing as npt


MUSCLE_IP = os.getenv('MUSCLE_IP')
if not MUSCLE_IP:
    raise Exception("MUSCLE_IP not set in environment variables")

WEIGHTS = np.array([])
PLAN_TEMP = 1.0


def detect_repitition(game: list[Position]) -> tuple[bool, list[int]]:
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

def fetch_evals(positions, retry_counter=0) -> list[Position]: # returns [{'fen': str, 'eval': {'pv': 'e2e4 e7e5', 'score': 20}}]
    response = requests.post(f'http://{MUSCLE_IP}/evaluate', json={'game_data': positions})
    if response.status_code != 200:
        raise Exception(f'MUSCLE evaluation failed with status code {response.status_code}, response: {response.text}')
    
    data = response.json()
    job_id: str = data.get('job_id')
    evals: list[Position] = data.get('cached', [])
    remaining: int = data.get('remaining', 0)

    start_time = time.time()
    while True:
        current_time = time.time()
        if current_time - start_time > 30: # timeout after 30 seconds
            raise Exception('MUSCLE evaluation timed out after 30 seconds')
        
        status_res = requests.get(f'http://{MUSCLE_IP}/result/{job_id}')
        if status_res.status_code != 200:
            raise Exception(f'MUSCLE status check failed with status code {status_res.status_code}, response: {status_res.text}')
        
        st_data = status_res.json()
        status = st_data.get('status')
        if 'failed' in status.lower() or 'expired' in status.lower():
            if retry_counter >= 3:
                raise Exception(f'MUSCLE evaluation failed with status: {status}. Retried {retry_counter} times.')  
            evals = fetch_evals(positions, retry_counter+1)
            break
        elif 'pending' in status.lower() or 'processing' in status.lower():
            time.sleep(0.5)
        elif 'complete' in status.lower():
            results = st_data.get('results', [])
            evals.extend([json.loads(pos) for pos in results])
            if len(results) != remaining:
                raise Exception(f'MUSCLE returned complete but results count {len(results)} does not match expected {remaining}')
            break
        else:
            raise Exception(f'Unexpected MUSCLE status: {status}')
        
    evals = sorted(evals, key=lambda x: x.index)
    return evals

def analysis_pipeline(evals: list[Position], color=1):
    log_data = {}
    for ev in evals:
        if not ev.eval:
            raise Exception('Evaluation data missing for some positions')
        
    cms = [ev for ev in evals if ev.index in flag_critical(evals, color)]
    criticals = [Position(cm.fen, cm.index, cm.move) for cm in cms]
    yield criticals

    for i in range(len(evals)-1):
        if i % 2 != color:
            continue
        
        pos_log: dict[str, Any] = {}
        pos_log['index'] = evals[i].index
        pos_log['fen'] = evals[i].fen
        pos_log['move'] = evals[i].move
        pos_log['strategic_analysis'] = positional_analysis(evals[i], evals[i+1].eval[0].evaluation)  # pyright: ignore[reportOptionalSubscript]
        pos_log['tactical_analysis'] = tactical_analysis() # TODO

        if evals[i].index in log_data['critical_moments']:
            pos_log['critical'] = True
        
        if pos_log['tactical_analysis']['tactical_mistake']:
            pos_log['overall_mistake'] = True
            pos_log['mistake_type'] = 'tactical'
        elif pos_log['strategic_analysis']['strategic_mistake']:
            pos_log['overall_mistake'] = True
            pos_log['mistake_type'] = 'strategic'

        yield pos_log

def tactical_analysis() -> dict:
    return {}

def flag_critical(evals: list[Position], color=1, threshold=50, mate_threshold=5) -> list[int]: # returns list of indices of critical moments
    critical_moments = []
    index = 0
    for eval in evals:
        if index == len(evals)-1:
            break

        if index % 2 != color:
            continue

        if len(eval.eval) == 0:
            raise Exception('No evaluation data available for critical moment analysis')
        
        current_eval = eval.eval[0]
        next_eval: PV = evals[index + 1].eval[0]

        if current_eval.evaluation.mate is not None:
            if next_eval.evaluation.mate is not None:
                if current_eval.evaluation.mate < 0:
                    continue # if already losing, not necessarily critical (may need to revise in future)

                mate_delta = next_eval.evaluation.mate - current_eval.evaluation.mate
                if next_eval.evaluation.mate * current_eval.evaluation.mate < 0: # sign change indicates a blunder leading to a losing position from a winning one
                    critical_moments.append(index)
                elif mate_delta > mate_threshold and current_eval.evaluation.mate < 10: # Missed mate or significant increase in mate distance
                    critical_moments.append(index)

            elif next_eval.evaluation.cp < 500: # pyright: ignore[reportOptionalOperand] # mate missed into a not as winning position, could be losing now
                critical_moments.append(index)
        
        elif next_eval.evaluation.mate is not None:
            if current_eval.evaluation.cp > 0 and next_eval.evaluation.mate < 0: # pyright: ignore[reportOptionalOperand] # missed a winning position into a losing one
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
            
def positional_analysis(ev: Position, next_position_eval: Evaluation) -> dict[str, Any]:
    '''
    Engine Moves:
    1. Classify move concept
    2. Compute vector repr
    3. Cluster based on vector
    4. Collect concepts per cluster

    User Move:
    1. Classify move concept
    2. Compute vector repr
    3. Compare to engine clusters, match by vector or move concept (tbd later)

    Compute V_Gap from selected cluster
    Extract top features from V_Gap

    if intent same, focus on features of V_gap
    if intent different, focus on intent mismatch and secondarily features of V_gap
    '''

    if not ev.eval or not ev.move:
        raise Exception('No evaluation or move data available for positional analysis')
    log_data = {}
    board = chess.Board(ev.fen)
    board.push_uci(ev.move)
    user_vector = generate_position_vector(board.fen())
    board.pop()

    engine_vectors: list[PositionVector] = []
    for pv in ev.eval:
        board.push_uci(pv.line.split()[0])
        engine_vector = generate_position_vector(board.fen())
        board.pop()
        engine_vectors.append(engine_vector)

    log_data['vectors'] = [user_vector] + engine_vectors
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
        representative_eval = ev.eval[cluster[0]].evaluation
        cluster_data.append(Cluster(V=representative, E=representative_eval, idx=ind))

    cluster_data = sorted(cluster_data, key=lambda x: x.E.score, reverse=True)
    log_data['cluster_data'] = cluster_data

    plan_distances = np.array([np.linalg.norm(WEIGHTS * (user_vector - cluster.V)) for cluster in cluster_data])
    log_data['plan_distances'] = plan_distances

    plan_probabilities: npt.NDArray[np.float64]  = softmax(-plan_distances / PLAN_TEMP)
    log_data['plan_probabilities'] = plan_probabilities

    user_plan = cluster_data[np.argmax(plan_probabilities)]
    log_data['user_plan'] = user_plan

    user_plan_confidence = np.max(plan_probabilities)
    log_data['user_plan_confidence'] = user_plan_confidence

    plan_match = 1
    if user_plan_confidence < 1 / len(plan_probabilities) + 0.1: # if all plans are very close in distance, no clear plan followed
        plan_match = 0
    elif user_plan_confidence < 1 / len(plan_probabilities) + 0.25:
        plan_match = 0.5

    log_data['plan_match'] = plan_match

    eval_diff = -np.diff([cluster.E.score for cluster in cluster_data]) 

    domination = False
    current_eval = cluster_data[0].E
    next_eval = cluster_data[1].E

    curr_mate = current_eval.mate
    next_mate = next_eval.mate

    curr_is_mate = curr_mate is not None
    next_is_mate = next_mate is not None

    if curr_is_mate and next_is_mate:
        if curr_mate < 6 and abs(eval_diff[0]) > 3:
            domination = True
    elif curr_is_mate:
        if next_eval.cp < 500: # type: ignore[reportOptionalOperand]
            domination = True
    elif next_eval.mate is not None and next_eval.mate < 0:
        if current_eval.cp > -500: # type: ignore[reportOptionalOperand]
            domination = True
    else:
        if abs(eval_diff[0]) > 50:
            domination = True

    log_data['domination'] = domination

    if domination:
        V_ref = cluster_data[0].V
        E_ref = cluster_data[0].E
    else:
        V_ref = user_plan.V
        E_ref = user_plan.E

    log_data['V_ref'] = V_ref
    V_gap = WEIGHTS * (V_ref - user_vector)
    log_data['V_gap'] = V_gap
    
    E_gap = E_ref - next_position_eval
    log_data['E_gap'] = E_gap

    is_acceptable_move = cluster_data[0].E - next_position_eval < 20
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
        return log_data
    
    if is_acceptable_move:
        result = f'User move is strong, follows cluster {user_plan.idx} with representative vector {user_plan.V} closely with similar evaluation to the representative move, no clear mistakes'
        log_data['strategic_mistake'] = False
        log_data['result'] = result
        return log_data
    
    if domination:
        if user_plan.idx != cluster_data[0].idx:
            result = f"User is not following the main plan of the position"
            log_data['strategic_mistake'] = True
            log_data['result'] = result
            return log_data
        
        result = f'User follows main plan of position, but there is a strategic gap shown by vector {V_gap}'
        log_data['strategic_mistake'] = True
        log_data['result'] = result
        return log_data


    result = f"User follows a clear plan with confidence {user_plan_confidence:.2f}, but there is a strategic gap shown by vector {V_gap} and evaluation gap of {E_gap} between user move and most similar engine plan move"
    log_data['strategic_mistake'] = True
    log_data['result'] = result
    return log_data

def generate_position_vector(fen: str, color=1) -> PositionVector:
    pass # RUN SCORERS
    return np.random.rand(300)