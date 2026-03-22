import os
import requests
import time

MUSCLE_IP = os.getenv('MUSCLE_IP')
if not MUSCLE_IP:
    raise Exception("MUSCLE_IP not set in environment variables")

def fetch_evals(positions):
    response = requests.post(f'http://{MUSCLE_IP}/evaluate/batch', json={'positions': positions})
    if response.status_code != 200:
        raise Exception(f'MUSCLE evaluation failed with status code {response.status_code}, response: {response.text}')
    
    data = response.json()
    task_id = data.get('task_id')

    start_time = time.time()
    while True:
        current_time = time.time()
        if current_time - start_time > 30: # timeout after 30 seconds
            raise Exception('MUSCLE evaluation timed out after 30 seconds')
        
        status_res = requests.get(f'http://{MUSCLE_IP}/evaluate/status/{task_id}')
        if status_res.status_code != 200:
            raise Exception(f'MUSCLE status check failed with status code {status_res.status_code}, response: {status_res.text}')
        
        st_data = status_res.json()
        completed = st_data.get('completed', False)
        evals = st_data.get('evals', {})

        if completed:
            return evals

        time.sleep(0.5)

def analysis_pipeline(evals):
    pass ## FUTURE