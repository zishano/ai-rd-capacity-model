"""Build the report figures and a deck with native charts and embedded Excel data."""
import argparse
import json
from calendar import monthrange
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from matplotlib import font_manager
from pptx import Presentation
from pptx.chart.data import XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_MARKER_STYLE, XL_TICK_MARK
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

from .observations import HERE, PARENT, records, series
from .trends import fit

INK = '193949'
COLORS = ['007C78','CD621E','345FB1','8657A1','566D39','946450','89949D']
MODEL_NAMES = ['全窗 OLS','近 56 日','近 84 日','中点分段','非负直线','有界对照']
NAMES = ['A 会话增多','B 会话延长','C 混合增长']


def curve(name,x,y,color,style='line'):
    return (name,list(x),list(y),color,style)


def panels(results,cfg):
    obs = series(PARENT/'observed_agent_workdays.csv','agent_workdays_per_researcher_day')
    ref = date.fromisoformat(cfg['reference_date'])
    years = cfg['years']
    cap = cfg['bounded_online_session_equivalents']*cfg['calendar_hours']/cfg['hours_per_reported_workday']
    methods = [fit(obs,k,cap) for k in cfg['models']]
    def month(d):
        return d.month+(d.day-1)/monthrange(d.year,d.month)[1]
    dates=[d for d,v in obs]
    history=[curve('公开图值',map(month,dates),[v for _,v in obs],COLORS[-1],'dots')]
    future=[]
    for i,(label,model) in enumerate(zip(MODEL_NAMES,methods)):
        window=dates[-56:] if model.method=='last56' else dates[-84:] if model.method=='last84' else dates
        history.append(curve(label,map(month,window),[model.predict(d) for d in window],COLORS[i]))
        plot_dates=[dates[-1]]+[date(y,m,1) for y in years for m in range(1,13)
                                 if dates[-1]<date(y,m,1)<ref.replace(year=years[-1])]+[ref.replace(year=years[-1])]
        def year_fraction(d):
            return d.year+(d-date(d.year,1,1)).days/(date(d.year+1,1,1)-date(d.year,1,1)).days
        future.append(curve(label,map(year_fraction,plot_dates),[model.predict(d) for d in plot_dates],COLORS[i]))
    history.append(curve('末次观测 10/18',[month(dates[-1])]*2,[0,6],INK,'dash'))
    annual=[r for r in records(results/'workload.csv') if r['method']=='ols']
    def paths(field,scale=1):
        return [curve(label,years,[float(r[field])*scale for r in annual if r['workload_scenario']==name],COLORS[i])
                for i,(label,name) in enumerate(zip(NAMES,'ABC'))]
    def panel(title,lines,unit='年份',xmin=2026,xmax=2030,step=1,log=False):
        return dict(title=title,lines=lines,xlabel=unit,xmin=xmin,xmax=xmax,step=step,log=log)
    t=[panel('历史拟合  ·  工作日/研究员日',history,'2026 年月份',5,11),
       panel('长期外推  ·  工作日/研究员日',future,'年份',2026,2030.99)]
    token=[panel(k,paths(f,scale)) for k,f,scale in [
        ('累计输入  ·  百万 Token/主 Agent 日','input_tokens_day',1e-6),
        ('生成输出  ·  千 Token/主 Agent 日','output_tokens_day',.001),
        ('缓存命中输入  ·  百万 Token/主 Agent 日','cached_input_tokens_day',1e-6),
        ('未缓存输入  ·  千 Token/主 Agent 日','uncached_input_tokens_day',.001)]]
    cc=paths('average_inference_concurrency')
    cc.append(curve('串行峰值',years,[1]*len(years),INK,'dash'))
    context=[]
    for i in (0,2):
        label='A/B' if i==0 else 'C'
        for f,style in [('p50','line'),('p90','dash')]:
            _,x,y,c,_=paths('context_request_'+f,.001)[i]
            context.append(curve(label+' '+f.upper(),x,y,c,style))
    sessions=[panel('等效会话数  ·  场/研究员日',paths('session_count_per_day')),
              panel('平均会话时长  ·  分钟/场',paths('mean_session_duration_hours',60)),
              panel('单主 Agent 请求在途均值与串行峰值  ·  对数轴',cc,log=True),
              panel('请求上下文 P50 / P90  ·  千 Token',context)]
    return [t,token,sessions]


TITLES=['AI 研发 Agent 的累计使用强度','相同的使用时长增长，三种单 Agent Token 路径','会话、请求并发与上下文的条件需求']
NOTES=['最后观测为 2026-10-18。169 个日度图值均为 28 天移动平均；外推曲线没有概率覆盖含义。',
       '23 条实测轨迹平均每题输入 82.0 万、输出 8,614 Token；每年 11/18 取样，2030 总时长倍率 8.67。',
       '会话数量按基准任务跨度折算，A/B 的上下文曲线重合。请求在途包含网络和等待，串行峰值为场景约束。']
FILES=['usage','tokens','sessions']


