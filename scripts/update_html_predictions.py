"""Apply saved monthly forecasts to the offline resource dashboard.

Edit data_predict/forecasts/upstream/forecast.csv, then run this script.
--check performs the same isolated rebuild and checks without publishing.
The monthly curves and single-algorithm endpoint cards consume these values.
This imports predictions; it does not train models or update annual baselines.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
INPUT = 'data_predict/forecasts/upstream/forecast.csv'
APPLIED = 'html/04_reproduce/project/resource_predictions/forecast.csv'
ALGORITHMS = 'html/03_data/algorithm_forecasts.json'
REPORT = 'html/06_validation/prediction_update_validation.json'
DIRECTORIES = ('html', 'data_row', 'data_predict')
SCRIPTS = ('update_html_predictions.py', 'export_html_datasets.py',
           'html_algorithm_projection.py', 'html_dataset_docs.py', 'import_ensemble_predictions.py')


def sha(content):
    return hashlib.sha256(content).hexdigest()


def snapshot(root):
    result = {}
    for directory in DIRECTORIES:
        base = root / directory
        if base.is_symlink() or not base.is_dir():
            raise ValueError('Missing directory or symbolic link: ' + directory)
        for path in sorted(base.rglob('*')):
            if path.is_symlink():
                raise ValueError('Symbolic links are not supported: ' + str(path))
            if '__pycache__' in path.parts or path.suffix == '.pyc' or not path.is_file():
                continue
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    for filename in SCRIPTS:
        name = 'scripts/' + filename
        path = root / name
        if path.is_symlink():
            raise ValueError('Script must be a regular file: ' + name)
        result[name] = path.read_bytes()
    return result


def run(root, script, *arguments):
    result = subprocess.run([sys.executable, '-B', str(root / script), *arguments],
                            cwd=root, text=True, capture_output=True, timeout=360,
                            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    if result.returncode:
        raise ValueError(script + ' failed:\n' + (result.stderr or result.stdout)[-6000:])
    return result.stdout.strip()


def changed_points(before, after):
    changes = []
    for method, metrics in after['forecasts'].items():
        for metric, rows in metrics.items():
            changed = [day for day, value in rows.items()
                       if value != before.get('forecasts', {}).get(method, {}).get(metric, {}).get(day)]
            if changed:
                changes.append({'method': method, 'metric': metric, 'points': len(changed),
                                'first_date': min(changed), 'last_date': max(changed)})
    return changes


def validate_scope(before, stage):
    """An import must leave observations, annual references and the raw page intact."""
    protected = []
    for name, content in before.items():
        preserve = (
            name.startswith('html/03_data/') and name != ALGORITHMS
            or name == 'html/01_pages/raw-data-dashboard.html'
            or name.startswith('html/04_reproduce/project/') and name != APPLIED
            or name.startswith('data_row/') and name not in ('data_row/manifest.json', 'data_row/README.md')
            or name.startswith('data_predict/forecasts/raw_page_')
            or '/annual_' in name or '/monthly_' in name
            or name == 'data_predict/team_projections/output_category_mix.csv'
        )
        if preserve:
            path = stage / name
            if not path.is_file() or path.read_bytes() != content:
                raise ValueError('Update crossed its monthly forecast scope: ' + name)
            protected.append(name)
    return protected


def replace_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.' + path.name + '.', suffix='.tmp',
                                     dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            if path.exists():
                os.chmod(temporary, path.stat().st_mode & 0o777)
            else:
                os.chmod(temporary, 0o644)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()


def publish(before, after, root):
    # Detect concurrent input/template edits before replacing any generated file.
    if snapshot(root) != before:
        raise ValueError('Files changed during validation; nothing was published. Run again with a stable input.')
    if before.keys() - after.keys():
        raise ValueError('Unexpected deletion in staged update.')
    changed = {name: content for name, content in after.items()
               if before.get(name) != content}
    if any(name.startswith('scripts/') or name == INPUT for name in changed):
        raise ValueError('Updater must preserve its scripts and the edited forecast input.')
    written = []
    try:
        # Source snapshots/data/pages first; validation records and manifests last.
        for name in sorted(changed, key=lambda n: (n.endswith('manifest.json'), n)):
            path = root / name
            current = path.read_bytes() if path.exists() else None
            if current != before.get(name):
                raise ValueError('Concurrent edit detected: ' + name)
            replace_file(path, changed[name])
            written.append(name)
    except BaseException:
        # Restore only bytes still owned by this run, never overwrite a later edit.
        for name in reversed(written):
            path = root / name
            if path.read_bytes() != changed[name]:
                continue
            if name in before:
                replace_file(path, before[name])
            else:
                path.unlink()
        raise
    return list(changed)


def update(root=ROOT, check=False):
    before = snapshot(root)
    if INPUT not in before:
        raise ValueError('Missing editable input: ' + INPUT)
    with tempfile.TemporaryDirectory(prefix='resource_prediction_update_') as temporary:
        stage = Path(temporary) / 'project'
        for name, content in before.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        applied = stage / APPLIED
        applied.parent.mkdir(parents=True, exist_ok=True)
        applied.write_bytes(before[INPUT])
        # The dedicated snapshot is used only by the resource algorithm adapter.
        # The raw four-chart builder keeps its independent upstream source.
        run(stage, 'html/04_reproduce/rebuild.py', '--publish', '--refresh-algorithms')
        algorithms = json.loads((stage / ALGORITHMS).read_bytes())
        if algorithms['meta']['source_sha256'] != sha(before[INPUT]):
            raise ValueError('Generated algorithm data does not match the edited input.')
        changes = changed_points(json.loads(before[ALGORITHMS]), algorithms)
        # Export validates embedded JSON and every derived monthly resource row.
        run(stage, 'scripts/export_html_datasets.py')
        protected = validate_scope(before, stage)
        validation = {
            'status': 'passed', 'scope': 'monthly future algorithms and single-algorithm endpoint cards; no model fitting',
            'editable_input': INPUT, 'applied_snapshot': APPLIED,
            'input_sha256': sha(before[INPUT]),
            'algorithm_data_sha256': sha((stage / ALGORITHMS).read_bytes()),
            'source_matches_input': True, 'input_rows': algorithms['meta']['validation']['forecast_points'],
            'methods': len(algorithms['methods']),
            'protected_file_count': len(protected), 'protected_files': protected,
            'unchanged': ['official observations', 'annual OLS reference analyses',
                          'raw four-chart page and its original forecast inputs',
                          'model, calibration ratios and original diagnostic reports'],
            'headline': {'date': '2030-11-18', 'algorithm_count': 1,
                         'source': 'selected algorithm monthly resource, agent and task endpoints',
                         'selection': 'independent single selection from all available algorithms; no aggregation'},
            'uncertainty': algorithms['meta'].get('uncertainty', {}),
            'checks': ['CSV coverage, duplicates, finite nonnegative values',
                       'monthly projections and resource arithmetic',
                       'HTML embedded data equals generated JSON',
                       'classification exports and lossless JSON reconstruction',
                       'protected source/output files byte-identical'],
            'browser_check': 'not run by this command',
            'diagnostics': 'Archived fit parameters/backtests describe the original model run; not recomputed by import.',
        }
        (stage / REPORT).write_text(json.dumps(validation, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        # Refresh source lineage after adding the validation report, then export
        # again so manifests describe the final self-contained bundle exactly.
        run(stage, 'html/04_reproduce/bundle_manifest.py', '--write')
        run(stage, 'scripts/export_html_datasets.py')
        run(stage, 'scripts/export_html_datasets.py', '--check')
        run(stage, 'html/04_reproduce/bundle_manifest.py')
        validate_scope(before, stage)
        after = snapshot(stage)
        planned = [name for name, content in after.items() if before.get(name) != content]
        if snapshot(root) != before:
            raise ValueError('Files changed during validation; nothing was published. Run again with a stable input.')
        if not check:
            publish(before, after, root)
        return {'status': 'passed', 'mode': 'check' if check else 'update',
                'input': INPUT, 'input_sha256': sha(before[INPUT]),
                'methods': len(algorithms['methods']), 'changed_forecast_points': changes,
                'planned_files' if check else 'updated_files': planned,
                'protected_files_unchanged': len(protected),
                'page': 'html/01_pages/resource-dashboard-preview.html',
                'report': REPORT, 'published': not check}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='validate and rebuild in a temporary directory; do not publish')
    args = parser.parse_args()
    try:
        result = update(check=args.check)
    except Exception as error:
        print(json.dumps({'status': 'failed', 'published': False, 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
