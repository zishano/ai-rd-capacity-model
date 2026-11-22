"""Build the standalone original researcher-data page without fitting models."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent


def main():
    payload = json.loads((HERE / 'raw_research_data.json').read_text(encoding='utf-8'))
    assert set(payload['metrics']) == {'workdays', 'concurrency', 'tasks', 'output'}
    styles = (HERE / 'dashboard.css').read_text(encoding='utf-8').replace(
        '#team-resource-dashboard-30t-v2', '#raw-research-dashboard-v1')
    styles += '\n' + (HERE / 'raw-dashboard.css').read_text(encoding='utf-8')
    source = (HERE / 'raw-dashboard.template.html').read_text(encoding='utf-8')
    source = source.replace('/* RAW_DASHBOARD_STYLES */', styles)
    source = source.replace('/* RAW_DASHBOARD_SCRIPT */', (HERE / 'raw-dashboard.js').read_text(encoding='utf-8'))
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    encoded = encoded.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    pattern = r'(<script type="application/json" id="raw-inline-data">).*?(</script>)'
    source, count = re.subn(pattern, lambda m: m.group(1) + encoded + m.group(2), source, count=1, flags=re.S)
    assert count == 1
    assert not re.search(r'<!doctype|<html\b|<head\b|<body\b', source, re.I)
    shell = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light dark"><title>研究员使用情况 · 原始数据推演</title><style>html{color-scheme:light dark;background:light-dark(#f0f4f8,#121923)}body{margin:0}</style></head><body>'
    target = HERE / 'raw-data-dashboard.html'
    target.write_text(shell + source + '</body></html>', encoding='utf-8')
    assert json.loads(re.search(r'id="raw-inline-data">(.*?)</script>', target.read_text(encoding='utf-8'), re.S).group(1)) == payload
    print(json.dumps({'page': str(target), 'bytes': target.stat().st_size,
                      'data_sha256': hashlib.sha256((HERE / 'raw_research_data.json').read_bytes()).hexdigest(),
                      'metrics': list(payload['metrics']), 'self_contained': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
