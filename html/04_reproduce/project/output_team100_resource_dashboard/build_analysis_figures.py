"""Export the dashboard's 2026 baseline and annual projections as editable charts.

Reads only the regenerated dashboard data. PNG/SVG/PDF provide a dense overview;
PowerPoint keeps the chart series and all labels editable, with embedded data.
"""
import json
import os
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

if Path('/tmp/ai_rd_report_deps').exists():
    sys.path.insert(0, '/tmp/ai_rd_report_deps')
os.environ.setdefault('MPLCONFIGDIR', '/tmp/team100_dashboard_mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager, ticker
import numpy as np
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
FONT = 'Noto Sans CJK SC'
INK, MUTED, BLUE, TEAL, ORANGE, PURPLE = '203B4B', '57707B', '326EA8', '228C8E', 'D57B44', '7963A4'
COLORS = ['#'+c for c in (TEAL, ORANGE, BLUE, PURPLE)]
YEARS = [2026, 2027, 2028, 2029, 2030]
YEAR_LABELS = ['2026基线', '2027', '2028', '2029', '2030']
STEM = 'team-resource-analysis-2026-2030'
FOOT = [
    '2026 OpenAI公开统计×100：输出截至8/15（官方14日滑动日均值，不再二次平滑）；时长、任务截至10/18（官方28日均值）。',
    '2027–2030：各年11/18的OLS预测日强度，输出沿用14日口径。输入、缓存与FLOPs：252条编码代理轨迹 + 合成30T模型的条件估算。',
    '2026输入/算力是将当年负载代入30T的估算。Agent平均活动当量=累计小时÷24，不能解释为团队峰值或LLM/GPU并发。',
]


def main():
    data = json.loads((HERE/'dashboard_data.json').read_text())
    rows = [next(r for r in data['rows'] if r['year'] == y and r['scenario'] == 'C') for y in YEARS]
    abc = [next(r for r in data['rows'] if r['year'] == 2030 and r['scenario'] == s) for s in 'ABC']
    assert rows[0]['date'] is None
    vals = lambda key, scale=1: np.array([r[key]/scale for r in rows])
    metrics = [('累计输入', 'input_tokens_per_team_day'), ('生成输出', 'output_tokens_per_team_day'),
               ('Agent时长', 'agent_hours_per_team_day'), ('任务发起', 'task_starts_per_team_day'),
               ('理论计算量', 'eflop_per_team_day'), ('未缓存输入', 'uncached_input_tokens_per_team_day')]
    growth = np.array([vals(k)/rows[0][k] for _, k in metrics])
    font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family': FONT, 'font.size': 11, 'axes.unicode_minus': False,
                         'text.color':'#'+INK, 'axes.labelcolor':'#'+MUTED,
                         'xtick.color':'#'+MUTED, 'ytick.color':'#'+MUTED,
                         'axes.spines.top':False, 'axes.spines.right':False,
                         'axes.edgecolor':'#C8D4DB', 'pdf.fonttype':42, 'svg.fonttype':'none'})
    fig = plt.figure(figsize=(20, 16), facecolor='white')
    gs = fig.add_gridspec(3, 2, left=.06, right=.97, top=.79, bottom=.135, hspace=.62, wspace=.19)
    fig.text(.055, .963, '百人研发团队：2026公开基线 → 2030资源需求', fontsize=27, weight='bold')
    fig.text(.055, .927, '100名研究员  ·  C：混合增长  ·  合成30T Top-8 MoE  ·  自然日日量', fontsize=14, color='#'+MUTED)
    top = [('2030累计输入', f"{rows[-1]['input_tokens_per_team_day']/1e8:,.2f} 亿Token"),
           ('2030输出', f"{rows[-1]['output_tokens_per_team_day']/1e8:,.2f} 亿Token"),
           ('2030累计Agent时长', f"{rows[-1]['agent_hours_per_team_day']:,.0f} 小时"),
           ('2030平均活动当量', f"{rows[-1]['mean_online_agent_equivalents']:,.0f}"),
           ('2030理论计算量', f"{rows[-1]['eflop_per_team_day']:,.2f} EFLOP")]
    for i, (label, value) in enumerate(top):
        fig.text(.055+i*.187, .876, label, fontsize=12, color='#'+MUTED)
        fig.text(.055+i*.187, .848, value, fontsize=20, weight='bold')

    def setup(ax, title, unit):
        ax.set_title(title, loc='left', fontsize=15, weight='bold', pad=18)
        ax.set_ylabel(unit)
        ax.set_xticks(YEARS, YEAR_LABELS)
        ax.grid(axis='y', alpha=.23)
        ax.set_axisbelow(True)
        ax.set_ylim(bottom=0)

    def point_labels(ax, values, decimals=1):
        for x, v in zip(YEARS, values):
            ax.annotate(f'{v:,.{decimals}f}', (x, v), xytext=(0, 7), textcoords='offset points', ha='center', fontsize=10)

    ax = fig.add_subplot(gs[0, 0])
    setup(ax, '01  输入与输出：分开标尺，保留量级差异', '累计输入 / 亿Token/日')
    ax.bar(YEARS, vals('cached_input_tokens_per_team_day',1e8), .55, color=COLORS[0], label='缓存输入')
    ax.bar(YEARS, vals('uncached_input_tokens_per_team_day',1e8), .55,
           bottom=vals('cached_input_tokens_per_team_day',1e8), color=COLORS[1], label='未缓存输入')
    point_labels(ax, vals('input_tokens_per_team_day',1e8))
    ax.set_ylim(0, 680)
    ax2 = ax.twinx()
    ax2.plot(YEARS, vals('output_tokens_per_team_day',1e8), '-o', color=COLORS[2], lw=2, label='输出（右轴）')
    ax2.set_ylabel('输出 / 亿Token/日', color=COLORS[2]); ax2.set_ylim(0, 6)
    for x, v in zip(YEARS, vals('output_tokens_per_team_day',1e8)):
        ax2.annotate(f'{v:.2f}', (x, v), xytext=(0,-17), textcoords='offset points', ha='center', fontsize=10, color=COLORS[2], bbox={'facecolor':'white','edgecolor':'none','alpha':.9,'pad':1})
    ax.legend(loc='upper left', frameon=False, fontsize=10)
    ax2.legend(loc='upper right', frameon=False, fontsize=10)

    ax = fig.add_subplot(gs[0, 1])
    setup(ax, '02  Agent活动：时长与任务发起', '累计Agent小时 / 万小时/日')
    ax.plot(YEARS, vals('agent_hours_per_team_day',1e4), '-o', color=COLORS[0], lw=2, label='累计Agent时长')
    point_labels(ax, vals('agent_hours_per_team_day',1e4),2); ax.set_ylim(0,5.8)
    ax2 = ax.twinx()
    ax2.plot(YEARS, vals('task_starts_per_team_day',1e3), '--s', color=COLORS[3], lw=2, label='任务发起（右轴）')
    ax2.set_ylabel('任务发起 / 千项/日'); ax2.set_ylim(0,22)
    ax.legend(loc='upper left', frameon=False, fontsize=10); ax2.legend(loc='upper right', frameon=False, fontsize=10)
    ax.text(.27,.07,'平均活动当量：190 → 1,899（累计小时÷24）',transform=ax.transAxes, fontsize=11)

    ax = fig.add_subplot(gs[1, 0])
    setup(ax, '03  理论计算量：Prefill与Decode构成', 'EFLOP / 日')
    ax.bar(YEARS, vals('prefill_eflop_per_team_day'), .55, color=COLORS[1], label='Prefill')
    ax.bar(YEARS, vals('decode_eflop_per_team_day'), .55, bottom=vals('prefill_eflop_per_team_day'), color=COLORS[2], label='Decode')
    point_labels(ax, vals('eflop_per_team_day')); ax.set_ylim(0,630)
    ax.legend(loc='upper left', ncol=2, frameon=False, fontsize=10)

    ax = fig.add_subplot(gs[1, 1])
    ax.set_title('04  2030情景对比：输入、缓存与计算量', loc='left', fontsize=15, weight='bold', pad=18)
    x = np.arange(3)
    ax.bar(x, [r['cached_input_tokens_per_team_day']/1e8 for r in abc], .5, color=COLORS[0], label='缓存输入')
    ax.bar(x, [r['uncached_input_tokens_per_team_day']/1e8 for r in abc], .5, bottom=[r['cached_input_tokens_per_team_day']/1e8 for r in abc], color=COLORS[1], label='未缓存输入')
    ax.set_xticks(x, ['A 增加会话','B 延长会话','C 混合增长']); ax.set_ylabel('亿Token / 日'); ax.set_ylim(0,730)
    ax.grid(axis='y', alpha=.23); ax.set_axisbelow(True)
    for i,r in enumerate(abc):
        ax.text(i,r['input_tokens_per_team_day']/1e8+15, f"{r['input_tokens_per_team_day']/1e8:.2f} 亿\n缓存 {r['prefix_cache_hit_rate']:.2%}\n{r['eflop_per_team_day']:.2f} EFLOP",ha='center',fontsize=11)
    ax.legend(frameon=False,loc='upper left',ncol=2,fontsize=10)

    ax = fig.add_subplot(gs[2, 0])
    setup(ax, '05  负载增长：2026实际基线与未来趋势', '任务发起 / 项/日')
    ax.bar(YEARS, vals('task_starts_per_team_day'), .55, color=[COLORS[0]]+[COLORS[2]]*4)
    point_labels(ax, vals('task_starts_per_team_day'),0); ax.set_ylim(0,21000)
    ax.text(.02,.92,'2026：官方人均统计 × 100  |  2027–2030：预测', transform=ax.transAxes, fontsize=10)

    ax = fig.add_subplot(gs[2, 1])
    ax.set_title('06  增长倍数热力图：以2026各指标为1×', loc='left', fontsize=15, weight='bold', pad=18)
    ax.imshow(growth, cmap='Blues', vmin=0, vmax=float(growth.max()), aspect='auto')
    ax.set_xticks(range(5), YEAR_LABELS); ax.set_yticks(range(6), [m[0] for m in metrics])
    ax.tick_params(length=0)
    for i in range(6):
        for j in range(5):
            ax.text(j,i,f'{growth[i,j]:.2f}×',ha='center',va='center',color='white' if growth[i,j]>growth.max()*.55 else '#'+INK,fontsize=12)
    for edge in ax.spines.values(): edge.set_visible(False)
    for i,line in enumerate(FOOT): fig.text(.055,.079-i*.024,line,fontsize=10,color='#'+MUTED)
    for suffix in ['png','svg','pdf']: fig.savefig(HERE/f'{STEM}.{suffix}',dpi=170,facecolor='white')
    plt.close(fig)
    build_ppt(rows, abc, growth, metrics, data['category_mix'])


