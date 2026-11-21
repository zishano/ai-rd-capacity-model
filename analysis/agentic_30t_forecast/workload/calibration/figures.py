"""Render the calibrated evidence, distributions and demand as PNG and editable PPTX."""
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import MaxNLocator
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.util import Inches, Pt

from ..observations import HERE, records

COLORS = ['197B76','3964AA','B66128']
FONT = 'Noto Sans CJK SC'


def specs(result):
    obs = [r for r in records(HERE/'observed_openai_research_usage.csv')
           if r['date'].endswith('-18') and r['date']<='2026-10-18']
    work = [(r['date'][5:7],float(r['workdays'])*8) for r in obs if r['workdays']]
    starts = [(r['date'][5:7],sum(float(v) for k,v in r.items() if k.startswith('task'))) for r in obs if r['task1_1']]
    stats = {r['metric']:r for r in records(result/'distributions.csv') if r['scope']=='all_complete'}
    qs = ['p10','p50','p90','p95']
    def quant(key, label, scale=1):
        return label,[float(stats[key][q])/scale for q in qs]
    d = [r for r in records(result/'researcher_day.csv') if r['date']=='2030-11-18']
    modes = ['维持末值','半速线性','全速线性']
    return [
        ('OpenAI 研究员时长与任务发起率', '2026 年 · 每月 18 日的 28 天窗口图值 · 两图各用自身分母及单位', [
            ('累计 Agent 小时 / 研究员日',[x for x,y in work],[('公开工作日 × 8',[y for x,y in work])]),
            ('研发任务发起 / 研究员日',[x for x,y in starts],[('公开分类估计',[y for x,y in starts])])],
         '横轴为月份。时长含符合条件的子 Agent，任务按交互窗口中的用户发起行为计数。来源：OpenAI 2026-11-18。','line'),
        ('编码代理的单任务分布','mini-SWE-agent × Kimi K2.5 high · 全量筛选后的 252 条完整轨迹 · 按题统计',[
            ('累计输入与缓存（万 Token）',qs,[quant('input','输入',1e4),quant('cached_input','其中缓存',1e4)]),
            ('输出与峰值上下文（千 Token）',qs,[quant('output','输出',1e3),quant('peak_request_context','峰值上下文',1e3)]),
            ('模型调用次数 / 题',qs,[quant('calls','调用次数')])],
         '缓存属于输入。上下文取题内最长请求的输入与输出之和。P95 为样本分位，原始联合记录用于第二层。','bar'),
        ('2030 年每研究员日的 Token 需求','三种任务发起率情景 · 费率与 GPU 型号均不参与换算',[
            ('发起任务 / 研究员日',modes,[('任务发起数',[float(r['initiated_tasks']) for r in d])]),
            ('条件输出（百万 Token / 日）',modes,[(name,[float(r[key])/1e6 for r in d]) for key,name in
                [('output_low_window','低强度窗口'),('output_if_pooled_intensity_transfers','四窗合并'),('output_high_window','高强度窗口')]])],
         '固定 2026 年跨报告的输出/发起强度。低、高为观察到的窗口端点；全研发输入与缓存尚无同口径计量。','bar')]


def render(result, dest):
    dest.mkdir(parents=True,exist_ok=True)
    font = Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    if font.exists():
        plt.rcParams['font.family']=font_manager.FontProperties(fname=font).get_name()
    prs=Presentation()
    prs.slide_width,prs.slide_height=Inches(13.33), Inches(7.5)
    def caption(slide, text, y, size):
        shape=slide.shapes.add_textbox(Inches(.48), Inches(y), Inches(12.45), Inches(.55))
        p=shape.text_frame.paragraphs[0]
        run=p.add_run();run.text=text;run.font.name=FONT;run.font.size=Pt(size)
        run.font.color.rgb=RGBColor.from_string('253D4A')
    for i,(title,subtitle,panels,note,kind) in enumerate(specs(result),1):
        slide=prs.slides.add_slide(prs.slide_layouts[6])
        caption(slide,title,.2,26);caption(slide,subtitle,.86,14);caption(slide,note,6.91,11)
        fig,axes=plt.subplots(1,len(panels),figsize=(14,5.8),squeeze=False)
        fig.subplots_adjust(left=.065,right=.985,top=.73,bottom=.23,wspace=.32)
        fig.text(.045,.94,title,size=22,color='#253D4A')
        fig.text(.045,.86,subtitle,size=12);fig.text(.045,.05,note,size=10)
        for j,(label,categories,series) in enumerate(panels):
            ax=axes[0,j]; ax.set_title(label,fontsize=13,loc='left')
            data=CategoryChartData();data.categories=categories
            for n,(name,values) in enumerate(series):
                data.add_series(name,values)
                color='#'+COLORS[n]
                if kind=='line':
                    ax.plot(range(len(categories)),values,color=color,marker='o',label=name)
                else:
                    width=.76/len(series)
                    ax.bar([k+(n-(len(series)-1)/2)*width for k in range(len(categories))],values,width,color=color,label=name)
            ax.set_xticks(range(len(categories)),categories);ax.set_ylim(bottom=0)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5));ax.spines[['right','top']].set_visible(False)
            ax.legend(loc='upper left',fontsize=8,frameon=False);ax.grid(axis='y',alpha=.17)
            w=12.35/len(panels)
            chart=slide.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS if kind=='line' else XL_CHART_TYPE.COLUMN_CLUSTERED,
                                         Inches(.44+j*w), Inches(1.65), Inches(w-.12), Inches(4.92), data).chart
            chart.has_title=True;chart.chart_title.text_frame.text=label
            chart.chart_title.text_frame.paragraphs[0].font.size=Pt(14)
            chart.has_legend=True;chart.legend.position=XL_LEGEND_POSITION.BOTTOM;chart.legend.font.size=Pt(10)
            chart.value_axis.minimum_scale=0
            for k,serie in enumerate(chart.series):
                color=RGBColor.from_string(COLORS[k])
                if kind=='line':serie.format.line.color.rgb=color
                else:
                    serie.format.fill.solid();serie.format.fill.fore_color.rgb=color
        fig.savefig(dest/f'calibration_{i}.png',dpi=155)
        plt.close(fig)
    prs.save(dest/'task_calibration.pptx')


if __name__=='__main__':
    render(HERE/'results/calibrated',HERE/'figures/calibration')
