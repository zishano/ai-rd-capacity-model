"""Exercise prediction imports in an isolated copy; never changes real datasets.

Run with Python 3.10+ and Node.js:
    python3 -B scripts/test_update_html_predictions.py
"""
from __future__ import annotations

import csv
from copy import deepcopy
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
INPUT = Path('data_predict/forecasts/upstream/forecast.csv')
ARCHIVE = Path('html/04_reproduce/project/resource_predictions/forecast.csv')
ENSEMBLE = 'ensemble_uncertainty'
ENSEMBLE_SOURCE = Path('html/04_reproduce/project/analysis/agentic_30t_forecast/workload/trend_models/results/original_style/ensemble_uncertainty')
QUANTILES = ('lower95', 'lower80', 'median', 'upper80', 'upper95')
RESOURCE_FIELDS = (
    'output_tokens_per_team_day', 'input_tokens_per_team_day',
    'cached_input_tokens_per_team_day', 'uncached_input_tokens_per_team_day',
    'total_tokens_per_team_day', 'eflop_per_team_day',
    'prefill_eflop_per_team_day', 'decode_eflop_per_team_day',
)


def fingerprint(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file() and '__pycache__' not in path.parts}


def encode_csv(rows, fields):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8')


def table(path):
    with path.open(newline='', encoding='utf-8-sig') as source:
        return list(csv.DictReader(source))


def inline(path):
    match = re.search(r'<script\b[^>]*\bid=[\"\']trd-inline-data[\"\'][^>]*>(.*?)</script>',
                      path.read_text(), flags=re.S)
    assert match, 'Missing embedded dashboard data: ' + str(path)
    return json.loads(match.group(1))


def near(actual, expected, identity):
    assert math.isfinite(float(actual)) and math.isclose(float(actual), float(expected), rel_tol=2e-12, abs_tol=1e-9), (identity, actual, expected)


class Harness:
    def __init__(self, root):
        self.root = root
        self.checks = []

    def command(self, script, *args, success=True):
        result = subprocess.run([sys.executable, '-B', str(self.root / 'scripts' / script), *args],
                                cwd=self.root, text=True, capture_output=True, timeout=240)
        assert (result.returncode == 0) == success, (script, args, result.returncode, result.stdout[-6000:], result.stderr[-6000:])
        return result

    def passed(self, name):
        self.checks.append(name)
        print(json.dumps({'check': name, 'status': 'passed'}), flush=True)


