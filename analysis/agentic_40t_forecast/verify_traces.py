"""Re-fetch the published sample and verify its selection, hashes and usage aggregates."""
import csv
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen
from xml.etree import ElementTree

BASE = 'https://swe-bench-submissions.s3.amazonaws.com/'
PREFIX = 'bash-only/20260217_mini-v2.0.0_kimi-k2-5-high/trajs/'


def verify(row):
    with urlopen(row['url'], timeout=60) as response:
        raw = response.read()
    if hashlib.sha256(raw).hexdigest() != row['sha256']:
        raise ValueError(f"Source changed for {row['instance']}")
    trace = json.loads(raw)
    assert trace['instance_id'] == row['instance']
    assert trace['info']['exit_status'] == row['status']
    usage = [m['extra']['response']['usage'] for m in trace['messages']
             if m['role'] == 'assistant' and m.get('extra', {}).get('response', {}).get('usage')]
    cache = [(u.get('prompt_tokens_details') or {}).get('cached_tokens') for u in usage]
    for u, cached in zip(usage, cache):
        assert u['prompt_tokens'] + u['completion_tokens'] == u['total_tokens']
        assert cached is None or 0 <= cached <= u['prompt_tokens']
    measured = dict(reported_calls=trace['info']['model_stats']['api_calls'], metered_calls=len(usage),
                    prompt=sum(u['prompt_tokens'] for u in usage),
                    completion=sum(u['completion_tokens'] for u in usage),
                    cache_read=sum(c for c in cache if c is not None),
                    unknown_cache_prompt=sum(u['prompt_tokens'] for u, c in zip(usage, cache) if c is None),
                    peak_request=max(u['total_tokens'] for u in usage))
    for key, value in measured.items():
        assert int(row[key]) == value, (row['instance'], key)


if __name__ == '__main__':
    with Path(__file__).with_name('trace_sample.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    with urlopen(BASE + '?list-type=2&max-keys=1000&prefix=' + PREFIX, timeout=60) as response:
        listing = ElementTree.parse(response)
    assert listing.findtext('{*}IsTruncated') == 'false'
    keys = [node.text for node in listing.findall('.//{*}Key') if node.text.endswith('.traj.json')]
    assert len(keys) == 500
    selected = sorted(keys, key=lambda k: hashlib.sha256(k.encode()).digest())[:40]
    assert [BASE+k for k in selected] == [r['url'] for r in rows]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(verify, rows))
    print(f'{len(rows)} trajectories verified against the public source')
