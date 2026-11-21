"""Verify the frozen public task and output-token tables against OpenAI's embedded charts."""
import csv
import json
import re
from collections import defaultdict
from math import isclose
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
BASE = 'https://openai.com/index/'


def spec(article, title):
    with urlopen(Request(BASE + article + '/', headers={'User-Agent': 'Mozilla/5.0'}), timeout=60) as response:
        html = response.read().decode()
    records = (json.loads(m[1]) for m in re.finditer(r'self\.__next_f\.push\((\[.*?\])\)</script>', html, re.S))
    content = ''.join(r[1] for r in records if len(r) > 1 and isinstance(r[1], str))
    for match in re.finditer(r'"vegaLiteSpec":', content):
        chart = json.JSONDecoder().raw_decode(content[match.end():])[0]
        if chart.get('title') == title:
            return chart
    raise ValueError(f'Chart not found: {title}')


def check_rows(path, expected):
    with path.open() as f:
        actual = {r['date']: r for r in csv.DictReader(f) if r['task1_1']}
    assert actual.keys() == expected.keys()
    for day, row in expected.items():
        for key, value in row.items():
            if key.startswith('task'):
                assert float(actual[day][key]) == value, (day, key)


def run():
    nov = spec('research-acceleration-jagged-frontier', 'Estimated AI R&D tasks per researcher')
    # Vega may place the source in a layer, in a shared dataset or at the root.
    def task_series(node):
        if isinstance(node, list):
            if node and isinstance(node[0], dict) and 'task1_1' in node[0]:
                yield node
            else:
                for child in node:
                    yield from task_series(child)
        elif isinstance(node, dict):
            for child in node.values():
                yield from task_series(child)
    data = next(task_series(nov))
    check_rows(HERE.parent/'observed_openai_research_usage.csv', {r['date']: r for r in data})
    sep = spec('research-acceleration-view-inside-openai', 'Researchers are using coding agents in new ways')['datasets']
    labels = {r['stackIndex']: 'task' + r['category'].split()[0].replace('.', '_') for r in sep['categoryRows']}
    daily = defaultdict(dict)
    for r in sep['areaRows']:
        daily[r['date']][labels[r['stackIndex']]] = r['value']
    assert all(isclose(sum(daily[r['date']].values()), r['value']) for r in sep['totalRows'])
    check_rows(HERE/'observed_output_tokens.csv', daily)
    print(len(data), 'start-rate dates;', len(daily), 'output-token dates verified')


if __name__ == '__main__':
    run()
