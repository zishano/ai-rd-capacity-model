"""Verify the classified bundle without accessing its original project."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1]
MANIFEST = BUNDLE / 'manifest.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files():
    return sorted(path for path in BUNDLE.rglob('*')
                  if path.is_file() and path != MANIFEST
                  and '__pycache__' not in path.parts and path.suffix != '.pyc')


def refresh():
    previous = json.loads(MANIFEST.read_text(encoding='utf-8')) if MANIFEST.exists() else {}
    old = {item['path']: item for item in previous.get('files', [])}
    entries = []
    for path in files():
        relative = path.relative_to(BUNDLE).as_posix()
        entry = {**old.get(relative, {}), 'path': relative,
                 'category': relative.split('/')[0], 'bytes': path.stat().st_size,
                 'sha256': digest(path)}
        entry.setdefault('origin', 'bundle_generated')
        if 'original_sha256' in entry:
            entry['matches_original'] = entry['sha256'] == entry['original_sha256']
        entries.append(entry)
    payload = {**previous, 'schema_version': 1,
               'updated_at_utc': datetime.now(timezone.utc).isoformat(),
               'path_base': 'bundle_root',
               'excludes': ['manifest.json (self-reference)', '__pycache__', '*.pyc'],
               'file_count': len(entries), 'total_bytes': sum(e['bytes'] for e in entries),
               'files': entries}
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return payload


def verify():
    payload = json.loads(MANIFEST.read_text(encoding='utf-8'))
    expected = {entry['path']: entry for entry in payload['files']}
    actual = {path.relative_to(BUNDLE).as_posix(): path for path in files()}
    failures = []
    for name, entry in expected.items():
        path = actual.get(name)
        if path is None:
            failures.append({'path': name, 'reason': 'missing'})
        elif path.is_symlink():
            failures.append({'path': name, 'reason': 'symlink'})
        elif path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
            failures.append({'path': name, 'reason': 'content changed'})
    failures.extend({'path': name, 'reason': 'unlisted'} for name in sorted(actual.keys() - expected.keys()))
    return {'status': 'failed' if failures else 'passed', 'files': len(expected), 'failures': failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='refresh the manifest after intentional edits')
    args = parser.parse_args()
    if args.write:
        payload = refresh()
        print(json.dumps({'status': 'updated', 'files': payload['file_count'], 'bytes': payload['total_bytes']}))
    result = verify()
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
