import os
import requests
import time
import json
import chess
from typing import Any
from scorers import *
from sklearn.metrics.pairwise import cosine_similarity
from scipy.special import softmax
import numpy as np

MUSCLE_IP = os.getenv('MUSCLE_IP')
if not MUSCLE_IP:
    raise Exception("MUSCLE_IP not set in environment variables")

WEIGHTS = np.array([])
PLAN_TEMP = 1.0

def fetch_evals(positions, color, retry_counter=0) -> list[dict]: # returns [{'fen': str, 'eval': {'pv': 'e2e4 e7e5', 'score': 20}}]
    response = requests.post(f'http://{MUSCLE_IP}/evaluate', json={'game_data': positions})
    if response.status_code != 200:
        raise Exception(f'MUSCLE evaluation failed with status code {response.status_code}, response: {response.text}')
    
    data = response.json()
    job_id = data.get('job_id')
    evals = data.get('cached')
    remaining = data.get('remaining', 0)

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
            evals = fetch_evals(positions, color, retry_counter+1)
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
        
    evals = sorted(evals, key=lambda x: x['index'])
    return evals

def analysis_pipeline(evals: list[dict], color=0):
    log_data = {}
    cms = [ev for ev in evals if ev['index'] in flag_critical(evals, color)]
    log_data['critical_moments'] = [(cm['index'],cm['fen'], cm['move']) for cm in cms]
    
    positional_log = []
    for i in range(len(evals)-1):
        if i % 2 != color:
            continue
        
        pos_log = {}
        pos_log['index'] = evals[i]['index']
        pos_log['fen'] = evals[i]['fen']
        pos_log['move'] = evals[i]['move']
        pos_log['strategic_analysis'] = positional_analysis(evals[i], evals[i+1]['eval'][0]['score'])
        pos_log['tactical_analysis'] = tactical_analysis() # TODO

        if evals[i]['index'] in log_data['critical_moments']:
            pos_log['critical'] = True
        
        if pos_log['strategic_analysis']['strategic_mistake'] or pos_log['tactical_analysis']['tactical_mistake']:
            pos_log['overall_mistake'] = True
            if pos_log['tactical_analysis']['tactical_mistake']:
                pos_log['mistake_type'] = 'tactical'
            else:
                pos_log['mistake_type'] = 'strategic'


        
        positional_log.append(pos_log)

    log_data['analysis'] = positional_log

def tactical_analysis() -> dict:
    return {}

def flag_critical(evals: list[dict], color=0, threshold=50, mate_threshold=5) -> list[int]: # returns list of indices of critical moments
    critical_moments = []
    index = 0
    for eval in evals:
        if index == len(evals)-1:
            break

        if index % 2 != color:
            continue

        current_eval = eval['eval'][0]
        next_eval = evals[index + 1]['eval'][0]

        if current_eval['mate'] is not None:
            if next_eval['mate'] is not None:
                if current_eval['mate'] < 0:
                    continue # if already losing, not necessarily critical (may need to revise in future)

                mate_delta = next_eval['mate'] - current_eval['mate']
                if next_eval['mate'] * current_eval['mate'] < 0: # sign change indicates a blunder leading to a losing position from a winning one
                    critical_moments.append(index)
                elif mate_delta > mate_threshold and current_eval['mate'] < 10: # Missed mate or significant increase in mate distance
                    critical_moments.append(index)

            elif next_eval['cp'] < 500: # mate missed into a not as winning position, could be losing now
                critical_moments.append(index)
        
        elif next_eval['mate'] is not None:
            if current_eval['cp'] > 0 and next_eval['mate'] < 0: # missed a winning position into a losing one
                critical_moments.append(index)
                continue

        elif current_eval['cp'] is not None and next_eval['cp'] is not None:
            cp_delta = next_eval['cp'] - current_eval['cp']
            if next_eval['cp'] * current_eval['cp'] < 0 and current_eval['cp'] > 0: # sign change indicates a blunder leading to a losing position from a winning one
                critical_moments.append(index)
            elif cp_delta < -threshold and current_eval['cp'] < 300: # significant mistake
                critical_moments.append(index)

        index += 1

    return critical_moments
            
