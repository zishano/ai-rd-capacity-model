"""Wrap the inline resource dashboard for browser inspection and local reuse."""
import json
import runpy
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
RENDERER = Path('/mnt/nvme1n1/data/lmk/codex-personal/codex-home/plugins/cache/openai-curated-remote/visualize/1.0.89/skills/visualize/scripts/render.py')


def main():
    source = HERE / 'team-resource-dashboard.html'
    target = HERE / 'resource-dashboard-preview.html'
    # A standalone document: all data, styles, charts and controls are local.
    shell = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light dark"><title>百人团队 · 资源探索</title><style>html{color-scheme:light dark;background:light-dark(#f0f4f8,#121923)}body{margin:0}</style></head><body>'
    target.write_text(shell + source.read_text(encoding='utf-8') + '</body></html>', encoding='utf-8')
    ppt = HERE / 'team-resource-overview-2030.pptx'
    ns = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
          'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
    with zipfile.ZipFile(ppt) as archive:
        assert archive.testzip() is None
        for name in archive.namelist():
            if name.endswith('.xml'):
                ET.fromstring(archive.read(name))
        slide = ET.fromstring(archive.read('ppt/slides/slide1.xml'))
        labels = [t.text for t in slide.findall('.//a:t', ns)]
        data = json.loads((HERE / 'dashboard_data.json').read_text(encoding='utf-8'))
        row = next(r for r in data['rows'] if r['year'] == 2030 and r['scenario'] == 'C')
        expected = [
            f"{row['input_tokens_per_team_day']/1e8:,.2f}",
            f"{row['output_tokens_per_team_day']/1e8:,.2f}",
            f"{row['eflop_per_team_day']:,.2f}",
            f"{row['eflop_per_team_day']*1000/86400:.2f}",
            f"{row['mean_online_agent_equivalents']:,.0f}",
            f"{row['task_starts_per_team_day']:,.0f}",
            f"{data['model']['total_parameters']/1e12:.2f} TB",
        ]
        assert all(any(value in label for label in labels) for value in expected), expected
        shapes = slide.findall('.//p:sp', ns)
        assert len(shapes) == 39
        assert not slide.findall('.//p:pic', ns), 'Overview must be native editable shapes.'
        for transform in slide.findall('.//a:xfrm', ns):
            offset, extent = transform.find('a:off', ns), transform.find('a:ext', ns)
            if offset is None or extent is None:
                continue
            x, y = int(offset.attrib['x']), int(offset.attrib['y'])
            width, height = int(extent.attrib['cx']), int(extent.attrib['cy'])
            assert min(x, y, width, height) >= 0
            assert x + width <= 16 * 914400 and y + height <= 9 * 914400
    result = {'status': 'passed', 'preview': str(target), 'fragment_bytes': source.stat().st_size,
              'ppt_native_editable_shapes': len(shapes), 'ppt_validation': 'OOXML, labels, native shapes and slide bounds; not Office rendering'}
    analysis_validation = HERE / 'analysis_figure_validation.json'
    if analysis_validation.exists():
        result['annual_analysis_exports'] = json.loads(analysis_validation.read_text())
    (HERE / 'artifact_validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
