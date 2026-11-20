"""Offline single-agent forecast from metered issue traces and a configured synthetic MoE profile."""
import argparse
import csv
import json
import math
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from inference.moe import calculate


def load(path):
    return json.loads(path.read_text())


def quantile(rows, q, key):
    return sorted(rows, key=key)[math.ceil(q * len(rows)) - 1]


def historical_volume(settings):
    return settings['online_hours'] * settings['duty'] * (settings['input_rate'] + settings['output_rate'])


def workload(row):
    return dict(input_tokens=int(row['prompt']), output_tokens=int(row['completion']),
                prefix_cache_hit_rate=int(row['cache_read']) / int(row['prompt']),
                context_tokens=int(row['peak_request']), peak_sequences=1)


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, rows[0].keys(), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def run(config, out, scratch):
    with (HERE / 'trace_sample.csv').open() as stream:
        sample = [r for r in csv.DictReader(stream) if r['metered_calls'] == r['reported_calls']
                  and int(r['metered_calls']) > 0 and int(r['unknown_cache_prompt']) == 0]
    hardware = load(ROOT / config['hardware_config'])
    for sku, peak in config['dense_fp8_tflops'].items():
        hardware['hardware'][sku]['fp8_dense_peak_tflops'] = peak
    hardware_path = scratch / 'hardware.json'
    hardware_path.write_text(json.dumps(hardware))
    model_path = scratch / 'model.json'
    forecasts, sensitivities, stress_grid = [], [], []
    for name, years in config['scenarios'].items():
        row = quantile(sample, config['completion_quantile'][name], lambda r: int(r['completion']))
        base_work = workload(row)
        for year, settings in years.items():
            model = load(ROOT / config['model_config'])
            if model['architecture']['target_total_parameters'] != config.get('target_total_parameters', 40_000_000_000_000):
                raise ValueError('Forecast target does not match the model configuration')
            arch, serving = model['architecture'], model['serving_assumptions']
            arch['experts_per_token'] = settings['top_k']
            model['weights']['bytes_per_parameter'] = config['weight_bytes'][year]
            model['kv_cache']['bytes_per_element'] = config['kv_bytes'][year]
            for field, values in config['year_efficiency'].items():
                serving[field] = values[year]
            sku = settings['hardware']
            dayscale = config['reference_tasks_per_day'] * historical_volume(settings) / historical_volume(years['2026'])
            model_path.write_text(json.dumps(model))
            def evaluate(work):
                return calculate(work, sku, model_path, hardware_path)
            result = evaluate(base_work)
            hours = result['infer_gpu_h'] * dayscale
            spread = [evaluate(workload(r))['infer_gpu_h'] * dayscale for r in sample]
            forecasts.append(dict(scenario=name, year=year, instance=row['instance'], hardware=sku,
                top_k=settings['top_k'], tasks_per_day=dayscale, input_tokens_day=int(row['prompt'])*dayscale,
                output_tokens_day=int(row['completion'])*dayscale, cache_fraction=base_work['prefix_cache_hit_rate'],
                context=base_work['context_tokens'], active_parameters=result['active_parameters'],
                total_parameters=result['total_parameters'], gpus_per_replica=result['deployment_gpus_per_replica'],
                prefill_gpu_h_day=result['prefill']['gpu_hours']*dayscale,
                decode_gpu_h_day=result['decode']['gpu_hours']*dayscale, gpu_h_day=hours,
                trace_p10=quantile(spread,.1,float), trace_p50=quantile(spread,.5,float),
                trace_p90=quantile(spread,.9,float)))
            if name != 'base':
                continue
            # Cross the unknown serving conditions using the same set of complete tasks.
            # Taking percentiles within a cell keeps engineering choices out of the sample distribution.
            original_batch = serving['decode_batch_sequences']
            original_latency = serving['all_to_all_latency_us_per_moe_layer']
            for batch in (1, 4):
                for latency in (5, 20):
                    serving['decode_batch_sequences'] = batch
                    serving['all_to_all_latency_us_per_moe_layer'] = latency
                    model_path.write_text(json.dumps(model))
                    for cache_mode in ('trace', 'cold'):
                        cell = []
                        for trace in sample:
                            work = workload(trace)
                            if cache_mode == 'cold':
                                work['prefix_cache_hit_rate'] = 0
                            cell.append(evaluate(work)['infer_gpu_h'] * dayscale)
                        stress_grid.append(dict(year=year, batch=batch, latency_us=latency, cache=cache_mode,
                            p10=quantile(cell,.1,float), p50=quantile(cell,.5,float), p90=quantile(cell,.9,float)))
            serving['decode_batch_sequences'] = original_batch
            serving['all_to_all_latency_us_per_moe_layer'] = original_latency
            model_path.write_text(json.dumps(model))
            # Each pair is either sampled from complete traces or an explicit engineering stress.
            def record(field, values, results, basis):
                for value, stress_hours in zip(values, results):
                    sensitivities.append(dict(year=year, parameter=field, endpoint=value, basis=basis,
                        baseline_gpu_h_day=hours, gpu_h_day=stress_hours, change_pct=100*(stress_hours/hours-1)))
            for field in ('input_tokens','output_tokens','prefix_cache_hit_rate','context_tokens'):
                observed = [workload(r)[field] for r in sample]
                values = [quantile(observed,q,float) for q in (.1,.9)]
                record(field,values,[evaluate(dict(base_work, **{field:v}))['infer_gpu_h']*dayscale for v in values],
                       'trace marginal P10/P90')
            record('prefix_cache_hit_rate',[0],[evaluate(dict(base_work,prefix_cache_hit_rate=0))['infer_gpu_h']*dayscale],
                   'cold cache stress')
            record('tasks_per_day',[dayscale/2,dayscale*2],[hours/2,hours*2],'half/double task volume')
            skus = list(hardware['hardware'])
            record('hardware', skus, [calculate(base_work, other, model_path, hardware_path)['infer_gpu_h']*dayscale
                                      for other in skus], 'same workload on each supported SKU')
            for coll,field,values in [(arch,'experts_per_token',[4,16]),
                    (serving,'all_to_all_latency_us_per_moe_layer',[5,20]),
                    (serving,'decode_batch_sequences',[1,4]),(serving,'prefill_batch_tokens',[32,128]),
                    (serving,'cross_node_traffic_fraction',[0,1]),(serving,'expert_weight_batch_reuse_factor',[1,2]),
                    (serving,'usable_hbm_fraction',[.75,.95]),(serving,'runtime_hbm_reserve_fraction',[0,.2]),
                    (serving,'tensor_parallel_size',[2,8]),
                    (serving['expert_parallel_by_hardware'],sku,
                     [serving['expert_parallel_by_hardware'][sku]//2, serving['expert_parallel_by_hardware'][sku]*2]),
                    (serving,'target_gpu_pool_utilization',[.5,.9]),
                    (model['weights'],'scale_metadata_overhead_fraction',[0,.06]),
                    (model['weights'],'bytes_per_parameter',[.5,1]),
                    (model['kv_cache'],'bytes_per_element',[1,2]),
                    *((serving,k,[max(.01,serving[k]/2),min(1,serving[k]*2)]) for k in config['year_efficiency'])]:
                original = coll[field]
                changed = []
                for value in values:
                    coll[field] = value
                    model_path.write_text(json.dumps(model))
                    changed.append(evaluate(base_work)['infer_gpu_h']*dayscale)
                coll[field] = original
                label = 'expert_parallel_size' if field == sku else field
                record(label,values,changed,'engineering stress, no probability assigned')
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out/'forecast_summary.csv',forecasts)
    write_csv(out/'sensitivity.csv',sensitivities)
    write_csv(out/'serving_stress.csv',stress_grid)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Output directory (defaults to the forecast configuration directory)')
    parser.add_argument('--config', type=Path, default=HERE/'forecast_config.json')
    args = parser.parse_args()
    with TemporaryDirectory() as temp:
        run(load(args.config), args.output or args.config.resolve().parent, Path(temp))