def figures(groups,out):
    font=Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    if font.exists():
        font_manager.fontManager.addfont(font)
        plt.rcParams['font.family']=font_manager.FontProperties(fname=font).get_name()
    for i,group in enumerate(groups):
        fig,axes=plt.subplots(1 if i==0 else 2,2,figsize=(12,5.3 if i==0 else 8.3))
        fig.subplots_adjust(top=.80 if i==0 else .88,bottom=.19 if i==0 else .12,hspace=.62,wspace=.27)
        fig.suptitle(TITLES[i],x=.06,ha='left',y=.975,fontsize=20,color='#'+INK)
        for ax,p in zip(axes.flat,group):
            for name,x,y,c,style in p['lines']:
                ax.plot(x,y,label=name,color='#'+c,linestyle={'line':'-','dots':'None','dash':'--'}[style],
                        marker='.' if style=='dots' else None,markersize=3,lw=1.8)
            ax.set(title=p['title'],xlabel=p['xlabel'],xlim=(p['xmin'],p['xmax']))
            ax.xaxis.set_major_locator(mtick.MultipleLocator(p['step']))
            ax.ticklabel_format(style='plain',axis='x',useOffset=False)
            if p['log']:
                ax.set_yscale('log')
                ax.set_ylim(.001,1.4)
            ax.grid(axis='y',alpha=.22)
            ax.spines[['top','right']].set_visible(False)
            ax.legend(fontsize=8,ncol=2,frameon=False)
        fig.text(.06,.025,NOTES[i],fontsize=10,color='#405C69')
        svg = out/(FILES[i]+'.svg')
        fig.savefig(svg, bbox_inches='tight', metadata={'Date': None})
        svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
        plt.close(fig)


def textbox(slide,x,y,w,h,text,size,color=INK,bold=False):
    box=slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    p=box.text_frame.paragraphs[0]
    p.text=text
    p.font.size=Pt(size)
    p.font.name='Microsoft YaHei'
    p.font.bold=bold
    p.font.color.rgb=RGBColor.from_string(color)
    return box


def ppt_chart(slide,p,x,y,w,h):
    textbox(slide,x,y,w,.34,p['title'],13,bold=True)
    data=XyChartData()
    for label,xs,ys,_,_ in p['lines']:
        series_data=data.add_series(label)
        for xx,yy in zip(xs,ys):
            series_data.add_data_point(xx,yy)
    chart=slide.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER_LINES_NO_MARKERS,
        Inches(x), Inches(y+.36), Inches(w), Inches(h-.36), data).chart
    chart.has_legend=True
    from pptx.enum.chart import XL_LEGEND_POSITION
    chart.legend.position=XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout=False
    chart.legend.font.size=Pt(9)
    for ser,(_,_,_,c,style) in zip(chart.series,p['lines']):
        ser.format.line.color.rgb=RGBColor.from_string(c)
        ser.format.line.width=Pt(1.8)
        if style=='dash':
            ser.format.line.dash_style=MSO_LINE_DASH_STYLE.DASH
        if style=='dots':
            ser.format.line.fill.background()
            ser.marker.style=XL_MARKER_STYLE.CIRCLE
            ser.marker.size=3
            ser.marker.format.fill.solid()
            ser.marker.format.fill.fore_color.rgb=RGBColor.from_string(c)
            ser.marker.format.line.color.rgb=RGBColor.from_string(c)
    xaxis=chart.category_axis
    xaxis.minimum_scale=p['xmin']
    xaxis.maximum_scale=p['xmax']
    xaxis.major_unit=p['step']
    xaxis.tick_labels.number_format='0'
    for axis in (xaxis,chart.value_axis):
        axis.tick_labels.font.size=Pt(9)
        axis.major_tick_mark=XL_TICK_MARK.NONE
    if p['log']:
        axis=chart.value_axis
        axis.minimum_scale=.001
        axis.maximum_scale=1.4
        base=OxmlElement('c:logBase')
        base.set('val','10')
        axis._element.scaling.insert(0,base)


def deck(groups,out):
    prs=Presentation()
    prs.slide_width,prs.slide_height=Inches(13.33), Inches(7.5)
    for i,group in enumerate(groups):
        slide=prs.slides.add_slide(prs.slide_layouts[6])
        textbox(slide,.42,.20,12.4,.65,TITLES[i],26,bold=True)
        height=5.65 if len(group)==2 else 2.84
        for j,p in enumerate(group):
            ppt_chart(slide,p,.45+(j%2)*6.25,1+(j//2)*2.92,6.05,height)
        textbox(slide,.45,6.95,12.45,.48,NOTES[i],12)
    slide=prs.slides.add_slide(prs.slide_layouts[6])
    textbox(slide,.45,.3,12.3,.7,'从单题公开计量到 30T 推理输入',28,bold=True)
    for i,(title,body) in enumerate([
        ('观测','OpenAI 总体时长覆盖 169 天。API 牌价另作趋势对照；Anthropic 工具链、自动化与平台并发用于检查口径。'),
        ('分解','研究员累计小时＝会话数 × 平均时长。主 Agent 日计一场焦点会话；其余会话与下游子 Agent 不再加到焦点 Token。'),
        ('接口','每个任务保留输入、输出、缓存率、上下文和串行峰值。逐题调用原有 calculate，再按日任务权重汇总设备工作量。'),
        ('不确定性','2030 全窗 OLS 为每研究员日 56.96 个八小时 Agent 日。时长跨 Agent 可累加；会话长度、分工与真实推理并发仍待生产遥测。')]):
        textbox(slide,.5,1.35+i*1.35,2.0,.42,title,19,'007C78',True)
        textbox(slide,2.35,1.25+i*1.35,10.1,.9,body,18)
    prs.save(out/'未来AI推理基础设施需求.pptx')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,default=HERE/'results')
    parser.add_argument('--output',type=Path,default=HERE/'figures')
    parser.add_argument('--config',type=Path,default=HERE/'settings.json')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    groups=panels(args.results,json.loads(args.config.read_text()))
    figures(groups,args.output)
    deck(groups,args.output)
