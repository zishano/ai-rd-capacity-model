"""Generate independent workload tables and per-task inputs for the 30T kernel."""
import argparse
import json
from collections import defaultdict
from datetime import date
from statistics import mean

from .adapter import task_input
from .calibration.daily_tables import task_mix_weights, update_daily_tables
from .calibration.model import run as calibrate_task_starts
from .observations import HERE, PARENT, complete, records, series, write_rows
from .trends import fit, diagnostics


def measured_tasks():
    calls = defaultdict(list)
    for c in records(HERE/'trace_calls.csv'):
        calls[c['instance']].append(c)
    tasks = []
    for t in complete():
        ms = calls.pop(t['instance'])
        for field in ('prompt','completion','cache_read'):
            if sum(int(c[field]) for c in ms) != int(t[field]):
                raise ValueError(f"Incorrect call totals: {t['instance']}/{field}")
        lengths = [int(c['prompt'])+int(c['completion']) for c in ms]
        if len(ms) != int(t['metered_calls']) or max(lengths) != int(t['peak_request']):
            raise ValueError(f"Incorrect call coverage: {t['instance']}")
        spans = sorted((int(c['created']),float(c['received'])) for c in ms)
        start = end = spans[0][0]
        active = 0.
        for left,right in spans:
            if right < left:
                raise ValueError('Negative request interval')
            active += max(0,right-max(left,end))
            end = max(end,right)
        tasks.append(dict(t, duration=(end-start)/3600, request_hours=active/3600, contexts=lengths))
    if calls:
        raise ValueError('Unmatched traces')
    return tasks


def weighted_percentile(values, q):
    target = sum(weight for value,weight in values)*q
    cumulative = 0.
    for value,weight in sorted(values):
        cumulative += weight
        if cumulative >= target:
            return value
    return max(v for v,w in values)


def decompose(tasks, cfg, name, growth, anchor, progress):
    scenario = cfg['scenarios'][name]
    share = scenario['upper_decile_mix_2030']*progress
    exponent = scenario['session_count_exponent']
    if not (0<=share<=1 and 0<=exponent<=1 and growth>0):
        raise ValueError('Invalid decomposition')
    weights = task_mix_weights(tasks, share)
    def mix(field):
        return sum(w*float(t[field]) for w,t in zip(weights,tasks))
    window = cfg['calendar_hours']
    sessions0_duration = mean(t['duration'] for t in tasks)*cfg['reference_tasks_per_main_agent_day']
    duration = sessions0_duration*growth**(1-exponent)
    if duration > window:
        raise ValueError('Single serial main-agent daily session budget exceeded')
    researcher_hours = anchor*cfg['hours_per_reported_workday']*growth
    sessions = anchor*cfg['hours_per_reported_workday']/sessions0_duration*growth**exponent
    # A focal main opens one reference session per day; the pool includes other agents.
    daily = duration/mix('duration')
    prompt,output,cache = (mix(k) for k in ('prompt','completion','cache_read'))
    duty = mix('request_hours')/mix('duration')
    context_values = [(v,w) for w,t in zip(weights,tasks) for v in t['contexts']]
    p50,p90 = (weighted_percentile(context_values,q) for q in (.5,.9))
    row = dict(workload_scenario=name, usage_multiplier=growth, tasks_per_day=daily,
        tasks_per_session=daily, calls_per_task=mix('metered_calls'), calls_per_day=daily*mix('metered_calls'),
        input_tokens_per_task=prompt,output_tokens_per_task=output,cached_input_tokens_per_task=cache,
        input_tokens_day=daily*prompt,output_tokens_day=daily*output,
        cached_input_tokens_day=daily*cache,uncached_input_tokens_day=daily*(prompt-cache),
        prefix_cache_hit_rate=cache/prompt,session_hours_per_day=researcher_hours,session_count_per_day=sessions,
        mean_session_duration_hours=duration, average_online_sessions=researcher_hours/window,
        main_session_hours_per_day=duration, main_sessions_per_day=1,
        inference_duty_proxy=duty,active_request_hours_per_main_day=duration*duty,
        average_inference_concurrency=duration*duty/window,peak_inference_concurrency=1,
        researcher_mean_request_concurrency_proxy=researcher_hours*duty/window,
        researcher_peak_inference_concurrency=None, researcher_p95_inference_concurrency=None,
        context_request_p50=p50,context_request_p90=p90,upper_tail_mix=share,
        evidence_type='Future Scenario')
    return row, weights