def verify_node_values(root, dashboard, tables):
    """Execute the actual frontend conversion functions against independent CSVs."""
    source = (root / 'html/02_frontend/dashboard.js').read_text()
    metrics = source[source.index('const metrics='):source.index('\nconst categories=')]
    functions = []
    for name in ('value', 'sourceRows', 'algorithmRows', 'headlineRow'):
        start = source.index('function ' + name + '(')
        functions.append(source[start:source.index('\nfunction ', start + 1)])
    program = '\n'.join([
        "const fs=require('fs');const data=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));",
        metrics,
        "const state={team:100,window:24,scenario:'C'},algorithmData=data.algorithm_forecasts;",
        *functions,
        "const result={resources:[],agents:[],tasks:[]};",
        "const representatives={resources:'output_tokens_per_team_day',agents:'agent_hours_per_team_day',tasks:'task_starts_per_team_day'};",
        "for(const method of algorithmData.methods.map(x=>x.id))for(const scenario of ['A','B','C'])for(const [kind,key]of Object.entries(representatives)){",
        "for(const row of algorithmRows(key,scenario,method)){const values={};for(const [metric,config]of Object.entries(metrics))if(config.source===kind)values[metric]=value(row,metric);result[kind].push({method,scenario,date:row.date,phase:row.phase,values});}}",
        "const headlines=[];",
        "for(const method of algorithmData.methods.map(x=>x.id))for(const scenario of ['A','B','C'])for(const team of [10,100,1000])for(const window of [8,12,24]){Object.assign(state,{scenario,team,window,headlineAlgorithm:method});const row=headlineRow(method),values={};for(const metric of Object.keys(metrics))values[metric]=value(row,metric);headlines.push({method,scenario,team,window,date:row.date,values});}",
        "process.stdout.write(JSON.stringify({series:result,headlines}));",
    ])
    payload_path = root / 'node-fixture.json'
    payload_path.write_text(json.dumps(dashboard))
    try:
        execution = subprocess.run(['node', '-e', program, str(payload_path)], capture_output=True, text=True, timeout=30)
        assert execution.returncode == 0, execution.stderr
        payload = json.loads(execution.stdout)
        actual = payload['series']
    finally:
        payload_path.unlink(missing_ok=True)
    histories = {
        'resources': dashboard['monthly_resources'],
        'agents': dashboard['monthly_trends']['agents'],
        'tasks': dashboard['monthly_tasks'],
    }
    count = 0
    for kind, rows in actual.items():
        exported = {(row['method'], row['scenario'], row['date']): row for row in tables[kind]}
        history = {(row['scenario'], row['date']): row for row in histories[kind] if row['phase'] == 'observed'}
        future_count = 0
        for row in rows:
            if row['phase'] == 'forecast':
                future_count += 1
                expected = exported[(row['method'], row['scenario'], row['date'])]
            else:
                expected = history[(row['scenario'], row['date'])]
            for key, value in row['values'].items():
                wanted = (float(expected['eflop_per_team_day']) * 1000 / 86400
                          if key == 'compute_pflops_window' else float(expected[key]))
                near(value, wanted, (kind, row['method'], row['scenario'], row['date'], key))
                count += 1
        assert future_count == len(exported), (kind, future_count, len(exported))
    endpoints = {
        kind: {(row['method'], row['scenario']): row for row in rows if row['date'] == '2030-11-18'}
        for kind, rows in tables.items()
    }
    for headline in payload['headlines']:
        assert headline['date'] == '2030-11-18'
        expected = {key: value for kind in ('resources', 'agents', 'tasks')
                    for key, value in endpoints[kind][(headline['method'], headline['scenario'])].items()}
        for key, value in headline['values'].items():
            wanted = float(expected[key])
            if key != 'prefix_cache_hit_rate':
                wanted *= headline['team'] / 100
            if key == 'compute_pflops_window':
                wanted *= 24 / headline['window']
            near(value, wanted, ('headline', headline['method'], headline['scenario'],
                                 headline['team'], headline['window'], key))
            count += 1
    return count