def positional_analysis(ev: dict, next_position_eval: int) -> dict[str, Any]:
    log_data = {}
    board = chess.Board(ev['fen'])
    board.push_uci(ev['move'])
    user_vector = generate_position_vector(board.fen())
    board.pop()

    engine_vectors = [(np.array([]), '')]
    engine_vectors.pop()
    for pv in ev['eval']:
        board.push_uci(pv['pv'].split()[0])
        engine_vector = generate_position_vector(board.fen())
        board.pop()
        engine_vectors.append((engine_vector, pv['pv']))

    log_data['vectors'] = [user_vector] + engine_vectors
    clusters = []
    v_ind = 0
    for vect, mv in engine_vectors:
        added = False
        for cluster in clusters:
            cluster_vecs = [engine_vectors[i][0] for i in cluster]
            sim_matrix = cosine_similarity(np.array([vect]), cluster_vecs) # type:ignore
            if np.mean(sim_matrix) > 0.85:
                cluster.append(v_ind)
                added = True
                break
        
        if not added:
            clusters.append([v_ind])
        v_ind += 1
    
    log_data['clusters'] = clusters
    cluster_data = []
    ind = 0
    for cluster in clusters:
        representative = engine_vectors[cluster[0]]
        representative_eval = ev['eval'][cluster[0]]['score']
        cluster_data.append({"V": representative, "E": representative_eval, 'idx': ind})
        ind += 1

    cluster_data = sorted(cluster_data, key=lambda x: x['E'], reverse=True)
    log_data['cluster_data'] = cluster_data

    plan_distances = np.array([np.linalg.norm(WEIGHTS * (user_vector - cluster['V'])) for cluster in cluster_data])
    log_data['plan_distances'] = plan_distances

    plan_probabilities = softmax(-plan_distances / PLAN_TEMP)
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

    eval_diff = -np.diff([cluster['E'] for cluster in cluster_data]) 

    domination = False
    current_eval = cluster_data[0]['E']
    next_eval = cluster_data[1]['E']
    
    current_is_mate = current_eval > 2**15 - 1001
    next_is_mate = next_eval > 2**15 - 1001
    
    if current_is_mate and next_is_mate:
        current_mate = 2**15 - 1 - current_eval
        next_mate = 2**15 - 1 - next_eval
        if not (current_mate > 7 and next_mate > 7) and abs(eval_diff[0]) > 4:
            domination = True
    elif current_is_mate or next_is_mate:
        cp_eval = next_eval if current_is_mate else current_eval
        if cp_eval < 5000:
            domination = True
    else:
        if abs(eval_diff[0]) > 50:
            domination = True

    log_data['domination'] = domination

    if domination:
        V_ref = cluster_data[0]['V']
        E_ref = cluster_data[0]['E']
    else:
        V_ref = user_plan['V']
        E_ref = user_plan['E']

    log_data['V_ref'] = V_ref
    V_gap = WEIGHTS * (V_ref - user_vector)
    log_data['V_gap'] = V_gap
    
    E_gap = E_ref - next_position_eval
    log_data['E_gap'] = E_gap

    
    if plan_match == 0:
        result = "No clear plan detected, didn't match any engine plans clearly"
        log_data['strategic_mistake'] = True
        log_data['result'] = result
        return log_data
    
    is_top_move = cluster_data[0]['E'] - next_position_eval < 20
    log_data['is_top_move'] = is_top_move
    if is_top_move:
        result = f'User move is strong, follows cluster {user_plan["idx"]} with representative vector {user_plan["V"]} closely with similar evaluation to the representative move, no clear mistakes'
        log_data['strategic_mistake'] = False
        log_data['result'] = result
        return log_data
    
    if domination:
        if user_plan['idx'] != cluster_data[0]['idx']:
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

def generate_position_vector(fen: str) -> np.ndarray:
    pass # RUN SCORERS
    return np.random.rand(300)
