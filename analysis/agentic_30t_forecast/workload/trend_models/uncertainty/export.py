"""Adapt the approved uncertainty figures to the original four-chart gallery."""
import hashlib
import json
import shutil

from ... import monthly_research_usage as style
from ...observations import HERE, records, write_rows
from ..run import HERE_NEW, inputs
from . import LABEL, NOTE, PRESET
from .run import ROOT, run
from .visualize import redraw

FIGURES = ('monthly_workdays', 'monthly_concurrency', 'monthly_tasks', 'monthly_output_tokens')


def export(out, folder, show_intervals=True, show_sample_paths=True):
    # Reuse the reviewed simulation for the default gallery. Custom result roots
    # get their own simulation and audit files, never another root's forecasts.
    source = ROOT/'results' if out.resolve() == (HERE_NEW/'results').resolve() else out/'uncertainty'
    if not (source/'predictive_paths.npz').exists():
        run(source)
        if not show_intervals or not show_sample_paths:
            redraw(source, show_intervals=show_intervals, show_sample_paths=show_sample_paths)
    else:
        manifest = json.loads((source/'manifest.json').read_text())
        for name, digest in manifest['sources'].items():
            if hashlib.sha256((HERE/name).read_bytes()).hexdigest() != digest:
                raise ValueError(f'Historical source changed: {name}; rerun uncertainty.run --output {source}')
        redraw(source, show_intervals=show_intervals, show_sample_paths=show_sample_paths)

    folder.mkdir(parents=True, exist_ok=True)
    for name in FIGURES:
        for ext in ('png', 'pdf'):
            shutil.copyfile(source/'figures'/f'{name}.{ext}', folder/f'{name}.{ext}')
    for name in ('forecast.csv', 'parameters.csv', 'team_parameters.csv', 'backtest.csv',
                 'scenarios.csv', 'output_aligned28.csv', 'main_concurrency.csv',
                 'main_concurrency_bands.csv', 'main_concurrency_metadata.json', 'manifest.json'):
        shutil.copyfile(source/name, folder/name)

    rows = [dict(r, method=PRESET) for r in records(source/'chart_data.csv')]
    _, historical = inputs()
    for status, distribution in (('observed', historical),
                                 ('forecast', records(source/'main_concurrency.csv'))):
        for r in distribution:
            total = sum(float(r[f'bin_{i}']) for i in range(9))
            for i, label in enumerate(style.BINS):
                rows.append(dict(metric='concurrency', method=PRESET, series=label,
                                 date=r['date'], value=float(r[f'bin_{i}'])/total, status=status))
    write_rows(folder/'chart_data.csv', rows)
    (folder/'preset.json').write_text(json.dumps(dict(
        method=PRESET, label=LABEL, note=NOTE, total_method='ensemble', point='median',
        concurrency_method='legacy_log_complement', concurrency_interval='paired_block_bootstrap_28d',
        show_intervals=show_intervals, show_sample_paths=show_sample_paths,
        source_results=str(source.resolve()),
        source_manifest_sha256=hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest(),
        resource_inputs_updated=False), ensure_ascii=False, indent=2)+'\n', encoding='utf8')
