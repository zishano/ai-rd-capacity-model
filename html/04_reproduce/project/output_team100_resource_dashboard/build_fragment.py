"""Embed the validated local resource data into the literal visualization fragment."""
from pathlib import Path
import hashlib
import json
import math
import re

from build_algorithm_data import SOURCE as ALGORITHM_SOURCE, validate_payload as validate_algorithms


HERE = Path(__file__).resolve().parent
DATA = HERE / 'dashboard_data.json'
FRAGMENT = HERE / 'team-resource-dashboard.html'


def main():
    data = json.loads(DATA.read_text(encoding='utf-8'))
    rows = data['rows']
    assert len(rows) == 15
    assert {(r['year'], r['scenario']) for r in rows} == {(y, s) for y in (2026, 2027, 2028, 2029, 2030) for s in 'ABC'}
    for row in rows:
        assert row['researchers'] == 100
        assert math.isclose(row['cached_input_tokens_per_team_day'] + row['uncached_input_tokens_per_team_day'], row['input_tokens_per_team_day'], rel_tol=1e-10)
        assert math.isclose(row['prefill_eflop_per_team_day'] + row['decode_eflop_per_team_day'], row['eflop_per_team_day'], rel_tol=1e-10)
        assert math.isclose(row['agent_hours_per_team_day'] / 24, row['mean_online_agent_equivalents'], rel_tol=1e-10)
        assert math.isclose(row['eflop_per_team_day'] * 1000 / 86400, row['compute_pflops_24h'], rel_tol=1e-10)
        categories = [c for c in data['category_mix'] if (c['year'], c['scenario']) == (row['year'], row['scenario'])]
        assert len(categories) == 18
        assert len({c['category'] for c in categories}) == 18
        assert math.isclose(sum(c['share'] for c in categories), 1, rel_tol=1e-10)
        assert math.isclose(sum(c['output_tokens_per_team_day'] for c in categories), row['output_tokens_per_team_day'], rel_tol=1e-10)
    assert len(data['category_mix']) == 270
    assert data['baseline_metadata']['output_14d']['date'] == '2026-08-15'
    assert data['baseline_metadata']['agent_hours']['date'] == '2026-10-18'
    assert data['baseline_metadata']['task_starts']['date'] == '2026-10-18'
    source = (HERE / 'dashboard.template.html').read_text(encoding='utf-8')
    source = source.replace('/* DASHBOARD_STYLES */', (HERE / 'dashboard.css').read_text(encoding='utf-8'))
    source = source.replace('/* DASHBOARD_SCRIPT */', (HERE / 'dashboard.js').read_text(encoding='utf-8'))
    # Keep the complete research archive in dashboard_data.json. Embed only the
    # source sections consumed by this page, without duplicating raw history.
    ui_data = {key: data[key] for key in ('rows', 'model', 'baseline_metadata', 'category_mix', 'monthly_resources', 'monthly_tasks')}
    # The stored resource series currently has one calibrated model. Expose that
    # actual model and its configured weight format, rather than a display-only precision switch.
    model_config = json.loads((HERE.parent / 'config/models/moe_30t.json').read_text(encoding='utf-8'))
    ui_data['model'] = {**data['model'], 'id': model_config['model_id'],
                        'display_name': '30T MoE模型', 'weights': model_config['weights']}
    ui_data['monthly_trends'] = {'agents': data['monthly_trends']['agents']}
    algorithms = json.loads((HERE / 'algorithm_forecasts.json').read_text(encoding='utf-8'))
    assert algorithms['meta']['source_sha256'] == hashlib.sha256(ALGORITHM_SOURCE.read_bytes()).hexdigest()
    assert algorithms['meta']['dashboard_sha256'] == hashlib.sha256(DATA.read_bytes()).hexdigest()
    validate_algorithms(algorithms, data)
    ui_data['algorithm_forecasts'] = algorithms
    encoded = json.dumps(ui_data, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    encoded = encoded.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    pattern = r'(<script type="application/json" id="trd-inline-data">).*?(</script>)'
    updated, count = re.subn(pattern, lambda match: match.group(1)+encoded+match.group(2), source, count=1, flags=re.S)
    assert count == 1
    assert not re.search(r'<!doctype|<html\b|<head\b|<body\b', updated, re.I)
    assert 'team-resource-dashboard-30t-v2' in updated
    assert 'team-resource-dashboard-30t-v1' not in updated
    assert len(updated.encode('utf-8')) < 1_000_000
    assert '\\"' not in updated
    FRAGMENT.write_text(updated, encoding='utf-8')
    reread = FRAGMENT.read_text(encoding='utf-8')
    match = re.search(pattern, reread, re.S)
    payload = re.search(r'id="trd-inline-data">(.*?)</script>', reread, re.S).group(1)
    assert json.loads(payload) == ui_data
    print(json.dumps({'fragment': str(FRAGMENT), 'rows': len(rows), 'category_rows': len(data['category_mix']), 'bytes': len(reread.encode('utf-8')),
                      'data_sha256': hashlib.sha256(DATA.read_bytes()).hexdigest(),
                      'algorithm_count': len(algorithms['methods']),
                      'embedded_ui_data_matches_source': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
