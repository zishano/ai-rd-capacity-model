"""Forecast comparisons and native editable PowerPoint charts."""
from datetime import date
from collections import defaultdict
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import dates as mdates
from matplotlib.ticker import PercentFormatter
from matplotlib.patches import Patch
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.util import Inches, Pt
from ..observations import records
from ..monthly_research_usage import configure_fonts, COLORS, TASK_GROUPS

LABELS={'naive':'保持末值','ols':'OLS','piecewise':'单变化点线性','damped_holt':'阻尼 Holt','auto_arima':'小范围 AutoARIMA',
        'legacy_ols':'旧脚本 OLS',
        'conditional_logistic':'条件 Logistic','joint_logratio':'九档对数比','legacy_log_complement':'原门槛模型'}
PALETTE=['#999999','#397BCD','#E39636','#2D9464','#9561B4','#C34D69','#618FA4','#444444']


def render(out,data,bins):
    configure_fonts()
    dest=out/'figures'
    dest.mkdir(exist_ok=True)
    prs=Presentation()
    prs.slide_width,prs.slide_height=Inches(13.33), Inches(7.5)

    def slide(title,categories,series,kind=XL_CHART_TYPE.LINE,note=''):
        s=prs.slides.add_slide(prs.slide_layouts[6])
        box=s.shapes.add_textbox(Inches(.4),Inches(.18),Inches(12.4),Inches(.65))
        box.text_frame.text=title
        box.text_frame.paragraphs[0].font.size=Pt(24)
        values=CategoryChartData()
        values.categories=categories
        for name,v in series:
            values.add_series(name,v)
        chart=s.shapes.add_chart(kind,Inches(.5),Inches(1.0),Inches(12.1),Inches(5.5),values).chart
        chart.has_legend=True
        chart.legend.position=XL_LEGEND_POSITION.BOTTOM
        chart.legend.font.size=Pt(10)
        box=s.shapes.add_textbox(Inches(.5),Inches(6.65),Inches(12.2),Inches(.65))
        box.text_frame.text=note
        box.text_frame.paragraphs[0].font.size=Pt(11)

    forecasts=records(out/'forecast.csv')
    units={'workdays':'Agent 工作日 / 研究员日','tasks':'发起任务 / 研究员日','output':'万输出 Token / 研究员日'}
    for number,metric in enumerate(data,1):
        days,y,_=data[metric]
        scale=1e4 if metric=='output' else 1
        methods=['naive','ols','piecewise','damped_holt','auto_arima','logistic_cap4x','gompertz_cap4x','legacy_ols']
        series=[]
        future=None
        fig,ax=plt.subplots(figsize=(13,6))
        ax.plot(days,y/scale,color='black',label='公开历史图值',lw=1.8)
        for m,color in zip(methods,PALETTE):
            r=[x for x in forecasts if x['metric']==metric and x['method']==m]
            future=[date.fromisoformat(x['date']) for x in r]
            values=[float(x['value'])/scale for x in r]
            label=LABELS.get(m,m.replace('_cap4x','（上限=历史最大值×4）'))
            ax.plot(future,values,color=color,label=label,lw=1.6,ls='--' if m=='legacy_ols' else '-')
            series.append((label,values))
        ax.axvline(days[-1],ls=':',color='#444')
        ax.set_ylabel(units[metric])
        ax.set_title(f'{units[metric]}的长期路径取决于增长机制',loc='left',fontsize=16)
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.spines[['right','top']].set_visible(False)
        ax.set_ylim(bottom=0)
        ax.legend(fontsize=8,frameon=False)
        fig.text(.08,.025,'来源 OpenAI · 竖线为观测截止 · 饱和上限为敏感性假设 · 模型间跨度为情景差异',fontsize=9)
        fig.tight_layout(rect=(0,.06,1,1))
        for ext in ('png','pdf'):fig.savefig(dest/f'{number}_{metric}.{ext}',dpi=160)
        plt.close(fig)
        observed_months=[i for i,d in enumerate(days) if d.day==18]
        dates=[str(days[i]) for i in observed_months]+[str(d) for d in future]
        native=[('公开历史',[float(y[i])/scale for i in observed_months]+[None]*len(future))]
        native.extend((label,[None]*len(observed_months)+v) for label,v in series)
        slide(f'{units[metric]}的增长机制对照',dates,native,
              note=f'公开观测截至 {days[-1]}；包含阻尼、线性与条件上限。单位 {units[metric]}。')

    r=records(out/'concurrency.csv')
    fig,axes=plt.subplots(2,2,figsize=(14,8),sharex=True,sharey=True)
    histdays=[date.fromisoformat(x['date']) for x in bins]
    history=np.array([[float(x[f'bin_{i}']) for x in bins] for i in range(9)])
    history=history/history.sum(axis=0)
    bin_labels=['0','(0,1)','[1,2)','[2,4)','[4,8)','[8,16)','[16,32)','[32,64)','[64,∞)']
    for ax,m in zip(axes.flat,('naive','legacy_log_complement','conditional_logistic','joint_logratio')):
        subset=[x for x in r if x['method']==m]
        future=[date.fromisoformat(x['date']) for x in subset]
        v=np.array([[float(x[f'bin_{i}']) for x in subset] for i in range(9)])
        allvalues=np.column_stack((history,v))
        ax.stackplot(histdays+future,*allvalues,colors=COLORS)
        ax.axvline(histdays[-1],color='#333',ls=':')
        ax.set_title(LABELS[m]);ax.set_ylim(0,1)
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.set_ylabel('研究员占比')
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        slide('并发档位分布 · '+LABELS[m],[str(d) for d in future],
              [(bin_labels[i],v[i].tolist()) for i in range(9)],XL_CHART_TYPE.AREA_STACKED,
              '九档顺序 0、(0,1)、[1,2)、[2,4)、[4,8)、[8,16)、[16,32)、[32,64)、[64,∞)。')
    fig.suptitle('九档并发份额对迁移假设敏感')
    fig.legend(handles=[Patch(color=c,label=b) for c,b in zip(COLORS,bin_labels)],
               loc='lower center',ncol=9,frameon=False)
    fig.tight_layout(rect=(0,.05,1,.96))
    for ext in ('png','pdf'):fig.savefig(dest/f'4_concurrency.{ext}',dpi=160)
    plt.close(fig)

    bt=records(out/'backtest.csv')
    fig,axes=plt.subplots(1,3,figsize=(15,5))
    for ax,metric in zip(axes,data):
        names=list(LABELS)[:5]
        heights=[]
        for m in names:
            values=[float(r['mae']) for r in bt if r['metric']==metric and r['method']==m
                    and r['horizon']=='28' and r['scoring']=='rolling_target']
            heights.append(float(np.mean(values)))
        ax.bar(range(5),heights,color=PALETTE[:5])
        ax.set_xticks(range(5),[LABELS[n] for n in names],rotation=35,ha='right')
        ax.set_title(metric+' · MAE')
        slide('28 天回测 · '+metric,[LABELS[n] for n in names],[('平均 MAE',heights)],
              XL_CHART_TYPE.COLUMN_CLUSTERED,'公开滚动均值目标；训练与目标底层日期部分重叠，另见非重叠窗口评分。')
    fig.suptitle('短期误差用于筛选候选，长期情景另行评价')
    fig.tight_layout()
    for ext in ('png','pdf'):fig.savefig(dest/f'5_backtest.{ext}',dpi=160)
    plt.close(fig)

    sens=records(out/'sensitivity.csv')
    fig,axes=plt.subplots(1,3,figsize=(15,5))
    for ax,metric in zip(axes,data):
        selected=[r for r in sens if r['metric']==metric and r['half_life']]
        x=[float(r['half_life']) for r in selected]; y=[float(r['value2030']) for r in selected]
        ax.plot(x,y,'o-',color='#2D9464');ax.set_title(metric);ax.set_xlabel('趋势半衰期（天）')
        slide('阻尼假设影响 2030 端点 · '+metric,[str(int(v)) for v in x],[('2030 预测',y)],
              note='半衰期固定为 30、90、365、730 天重新拟合。均为敏感性条件。')
    fig.suptitle('同一段历史可对应不同的趋势衰减速度')
    fig.tight_layout()
    for ext in ('png','pdf'):fig.savefig(dest/f'6_sensitivity.{ext}',dpi=160)
    plt.close(fig)

    category_rows=records(out/'categories.csv')
    colors=[c for _,items in TASK_GROUPS for _,c in items]
    for metric in ('tasks','output'):
        fig,axes=plt.subplots(2,2,figsize=(14,9),sharex=True,sharey=True)
        for ax,method in zip(axes.flat,('ols','piecewise','damped_holt','auto_arima')):
            subset=[r for r in category_rows if r['metric']==metric and r['method']==method and r['composition_window']=='84']
            dates=sorted({r['date'] for r in subset});keys=list(dict.fromkeys(r['category'] for r in subset))
            lookup={(r['category'],r['date']):float(r['value']) for r in subset}
            scale=1e4 if metric=='output' else 1
            ax.stackplot([date.fromisoformat(d) for d in dates],*[[lookup[k,d]/scale for d in dates] for k in keys],colors=colors)
            ax.set_ylabel(units[metric])
            ax.set_title(LABELS[method]);ax.xaxis.set_major_locator(mdates.YearLocator());ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        fig.suptitle(metric+' · 同类别配色的总量模型对照（84 日构成）')
        fig.legend(handles=[Patch(color=c,label=label) for c,label in
                   zip(colors,[label for _,items in TASK_GROUPS for label,_ in items])],
                   loc='lower center',ncol=3,frameon=False,fontsize=8)
        fig.tight_layout(rect=(0,.18,1,.96))
        fig.savefig(dest/f'{metric}_category_comparison.png',dpi=160)
        plt.close(fig)
    prs.save(dest/'trend_comparison.pptx')
