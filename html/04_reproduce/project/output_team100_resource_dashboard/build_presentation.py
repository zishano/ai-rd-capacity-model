"""Editable default-state resource overview, without hardware sizing assumptions."""
import json
import sys
from pathlib import Path

DEPS = Path('/tmp/ai_rd_report_deps')
if DEPS.exists():
    sys.path.insert(0, str(DEPS))
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
FONT = 'Noto Sans CJK SC'
INK, MUTED = '193B4B', '577080'
BLUE, TEAL, ORANGE = '276B8A', '147F8E', 'C76C3E'
PALE, LINE = 'F2F6F8', 'D6E1E7'


def main():
    data = json.loads((HERE / 'dashboard_data.json').read_text(encoding='utf-8'))
    row = next(r for r in data['rows'] if r['year'] == 2030 and r['scenario'] == 'C')
    model = data['model']
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(16), Inches(9)
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    def rect(x, y, w, h, color=PALE, rounded=False):
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
                                      Inches(x), Inches(y), Inches(w), Inches(h))
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(color)
        shape.line.fill.background()
        if rounded:
            shape.adjustments[0] = .08
        return shape

    def txt(text, x, y, w, h, size=14, color=INK, bold=False):
        shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        frame = shape.text_frame
        frame.word_wrap = True
        frame.margin_left = frame.margin_right = Inches(.02)
        frame.margin_top = frame.margin_bottom = Inches(.01)
        for index, line in enumerate(str(text).split('\n')):
            p = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            p.text = line
            p.font.name, p.font.size, p.font.bold = FONT, Pt(size), bold
            p.font.color.rgb = RGBColor.from_string(color)
        return shape

    txt('百人团队 · 每日推理资源总览', .48, .29, 12, .6, 30, bold=True)
    txt('2030年11月18日  /  C：混合增长  /  合成30T Top-8 MoE  /  OLS参考 · 输出14日均值', .5, .94, 14.8, .4, 13, MUTED)
    rect(.5, 1.47, 15, .025, LINE)

    # People and activity: these are independently projected organization-level quantities.
    rect(.5, 1.78, 3.02, 5.99, PALE, True)
    txt('研究员与Agent活动', .72, 1.99, 2.57, .4, 17, bold=True)
    txt('100', .72, 2.58, 2.5, .7, 42, BLUE, True)
    txt('名研究员', .75, 3.3, 2.5, .32, 13, MUTED)
    txt(f"{row['task_starts_per_team_day']:,.0f}", .72, 3.93, 2.5, .6, 31, bold=True)
    txt('研发任务发起 / 日', .75, 4.58, 2.5, .32, 13, MUTED)
    txt(f"{row['mean_online_agent_equivalents']:,.0f}", .72, 5.18, 2.5, .65, 35, BLUE, True)
    txt('平均在线Agent活动当量', .75, 5.9, 2.5, .32, 12, MUTED)
    txt(f"累计 {row['agent_hours_per_team_day']:,.0f} Agent小时/日\n按累计小时 ÷ 24 换算", .75, 6.49, 2.5, .75, 12, MUTED)

    # Token units are kept separate from compute units; arrows indicate causality only.
    x = 3.85
    txt('TOKEN工作量', x, 1.98, 7.75, .4, 17, bold=True)
    inp = row['input_tokens_per_team_day'] / 1e8
    cached = row['cached_input_tokens_per_team_day'] / 1e8
    fresh = row['uncached_input_tokens_per_team_day'] / 1e8
    out = row['output_tokens_per_team_day'] / 1e8
    hit = row['prefix_cache_hit_rate']
    txt(f'累计输入  {inp:,.2f} 亿Token/日', x, 2.5, 7.7, .55, 23, bold=True)
    rect(x, 3.15, 7.65 * hit, .22, TEAL)
    rect(x + 7.65 * hit, 3.15, 7.65 * (1-hit), .22, ORANGE)
    txt(f'缓存输入  {cached:,.2f} 亿', x, 3.55, 4.2, .42, 18, TEAL, True)
    txt(f'Prefix Cache命中率 {hit:.2%}', x, 4.02, 4.25, .35, 12, MUTED)
    txt(f'未缓存输入  {fresh:,.2f} 亿', x+4.45, 3.55, 3.4, .42, 18, ORANGE, True)
    txt('进入 Prefill 计算', x+4.45, 4.02, 3.2, .35, 12, MUTED)
    txt(f'生成输出  {out:,.2f} 亿Token/日', x, 4.55, 7.7, .45, 20, BLUE, True)
    txt('输入包含缓存复用；输出单独计量。', x, 5.03, 7.7, .32, 12, MUTED)

    txt('理论计算需求', x, 5.7, 7.7, .4, 17, bold=True)
    pf, dc, total = (row[k] for k in ['prefill_eflop_per_team_day', 'decode_eflop_per_team_day', 'eflop_per_team_day'])
    rect(x, 6.26, 7.65 * pf/total, .27, ORANGE)
    rect(x+7.65*pf/total, 6.26, 7.65*dc/total, .27, BLUE)
    txt(f'Prefill  {pf:,.2f} EFLOP/日', x, 6.68, 4.4, .35, 14, ORANGE, True)
    txt(f'Decode  {dc:,.2f} EFLOP/日', x+4.46, 6.68, 3.4, .35, 14, BLUE, True)
    txt(f'{total:,.2f} EFLOP/日', x, 7.2, 4.1, .55, 24, bold=True)
    txt(f"24h摊平 → {total*1000/86400:.2f} PFLOP/s", x+4.46, 7.25, 3.4, .5, 18, bold=True)

    # Model memory is one shared copy, not per researcher and not multiplied by online Agents.
    rect(12.02, 1.78, 3.48, 5.99, PALE, True)
    txt('模型与存储边界', 12.25, 1.99, 3.0, .4, 17, bold=True)
    txt(f"{model['total_parameters']/1e12:.2f} T", 12.25, 2.58, 3.0, .62, 33, bold=True)
    txt('总参数 · 合成MoE架构', 12.27, 3.25, 3.0, .35, 12, MUTED)
    txt(f"激活 {model['active_parameters']/1e9:.2f} B / Token\nTop-{model['experts_per_token']}", 12.27, 3.87, 3.0, .85, 16, BLUE, True)
    txt(f"{model['total_parameters']/1e12:.2f} TB", 12.25, 4.96, 3.0, .65, 32, TEAL, True)
    txt('单份FP8纯权重 · 1字节/参数\n未计副本与量化元数据', 12.27, 5.63, 3.0, .72, 12, MUTED)
    txt('KV驻留 / HBM带宽 / 网络通信\n需补充请求级与部署参数', 12.27, 6.66, 3.0, .72, 12, MUTED)

    txt('依据：OpenAI研究员输出、任务与时长趋势外推；输入/缓存与FLOPs另依赖252条编码代理轨迹及合成30T架构。', .5, 8.1, 15, .33, 11, MUTED)
    txt('平均活动当量不是峰值或LLM/GPU并发；PFLOP/s为理论工作量摊平速率，尚未计实际Serving效率。', .5, 8.5, 15, .33, 11, MUTED)
    dest = HERE / 'team-resource-overview-2030.pptx'
    prs.save(dest)
    print(json.dumps({'status': 'written', 'file': str(dest), 'native_editable_shapes': len(slide.shapes)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
