"""Separate focal-session accounting from the researcher-day sum over 18 task classes."""
import json
from datetime import timedelta
from math import ceil, fsum
from statistics import mean

from inference.moe import calculate
from ..adapter import task_input
from ..observations import PARENT, ROOT, records, write_rows
from ..trends import fit
from .model import CODE, DATA, history_tables


def task_mix_weights(tasks, tail_share):
    outputs = [int(t['completion']) for t in tasks]
    cutoff = sorted(outputs)[ceil(.9 * len(tasks)) - 1]
    tail_size = sum(value >= cutoff for value in outputs)
    return [(1-tail_share)/len(tasks) + (tail_share/tail_size if value >= cutoff else 0)
            for value in outputs]


def update_daily_tables(out, cfg, trends):
    trend = next((r for r in trends if r['method'] == 'ols' and r['date'].year == 2030), None)
    if trend is None:
        return
    day = str(trend['date'])
    rates = [r for r in records(out/'rates_by_category.csv')
             if r['date'] == day and r['scenario'] == 'full_slope']
    _, output_history = history_tables()
    cutoff = max(output_history)
    # The September series reports trailing 14-day means. Two adjacent windows
    # give the 28-day mean at the task-start forecast date.
    aligned_output = {}
    for key in output_history[cutoff]:
        points = [(d, row[key]) for d, row in sorted(output_history.items())]
        slope = fit(points, 'ols').slope
        windows = [trend['date'] - timedelta(days=n) for n in (0, 14)]
        values = [max(0., output_history[cutoff][key] + slope * (d-cutoff).days) for d in windows]
        aligned_output[key] = mean(values)
    tasks = [r for r in records(DATA/'public_tasks.csv') if r['complete'] == '1']
    config = json.loads((PARENT/'forecast_config.json').read_text())
    model_path = ROOT/config['model_config']
    # Only FLOPs are used. The kernel computes them from architecture, context and tokens.
    serving = config['scenarios']['base']['2030']
    if json.loads(model_path.read_text())['architecture']['experts_per_token'] != serving['top_k']:
        raise ValueError('2030 Top-K differs from the selected architecture')
    for t in tasks:
        cost = calculate(task_input(t, cfg['peak_sequences_per_serial_main']),
                         serving['hardware'], model_path, ROOT/config['hardware_config'])
        t['eflop'] = cost['prefill_eflop'] + cost['decode_eflop']

    growth = trend['usage_multiplier']
    hours = trend['usage'] * cfg['hours_per_reported_workday']
    base_minutes = mean(float(t['duration_min']) for t in tasks) * cfg['reference_tasks_per_main_agent_day']
    focal, ledger, totals = [], [], []
    for scenario, settings in cfg['scenarios'].items():
        weights = task_mix_weights(tasks, settings['upper_decile_mix_2030'])

        def weighted(field):
            return fsum(w * float(t[field]) for w, t in zip(weights, tasks))

        prompt, cached, output = (weighted(k) for k in ('prompt', 'cache_read', 'completion'))
        calls, span, flops = (weighted(k) for k in ('metered_calls', 'duration_min', 'eflop'))
        count_multiplier = growth ** settings['session_count_exponent']
        duration_multiplier = growth ** (1 - settings['session_count_exponent'])
        minutes = base_minutes * duration_multiplier
        if minutes > 60 * cfg['calendar_hours']:
            raise ValueError('Focal session exceeds one calendar day')
        equivalents = minutes / span
        focal.append(dict(date=day, scenario=scenario, hours_multiplier=growth, researcher_agent_hours=hours,
                          mean_online_equivalents=hours/cfg['calendar_hours'], session_count_multiplier=count_multiplier,
                          duration_multiplier=duration_multiplier, session_minutes=minutes, sessions_per_researcher_day=60*hours/minutes,
                          task_equivalents_per_main_day=equivalents, visible_minutes_per_issue=span, calls_per_issue=calls,
                          input_per_issue=prompt, cached_per_issue=cached, output_per_issue=output, cache_fraction=cached/prompt,
                          mean_peak_context=weighted('peak_request'), peak_sequences=cfg['peak_sequences_per_serial_main'],
                          input_per_main_day=equivalents*prompt, cached_per_main_day=equivalents*cached,
                          output_per_main_day=equivalents*output, calls_per_main_day=equivalents*calls))
        categories = []
        for rate in rates:
            starts = float(rate['starts'])
            daily_output = aligned_output[rate['category']]
            row = dict(date=day, scenario=scenario, category=rate['category'], starts=starts,
                       historical_intensity_available=bool(rate['output_per_start_aggregate_ratio']),
                       output_basis='full_slope_28d')
            for metric, daily in [('input', daily_output*prompt/output), ('cached', daily_output*cached/output),
                                  ('output', daily_output), ('eflop', daily_output*flops/output)]:
                row[metric+'_per_researcher_day'] = daily
                row[metric+'_per_start'] = daily/starts if starts > 0 else None
            categories.append(row)
        ledger.extend(categories)
        known = [r for r in categories if r['historical_intensity_available']]
        summed = {k: fsum(r[k+'_per_researcher_day'] for r in categories) for k in ('input','cached','output','eflop')}
        code_starts = next(r['starts'] for r in categories if r['category']==CODE)
        totals.append(dict(date=day, scenario=scenario, rate_path='full_slope', researcher_agent_hours=hours,
                           research_starts=fsum(r['starts'] for r in categories), calibrated_output_classes=len(known),
                           starts_with_class_output_ratio=fsum(r['starts'] for r in known),
                           forecast_output_historical_ratio_available=fsum(r['output_per_researcher_day'] for r in known),
                           forecast_output_historical_ratio_unavailable=fsum(r['output_per_researcher_day'] for r in categories
                                                        if not r['historical_intensity_available']),
                           forecast_output_zero_starts=fsum(r['output_per_researcher_day'] for r in categories
                                                         if r['starts'] == 0),
                           conditional_input=summed['input'], conditional_cached=summed['cached'],
                           conditional_uncached=summed['input']-summed['cached'], conditional_output=summed['output'],
                           conditional_total_tokens=summed['input']+summed['output'], conditional_eflop=summed['eflop'],
                           code_starts=code_starts, code_input_one_issue_per_start=code_starts*prompt,
                           code_cached_one_issue_per_start=code_starts*cached, code_output_one_issue_per_start=code_starts*output,
                           code_eflop_one_issue_per_start=code_starts*flops))
    write_rows(out/'focal_main_2030.csv', focal)
    write_rows(out/'category_token_ledger_2030.csv', ledger)
    write_rows(out/'researcher_18_categories_2030.csv', totals)