def integration(root):
    harness = Harness(root)
    before = fingerprint(root)
    harness.command('update_html_predictions.py', '--check')
    assert fingerprint(root) == before, '--check changed files'
    harness.passed('full dry run leaves every input and generated file unchanged')

    source = root / INPUT
    original_bytes = source.read_bytes()
    original_rows = table(source)
    fields = list(original_rows[0])
    assert len(original_rows) == 2400
    # Verify the actual upstream quantiles, not only internally consistent JSON.
    initial_algorithm = json.loads((root / 'html/03_data/algorithm_forecasts.json').read_text())
    native = table(root / ENSEMBLE_SOURCE / 'forecast.csv')
    aligned = table(root / ENSEMBLE_SOURCE / 'output_aligned28.csv')
    native_points = {(row['metric'], row['date']): row for row in native if row['method'] == 'ensemble'}
    aligned_points = {row['date']: row for row in aligned if row['method'] == 'ensemble'}
    imported = {(row['metric'], row['date']): row for row in original_rows if row['method'] == ENSEMBLE}
    uncertainty = initial_algorithm['uncertainty'][ENSEMBLE]
    assert initial_algorithm['meta']['rolling_window_days'] == {'output': 14, 'workdays': 28, 'tasks': 28}
    assert len(imported) == 150 and sum(map(len, uncertainty.values())) == 150
    for (metric, day), row in imported.items():
        official = native_points[(metric, day)]
        near(row['value'], official['median'], ('upstream median', metric, day))
        near(initial_algorithm['forecasts'][ENSEMBLE][metric][day], official['median'], ('native target', metric, day))
        for quantile in QUANTILES:
            near(uncertainty[metric][day][quantile], official[quantile], ('upstream quantile', metric, day, quantile))
        if metric == 'output':
            near(row['output_tokens_28d'], aligned_points[day]['median'], ('28-day historical reference', day))
    endpoint = '2030-11-18'
    assert not math.isclose(float(aligned_points[endpoint]['median']), float(native_points[('output', endpoint)]['median']), rel_tol=1e-6)
    harness.passed('all 150 ensemble medians and nominal bounds match native targets: 14-day output and 28-day workdays/tasks')
    raw = json.loads((root / 'html/03_data/raw_research_data.json').read_text())
    raw_output = raw['metrics']['output']
    assert raw_output['windowDays'] == 14
    shared_points = 0
    for method, pack in raw_output['forecast'].items():
        for day, values in zip(pack['dates'], pack['values']):
            near(initial_algorithm['forecasts'][method]['output'][day], math.fsum(values), ('raw/resource output', method, day))
            shared_points += 1
    for band in raw_output['uncertainty'][ENSEMBLE]['bands']:
        for point in band['points']:
            for key in QUANTILES:
                near(uncertainty['output'][point['date']][key], point['center' if key == 'median' else key], ('raw/resource interval', point['date'], key))
    dashboard = json.loads((root / 'html/03_data/dashboard_data.json').read_text())
    history = {row['date']: row for row in dashboard['history'] if row['metric'] == 'output_tokens_14d'}
    for day, values in zip(raw_output['history']['dates'], raw_output['history']['values']):
        near(history[day]['value_per_researcher_day'], math.fsum(values), ('official 14-day history', day))
    for row in dashboard['monthly_resources']:
        assert row['rolling_window_days'] == 14
        if row['phase'] == 'observed':
            near(row['output_tokens_per_team_day'], history[row['date']]['value_per_team_day'], ('monthly observed 14-day output', row['date']))
    assert all(row['rolling_window_days'] == 14 for row in dashboard['category_mix'])
    assert all(row['rolling_window_days'] == 28 for row in dashboard['monthly_trends']['agents'])
    assert all(row['rolling_window_days'] == 28 for row in dashboard['monthly_tasks'])
    for phase in ('observed', 'forecast'):
        for directory in ('team_projections', 'resource_estimates'):
            for row in table(root / 'data_predict' / directory / f'annual_{phase}_basis.csv'):
                assert row['output_rolling_window_days'] == '14'
                assert row['agent_rolling_window_days'] == '28'
                assert row['task_rolling_window_days'] == '28'
    observed_fragments = json.loads((root / 'data_predict/team_projections/observed_basis.fragments.json').read_text())['records']
    forecast_fragments = json.loads((root / 'data_predict/team_projections/forecast_basis.fragments.json').read_text())['records']
    observed_categories = [row['value'] for row in observed_fragments
                           if row['source'] == 'dashboard_data.json' and row['pointer'].startswith('/category_mix/')]
    forecast_categories = [row['value'] for row in forecast_fragments
                           if row['source'] == 'dashboard_data.json' and row['pointer'].startswith('/category_mix/')]
    assert len(observed_categories) == 54 and all(row['year'] == 2026 for row in observed_categories)
    assert len(forecast_categories) == 216 and all(row['year'] > 2026 for row in forecast_categories)
    harness.passed(f'both pages share native 14-day output histories, {shared_points} forecast totals and ensemble bounds; Agent/task windows remain 28 days')
    invalids = []
    bad = deepcopy(original_rows); bad.append(deepcopy(bad[0])); invalids.append(('duplicate identity', bad))
    bad = deepcopy(original_rows); bad.pop(); invalids.append(('missing forecast date', bad))
    for value, name in (('-1', 'negative value'), ('NaN', 'NaN value'), ('Infinity', 'infinite value')):
        bad = deepcopy(original_rows)
        item = next(row for row in bad if row['metric'] == 'output')
        item['value'] = value
        invalids.append((name, bad))
    bad = deepcopy(original_rows); bad[0]['method'] = 'unknown_method'; invalids.append(('unknown method', bad))
    for name, rows in invalids:
        source.write_bytes(encode_csv(rows, fields))
        previous = fingerprint(root)
        harness.command('update_html_predictions.py', success=False)
        assert fingerprint(root) == previous, 'Invalid import wrote files: ' + name
    source.write_bytes(original_bytes)
    harness.passed('duplicate, missing, negative, nonfinite and unknown-method imports fail without publishing')

    altered = deepcopy(original_rows)
    factors = {'output': 1.1, 'workdays': 1.2, 'tasks': 1.3}
    for row in altered:
        if row['method'] in ('legacy_ols', 'naive'):
            row['value'] = str(float(row['value']) * factors[row['metric']])
    candidate = encode_csv(altered, fields)
    source.write_bytes(candidate)
    previous = fingerprint(root)
    harness.command('export_html_datasets.py', success=False)
    assert fingerprint(root) == previous, 'Exporter clobbered a pending editable input'
    harness.passed('ordinary export protects pending edits to the canonical input')

    harness.command('update_html_predictions.py', '--check')
    assert fingerprint(root) == previous, 'Changed-input dry run wrote files'
    harness.command('update_html_predictions.py')
    current = fingerprint(root)
    assert source.read_bytes() == candidate
    assert (root / ARCHIVE).read_bytes() == candidate
    # These are intentionally frozen even when editable monthly legacy OLS differs.
    protected = [name for name in previous if (
        name.startswith('data_row/observations/') or name.startswith('data_row/official_sources/')
        or name.startswith('data_row/observed_transforms/') or name.startswith('data_row/proxy_samples/')
        or name.startswith('data_predict/forecasts/raw_page_')
        or name.startswith('html/04_reproduce/project/analysis/')
        or name in ('html/03_data/dashboard_data.json', 'html/03_data/dashboard_data.csv',
                    'html/03_data/raw_research_data.json', 'html/01_pages/raw-data-dashboard.html')
        or ('/annual_' in name or '/monthly_' in name) and name.endswith('_basis.csv')
    )]
    changed = [name for name in protected if previous[name] != current.get(name)]
    assert not changed, ('Out-of-scope data changed', changed)
    harness.passed('updated legacy and alternative forecasts preserve observations, annual baseline and raw-data page')

    algorithm = json.loads((root / 'html/03_data/algorithm_forecasts.json').read_text())
    for row in altered:
        near(algorithm['forecasts'][row['method']][row['metric']][row['date']], float(row['value']), (row['method'], row['metric'], row['date']))
    embedded = inline(root / 'html/01_pages/resource-dashboard-preview.html')
    assert embedded['algorithm_forecasts'] == algorithm
    assert inline(root / 'html/01_pages/team-resource-dashboard.html')['algorithm_forecasts'] == algorithm
    interval_table = table(root / 'data_predict/forecasts/resource_page_uncertainty.csv')
    interval_rows = {(row['method'], row['metric'], row['date']): row for row in interval_table}
    assert len(interval_table) == len(interval_rows) == 150
    for metric, days in algorithm['uncertainty'][ENSEMBLE].items():
        for day, quantiles in days.items():
            row = interval_rows[(ENSEMBLE, metric, day)]
            assert row['rolling_window_days'] == ('14' if metric == 'output' else '28') and row['scope'] == 'per_researcher_calendar_day'
            for key, value in quantiles.items():
                near(row[key], value, ('classified uncertainty export', metric, day, key))
    dashboard = json.loads((root / 'html/03_data/dashboard_data.json').read_text())
    assert embedded['rows'] == dashboard['rows']
    csvs = {
        'resources': table(root / 'data_predict/resource_estimates/all_algorithms_monthly_resources.csv'),
        'agents': table(root / 'data_predict/team_projections/all_algorithms_monthly_agents.csv'),
        'tasks': table(root / 'data_predict/team_projections/all_algorithms_monthly_tasks.csv'),
    }
    resource_refs = {(row['scenario'], row['date']): row for row in dashboard['monthly_resources']}
    for kind, rows in csvs.items():
        for row in rows:
            method, day, scenario = row['method'], row['date'], row['scenario']
            prediction = algorithm['forecasts'][method]
            if kind == 'resources':
                base = resource_refs[(scenario, day)]
                output = prediction['output'][day] * 100
                for key in RESOURCE_FIELDS:
                    expected = output if key == 'output_tokens_per_team_day' else output * base[key] / base['output_tokens_per_team_day']
                    near(row[key], expected, (method, day, scenario, key))
                near(row['compute_pflops_window'], float(row['eflop_per_team_day']) * 1000 / 86400, (method, day, 'rate'))
                near(row['prefix_cache_hit_rate'], base['prefix_cache_hit_rate'], (method, day, 'cache rate'))
                near(row['tail_share'], base['tail_share'], (method, day, 'C mix schedule'))
            elif kind == 'agents':
                hours = prediction['workdays'][day] * 800
                near(row['agent_hours_per_team_day'], hours, (method, day, 'hours'))
                near(row['mean_online_agent_equivalents'], hours / 24, (method, day, 'activity'))
            else:
                near(row['task_starts_per_team_day'], prediction['tasks'][day] * 100, (method, day, 'tasks'))
    assert sum(map(len, csvs.values())) == 7152
    harness.passed('2400 imported points reach both HTML entries and all 7152 derived monthly rows')
    compared = verify_node_values(root, embedded, csvs)
    harness.passed(f'actual JavaScript conversions agree with CSVs and unchanged history ({compared} numeric values)')
    harness.command('export_html_datasets.py', '--check')
    harness.passed('published classified exports and source manifests verify successfully')

    stable = fingerprint(root)
    harness.command('update_html_predictions.py')
    rerun = fingerprint(root)
    mutable_reports = ('/manifest.json', '/validation.json', '/prediction_update_validation.json')
    unexpected = [name for name in stable if stable[name] != rerun.get(name)
                  and not name.endswith(mutable_reports)
                  and not (name.startswith('html/06_validation/') and name.endswith('.json'))]
    assert not unexpected, ('Repeat update changed content', unexpected)
    harness.passed('repeated import leaves prediction values and rendered page content stable')

    # The upstream schema contains 14-day and aligned 28-day output columns.
    # The latter is now reference-only and must not affect current outputs.
    only_28d = deepcopy(altered)
    for row in only_28d:
        if row['metric'] == 'output':
            row['output_tokens_28d'] = str(float(row['output_tokens_28d']) * 1.37)
    raw_bytes = (root / 'html/01_pages/raw-data-dashboard.html').read_bytes()
    source.write_bytes(encode_csv(only_28d, fields))
    harness.command('update_html_predictions.py')
    refreshed = json.loads((root / 'html/03_data/algorithm_forecasts.json').read_text())
    assert refreshed['forecasts'] == algorithm['forecasts']
    assert refreshed['uncertainty'] == algorithm['uncertainty'], '28-day reference edits changed resource uncertainty'
    assert (root / 'html/01_pages/raw-data-dashboard.html').read_bytes() == raw_bytes
    for kind, filename in (
        ('resources', 'resource_estimates/all_algorithms_monthly_resources.csv'),
        ('agents', 'team_projections/all_algorithms_monthly_agents.csv'),
        ('tasks', 'team_projections/all_algorithms_monthly_tasks.csv'),
    ):
        assert table(root / 'data_predict' / filename) == csvs[kind]
    harness.passed('28-day reference edits do not change 14-day resource curves, intervals, Agent/tasks or the raw-data page')

    # Changing only native output must scale resources and leave Agent/tasks intact.
    only_14d = deepcopy(altered)
    for row in only_14d:
        if row['metric'] == 'output':
            row['value'] = str(float(row['value']) * 1.37)
    source.write_bytes(encode_csv(only_14d, fields))
    harness.command('update_html_predictions.py')
    refreshed = json.loads((root / 'html/03_data/algorithm_forecasts.json').read_text())
    for method, metrics in algorithm['forecasts'].items():
        assert refreshed['forecasts'][method]['workdays'] == metrics['workdays']
        assert refreshed['forecasts'][method]['tasks'] == metrics['tasks']
        for day, value in metrics['output'].items():
            near(refreshed['forecasts'][method]['output'][day], value * 1.37, ('native output edit', method, day))
    for kind, filename in (
        ('agents', 'team_projections/all_algorithms_monthly_agents.csv'),
        ('tasks', 'team_projections/all_algorithms_monthly_tasks.csv'),
    ):
        assert table(root / 'data_predict' / filename) == csvs[kind]
    updated_resources = table(root / 'data_predict/resource_estimates/all_algorithms_monthly_resources.csv')
    originals = {(row['method'], row['scenario'], row['date']): row for row in csvs['resources']}
    for row in updated_resources:
        previous = originals[(row['method'], row['scenario'], row['date'])]
        for key in (*RESOURCE_FIELDS, 'compute_pflops_window'):
            near(row[key], float(previous[key]) * 1.37, ('native output resource edit', row['method'], row['date'], key))
        near(row['prefix_cache_hit_rate'], previous['prefix_cache_hit_rate'], 'output edit retains cache ratio')
    assert (root / 'html/01_pages/raw-data-dashboard.html').read_bytes() == raw_bytes
    harness.passed('14-day output edits scale Token and compute resources without changing Agent/tasks, cache ratios or the independently archived raw page')

    # A manually edited median must not silently retain its old distribution.
    ensemble_edit = deepcopy(altered)
    changed_point = next(row for row in ensemble_edit if row['method'] == ENSEMBLE and row['metric'] == 'output' and row['date'] == endpoint)
    changed_point['value'] = str(float(changed_point['value']) * 1.23)
    source.write_bytes(encode_csv(ensemble_edit, fields))
    harness.command('update_html_predictions.py')
    edited = json.loads((root / 'html/03_data/algorithm_forecasts.json').read_text())
    assert endpoint not in edited['uncertainty'][ENSEMBLE]['output']
    assert len(edited['uncertainty'][ENSEMBLE]['output']) == len(uncertainty['output']) - 1
    assert edited['uncertainty'][ENSEMBLE]['workdays'] == uncertainty['workdays']
    assert edited['uncertainty'][ENSEMBLE]['tasks'] == uncertainty['tasks']
    near(edited['forecasts'][ENSEMBLE]['output'][endpoint], changed_point['value'], 'edited ensemble median remains available')
    omitted = edited['meta']['uncertainty'][ENSEMBLE]['omitted_points']
    assert len(omitted) == 1 and omitted[0]['metric'] == 'output' and omitted[0]['date'] == endpoint
    assert omitted[0]['reason'] == 'point_forecast_differs_from_archived_median'
    retained_intervals = table(root / 'data_predict/forecasts/resource_page_uncertainty.csv')
    assert len(retained_intervals) == 149 and not any(row['metric'] == 'output' and row['date'] == endpoint for row in retained_intervals)
    assert (root / 'html/01_pages/raw-data-dashboard.html').read_bytes() == raw_bytes
    harness.passed('changing one ensemble median removes only its obsolete nominal interval and leaves the raw-page archive unchanged')

    # Zero is valid data, including coincident forecasts for all 16 methods.
    zero_rows = deepcopy(altered)
    for row in zero_rows:
        row['value'] = '0'
    source.write_bytes(encode_csv(zero_rows, fields))
    harness.command('update_html_predictions.py')
    zero_algorithm = json.loads((root / 'html/03_data/algorithm_forecasts.json').read_text())
    assert all(not points for points in zero_algorithm['uncertainty'][ENSEMBLE].values())
    assert len(zero_algorithm['meta']['uncertainty'][ENSEMBLE]['omitted_points']) == 150
    assert table(root / 'data_predict/forecasts/resource_page_uncertainty.csv') == []
    zero_resources = table(root / 'data_predict/resource_estimates/all_algorithms_monthly_resources.csv')
    for row in zero_resources:
        for key in (*RESOURCE_FIELDS, 'compute_pflops_window'):
            assert float(row[key]) == 0, (key, row)
        near(row['prefix_cache_hit_rate'], resource_refs[(row['scenario'], row['date'])]['prefix_cache_hit_rate'], 'zero output retains assumed cache ratio')
    for filename, keys in (
        ('team_projections/all_algorithms_monthly_agents.csv', ('agent_hours_per_team_day', 'mean_online_agent_equivalents')),
        ('team_projections/all_algorithms_monthly_tasks.csv', ('task_starts_per_team_day',)),
    ):
        assert all(float(row[key]) == 0 for row in table(root / 'data_predict' / filename) for key in keys)
    harness.passed('zero and identical method forecasts import with finite zero totals and preserved scenario ratios')
    return harness.checks


def main():
    assert shutil.which('node'), 'Node.js is required for the actual frontend formula cross-check'
    with tempfile.TemporaryDirectory(prefix='dashboard_prediction_update_test_') as folder:
        root = Path(folder)
        for directory in ('html', 'data_row', 'data_predict', 'scripts'):
            shutil.copytree(ROOT / directory, root / directory, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        checks = integration(root)
    print(json.dumps({'status': 'passed', 'checks': len(checks), 'isolated_fixture': True, 'real_datasets_unchanged': True}))


if __name__ == '__main__':
    main()
