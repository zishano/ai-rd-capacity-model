"""Researcher-day estimates from published task starts and metered issue trajectories."""
import json
from datetime import date, timedelta
from math import ceil
from pathlib import Path
from statistics import mean, median

from ..adapter import task_input
from ..observations import HERE, TRACE, records, write_rows
from ..trends import fit

DATA = Path(__file__).resolve().parent
CODE = 'task3_1'
TOTAL = 'all'


def summarize(rows, scope):
    columns = {
        'input': [int(t['prompt']) for t in rows], 'output': [int(t['completion']) for t in rows],
        'cached_input': [int(t['cache_read']) for t in rows],
        'uncached_input': [int(t['prompt'])-int(t['cache_read']) for t in rows],
        'cache_fraction': [int(t['cache_read'])/int(t['prompt']) for t in rows],
        'calls': [int(t['metered_calls']) for t in rows],
        'peak_request_context': [int(t['peak_request']) for t in rows],
        'visible_minutes': [float(t['duration_min']) for t in rows],
    }
    return [distribution(v, scope, key) for key, v in columns.items()]


def distribution(values, scope, metric):
    v = sorted(values)
    return dict(scope=scope, metric=metric, n=len(v), mean=mean(v), p50=median(v),
                **{f'p{q}': v[ceil(len(v)*q/100)-1] for q in (10, 90, 95)})


def history_tables():
    starts = {}
    for r in records(HERE/'observed_openai_research_usage.csv'):
        if r['task1_1']:
            starts[date.fromisoformat(r['date'])] = {k: float(v) for k, v in r.items() if k.startswith('task')}
    output = {date.fromisoformat(r['date']): {k: float(v) for k, v in r.items() if k.startswith('task')}
              for r in records(DATA/'observed_output_tokens.csv')}
    return starts, output


def aligned_windows(starts, output):
    # Disjoint 28-day windows with the normal roster, after starts coverage begins.
    first = min(starts) + timedelta(days=27)
    rows = []
    day = first
    while day <= min(max(starts), max(output)):
        left = day - timedelta(days=27)
        if not (left <= date(2026, 7, 31) and day >= date(2026, 7, 1)):
            measured = {k: (output[day][k]+output[day-timedelta(days=14)][k])/2 for k in starts[day]}
            for k in [*measured, TOTAL]:
                o = sum(measured.values()) if k == TOTAL else measured[k]
                n = sum(starts[day].values()) if k == TOTAL else starts[day][k]
                rows.append(dict(window_start=left, window_end=day, category=k, starts_per_day=n,
                                 output_per_day=o, output_per_start=o/n if n else None))
        day += timedelta(days=28)
    return rows


