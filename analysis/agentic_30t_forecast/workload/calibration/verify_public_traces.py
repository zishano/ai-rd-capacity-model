"""Rebuild field-only task measurements from the 500 public submission objects."""
import argparse
import csv
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median
from urllib.request import urlopen

from analysis.agentic_40t_forecast.verify_traces import BASE, PREFIX

HERE = Path(__file__).resolve().parent
OUTCOME_URL = ('https://raw.githubusercontent.com/SWE-bench/experiments/main/evaluation/verified/'
               '20260217_mini-v2.0.0_kimi-k2-5-high/per_instance_details.json')


def cached(url, path):
    if path.exists():
        return path.read_bytes()
    for attempt in range(4):
        try:
            with urlopen(url, timeout=40) as response:
                data = response.read()
            path.write_bytes(data)
            return data
        except OSError:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def measure(instance, outcome, cache_dir):
    url = f'{BASE}{PREFIX}{instance}/{instance}.traj.json'
    data = cached(url, cache_dir / (instance + '.json'))
    trace = json.loads(data)
    assert trace['instance_id'] == instance
    reported = trace['info']['model_stats']['api_calls']
    assert reported == outcome['api_calls']
    prompts, outputs, caches, starts, ends, lengths = [], [], [], [], [], []
    for msg in trace['messages']:
        if msg['role'] != 'assistant':
            continue
        extra = msg.get('extra', {})
        response = extra.get('response') or {}
        u = response.get('usage')
        if not u:
            continue
        i, o = u['prompt_tokens'], u['completion_tokens']
        assert i + o == u['total_tokens'] and min(i, o) >= 0
        prompts.append(i)
        outputs.append(o)
        lengths.append(i + o)
        c = (u.get('prompt_tokens_details') or {}).get('cached_tokens')
        if c is not None:
            assert 0 <= c <= i
            caches.append(c)
        if response.get('created') is not None and extra.get('timestamp') is not None:
            starts.append(response['created'])
            ends.append(extra['timestamp'])
    complete = 0 < reported == len(lengths) == len(caches) == len(starts)
    return dict(instance=instance, status=trace['info']['exit_status'], resolved=int(outcome['resolved']),
                reported_calls=reported, metered_calls=len(lengths), cache_calls=len(caches),
                timed_calls=len(starts), complete=int(complete), prompt=sum(prompts),
                completion=sum(outputs), cache_read=sum(caches),
                peak_request=max(lengths, default=0), median_request=median(lengths) if lengths else '',
                start=min(starts) if starts else '', end=max(ends) if ends else '',
                duration_min=(max(ends)-min(starts))/60 if starts else '',
                sha256=hashlib.sha256(data).hexdigest(), url=url), lengths


def main(cache_dir, output):
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = cached(OUTCOME_URL, cache_dir/'outcomes.json')
    if hashlib.sha256(payload).hexdigest() != '3794b2c4b853845d97cf89db10f4264a0b27ba75f6b1bbbf1e34ddf6fa8a5c1f':
        raise ValueError('Public evaluation summary changed. Check the submission version.')
    outcomes = json.loads(payload)
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda k: measure(k, outcomes[k], cache_dir), sorted(outcomes)))
    tasks = [t for t, _ in results]
    with (HERE/'public_tasks.csv').open() as f:
        frozen_hashes = {row['instance']: row['sha256'] for row in csv.DictReader(f)}
    current_hashes = {row['instance']: row['sha256'] for row in tasks}
    if frozen_hashes != current_hashes:
        raise ValueError('Trajectory IDs or content changed relative to the frozen submission')
    output.mkdir(parents=True, exist_ok=True)
    with (output/'public_tasks.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, tasks[0], lineterminator='\n')
        w.writeheader()
        w.writerows(tasks)
    with (output/'request_context_histogram.csv').open('w', newline='') as f:
        from collections import Counter
        h = Counter(v for t, lengths in results if t['complete'] for v in lengths)
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['prompt_plus_completion', 'calls'])
        w.writerows(sorted(h.items()))
    print(len(tasks), 'public tasks;', sum(t['complete'] for t in tasks), 'complete')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cache_dir', type=Path)
    parser.add_argument('--output', type=Path, default=HERE)
    args = parser.parse_args()
    main(args.cache_dir, args.output)
