"""Import the saved ensemble predictions and archive their provenance, without fitting.

Run after pulling upstream: python3 -B scripts/import_ensemble_predictions.py
Then apply the input with scripts/update_html_predictions.py. --check writes nothing.
Existing non-ensemble CSV records are preserved byte for byte. A changed existing
ensemble requires --replace-ensemble so manual edits cannot be overwritten silently.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from math import isfinite
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
TREND = Path('analysis/agentic_30t_forecast/workload/trend_models')
STYLE = TREND / 'results/original_style/ensemble_uncertainty'
ARCHIVE = Path('html/04_reproduce/project')
INPUT = Path('data_predict/forecasts/upstream/forecast.csv')
METHOD = 'ensemble_uncertainty'
FIELDS = ('metric', 'date', 'method', 'value', 'output_tokens_28d', 'lower95', 'upper95', 'interval_basis')
QUANTILES = ('lower95', 'lower80', 'median', 'upper80', 'upper95')


def sha(content):
    return hashlib.sha256(content).hexdigest()


def dates(metric):
    return {f'{year:04d}-{month:02d}-18' for year in range(2026, 2031) for month in range(1, 13)
            if ('2026-08-18' if metric == 'output' else '2026-11-18') <= f'{year:04d}-{month:02d}-18' <= '2030-11-18'}


def load_ensemble(path, aligned=False):
    values = {metric: {} for metric in (('output',) if aligned else ('output', 'workdays', 'tasks'))}
    for row in csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig'))):
        if row['method'] != 'ensemble':
            continue
        metric = 'output' if aligned else row['metric']
        day = row['date']
        if metric not in values or day in values[metric]:
            raise ValueError(f'Unexpected or duplicate ensemble record: {metric}/{day}')
        quantiles = [float(row[key]) for key in QUANTILES]
        if not all(isfinite(v) and v >= 0 for v in quantiles) or quantiles != sorted(quantiles):
            raise ValueError(f'Invalid ensemble quantiles: {metric}/{day}')
        if int(row['window_days']) != (28 if aligned or metric != 'output' else 14):
            raise ValueError(f'Unexpected rolling window: {metric}/{day}')
        values[metric][day] = row
    for metric, rows in values.items():
        if set(rows) != dates(metric):
            raise ValueError(f'Incomplete ensemble date coverage: {metric}')
    return values


def prepare(root=ROOT, replace=False):
    original = (root / INPUT).read_bytes()
    lines = original.splitlines(keepends=True)
    if not lines or tuple(next(csv.reader([lines[0].decode('utf-8-sig')]))) != FIELDS:
        raise ValueError('Editable input must retain the documented eight-column header.')
    # The canonical table contains scalar fields only. Keep every existing record
    # verbatim rather than round-tripping floats or line endings through a writer.
    kept, existing = [], []
    for line in lines[1:]:
        row = next(csv.reader([line.decode('utf-8')]))
        if len(row) != len(FIELDS):
            raise ValueError('Editable input contains an invalid record.')
        (existing if row[2] == METHOD else kept).append(line)
    saved = load_ensemble(root / STYLE / 'forecast.csv')
    aligned = load_ensemble(root / STYLE / 'output_aligned28.csv', aligned=True)['output']
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator='\n')
    for metric in ('output', 'workdays', 'tasks'):
        for day, row in sorted(saved[metric].items()):
            writer.writerow(dict(metric=metric, date=day, method=METHOD, value=row['median'],
                                 output_tokens_28d=aligned[day]['median'] if metric == 'output' else '',
                                 lower95=row['lower95'], upper95=row['upper95'],
                                 interval_basis=f"conditional simulation quantiles; {14 if metric == 'output' else 28}d target; not calibrated four-year coverage"))
    appended = stream.getvalue().encode('utf-8')
    if existing and b''.join(existing) != appended and not replace:
        raise ValueError('Existing ensemble records differ. Review them, then use --replace-ensemble to replace only this method.')
    base = lines[0] + b''.join(kept)
    if not base.endswith((b'\n', b'\r')):
        raise ValueError('Canonical input must end each record with a newline before appending.')
    output = base + appended
    files = {}
    # Archive the uniform four-chart inputs and originals, plus the methodology
    # and tabular diagnostics. The 23 MB path sample NPZ is not consumed by HTML.
    sources = sorted((root / STYLE).iterdir())
    uncertainty = root / TREND / 'uncertainty'
    sources += sorted(p for p in uncertainty.iterdir() if p.is_file())
    sources += sorted(p for p in (uncertainty / 'results').iterdir() if p.suffix in ('.csv', '.json'))
    provenance = []
    for source in sources:
        if not source.is_file() or source.is_symlink():
            raise ValueError('Source must be a regular file: ' + str(source))
        relative = source.relative_to(root)
        content = source.read_bytes()
        destination = ARCHIVE / relative
        files[destination.as_posix()] = content
        provenance.append(dict(source=relative.as_posix(), archive=destination.as_posix(), sha256=sha(content), bytes=len(content)))
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    metadata = dict(schema_version=1, method=METHOD, source_method='ensemble', source_commit=commit,
                    source_directory=STYLE.as_posix(), canonical_input=INPUT.as_posix(),
                    retained_non_ensemble_rows=len(kept), retained_non_ensemble_sha256=sha(base), imported_rows=150,
                    conversion={'value': 'forecast.csv median; output is 14-day target, workdays/tasks are 28-day targets',
                                'output_tokens_28d': 'output_aligned28.csv median; quantiles are taken after aligning each simulated path',
                                'intervals': 'nominal conditional 80%/95% model quantiles, not calibrated four-year coverage'},
                    omitted=['uncertainty/results/predictive_paths.npz (not read by HTML; retained in the upstream repository)'],
                    files=provenance)
    files[(ARCHIVE / STYLE / 'import_provenance.json').as_posix()] = (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode()
    files[INPUT.as_posix()] = output
    return files, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--replace-ensemble', action='store_true')
    args = parser.parse_args()
    files, metadata = prepare(replace=args.replace_ensemble)
    changed = [name for name, content in files.items() if not (ROOT / name).exists() or (ROOT / name).read_bytes() != content]
    if not args.check:
        for name in changed:
            path = ROOT / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(files[name])
    print(json.dumps(dict(status='passed', published=not args.check, method=METHOD, imported_rows=metadata['imported_rows'],
                         retained_rows=metadata['retained_non_ensemble_rows'], source_commit=metadata['source_commit'],
                         changed_files=changed, next_command='python3 -B scripts/update_html_predictions.py'), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
