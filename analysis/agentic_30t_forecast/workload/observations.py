"""Read the frozen source snapshots and optionally verify per-call metadata online."""
import csv
import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
ROOT = HERE.parents[2]
TRACE = ROOT / 'analysis/agentic_40t_forecast/trace_sample.csv'


def records(path):
    with path.open(encoding='utf8', newline='') as stream:
        return list(csv.DictReader(stream))


def write_rows(path, rows):
    with path.open('w', encoding='utf8', newline='') as f:
        writer = csv.DictWriter(f, rows[0].keys(), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def series(path, field):
    pairs = [(date.fromisoformat(r['date']), float(r[field])) for r in records(path)]
    if len(pairs) < 2 or any(not math.isfinite(v) or v < 0 for _, v in pairs):
        raise ValueError(f'Invalid series: {path}')
    if any(b <= a for (a, _), (b, _) in zip(pairs, pairs[1:])):
        raise ValueError(f'Dates must increase: {path}')
    return pairs


def complete():
    return [r for r in records(TRACE) if int(r['metered_calls']) == int(r['reported_calls']) > 0
            and int(r['unknown_cache_prompt']) == 0]


def fetch_calls(row):
    with urlopen(row['url'], timeout=60) as res:
        raw = res.read()
    if hashlib.sha256(raw).hexdigest() != row['sha256']:
        raise ValueError(f"Trace changed: {row['instance']}")
    messages = json.loads(raw)['messages']
    calls = []
    for m in messages:
        if m['role'] != 'assistant':
            continue
        extra = m.get('extra', {})
        response = extra.get('response', {})
        if not response.get('usage'):
            continue
        u = response['usage']
        calls.append(dict(instance=row['instance'], call=len(calls)+1, prompt=u['prompt_tokens'],
                          completion=u['completion_tokens'], cache_read=u['prompt_tokens_details']['cached_tokens'],
                          created=response['created'], received=extra['timestamp']))
    for k in ('prompt','completion','cache_read'):
        if sum(c[k] for c in calls) != int(row[k]):
            raise ValueError(f"Usage mismatch: {row['instance']}/{k}")
    return calls


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Re-extract metering fields from verified public logs.')
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=6) as pool:
        data = [c for calls in pool.map(fetch_calls, complete()) for c in calls]
    write_rows(args.destination, data)
