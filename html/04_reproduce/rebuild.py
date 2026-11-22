"""Rebuild the two offline pages using only this classified resource bundle."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from bundle_manifest import refresh

BUNDLE = Path(__file__).resolve().parents[1]
PROJECT = BUNDLE / '04_reproduce/project'
OUTPUT_NAME = 'output_team100_resource_dashboard'
PAGES = ('resource-dashboard-preview.html', 'raw-data-dashboard.html', 'team-resource-dashboard.html')
QA = (('validate_explorer.py', 'qa_validation.json'),
      ('validate_algorithms.py', 'algorithm_qa_validation.json'),
      ('validate_raw_dashboard.py', 'raw_qa_validation.json'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def assemble(workspace):
    shutil.copytree(PROJECT, workspace, dirs_exist_ok=True)
    output = workspace / OUTPUT_NAME
    output.mkdir(parents=True, exist_ok=True)
    # The original scripts expect these siblings. Copies in a temporary project
    # retain that contract without duplicating editable files in this archive.
    sources = ('02_frontend', '03_data', '01_pages', '05_figures/exports',
               '05_figures/screenshots', '06_validation/scripts', '06_validation/references',
               '06_validation/historical_reports')
    mapping = {}
    for directory in sources:
        for path in sorted((BUNDLE / directory).glob('*')):
            if path.is_file():
                target = output / path.name
                if target.exists() and sha(target) != sha(path):
                    raise ValueError('Conflicting sibling file: ' + path.name)
                shutil.copy2(path, target)
                mapping[str(target)] = path.relative_to(BUNDLE).as_posix()
    return output, mapping


def run_script(script, output, commands, *arguments):
    command = [sys.executable, '-B', str(output / script), *map(str, arguments)]
    result = subprocess.run(command, cwd=output.parent, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                            text=True, capture_output=True, timeout=360)
    item = {'script': script, 'exit_code': result.returncode,
            'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}
    commands.append(item)
    print(json.dumps({'script': script, 'exit_code': result.returncode}, ensure_ascii=False), flush=True)
    if result.returncode:
        raise RuntimeError(script + ': ' + (result.stderr or result.stdout)[-6000:])


def relocate_report(value, workspace, mapping):
    if isinstance(value, dict):
        return {relocate_report(key, workspace, mapping): relocate_report(item, workspace, mapping)
                for key, item in value.items()}
    if isinstance(value, list):
        return [relocate_report(item, workspace, mapping) for item in value]
    if isinstance(value, str):
        if value in mapping:
            return mapping[value]
        return value.replace(str(workspace) + '/', 'reconstructed_project/')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='compare reconstructed pages/data (default)')
    mode.add_argument('--publish', action='store_true', help='update this bundle with rebuilt pages/data')
    parser.add_argument('--recompute-data', action='store_true', help='recalculate from archived inputs; reuse saved algorithm fits')
    parser.add_argument('--refresh-algorithms', action='store_true', help='rebuild monthly algorithm data only, using the applied resource prediction snapshot')
    parser.add_argument('--browser-check', action='store_true', help='run all three original Chrome validators')
    parser.add_argument('--export-figures', action='store_true', help='regenerate static figures; needs optional packages and CJK font')
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error('Python 3.10 or later is required')
    report = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'running',
              'scope': 'archived-input rebuild; saved trend-model fits are not retrained',
              'options': vars(args), 'commands': [], 'comparisons': [],
              'source': '04_reproduce/project + classified bundle files; original checkout not used'}
    try:
        with tempfile.TemporaryDirectory(prefix='research_dashboard_bundle_') as directory:
            workspace = Path(directory) / 'project'
            output, mapping = assemble(workspace)
            if args.recompute_data:
                for script in ('build_data.py', 'build_algorithm_data.py', 'build_raw_data.py'):
                    run_script(script, output, report['commands'])
            elif args.refresh_algorithms:
                run_script('build_algorithm_data.py', output, report['commands'])
            if args.export_figures:
                for script in ('build_presentation.py', 'build_analysis_figures.py'):
                    run_script(script, output, report['commands'])
            for script in ('build_fragment.py', 'build_preview.py', 'build_raw_dashboard.py'):
                run_script(script, output, report['commands'])
            generated = [(output / name, BUNDLE / '01_pages' / name) for name in PAGES]
            generated += [(output / path.name, path) for path in sorted((BUNDLE / '03_data').iterdir()) if path.is_file()]
            for built, archived in generated:
                comparison = {'path': archived.relative_to(BUNDLE).as_posix(),
                              'archived_sha256': sha(archived), 'rebuilt_sha256': sha(built)}
                comparison['identical'] = comparison['archived_sha256'] == comparison['rebuilt_sha256']
                report['comparisons'].append(comparison)
            if not args.publish and not all(item['identical'] for item in report['comparisons']):
                raise ValueError('Reconstructed pages/data differ. Review edits, then use --publish to update the bundle.')
            if args.browser_check:
                for script, filename in QA:
                    arguments = ['--page', output / PAGES[1], '--resource-page', output / PAGES[0]] if script == 'validate_raw_dashboard.py' else ['--preview', output / PAGES[0]]
                    run_script(script, output, report['commands'], *arguments)
                    result = json.loads((output / filename).read_text(encoding='utf-8'))
                    if result['status'] != 'passed':
                        raise ValueError(filename + ' did not pass')
                    # Verify reports while the temporary absolute paths exist.
                    for path, expected in result['source_sha256'].items():
                        if sha(Path(path)) != expected:
                            raise ValueError('QA source changed: ' + path)
                    normalized = relocate_report(result, workspace, mapping)
                    normalized['source_path_base'] = 'bundle_root'
                    normalized['run_context'] = 'isolated reconstructed project, using only archived bundle files'
                    dump(BUNDLE / '06_validation/latest_reports' / filename, normalized)
                report['browser_checks'] = sum(len(json.loads((output / filename).read_text())['checks']) for _, filename in QA)
            if args.publish:
                for built, archived in generated:
                    shutil.copy2(built, archived)
                if args.export_figures:
                    for filename in ('team-resource-overview-2030.pptx', 'team-resource-analysis-2026-2030.png',
                                     'team-resource-analysis-2026-2030.svg', 'team-resource-analysis-2026-2030.pdf',
                                     'team-resource-analysis-2026-2030.pptx'):
                        shutil.copy2(output / filename, BUNDLE / '05_figures/exports' / filename)
                if args.browser_check:
                    for filename in QA:
                        result = json.loads((output / filename[1]).read_text())
                        for shot in result.get('screenshots', []):
                            shutil.copy2(output / shot['file'], BUNDLE / '05_figures/screenshots' / shot['file'])
            for name in ('data_validation.json', 'artifact_validation.json', 'analysis_figure_validation.json'):
                value = json.loads((output / name).read_text())
                dump(BUNDLE / '06_validation/latest_reports' / name, relocate_report(value, workspace, mapping))
            report = relocate_report(report, workspace, mapping)
            report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
    dump(BUNDLE / '06_validation/rebuild_validation.json', report)
    refresh()
    print(json.dumps({'status': report['status'], 'compared_files': len(report['comparisons']),
                      'browser_checks': report.get('browser_checks', 0), 'error': report.get('error')}, ensure_ascii=False))
    raise SystemExit(0 if report['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
