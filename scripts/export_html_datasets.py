"""Export the archived HTML inputs into observations and conditional predictions.

Run from any directory: python3 -B scripts/export_html_datasets.py [--check]
No network, model fitting, HTML edits, or changes to the source bundle.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import re
from pathlib import Path

from html_algorithm_projection import project_monthly
from html_dataset_docs import READMES


ROOT = Path(__file__).resolve().parents[1]
HTML = 'html'
PROJECT = HTML + '/04_reproduce/project'
WORKLOAD = PROJECT + '/analysis/agentic_30t_forecast/workload'
RESULTS = WORKLOAD + '/trend_models/results'
ENSEMBLE = RESULTS + '/original_style/ensemble_uncertainty'
APPLIED_FORECAST = PROJECT + '/resource_predictions/forecast.csv'
INPUT_NAMES = ('dashboard_data.json', 'algorithm_forecasts.json', 'raw_research_data.json')
GROUPS = {
    'observed': 'data_row/observations/page_observations.fragments.json',
    'transformed': 'data_row/observed_transforms/page_transforms.fragments.json',
    'team_observed': 'data_predict/team_projections/observed_basis.fragments.json',
    'team_forecast': 'data_predict/team_projections/forecast_basis.fragments.json',
    'resource_observed': 'data_predict/resource_estimates/historical_estimates.fragments.json',
    'resource_forecast': 'data_predict/resource_estimates/future_estimates.fragments.json',
    'forecast': 'data_predict/forecasts/page_forecasts.fragments.json',
    'metadata': 'data_predict/assumptions/page_metadata.fragments.json',
}
RESOURCE_KEYS = {
    'input_tokens_per_team_day', 'cached_input_tokens_per_team_day',
    'uncached_input_tokens_per_team_day', 'total_tokens_per_team_day',
    'prefill_eflop_per_team_day', 'decode_eflop_per_team_day', 'eflop_per_team_day',
    'prefix_cache_hit_rate', 'compute_pflops_24h', 'resource_evidence',
    'input_evidence', 'cached_input_evidence', 'uncached_input_evidence',
    'total_tokens_evidence', 'prefill_eflop_evidence', 'decode_eflop_evidence',
    'eflop_evidence', 'prefix_cache_hit_rate_evidence', 'compute_pflops_24h_evidence',
    'input_proxy_source_url', 'tail_share',
}
OBSERVATION_TEAM_KEYS = {'value_per_team_day', 'researchers'}


def sha(content):
    return hashlib.sha256(content).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def pointer(parts):
    return ''.join('/' + str(p).replace('~', '~0').replace('/', '~1') for p in parts)


def parts(path):
    return [p.replace('~1', '/').replace('~0', '~') for p in path.split('/')[1:]]


class Export:
    def __init__(self):
        self.sources = {}
        self.outputs = {}
        self.entries = {}
        self.checks = []

    def read(self, name):
        name = str(name)
        if name not in self.sources:
            path = ROOT / name
            if path.is_symlink():
                raise ValueError('Source must be a regular file: ' + name)
            self.sources[name] = path.read_bytes()
        return self.sources[name]

    def read_json(self, name):
        return json.loads(self.read(name))

    def put(self, name, content, classification, inputs=(), rule='', rows=None):
        if name in self.outputs:
            raise ValueError('Duplicate destination: ' + name)
        self.outputs[name] = content
        self.entries[name] = dict(classification=classification, source_files=list(inputs), export_rule=rule)
        if rows is not None:
            self.entries[name]['rows'] = rows

    def json(self, name, value, classification, inputs=(), rule='', rows=None):
        self.put(name, encoded(value), classification, inputs, rule, rows)

    def csv(self, name, rows, classification, inputs=(), rule=''):
        if not rows:
            raise ValueError('Unexpected empty table: ' + name)
        columns = list(dict.fromkeys(key for row in rows for key in row))
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        writer.writerows({k: canonical(v) if isinstance(v, (dict, list)) else v for k, v in row.items()} for row in rows)
        self.put(name, stream.getvalue().encode('utf-8'), classification, inputs, rule, len(rows))

    def copy(self, source, destination, classification):
        content = self.read(source)
        rows = len(list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))) if source.endswith('.csv') else None
        self.put(destination, content, classification, [source], 'byte-identical source copy', rows)

    def check(self, name, condition, **details):
        if not condition:
            raise ValueError('Validation failed: ' + name + ' ' + str(details))
        self.checks.append(dict(name=name, status='passed', **details))


def at(value, path):
    for part in path:
        value = value[part]
    return value


def classify(name, path, data):
    """Return a semantic partition, or descend when a record mixes evidence."""
    if not path:
        return None
    top = path[0]
    if name == 'algorithm_forecasts.json':
        return 'forecast' if top in ('forecasts', 'uncertainty') else 'metadata'
    if name == 'raw_research_data.json':
        if top != 'metrics':
            return 'metadata'
        if len(path) < 3:
            return None
        if path[2] == 'history':
            return 'transformed' if path[1] == 'concurrency' else 'observed'
        return 'forecast' if path[2] in ('forecast', 'uncertainty') else 'metadata'
    if top in ('baseline_metadata', 'baseline'):
        is_metrics = top == 'baseline_metadata' or len(path) >= 2 and path[1] == 'metrics'
        if not is_metrics:
            return None if len(path) == 1 else 'team_observed'
        offset = 1 if top == 'baseline_metadata' else 2
        if len(path) <= offset:
            return None
        if path[offset] == 'resource_estimates':
            return 'resource_observed'
        if len(path) <= offset + 1:
            return None
        if path[-1] in OBSERVATION_TEAM_KEYS:
            return 'team_observed'
        metric = at(data, path[:offset + 1])
        return 'observed' if metric['evidence'] == 'official_observation' else 'transformed'
    if top == 'history':
        if len(path) < 3:
            return None
        if path[-1] in OBSERVATION_TEAM_KEYS:
            return 'team_observed'
        return 'observed' if data['history'][path[1]]['evidence'] == 'official_observation' else 'transformed'
    if top == 'category_mix':
        if len(path) < 2:
            return None
        row = data[top][path[1]]
        return 'team_observed' if row['evidence'] in (
            'derived_from_observed', 'official_observation_scaled_to_team'
        ) else 'team_forecast'
    if top in ('rows', 'monthly_resources', 'monthly_tasks', 'monthly_trends'):
        row_depth = 3 if top == 'monthly_trends' else 2
        if len(path) <= row_depth:
            return None
        row = at(data, path[:row_depth])
        phase = 'forecast' if row.get('row_type') == 'forecast' or row.get('phase') == 'forecast' else 'observed'
        return ('resource_' if path[row_depth] in RESOURCE_KEYS else 'team_') + phase
    return 'metadata'


def split_json(export, inputs):
    records = {group: [] for group in GROUPS}
    structures = {}

    def walk(name, node, path):
        group = classify(name, path, inputs[name])
        if group:
            records[group].append(dict(source=name, pointer=pointer(path), value=node))
            return
        if not isinstance(node, (dict, list)):
            raise ValueError('Unclassified scalar: ' + name + pointer(path))
        structures[name].append(dict(pointer=pointer(path), kind='list' if isinstance(node, list) else 'dict',
                                     **({'length': len(node)} if isinstance(node, list) else {})))
        for key, value in (enumerate(node) if isinstance(node, list) else node.items()):
            walk(name, value, [*path, key])

    for name, data in inputs.items():
        structures[name] = []
        walk(name, data, [])
    for group, entries in records.items():
        export.json(GROUPS[group], {'classification': group, 'records': entries}, group,
                    [HTML + '/03_data/' + n for n in inputs if any(e['source'] == n for e in entries)],
                    'Lossless JSON Pointer fragments; values preserved, not rounded.', len(entries))
    export.json('data_predict/assumptions/reconstruction.json',
                dict(schema_version=1, structures=structures, partitions=GROUPS,
                     source_files={name: HTML + '/03_data/' + name for name in inputs},
                     explanation='Create the recorded empty containers in order; assign each fragment at its JSON Pointer. List lengths and null dates are preserved.'),
                'reconstruction_metadata', [HTML + '/03_data/' + n for n in inputs])
    records = {group: json.loads(export.outputs[filename])['records'] for group, filename in GROUPS.items()}

    def assign(root, path, value):
        if not path:
            return value
        parent = root
        tokens = parts(path)
        for token in tokens[:-1]:
            parent = parent[int(token)] if isinstance(parent, list) else parent[token]
        parent[int(tokens[-1]) if isinstance(parent, list) else tokens[-1]] = value
        return root

    for name, original in inputs.items():
        rebuilt = None
        seen = set()
        for container in structures[name]:
            rebuilt = assign(rebuilt, container['pointer'], [None] * container['length'] if container['kind'] == 'list' else {})
        for entries in records.values():
            for item in entries:
                if item['source'] == name:
                    if item['pointer'] in seen:
                        raise ValueError('Duplicate fragment pointer')
                    seen.add(item['pointer'])
                    rebuilt = assign(rebuilt, item['pointer'], copy.deepcopy(item['value']))
        export.check('lossless_reconstruction:' + name, canonical(original) == canonical(rebuilt),
                     fragments=len(seen), canonical_sha256=sha(canonical(rebuilt).encode()))


def copy_sources(export):
    for family, files in {
        'output_openai_researcher_forecast': (
            'source_downloads/selected_zh_article.html', 'source_downloads/chart_08.json',
            'source_downloads/selected_chart_identity.json', 'source_downloads/download_manifest.json',
            'official_data/normalization_manifest.json'),
        'output_openai_official_100': (
            'source_downloads/november_2026_page.html', 'source_downloads/november_2026_chart_02.json',
            'source_downloads/november_2026_chart_03.json', 'source_downloads/november_2026_chart_08.json',
            'source_downloads/download_manifest.json', 'official_data/normalization_manifest.json'),
    }.items():
        for file in files:
            export.copy(PROJECT + '/' + family + '/' + file, 'data_row/official_sources/' + family + '/' + file, 'official_source_archive')
    for family, name in [('output_openai_researcher_forecast', 'output_tokens_14d.csv'),
                         ('output_openai_official_100', 'workdays.csv'), ('output_openai_official_100', 'task_starts.csv')]:
        export.copy(PROJECT + '/' + family + '/official_data/' + name, 'data_row/observations/' + name, 'official_observation')
    for name in ('observed_openai_research_usage.csv', 'observed_workdays_by_team.csv', 'calibration/observed_output_tokens.csv'):
        export.copy(WORKLOAD + '/' + name, 'data_row/observations/source_snapshots/' + name, 'observational_source_snapshot')
    export.copy(WORKLOAD + '/sources.csv', 'data_row/official_sources/source_index.csv', 'source_lineage')
    for name in ('public_tasks.csv', 'REPORT.md'):
        export.copy(WORKLOAD + '/calibration/' + name, 'data_row/proxy_samples/' + name, 'third_party_measurement' if name.endswith('.csv') else 'historical_method_note')
    export.copy(PROJECT + '/config/models/moe_30t.json', 'data_predict/assumptions/moe_30t.json', 'synthetic_model_assumption')
    export.copy(WORKLOAD + '/settings.json', 'data_predict/assumptions/settings.json', 'scenario_assumption')
    forecast_source = APPLIED_FORECAST if (ROOT / APPLIED_FORECAST).exists() else RESULTS + '/forecast.csv'
    export.copy(forecast_source, 'data_predict/forecasts/upstream/forecast.csv', 'conditional_forecast_input')
    export.copy(RESULTS + '/concurrency.csv', 'data_predict/forecasts/upstream/concurrency.csv', 'conditional_forecast')
    algorithm_meta = export.read_json(HTML + '/03_data/algorithm_forecasts.json')['meta']
    export.check('applied_forecast_matches_algorithm_source',
                 sha(export.read(forecast_source)) == algorithm_meta['source_sha256'], source=forecast_source)
    for name in ('parameters.csv', 'backtest.csv', 'concurrency_backtest.csv', 'audit.json', 'manifest.json'):
        export.copy(RESULTS + '/' + name, 'data_predict/assumptions/algorithm_diagnostics/' + name, 'fit_parameters_or_historical_diagnostic')
    export.copy(WORKLOAD + '/trend_models/README.md', 'data_predict/assumptions/algorithm_diagnostics/README.upstream.md', 'historical_method_note')
    for method in ('legacy_ols', 'damped_holt', 'damped_holt_hl365', 'logistic_cap4x', 'gompertz_cap4x'):
        export.copy(RESULTS + '/original_style/' + method + '/team_parameters.csv',
                    'data_predict/assumptions/algorithm_diagnostics/' + method + '/team_parameters.csv', 'team_fit_parameters')
    for name in ('forecast.csv', 'output_aligned28.csv', 'scenarios.csv',
                 'main_concurrency.csv', 'main_concurrency_bands.csv'):
        export.copy(ENSEMBLE + '/' + name, 'data_predict/forecasts/upstream/ensemble_uncertainty/' + name,
                    'conditional_simulation_quantiles_or_scenarios')
    export.copy(ENSEMBLE + '/chart_data.csv', 'data_predict/forecasts/upstream/ensemble_uncertainty/chart_data.csv',
                'mixed_historical_forecast_source_archive')
    for name in ('parameters.csv', 'team_parameters.csv', 'backtest.csv', 'manifest.json',
                 'preset.json', 'main_concurrency_metadata.json', 'import_provenance.json'):
        export.copy(ENSEMBLE + '/' + name, 'data_predict/assumptions/algorithm_diagnostics/ensemble_uncertainty/' + name,
                    'ensemble_parameters_or_provenance')
    for name in ('README.md', 'sources.json'):
        export.copy(WORKLOAD + '/trend_models/uncertainty/' + name,
                    'data_predict/assumptions/algorithm_diagnostics/ensemble_uncertainty/' + ('README.upstream.md' if name == 'README.md' else name),
                    'ensemble_method_note')
    for name in ('concurrency.csv', 'concurrency_thresholds.csv', 'concurrency_backtest.csv', 'sensitivity.csv'):
        export.copy(WORKLOAD + '/trend_models/uncertainty/results/' + name,
                    'data_predict/assumptions/algorithm_diagnostics/ensemble_uncertainty/' + name,
                    'ensemble_experimental_diagnostic')


def raw_tables(export, raw):
    source = [HTML + '/03_data/raw_research_data.json']
    counts = {}
    uncertainty = []
    for key, definition in raw['metrics'].items():
        def flatten(pack, method=None):
            result = []
            for index, day in enumerate(pack['dates']):
                for series_index, series in enumerate(definition['series']):
                    result.append(dict(date=day, metric=key, series=series['id'], series_label=series['name'],
                                       value=pack['values'][index][series_index], unit=definition['unit'],
                                       rolling_window_days=definition['windowDays'], method=method or '',
                                       classification='conditional_forecast' if method else 'normalized_observation' if key == 'concurrency' else 'official_observation',
                                       observed_cutoff=definition['cutoff'],
                                       scope='researcher_fraction' if key == 'concurrency' else 'per_researcher_calendar_day'))
            return result
        history = flatten(definition['history'])
        directory = 'observed_transforms' if key == 'concurrency' else 'observations'
        export.csv('data_row/' + directory + '/raw_page_' + key + '.csv', history, 'normalized_observation' if key == 'concurrency' else 'official_observation', source,
                   'One shared history for every algorithm; unscaled underlying units; concurrency sums to 1.')
        future = [row for method, pack in definition['forecast'].items() for row in flatten(pack, method)]
        export.csv('data_predict/forecasts/raw_page_' + key + '.csv', future, 'conditional_forecast', source,
                   'All saved methods; original output uses a 14-day window; no team scaling.')
        counts[key] = dict(history_rows=len(history), forecast_rows=len(future), methods=len(definition['forecast']))
        for method, pack in definition.get('uncertainty', {}).items():
            for band in pack['bands']:
                for point in band['points']:
                    uncertainty.append(dict(metric=key, method=method, band=band['id'], band_label=band['name'],
                                            threshold=band.get('threshold', ''), **point, unit=definition['unit'],
                                            rolling_window_days=definition['windowDays'], scope=pack['scope'],
                                            calibrated=pack['calibrated'], classification='conditional_simulation_quantiles'))
    if uncertainty:
        export.csv('data_predict/forecasts/raw_page_uncertainty.csv', uncertainty, 'conditional_simulation_quantiles', source,
                   'Raw output target is 14 days; concurrency bounds describe cumulative boundaries, never independent bin areas.')
    export.check('raw_chart_coverage', sum(v['history_rows'] for v in counts.values()) > 0, metrics=counts)


def dashboard_tables(export, data):
    source = [HTML + '/03_data/dashboard_data.json']
    for evidence, directory in [('official_observation', 'observations'), ('derived_from_observed', 'observed_transforms')]:
        history = [{k: v for k, v in row.items() if k not in OBSERVATION_TEAM_KEYS} for row in data['history'] if row['evidence'] == evidence]
        export.csv('data_row/' + directory + '/resource_page_history.csv', history, evidence, source, 'Only per-researcher fields; hypothetical team fields are exported separately.')
        baseline = [dict(metric=key, **{k: v for k, v in row.items() if k not in OBSERVATION_TEAM_KEYS})
                    for key, row in data['baseline_metadata'].items() if row['evidence'] == evidence]
        export.csv('data_row/' + directory + '/resource_page_baseline.csv', baseline, evidence, source)
    team_history = [dict(row, source_evidence=row['evidence'], evidence='team_scaled_from_observation',
                         classification='hypothetical_team_projection') for row in data['history']]
    export.csv('data_predict/team_projections/observed_intensity_history.csv', team_history, 'hypothetical_team_projection', source,
               'Official per-researcher intensity multiplied by 100; not a measured 100-person team.')
    export.csv('data_predict/team_projections/output_category_mix.csv', data['category_mix'], 'hypothetical_team_projection', source,
               'Current category values use the official 14-day output target for history and forecasts; evidence identifies basis.')
    context = ('year', 'date', 'scenario', 'researchers', 'row_type', 'observed_dates',
               'output_rolling_window_days', 'agent_rolling_window_days', 'task_rolling_window_days')
    for phase in ('observed', 'forecast'):
        annual = [row for row in data['rows'] if (row['row_type'] == 'forecast') == (phase == 'forecast')]
        team_rows = [{k: v for k, v in row.items() if k not in RESOURCE_KEYS} for row in annual]
        for row in team_rows:
            row['classification'] = 'hypothetical_team_projection' if phase == 'observed' else 'conditional_team_forecast'
            row['basis_evidence'] = row.pop('evidence')
        export.csv('data_predict/team_projections/annual_' + phase + '_basis.csv', team_rows, 'team_' + phase, source)
        resource_rows = [{**{k: v for k, v in row.items() if k in RESOURCE_KEYS or k in context},
                          'basis_output_tokens_per_team_day': row['output_tokens_per_team_day'],
                          'classification': 'historical_proxy_estimate' if phase == 'observed' else 'conditional_resource_forecast'} for row in annual]
        export.csv('data_predict/resource_estimates/annual_' + phase + '_basis.csv', resource_rows, 'resource_' + phase, source,
                   '2026 has different observation dates by metric; null date is retained.')
        monthly_resources = [row for row in data['monthly_resources'] if row['phase'] == phase]
        resources = []
        for original in monthly_resources:
            row = dict(original)
            for key in ('phase', 'output_tokens_per_team_day', 'output_evidence'):
                row['basis_' + key] = row.pop(key)
            row['classification'] = 'historical_proxy_estimate' if phase == 'observed' else 'conditional_resource_forecast'
            row['method'] = 'legacy_ols' if phase == 'forecast' else ''
            resources.append(row)
        export.csv('data_predict/resource_estimates/monthly_' + phase + '_basis.csv', resources, 'resource_' + phase, source)
        team = []
        for kind, collection in [('tokens', data['monthly_trends']['tokens']), ('agents', data['monthly_trends']['agents']), ('tasks', data['monthly_tasks'])]:
            for original in collection:
                if original['phase'] == phase:
                    row = {k: v for k, v in original.items() if k not in RESOURCE_KEYS}
                    row.update(family=kind, classification='hypothetical_team_projection' if phase == 'observed' else 'conditional_team_forecast')
                    team.append(row)
        export.csv('data_predict/team_projections/monthly_' + phase + '_basis.csv', team, 'team_' + phase, source)
    export.check('mixed_historical_resource_rows_classified', all(r['input_evidence'] == 'estimated' for r in data['monthly_resources'] if r['phase'] == 'observed'))


def algorithm_tables(export, data, algorithms):
    inputs = [HTML + '/03_data/dashboard_data.json', HTML + '/03_data/algorithm_forecasts.json', HTML + '/02_frontend/dashboard.js']
    export.read(inputs[-1])
    windows = algorithms['meta']['rolling_window_days']
    export.check('metric_specific_rolling_windows', windows == {'output': 14, 'workdays': 28, 'tasks': 28})
    base = [dict(method=method, metric=metric, date=day, value=value,
                 unit=algorithms['meta']['units'][metric], rolling_window_days=windows[metric],
                 classification='conditional_forecast', scope='per_researcher_calendar_day')
            for method, metrics in algorithms['forecasts'].items() for metric, values in metrics.items() for day, value in values.items()]
    export.csv('data_predict/forecasts/resource_page_algorithms.csv', base, 'conditional_forecast', inputs[:2],
               'All registered methods, including the 2026-08-18 output point not displayed by the resource timeline.')
    intervals = [dict(method=method, metric=metric, date=day, **bounds,
                      unit=algorithms['meta']['units'][metric], rolling_window_days=windows[metric],
                      classification='conditional_simulation_quantiles', scope='per_researcher_calendar_day',
                      interval_basis=algorithms['meta']['uncertainty'][method]['interval_basis'])
                 for method, metrics in algorithms.get('uncertainty', {}).items()
                 for metric, rows in metrics.items() for day, bounds in rows.items()]
    # A user can replace every ensemble center; in that case preserve an empty
    # schema rather than retaining stale intervals from the preceding export.
    interval_path = 'data_predict/forecasts/resource_page_uncertainty.csv'
    if intervals:
        export.csv(interval_path, intervals, 'conditional_simulation_quantiles', inputs[:2],
                   'Native target quantiles: output 14 days, workdays/tasks 28 days; edited centers with unmatched archived medians are omitted, never recentered.')
    else:
        export.put(interval_path, b'method,metric,date,lower95,lower80,median,upper80,upper95,unit,rolling_window_days,classification,scope,interval_basis\n',
                   'conditional_simulation_quantiles', inputs[:2], 'No archived intervals match the edited point forecasts.', rows=0)
    export.check('ensemble_uncertainty_centers_match', all(row['median'] == algorithms['forecasts'][row['method']][row['metric']][row['date']]
                                                          for row in intervals), intervals=len(intervals),
                 omitted=len(algorithms['meta'].get('uncertainty_omitted_points', [])))
    projected = project_monthly(data, algorithms)
    for family, rows in projected.items():
        directory = 'resource_estimates' if family == 'resources' else 'team_projections'
        export.csv('data_predict/' + directory + '/all_algorithms_monthly_' + family + '.csv', rows, 'conditional_projection', inputs,
                   'Matches dashboard.js default 100 researchers / 24-hour window, all A/B/C scenarios, forecast dates only.')
    method_count = len(algorithms['methods'])
    expected = {'resources': method_count * sum(r['phase'] == 'forecast' for r in data['monthly_resources']),
                'agents': method_count * sum(r['phase'] == 'forecast' for r in data['monthly_trends']['agents']),
                'tasks': method_count * sum(r['phase'] == 'forecast' for r in data['monthly_tasks'])}
    export.check('all_algorithm_coverage', len(base) == sum(len(values) for metrics in algorithms['forecasts'].values() for values in metrics.values())
                 and all(len(projected[key]) == count for key, count in expected.items()),
                 per_researcher_rows=len(base), projected_rows={k: len(v) for k, v in projected.items()})


def verify_embedded_pages(export, inputs, model):
    data = inputs['dashboard_data.json']
    expected = {key: data[key] for key in ('rows', 'model', 'baseline_metadata', 'category_mix', 'monthly_resources', 'monthly_tasks')}
    expected['model'] = {**data['model'], 'id': model['model_id'], 'display_name': '30T MoE模型', 'weights': model['weights']}
    expected['monthly_trends'] = {'agents': data['monthly_trends']['agents']}
    expected['algorithm_forecasts'] = inputs['algorithm_forecasts.json']
    for name, identifier, value in [('resource-dashboard-preview.html', 'trd-inline-data', expected),
                                    ('team-resource-dashboard.html', 'trd-inline-data', expected),
                                    ('raw-data-dashboard.html', 'raw-inline-data', inputs['raw_research_data.json'])]:
        page = export.read(HTML + '/01_pages/' + name).decode('utf-8')
        matches = re.findall(r'<script\b[^>]*\bid="' + identifier + r'"[^>]*>(.*?)</script>', page, re.S)
        export.check('embedded_page_matches_inputs:' + name, len(matches) == 1 and canonical(json.loads(matches[0])) == canonical(value))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only: compare all exports and manifests with the current HTML archive.')
    args = parser.parse_args()
    editable = ROOT / 'data_predict/forecasts/upstream/forecast.csv'
    applied = ROOT / (APPLIED_FORECAST if (ROOT / APPLIED_FORECAST).exists() else RESULTS + '/forecast.csv')
    if editable.exists() and editable.read_bytes() != applied.read_bytes():
        raise ValueError('Pending forecast edits: run python3 -B scripts/update_html_predictions.py to validate and apply them; export will not overwrite this input.')
    export = Export()
    # Snapshot all HTML bundle files to prove this task never changes them.
    bundle_before = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in (ROOT / HTML).rglob('*') if p.is_file()}
    for name in ('scripts/export_html_datasets.py', 'scripts/html_algorithm_projection.py',
                 'scripts/html_dataset_docs.py', 'scripts/update_html_predictions.py', 'scripts/import_ensemble_predictions.py'):
        export.read(name)
    inputs = {name: export.read_json(HTML + '/03_data/' + name) for name in INPUT_NAMES}
    model = export.read_json(PROJECT + '/config/models/moe_30t.json')
    verify_embedded_pages(export, inputs, model)
    split_json(export, inputs)
    copy_sources(export)
    raw_tables(export, inputs['raw_research_data.json'])
    dashboard_tables(export, inputs['dashboard_data.json'])
    algorithm_tables(export, inputs['dashboard_data.json'], inputs['algorithm_forecasts.json'])
    export.json('data_predict/assumptions/page_defaults_and_formulas.json', {
        'researchers': 100, 'service_window_hours': 24, 'default_scenario': 'C', 'default_method': 'legacy_ols',
        'endpoint': '2030-11-18', 'scenarios_exported': ['A', 'B', 'C'],
        'rolling_window_days': {'output': 14, 'workdays': 28, 'tasks': 28},
        'headline': {'date': '2030-11-18', 'algorithm_count': 1,
                     'selection': 'independent single selection from all available algorithms; always enabled and independent of the 1-3 curve selections',
                     'source_tables': ['resource_estimates/all_algorithms_monthly_resources.csv',
                                       'team_projections/all_algorithms_monthly_agents.csv',
                                       'team_projections/all_algorithms_monthly_tasks.csv'],
                     'filter': 'method = selected headline algorithm; date = 2030-11-18; scenario = selected scenario',
                     'scale': 'exports use 100 people and a 24-hour window; page uses current team and window settings'},
        'model': {**inputs['dashboard_data.json']['model'], 'id': model['model_id'], 'display_name': '30T MoE模型', 'weights': model['weights']},
        'pure_weight_tb': inputs['dashboard_data.json']['model']['total_parameters'] * model['weights']['bytes_per_parameter'] / 1e12,
        'formulas': {'team_intensity': 'per_researcher_intensity * researchers', 'agent_hours': 'workdays * 8 * researchers',
                     'mean_online_agent_equivalents': 'agent_hours / 24', 'compute_pflops_window': 'eflop_per_team_day * (researchers / 100) * 1000 / (service_window_hours * 3600)',
                     'output_14d': 'official published 14-day rolling mean; forecast.csv value for metric=output; no second smoothing',
                     'output_28d_reference_only': '(output_14d(d) + output_14d(d - 14 days)) / 2; retained historical reference, not the current resource-page output',
                     'monthly_algorithm_resource': 'resource_field * (forecast_output_14d * 100 / original_output_14d); all methods including legacy_ols; cache rate unchanged'},
        'notes': ['历史资源估算不属于实测；百人值为相同人均强度的假设团队换算。',
                  '两个页面的输出统一采用官方14日滑动平均目标；官方已平滑序列不再二次平滑。任务和Agent工作日仍保留原始28日统计窗口。',
                  '动态导出中的 legacy_reference_compute_pflops_24h 是未被界面使用的原OLS辅助值；实际速率见 compute_pflops_window。',
                  '模型配置含部分当前页面未使用的硬件参数；未估算GPU卡数、HBM或网络。',
                  '页面人数和窗口仍可交互调整；导出为默认100人/24小时，并完整保留基础数据与换算公式。',
                  '月度算法预测可通过 update_html_predictions.py 更新；顶部显示所选单一算法的2030-11-18终点值，年度分析和原始四图使用各自独立归档。',
                  'ensemble_uncertainty 的中心为混合分布中位数；80%/95%分位带是未经长期覆盖校准的条件模拟结果。编辑中心后不匹配日期的旧区间会被剥离。',
                  'algorithm_diagnostics 是原始拟合的历史记录，导入新预测不会重拟合或更新回测。'],
        'not_included': ['逐题编码轨迹原件', '完整重拟合执行模块和未归档的categories/backtest_parameters/sensitivity等文件', '并发算法完整拟合系数', '个人研究员原始日志'],
    }, 'assumptions_and_formulas', [HTML + '/03_data/dashboard_data.json', PROJECT + '/config/models/moe_30t.json', HTML + '/02_frontend/dashboard.js'])
    for directory, content in READMES.items():
        export.put(directory + '/README.md', content.encode('utf-8'), 'documentation', ['scripts/html_dataset_docs.py'])
    checked_links = 0
    for directory, content in READMES.items():
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', content):
            if '://' in target or target.startswith('#'):
                continue
            path = (ROOT / directory / target.split('#')[0]).resolve()
            if not path.is_relative_to(ROOT) or (not path.exists() and str(path.relative_to(ROOT)) not in export.outputs):
                raise ValueError('Missing documentation link: ' + directory + '/' + target)
            checked_links += 1
    export.check('documentation_local_links', checked_links > 0, links=checked_links)
    bundle_manifest = export.read_json(HTML + '/manifest.json')
    archived = {HTML + '/' + entry['path']: entry for entry in bundle_manifest['files']}
    selected_sources = {name: content for name, content in export.sources.items() if name.startswith(HTML + '/') and name != HTML + '/manifest.json'}
    export.check('inputs_match_html_archive_manifest', all(name in archived and sha(content) == archived[name]['sha256'] and len(content) == archived[name]['bytes']
                                                        for name, content in selected_sources.items()), files=len(selected_sources))
    export.check('source_bundle_unchanged', all((ROOT / name).is_file() and sha((ROOT / name).read_bytes()) == digest for name, digest in bundle_before.items()), files=len(bundle_before))
    export.json('data_predict/validation.json', dict(status='passed', scope='data partition, exact JSON reconstruction, coverage; no model refit or new browser run',
                                                  checks=export.checks), 'validation_report', [HTML + '/03_data/' + n for n in INPUT_NAMES])
    source_info = {name: {'sha256': sha(content), 'bytes': len(content)} for name, content in sorted(export.sources.items())}
    export_version = sha(canonical(source_info).encode())
    for directory in ('data_row', 'data_predict'):
        files = [dict(path=name[len(directory) + 1:], sha256=sha(content), bytes=len(content), **export.entries[name])
                 for name, content in sorted(export.outputs.items()) if name.startswith(directory + '/')]
        export.json(directory + '/manifest.json', dict(schema_version=1, export_version=export_version,
                    path_base=directory, source_path_base='project_root', files=files, file_count=len(files),
                    source_files=source_info, excludes=['manifest.json (self-reference)'],
                    command='python3 -B scripts/export_html_datasets.py', readonly_check='python3 -B scripts/export_html_datasets.py --check'), 'manifest')
    if any((ROOT / name).read_bytes() != content for name, content in export.sources.items()):
        raise ValueError('An input changed while exporting; retry with a consistent snapshot.')
    failures = []
    for directory in ('data_row', 'data_predict'):
        actual = {str(p.relative_to(ROOT)) for p in (ROOT / directory).rglob('*') if p.is_file()}
        expected = {name for name in export.outputs if name.startswith(directory + '/')}
        if actual - expected:
            raise ValueError('Unexpected files; preserve/review them before exporting: ' + ', '.join(sorted(actual - expected)))
        if any(p.is_symlink() for p in (ROOT / directory).rglob('*')) or (ROOT / directory).is_symlink():
            raise ValueError('Destination must not contain symbolic links.')
    if args.check:
        for name, content in export.outputs.items():
            path = ROOT / name
            if not path.is_file() or path.read_bytes() != content:
                failures.append(name)
    else:
        # Previously generated files are writable only when their saved checksum
        # still matches, so later hand edits are never silently overwritten.
        for directory in ('data_row', 'data_predict'):
            manifest = ROOT / directory / 'manifest.json'
            previous = json.loads(manifest.read_text()) if manifest.exists() else {'files': []}
            owned = {directory + '/' + entry['path']: entry['sha256'] for entry in previous['files']}
            for name, content in export.outputs.items():
                if not name.startswith(directory + '/') or name.endswith('/manifest.json'):
                    continue
                path = ROOT / name
                if path.exists() and path.read_bytes() != content and sha(path.read_bytes()) != owned.get(name):
                    if name == 'data_predict/forecasts/upstream/forecast.csv':
                        raise ValueError('Pending forecast edits: run python3 -B scripts/update_html_predictions.py to validate and apply them; export will not overwrite this input.')
                    raise ValueError('Locally edited export; preserve it before regenerating: ' + name)
        for name, content in export.outputs.items():
            path = ROOT / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or path.read_bytes() != content:
                path.write_bytes(content)
    if failures:
        print(json.dumps({'status': 'failed', 'mismatched_or_missing': failures}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps({'status': 'passed', 'mode': 'check' if args.check else 'export', 'files': len(export.outputs),
                      'bytes': sum(map(len, export.outputs.values())), 'checks': len(export.checks), 'export_version': export_version}, ensure_ascii=False))


if __name__ == '__main__':
    main()