def build_ppt(rows, abc, growth, metrics, category_mix):
    prs = Presentation(); prs.slide_width=Inches(16); prs.slide_height=Inches(9)
    def text(slide, msg, x,y,w,h, size=13, color=INK, bold=False):
        box=slide.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h))
        box.text_frame.word_wrap=True
        box.text_frame.margin_left=box.text_frame.margin_right=0
        box.text_frame.margin_top=0
        for i,line in enumerate(str(msg).split('\n')):
            p=box.text_frame.paragraphs[0] if i==0 else box.text_frame.add_paragraph()
            p.text=line; p.font.name=FONT; p.font.size=Pt(size); p.font.bold=bold; p.font.color.rgb=RGBColor.from_string(color)
        return box
    def slide(title):
        s=prs.slides.add_slide(prs.slide_layouts[6]); text(s,title,.45,.22,15,.5,25,bold=True)
        text(s,'100名研究员 · C混合增长 · 合成30T Top-8 MoE · 自然日日量',.45,.85,15,.3,12,MUTED)
        for i,line in enumerate(FOOT): text(s,line,.45,7.91+i*.26,15,.25,9,MUTED)
        return s
    def chart(s,title,categories,series,x,y,w,h,kind=XL_CHART_TYPE.LINE_MARKERS):
        text(s,title,x,y,w,.3,15,bold=True)
        cd=CategoryChartData(); cd.categories=categories
        for name,values,color in series: cd.add_series(name,[float(v) for v in values])
        ch=s.shapes.add_chart(kind,Inches(x),Inches(y+.37),Inches(w),Inches(h-.37),cd).chart
        ch.font.name=FONT; ch.font.size=Pt(10)
        ch.has_legend=len(series)>1
        if ch.has_legend: ch.legend.position=XL_LEGEND_POSITION.BOTTOM; ch.legend.include_in_layout=False
        ch.category_axis.tick_labels.font.name=FONT; ch.category_axis.tick_labels.font.size=Pt(10)
        ch.value_axis.minimum_scale=0; ch.value_axis.tick_labels.font.size=Pt(10)
        ch.value_axis.has_major_gridlines=True
        for serie,(_,_,color) in zip(ch.series,series):
            serie.format.fill.solid(); serie.format.fill.fore_color.rgb=RGBColor.from_string(color)
            serie.format.line.color.rgb=RGBColor.from_string(color)
        return ch
    v=lambda key,scale=1:[r[key]/scale for r in rows]
    s=slide('百人团队资源需求：2026公开基线与年度预测')
    chart(s,'累计输入 / 亿Token/日',YEAR_LABELS,[('缓存输入',v('cached_input_tokens_per_team_day',1e8),TEAL),('未缓存输入',v('uncached_input_tokens_per_team_day',1e8),ORANGE)],.45,1.4,7.25,2.8,XL_CHART_TYPE.COLUMN_STACKED)
    chart(s,'生成输出 / 亿Token/日',YEAR_LABELS,[('输出',v('output_tokens_per_team_day',1e8),BLUE)],8.05,1.4,7.5,2.8)
    chart(s,'累计Agent时长 / 万小时/日',YEAR_LABELS,[('累计时长',v('agent_hours_per_team_day',1e4),TEAL)],.45,4.65,7.25,2.8)
    chart(s,'平均在线Agent活动当量 / 累计小时÷24',YEAR_LABELS,[('平均活动当量',v('mean_online_agent_equivalents'),PURPLE)],8.05,4.65,7.5,2.8)
    s=slide('计算构成、任务规模与增长倍数')
    chart(s,'理论计算量 / EFLOP/日',YEAR_LABELS,[('Prefill',v('prefill_eflop_per_team_day'),ORANGE),('Decode',v('decode_eflop_per_team_day'),BLUE)],.45,1.4,7.25,2.8,XL_CHART_TYPE.COLUMN_STACKED)
    chart(s,'2030：A增加会话 / B延长会话 / C混合增长', ['A','B','C'], [('Prefill / EFLOP', [r['prefill_eflop_per_team_day'] for r in abc],ORANGE),('Decode / EFLOP',[r['decode_eflop_per_team_day'] for r in abc],BLUE)],8.05,1.4,7.5,2.8,XL_CHART_TYPE.COLUMN_STACKED)
    chart(s,'任务发起 / 项/日',YEAR_LABELS,[('任务发起',v('task_starts_per_team_day'),TEAL)],.45,4.65,7.25,2.8,XL_CHART_TYPE.COLUMN_CLUSTERED)
    text(s,'增长倍数热力图：2026各指标 = 1×',8.05,4.65,7.5,.3,15,bold=True)
    maxv=float(growth.max())
    for j,year in enumerate(YEAR_LABELS): text(s,year,9.7+j*1.13,5.06,1.1,.28,11)
    for i,(label,_) in enumerate(metrics):
        text(s,label,8.05,5.42+i*.32,1.55,.29,11)
        for j in range(5):
            val=float(growth[i,j]); rgba=plt.get_cmap('Blues')(val/maxv)
            shape=s.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(9.65+j*1.13),Inches(5.4+i*.32),Inches(1.1),Inches(.3))
            shape.fill.solid(); shape.fill.fore_color.rgb=RGBColor(*(round(c*255) for c in rgba[:3])); shape.line.fill.background()
            text(s,f'{val:.2f}×',9.91+j*1.13,5.42+i*.32,.82,.26,11,'FFFFFF' if val>maxv*.55 else INK)
    s=slide('2030：研发活动构成与缓存输入')
    categories=[r for r in category_mix if r['year']==2030 and r['scenario']=='C']
    ch=chart(s,'18类研发活动：占全部输出Token的比例 / %',
             [r['category_label'] for r in categories],
             [('输出Token占比',[r['share']*100 for r in categories],TEAL)],
             .45,1.4,10.3,6.0,XL_CHART_TYPE.BAR_CLUSTERED)
    ch.category_axis.tick_labels.font.size=Pt(9)
    chart(s,'2030输入构成 / 亿Token/日',['A','B','C'],
          [('缓存输入',[r['cached_input_tokens_per_team_day']/1e8 for r in abc],TEAL),
           ('未缓存输入',[r['uncached_input_tokens_per_team_day']/1e8 for r in abc],ORANGE)],
          11.0,1.4,4.55,3.6,XL_CHART_TYPE.COLUMN_STACKED)
    text(s,'A：增加会话\nB：延长会话\nC：混合增长',11.15,5.3,4.2,1.0,14)
    text(s,'缓存命中率\nA/B：93.86%\nC：96.13%',11.15,6.45,4.2,1.0,13,MUTED)
    dest=HERE/f'{STEM}.pptx'; prs.save(dest)
    ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        names=z.namelist(); charts=[n for n in names if n.startswith('ppt/charts/chart') and n.endswith('.xml')]
        workbooks=[n for n in names if n.startswith('ppt/embeddings/') and n.endswith('.xlsx')]
        assert len(charts)==len(workbooks)==9
        for name in names:
            if name.endswith('.xml'): ET.fromstring(z.read(name))
        for i in [1,2,3]:
            root=ET.fromstring(z.read(f'ppt/slides/slide{i}.xml'))
            assert not root.findall('.//p:pic',ns)
            for tr in root.findall('.//a:xfrm',ns):
                off,ext=tr.find('a:off',ns),tr.find('a:ext',ns)
                if off is not None and ext is not None:
                    assert int(off.attrib['x'])+int(ext.attrib['cx'])<=16*914400
                    assert int(off.attrib['y'])+int(ext.attrib['cy'])<=9*914400
    result={'status':'passed','annual_rows':5,'scenario':'C','png_svg_pdf_panels':6,
            'ppt_slides':3,'ppt_native_charts':9,'embedded_workbooks':9,'heatmap_native_cells':30,
            'ppt_validation':'OOXML, native charts, workbooks and bounds; not Office rendering',
            'files':[f'{STEM}.{ext}' for ext in ['png','svg','pdf','pptx']]}
    (HERE/'analysis_figure_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__': main()
