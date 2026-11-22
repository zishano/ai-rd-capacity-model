"""Keep the original category/style encodings and add clearly separated uncertainty."""
from datetime import date
import json

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter
import numpy as np

from ... import monthly_research_usage as style
from ...observations import HERE, records, write_rows
from ..run import KEYS, END
from .probabilistic import forecast,legacy_concurrency_bands
from .run import summary,SEED,ROOT
from . import LABEL


def render(out,data,bins,caches,bin_cache,draws):
    style.configure_fonts()
    dest=out/'figures';dest.mkdir(exist_ok=True)
    scenarios=records(out/'scenarios.csv')
    exported=[];team_parameters=[]
    def save(fig,name,note):
        fig.text(.045,.026,note,fontsize=9,color='#455969')
        for ext in ('png','pdf'):fig.savefig(dest/f'{name}.{ext}',dpi=155)
        plt.close(fig)

    def overlay(ax,metric):
        c=caches[metric];d=c['dates'];s=c['summary']
        ax.fill_between(d,s['lower95'],s['upper95'],color='#7F91AC',alpha=.18,zorder=4)
        ax.fill_between(d,s['lower80'],s['upper80'],color='#647C9D',alpha=.20,zorder=4)
        ax.plot(d,s['upper95'],lw=.7,color='#647C9D',ls=':',zorder=5)
        ax.plot(d,s['lower95'],lw=.7,color='#647C9D',ls=':',zorder=5)
        # One fixed-index draw from each mixture component; never chosen by its shape.
        example_indices=(0,draws+min(100,draws-1),2*draws+min(500,draws-1))
        for i in example_indices:
            ax.plot(d,c['paths'][i],color='#555',lw=.65,alpha=.45,zorder=5)
        sc=[r for r in scenarios if r['metric']==metric]
        ax.plot(d,[float(r['plateau']) for r in sc],color='#333',ls='--',lw=1.2,zorder=6)
        ax.plot(d,[float(r['contraction10']) for r in sc],color='#8B3B32',ls='-.',lw=1.4,zorder=6)
        ax.set_ylim(0,max(float(max(s['upper95'])),float(c['paths'][list(example_indices)].max()),float(ax.get_ylim()[1]))*1.05)
        return [Patch(color='#7F91AC',alpha=.18,label='名义 95% 模型分位带'),
                Patch(color='#647C9D',alpha=.38,label='名义 80% 模型分位带'),
                Line2D([],[],color='#555',lw=.8,label='3 条固定抽样路径'),
                Line2D([],[],color='#333',ls='--',label='2028 起停滞（假设）'),
                Line2D([],[],color='#8B3B32',ls='-.',label='2028 起年降 10%（假设）')]

    def record(metric,series,points,cutoff):
        for d,v in points.items():
            exported.append(dict(metric=metric,series=series,date=d,value=float(v),
                                 status='observed' if d<=cutoff else 'forecast'))

    future=caches['workdays']['dates']
    team_rows=records(HERE/'observed_workdays_by_team.csv');teams={}
    for key,label,color in style.TEAMS:
        observed={date.fromisoformat(r['date']):float(r[key]) for r in team_rows
                  if r[key] and r['date']<=str(style.CUTOFF)}
        days=sorted(observed)
        if key=='Overall Research':
            median=caches['workdays']['summary']['median']
        else:
            paths,p=forecast([observed[d] for d in days],28,[(d-days[-1]).days for d in future],
                             'ensemble',draws=draws,seed=SEED)
            median=np.median(paths,axis=0)
            team_parameters.append(dict(team=key,parameters=json.dumps(p)))
        teams[key]=observed|dict(zip(future,median))
        record('workdays',key,teams[key],days[-1])
    fig,ax=plt.subplots(figsize=(14,8.2))
    fig.subplots_adjust(left=.085,right=.92,top=.81,bottom=.25)
    fig.suptitle(style.TITLES[0],x=.055,y=.97,ha='left',fontsize=20,weight='bold')
    fig.text(.055,.91,f'{LABEL} · 中位数 · 阴影对应总体 · 每月 18 日',fontsize=11)
    style.draw_workdays(ax,teams)
    handles=overlay(ax,'workdays')
    # Team endpoint medians can nearly coincide; keep both two-decimal labels legible.
    for annotation in list(ax.texts):
        if annotation.get_text().endswith('×'):
            annotation.remove()
    previous=-1.
    ymax=ax.get_ylim()[1]
    for value,color in sorted((float(teams[key][future[-1]]),color) for key,_,color in style.TEAMS):
        position=max(value/ymax,previous+.035)
        ax.annotate(f'{value:.2f}×',(future[-1],value),xytext=(1.008,position),
                    textcoords='axes fraction',va='center',fontsize=10,color=color,
                    arrowprops=dict(arrowstyle='-',color=color,lw=.6),annotation_clip=False)
        previous=position
    style.monthly_ticks(ax);ax.spines[['top','right']].set_visible(False)
    ax.set_xlim(min(teams['Overall Research']),END)
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.075),ncol=5,frameon=False,fontsize=9)
    save(fig,'monthly_workdays','统计带不包含全部结构变化；回落线是独立条件情景，没有赋予发生概率。模型未通过四年覆盖率验证。')

    for metric in ('tasks','output'):
        days,y,source=data[metric];c=caches[metric]
        matrix=np.array([[float(r[k]) for k in KEYS] for r in source[-84:]])
        shares=matrix.sum(0)/matrix.sum()
        parts={}
        for k,share in zip(KEYS,shares):
            parts[k]={d:float(r[k]) for d,r in zip(days,source)}|dict(zip(c['dates'],c['summary']['median']*share))
            record(metric,k,parts[k],days[-1])
        if metric=='tasks':
            fig,ax=plt.subplots(figsize=(14,8.2))
            fig.subplots_adjust(left=.085,right=.76,top=.81,bottom=.25)
            fig.suptitle(style.TITLES[2],x=.055,y=.97,ha='left',fontsize=20,weight='bold')
            fig.text(.055,.91,f'{LABEL} · 中位数 · 28 日窗口 · 末 84 日类别份额',fontsize=11)
            style.draw_tasks(ax,parts)
        else:
            fig,ax=plt.subplots(figsize=(15.6,9.2))
            fig.subplots_adjust(left=.091,right=.975,top=.62,bottom=.23)
            fig.suptitle('研究人员正在以全新方式使用编码智能体',x=.045,y=.977,ha='left',fontsize=20,weight='bold')
            fig.text(.046,.91,f'{LABEL} · 中位数 · 每研究员日输出 Token · 14 日窗口',fontsize=12)
            style.draw_token_legend(fig.add_axes([.04,.66,.94,.21]))
            style.draw_token_stack(ax,list(parts[KEYS[0]]),[list(parts[k].values()) for k in KEYS],days[-1])
        handles=overlay(ax,metric)
        ax.set_xlim(days[0],END);style.monthly_ticks(ax);ax.spines[['top','right']].set_visible(False)
        fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.075),ncol=5,frameon=False,fontsize=9)
        if metric=='output':
            bt=[r for r in records(out/'backtest.csv') if r['metric']=='output' and r['method']=='ensemble'
                and r['horizon']=='28' and r['scoring']=='new_underlying_days']
            coverage=np.mean([float(r['coverage95']) for r in bt])
            ax.text(.015,.89,f'注意：28 天回测名义 95% 带的覆盖率仅 {coverage:.1%}，尚未校准',
                    transform=ax.transAxes,fontsize=10,color='#9B3535')
        save(fig,'monthly_tasks' if metric=='tasks' else 'monthly_output_tokens',
             '灰色带是总量的条件区间，不能解释为各类别独立区间；未识别未来类别迁移。未来原始日波动也不等于图中的平滑指标波动。')

    histdays=[date.fromisoformat(r['date']) for r in bins]
    observed=np.array([[float(r[f'bin_{i}']) for i in range(9)] for r in bins]);observed/=observed.sum(1,keepdims=True)
    for method,(future,paths,center) in bin_cache.items():
        # Match the original single-panel canvas and margins. Uncertainty gets a separate file.
        fig,ax=plt.subplots(figsize=(14,5.8))
        fig.subplots_adjust(left=.105,right=.875,bottom=.17,top=.78)
        title='无漂移构成基线' if method=='composition_rw' else '阻尼构成趋势 · 半衰期365天'
        fig.suptitle('研究员的 Agent 平均日峰值并发分布',x=.04,y=.97,ha='left',fontsize=20)
        fig.text(.04,.895,f'每月 18 日 · 28 天窗口    |    {title}',fontsize=11)
        style.draw_concurrency(ax,list(zip(histdays,observed))+list(zip(future,center)),standalone=True)
        style.monthly_ticks(ax)
        ax.spines[['top','right','left']].set_visible(False)
        ax.grid(axis='y',color='white',alpha=.25)
        filename='concurrency_no_drift' if method=='composition_rw' else 'concurrency_damped'
        save(fig,filename,
             '主图展示合计 100% 的中心构成；名义 80%/95% 区间见独立配套图。'
             +('无漂移中心保持末期份额，不代表未来不会波动。' if method=='composition_rw' else '趋势半衰期为条件假设。'))

        # Keep thresholds in separate panels so their translucent bands do not obscure each other.
        fig,axes=plt.subplots(2,1,figsize=(14,7.4),sharex=True)
        fig.subplots_adjust(left=.085,right=.95,top=.82,bottom=.20,hspace=.28)
        fig.suptitle('并发门槛占比的不确定性 · 配套图',x=.055,y=.97,ha='left',fontsize=20)
        fig.text(.055,.91,title+' · 浅色为名义95%带，深色为名义80%带',fontsize=11)
        for lower,(start,color) in zip(axes,((4,'#316BC2'),(6,'#774FCB'))):
            s=summary(paths[:,:,start:].sum(2))
            lower.plot(histdays,observed[:,start:].sum(1),color=color,lw=1)
            lower.plot(future,center[:,start:].sum(1),color=color,label=f'≥{4 if start==4 else 16} 占比中心')
            lower.fill_between(future,s['lower95'],s['upper95'],color=color,alpha=.09)
            lower.fill_between(future,s['lower80'],s['upper80'],color=color,alpha=.2)
            lower.set_ylim(0,1);lower.yaxis.set_major_formatter(PercentFormatter(1))
            lower.set_ylabel('研究员占比');lower.legend(frameon=False,fontsize=9,loc='upper left')
            lower.axvline(histdays[-1],color='#777',ls=':')
            lower.spines[['top','right']].set_visible(False)
        axes[-1].set_xlim(histdays[0],END);style.monthly_ticks(axes[-1])
        save(fig,'concurrency_threshold_intervals' if method=='composition_rw' else 'concurrency_damped_threshold_intervals',
             '模型条件分位带不保证四年覆盖率。使用者总人数与 [64,∞) 档内部均值未知；各档边际分位数不能相加。')

    # The main figure retains the user's original forecasting algorithm and one-panel layout.
    future=bin_cache['composition_rw'][0]
    legacy_paths,legacy_center,metadata=legacy_concurrency_bands(histdays,observed,future,draws=draws,seed=SEED)
    fig,ax=plt.subplots(figsize=(14,5.8))
    fig.subplots_adjust(left=.105,right=.875,bottom=.17,top=.78)
    fig.suptitle('研究员的 Agent 平均日峰值并发分布',x=.04,y=.97,ha='left',fontsize=20)
    fig.text(.04,.895,f'{LABEL} | 原双门槛 + Bootstrap · 每月 18 日 · 28 天窗口',fontsize=11)
    style.draw_concurrency(ax,list(zip(histdays,observed))+list(zip(future,legacy_center)),standalone=True)
    band_rows=[]
    for start,color in ((4,'#174779'),(6,'#4E267A')):
        boundary=legacy_paths[:,:,:start].sum(2)
        q=np.quantile(boundary,[.025,.1,.9,.975],axis=0)
        line=legacy_center[:,:start].sum(1)
        ax.fill_between(future,q[1],q[2],color=color,alpha=.18,zorder=4)
        ax.plot(future,line,color=color,lw=1,zorder=5)
        ax.plot(future,q[0],color=color,lw=.8,ls=':',zorder=5)
        ax.plot(future,q[3],color=color,lw=.8,ls=':',zorder=5)
        for i,d in enumerate(future):
            band_rows.append(dict(date=d,threshold=4 if start==4 else 16,center_share=float(1-line[i]),
                   boundary_center=float(line[i]),boundary_p025=float(q[0,i]),boundary_p10=float(q[1,i]),
                   boundary_p90=float(q[2,i]),boundary_p975=float(q[3,i])))
    style.monthly_ticks(ax);ax.spines[['top','right','left']].set_visible(False)
    ax.grid(axis='y',color='white',alpha=.25)
    save(fig,'monthly_concurrency',
         '≥4、≥16 分界：实线为原趋势，阴影为80%重采样范围，点线为95%范围；仅反映趋势拟合不确定性，未校准。')
    write_rows(out/'main_concurrency.csv',[dict(date=d,method='legacy_log_complement',
               **{f'bin_{i}':float(v) for i,v in enumerate(row)}) for d,row in zip(future,legacy_center)])
    write_rows(out/'main_concurrency_bands.csv',band_rows)
    (out/'main_concurrency_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')

    # Per-bin marginal intervals are separate from the coherent stacked center.
    future,paths,center=bin_cache['composition_rw'];s=summary(paths)
    fig,axes=plt.subplots(3,3,figsize=(14,10),sharex=True,sharey=True)
    for i,ax in enumerate(axes.flat):
        ax.plot(future,center[:,i],color=style.COLORS[i],lw=2)
        ax.fill_between(future,s['lower95'][:,i],s['upper95'][:,i],color='#647C9D',alpha=.15)
        ax.fill_between(future,s['lower80'][:,i],s['upper80'][:,i],color='#647C9D',alpha=.3)
        ax.set_title(style.BINS[i]);ax.set_ylim(0,1);ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.spines[['top','right']].set_visible(False)
    fig.suptitle('九档并发的边际条件区间 · 不能将九个上界或下界相加')
    fig.tight_layout(rect=(0,.07,1,.95));save(fig,'concurrency_bin_intervals','联合路径始终满足概率约束；边际区间是各档分别取分位数，通常不合计为 100%。')
    write_rows(out/'chart_data.csv',exported)
    write_rows(out/'team_parameters.csv',team_parameters)
    def gallery(names):
        return ''.join(f'<h2>{name}</h2><a href="figures/{name}.pdf"><img src="figures/{name}.png"></a>' for name in names)
    links=gallery(('monthly_workdays','monthly_concurrency','monthly_tasks','monthly_output_tokens'))
    links+='<details><summary>实验算法诊断图（非四张主图）</summary>'+gallery((
        'concurrency_no_drift','concurrency_damped','concurrency_threshold_intervals',
        'concurrency_damped_threshold_intervals','concurrency_bin_intervals'))+'</details>'
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Agent 预测与不确定性</title>'
       '<style>body{font-family:sans-serif;margin:30px auto;max-width:1500px}img{width:100%}</style>'
       '<h1>Agent 工作负载：趋势、条件区间与回落情景</h1><p>没有把情景范围当作置信区间；'
       '预测对象是公开平滑指标，不是原始日流量。四年覆盖率无法用当前历史验证。</p>'+links,encoding='utf8')


def redraw(out):
    """Redraw saved distributions without rerunning selection or backtests."""
    from ..run import inputs
    saved=np.load(out/'predictive_paths.npz')
    caches={}
    for metric in ('workdays','tasks','output'):
        paths=saved[metric+'_paths']
        caches[metric]=dict(dates=[date.fromisoformat(str(d)) for d in saved[metric+'_dates']],
                            paths=paths,summary=summary(paths))
    concurrency_rows=records(out/'concurrency.csv');bin_cache={}
    for method in ('composition_rw','composition_damped'):
        rows=[r for r in concurrency_rows if r['method']==method]
        future=sorted({r['date'] for r in rows})
        lookup={(r['date'],int(r['bin'])):float(r['center']) for r in rows}
        centers=np.array([[lookup[d,i] for i in range(9)] for d in future])
        bin_cache[method]=([date.fromisoformat(d) for d in future],saved[method+'_paths'],centers)
    data,bins=inputs()
    render(out,data,bins,caches,bin_cache,json.loads((out/'manifest.json').read_text())['draws_per_component'])


if __name__=='__main__':
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=ROOT/'results')
    redraw(parser.parse_args().results)