def run(out, days):
    out.mkdir(parents=True, exist_ok=True)
    starts, output = history_tables()
    categories = list(next(iter(starts.values())))
    windows = aligned_windows(starts, output)
    write_rows(out/'matched_windows.csv', windows)
    intensities = {}
    ratios = {}
    for k in [*categories, TOTAL]:
        w = [r for r in windows if r['category'] == k]
        n = sum(r['starts_per_day'] for r in w)
        intensities[k] = sum(r['output_per_day'] for r in w)/n if n else None
        ratios[k] = [r['output_per_start'] for r in w if r['output_per_start'] is not None]
    write_rows(out/'output_intensity.csv', [
        dict(category=k, matched_windows=len(windows)//(1+len(categories)), pooled_output_per_start=v,
             window_min=min(ratios[k], default=None), window_max=max(ratios[k], default=None))
        for k,v in intensities.items()])

    total_windows = [r for r in windows if r['category'] == TOTAL]
    checks = []
    for i, holdout in enumerate(total_windows[1:], 1):
        previous = total_windows[:i]
        intensity = sum(r['output_per_day'] for r in previous)/sum(r['starts_per_day'] for r in previous)
        est = holdout['starts_per_day']*intensity
        checks.append(dict(held_end=holdout['window_end'], training_windows=i, measured_output=holdout['output_per_day'],
                           output_given_observed_starts=est, relative_error=est/holdout['output_per_day']-1))
    write_rows(out/'intensity_backtest.csv',checks)

    archive = records(DATA/'public_tasks.csv')
    complete = [r for r in archive if r['complete']=='1']
    original = {r['instance'] for r in records(TRACE)}
    old = [r for r in complete if r['instance'] in original]
    coverage = []
    for name, members in [('all_attempts', archive), ('complete', complete),
                          ('incomplete', [r for r in archive if r['complete'] == '0'])]:
        coverage.append(dict(
            scope=name, attempts=len(members), resolved=sum(int(r['resolved']) for r in members),
            reported_calls=sum(int(r['reported_calls']) for r in members),
            metered_calls=sum(int(r['metered_calls']) for r in members),
            mean_visible_minutes=mean(float(r['duration_min']) for r in members if r['duration_min']),
            **{f'mean_recorded_{key}': mean(int(r[key]) for r in members)
               for key in ('prompt', 'cache_read', 'completion')}
        ))
    write_rows(out/'coverage.csv', coverage)
    stats = []
    for group, members in [('original_complete',old),('all_complete',complete),
                           ('resolved_complete',[r for r in complete if r['resolved']=='1']),
                           ('unresolved_complete',[r for r in complete if r['resolved']=='0'])]:
        stats.extend(summarize(members,group))
    hist = records(DATA/'request_context_histogram.csv')
    lengths = [int(r['prompt_plus_completion']) for r in hist for _ in range(int(r['calls']))]
    stats.append(distribution(lengths, 'all_metered_calls_of_complete_tasks', 'request_context'))
    write_rows(out/'distributions.csv', stats)
    ordered = sorted(complete, key=lambda r: (int(r['completion']), r['instance']))
    quartile = ceil(len(ordered)/4)
    mixtures = {'lower_output_quartile': ordered[:quartile], 'all_complete': complete,
                'upper_output_quartile': ordered[-quartile:]}
    ii = sum(int(r['prompt']) for r in complete)
    oo = sum(int(r['completion']) for r in complete)
    cc = sum(int(r['cache_read']) for r in complete)
    latest = max(starts)
    regressions = {k:fit([(d,r[k]) for d,r in starts.items()], 'ols') for k in categories}
    rates, demand, sensitivity, jobs = [], [], [], []
    for day in days:
        for scenario in ('last_observed', 'half_slope', 'full_slope'):
            counts = {}
            for k, regression in regressions.items():
                anchor = regression.predict(latest)
                if scenario == 'last_observed':
                    counts[k] = starts[latest][k]
                else:
                    fraction = .5 if scenario=='half_slope' else 1.
                    counts[k] = max(0., anchor + fraction*(regression.predict(day)-anchor))
                rates.append(dict(date=day, scenario=scenario, category=k, starts=counts[k],
                                  output_per_start_aggregate_ratio=intensities[k],
                                  conditional_output_by_category=(counts[k]*intensities[k]
                                      if intensities[k] is not None else None)))
            n = sum(counts.values())
            estimated_o = n*intensities[TOTAL]
            demand.append(dict(date=day, scenario=scenario, scope='researcher_calendar_day',
                               initiated_tasks=n, code_starts=counts[CODE],
                               output_if_pooled_intensity_transfers=estimated_o,
                               coding_input_floor_if_full_archive_mix=counts[CODE]*coverage[0]['mean_recorded_prompt'],
                               coding_output_floor_if_full_archive_mix=counts[CODE]*coverage[0]['mean_recorded_completion'],
                               input_tokens=None, cached_input_tokens=None, calls=None, sessions=None,
                               average_request_concurrency=None, peak_request_concurrency=None,
                               input_if_coding_io_transfers=estimated_o*ii/oo,
                               cached_if_coding_io_transfers=estimated_o*cc/oo,
                               uncached_if_coding_io_transfers=estimated_o*(ii-cc)/oo,
                               output_low_window=n*min(ratios[TOTAL]), output_high_window=n*max(ratios[TOTAL])))
            for mix, members in mixtures.items():
                weight = counts[CODE]/len(members)
                volumes = {k: sum(int(r[k])*weight for r in members) for k in ('prompt','cache_read','completion','metered_calls')}
                sensitivity.append(dict(date=day, rate_scenario=scenario, coding_mix=mix,
                                        scope='task3_1_only', assumed_issue_equivalents_per_code_start=1,
                                        code_starts=counts[CODE], **volumes))
                if mix=='all_complete' and day==max(days):
                    for t in members:
                        jobs.append(dict(date=str(day), rate_scenario=scenario, category=CODE, instance=t['instance'],
                                         tasks_per_researcher_day=weight, workload=task_input(t,1)))
    write_rows(out/'rates_by_category.csv',rates)
    write_rows(out/'researcher_day.csv',demand)
    write_rows(out/'coding_sensitivity.csv',sensitivity)
    (out/'coding_inference_inputs.json').write_text(json.dumps(jobs,indent=2)+'\n')
