"""Compare GPU-hours per researcher-day using the 2030 base serving assumptions."""
import json
from math import fsum
from pathlib import Path
from tempfile import TemporaryDirectory

from inference.moe import calculate
from .observations import HERE, PARENT, ROOT, records, write_rows


def run():
    year = '2030'
    results = HERE / 'results'
    config = json.loads((PARENT / 'forecast_config.json').read_text())
    model = json.loads((ROOT / config['model_config']).read_text())
    hardware = json.loads((ROOT / config['hardware_config']).read_text())
    model['architecture']['experts_per_token'] = config['scenarios']['base'][year]['top_k']
    model['weights']['bytes_per_parameter'] = config['weight_bytes'][year]
    model['kv_cache']['bytes_per_element'] = config['kv_bytes'][year]
    efficiency_keys = {
        'compute_efficiency': 'compute_efficiency',
        'hbm_efficiency': 'hbm_bandwidth_efficiency',
        'communication_efficiency': 'communication_bandwidth_efficiency',
    }
    for source, target in efficiency_keys.items():
        model['serving_assumptions'][target] = config['year_efficiency'][source][year]
    for sku, peak in config['dense_fp8_tflops'].items():
        hardware['hardware'][sku]['fp8_dense_peak_tflops'] = peak

    jobs = json.loads((results / 'inference_inputs.json').read_text())
    volumes = [row for row in records(results / 'workload.csv')
               if row['date'] == '2030-11-18' and row['method'] == 'ols']
    rows = []
    with TemporaryDirectory() as tmp:
        model_path = Path(tmp) / 'model.json'
        hardware_path = Path(tmp) / 'hardware.json'
        model_path.write_text(json.dumps(model))
        hardware_path.write_text(json.dumps(hardware))
        for volume in volumes:
            scenario = volume['workload_scenario']
            sessions = float(volume['session_count_per_day'])
            sessions_per_main_day = float(volume['main_sessions_per_day'])
            tasks = [(job['workload'], job['tasks_per_day'] * sessions / sessions_per_main_day)
                     for job in jobs if job['year'] == int(year) and job['scenario'] == scenario]
            if not tasks:
                raise ValueError(f'Missing task inputs for {year} scenario {scenario}')
            for sku in config['dense_fp8_tflops']:
                costs = [(calculate(task, sku, model_path, hardware_path), weight)
                         for task, weight in tasks]
                prefill = fsum(cost['prefill']['gpu_hours'] * weight for cost, weight in costs)
                decode = fsum(cost['decode']['gpu_hours'] * weight for cost, weight in costs)
                rows.append(dict(date=volume['date'], workload_scenario=scenario, hardware=sku,
                                 tasks_per_researcher_day=fsum(weight for _, weight in tasks),
                                 prefill_gpu_h_per_researcher_day=prefill,
                                 decode_gpu_h_per_researcher_day=decode,
                                 total_gpu_h_per_researcher_day=prefill + decode))
    write_rows(results / 'researcher_hardware_2030.csv', rows)


if __name__ == '__main__':
    run()