def session_bounds(tasks, weights, row, day, window):
    """Independent empirical transfer sensitivities, holding the other inputs fixed."""
    duration_values = [(t['duration'],weight) for t,weight in zip(tasks,weights)]
    duties = [(t['request_hours']/t['duration'],weight) for t,weight in zip(tasks,weights)]
    mean_task_span = sum(d*w for d,w in duration_values)
    rows = []
    for q in (.1,.9):
        duration = row['mean_session_duration_hours']*weighted_percentile(duration_values,q)/mean_task_span
        duty = weighted_percentile(duties,q)
        rows.append(dict(date=day, scenario=row['workload_scenario'], trace_quantile=q,
            session_duration_hours_if_transferred=duration,
            researcher_sessions_per_day_at_duration=row['session_hours_per_day']/duration,
            request_duty_if_transferred=duty,
            main_mean_request_concurrency_at_duty=row['main_session_hours_per_day']*duty/window))
    return rows


def run(cfg, out):
    obs = series(PARENT/'observed_agent_workdays.csv','agent_workdays_per_researcher_day')
    api = series(PARENT/'observed_api_usage_value.csv','median_api_list_usd_per_researcher_day')
    if cfg['peak_sequences_per_serial_main'] != 1:
        raise ValueError('This adapter models one serial main agent per task')
    ref = date.fromisoformat(cfg['reference_date'])
    years = cfg['years']
    tasks = measured_tasks()
    cap = cfg['bounded_online_session_equivalents']*cfg['calendar_hours']/cfg['hours_per_reported_workday']
    trends,stats,workloads,adapter,contexts = [],[],[],[],[]
    session_stress = []
    for method in cfg['models']:
        model = fit(obs, method, cap)
        stats.append(diagnostics(model, obs, cap))
        baseline = model.predict(ref)
        for year in years:
            day = ref.replace(year=year)
            usage = model.predict(day)
            growth = usage/baseline
            trends.append(dict(method=method,date=day,usage=usage,usage_multiplier=growth))
            for name in cfg['scenarios']:
                progress = (year-years[0])/(years[-1]-years[0])
                row,weights = decompose(tasks,cfg,name,growth,baseline,progress)
                workloads.append(dict(date=day,method=method,**row))
                if method != 'ols':
                    continue
                session_stress.extend(session_bounds(tasks,weights,row,day,cfg['calendar_hours']))
                for factor in cfg['context_stress_factors']:
                    contexts.append(dict(year=year,scenario=name,context_factor=factor,
                        p50=row['context_request_p50']*factor,p90=row['context_request_p90']*factor))
                for t,w in zip(tasks,weights):
                    adapter.append(dict(year=year,scenario=name,instance=t['instance'],
                        tasks_per_day=row['tasks_per_day']*w,
                        workload=task_input(t,cfg['peak_sequences_per_serial_main'])))
    api_fit = fit(api,'ols')
    api_rows = [dict(date=ref.replace(year=y),predicted_api_value=api_fit.predict(ref.replace(year=y)),
                     multiplier=api_fit.predict(ref.replace(year=y))/api_fit.predict(ref)) for y in years]
    out.mkdir(parents=True,exist_ok=True)
    for filename,table in [('trend_fits',stats),('trends',trends),('workload',workloads),
                           ('context_stress',contexts),('session_sensitivity',session_stress),('api_crosscheck',api_rows)]:
        write_rows(out/(filename+'.csv'),table)
    (out/'inference_inputs.json').write_text(json.dumps(adapter,indent=2)+'\n')
    calibrate_task_starts(out/'calibrated', [ref.replace(year=y) for y in years])
    update_daily_tables(out/'calibrated', cfg, trends)


if __name__=='__main__':
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=HERE/'settings.json')
    parser.add_argument('--output',type=Path,default=HERE/'results')
    args=parser.parse_args()
    run(json.loads(args.config.read_text()),args.output)
