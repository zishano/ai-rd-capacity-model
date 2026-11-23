"""Render one four-chart set per model, reusing the original chart drawing functions.

Run after trend_models.run, or use --method to redraw one saved projection.
Fixed half-lives and carrying capacities are conditional scenarios, not fitted facts.
"""
import argparse
from datetime import date
import html
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .. import monthly_research_usage as style
from ..observations import HERE, records, write_rows
from .models import fit_predict
from .run import END, HERE_NEW, KEYS, inputs
from .uncertainty import PRESET as UNCERTAINTY_PRESET, LABEL as UNCERTAINTY_LABEL, NOTE as UNCERTAINTY_NOTE

PRESETS = {
    'damped_holt_hl365': ('阻尼 Holt · 半衰期 365 天', '条件情景：趋势半衰期人为固定为 365 天，不代表历史已识别该参数'),
    'damped_holt': ('阻尼 Holt · 历史拟合', '阻尼由历史拟合；任务与输出触及 14 天下界，长期可能很快趋平'),
    'logistic_cap4x': ('Logistic · 条件上限', '条件情景：上限设为各序列历史最大值的 4 倍，尚无外部容量证据'),
    'gompertz_cap4x': ('Gompertz · 条件上限', '条件情景：上限设为各序列历史最大值的 4 倍，尚无外部容量证据'),
    'legacy_ols': ('原脚本 OLS · 线性参照', '保持原 OLS 斜率与锚点规则，作为持续绝对增量的参照'),
    UNCERTAINTY_PRESET: (UNCERTAINTY_LABEL, UNCERTAINTY_NOTE),
}
CONCURRENCY_LABELS = {
    'legacy_log_complement': '原双门槛模型', 'conditional_logistic': '条件 Logistic',
    'joint_logratio': '九档对数比', 'naive': '保持末值',
}


def team_prediction(days, values, future, method):
    h = [(d-days[-1]).days for d in future]
    if method == 'legacy_ols':
        return fit_predict(values, h, 'ols')
    if method.startswith('damped_holt_hl'):
        return fit_predict(values, h, 'damped_holt', half_life=int(method.split('hl')[-1]))
    if '_cap' in method:
        name, cap = method.split('_cap')
        return fit_predict(values, h, name, cap=float(cap[:-1])*max(values))
    return fit_predict(values, h, method)


def render(out, methods=None, concurrency_method='legacy_log_complement', show_intervals=True, show_sample_paths=True):
    out = Path(out)
    methods = list(PRESETS) if methods is None else methods
    if UNCERTAINTY_PRESET in methods and concurrency_method != 'legacy_log_complement':
        print('ensemble_uncertainty 固定使用原双门槛 + Bootstrap；--concurrency-method 仅作用于旧预设',flush=True)
    needs_legacy = any(m != UNCERTAINTY_PRESET for m in methods)
    data, bins = inputs()
    forecasts = records(out/'forecast.csv') if needs_legacy else []
    category_rows = records(out/'categories.csv') if needs_legacy else []
    concurrency_rows = records(out/'concurrency.csv') if needs_legacy else []
    team_rows = style.source_rows('observed_workdays_by_team.csv', None)
    exported, parameters = [], []
    root = out/'original_style'
    root.mkdir(parents=True,exist_ok=True)
    style.configure_fonts()

    def record(metric, method, series, points, cutoff):
        for day, value in points.items():
            exported.append(dict(metric=metric,method=method,series=series,date=day,
                                 value=float(value),status='observed' if day<=cutoff else 'forecast'))

    def save(fig, folder, filename, note):
        fig.text(.045,.018,note,fontsize=9,color='#455969')
        for ext in ('png','pdf'):
            fig.savefig(folder/f'{filename}.{ext}',dpi=160)
        plt.close(fig)

    for method in methods:
        title, note = PRESETS[method]
        folder = root/method
        folder.mkdir(exist_ok=True)
        if method == UNCERTAINTY_PRESET:
            from .uncertainty.export import export
            export(out, folder, show_intervals=show_intervals, show_sample_paths=show_sample_paths)
            continue
        selected = [r for r in forecasts if r['method']==method]
        if not selected:
            raise ValueError(f'No projections for {method}; run trend_models.run first')
        teams = {}
        floored_teams = []
        for key, _, _ in style.TEAMS:
            observed = {date.fromisoformat(r['date']):float(r[key]) for r in team_rows
                        if r[key] and r['date']<=style.CUTOFF.isoformat()}
            days = sorted(observed)
            subset = [r for r in selected if r['metric']=='workdays']
            future = [date.fromisoformat(r['date']) for r in subset]
            if key == 'Overall Research':
                predicted = np.array([float(r['value']) for r in subset])
                parameter = {'basis':'forecast.csv overall series, identical to model comparison'}
            else:
                predicted, parameter, _ = team_prediction(days,[observed[d] for d in days],future,method)
            if parameter.get('negative_forecasts_before_floor',0):
                floored_teams.append(key)
            teams[key] = observed | dict(zip(future,predicted))
            parameters.append(dict(method=method,series=key,parameters=json.dumps(parameter)))
            record('workdays',method,key,teams[key],days[-1])

        classified = {}
        for metric in ('tasks','output'):
            days, _, source = data[metric]
            components = {}
            for key in KEYS:
                observed = {day:float(row[key]) for day,row in zip(days,source)}
                rows = [r for r in category_rows if r['metric']==metric and r['method']==method
                        and r['composition_window']=='84' and r['category']==key]
                future = {date.fromisoformat(r['date']):float(r['value']) for r in rows}
                if method=='legacy_ols':
                    fitted = style.trend(observed,False)
                    if metric=='output':
                        future = {d:max(0.,observed[days[-1]]+fitted(d)-fitted(days[-1])) for d in future}
                    else:
                        future = {d:fitted(d) for d in future}
                components[key] = observed | future
                record(metric,method,key,components[key],days[-1])
            classified[metric] = components

        distribution = []
        for row in bins:
            v = np.array([float(row[f'bin_{i}']) for i in range(9)])
            distribution.append((date.fromisoformat(row['date']),v/v.sum()))
        for row in concurrency_rows:
            if row['method']==concurrency_method:
                distribution.append((date.fromisoformat(row['date']),[float(row[f'bin_{i}']) for i in range(9)]))
        for i, label in enumerate(style.BINS):
            record('concurrency',method,label,{d:v[i] for d,v in distribution},style.CUTOFF)

        # Original team colors, line styles, top legend and two-decimal endpoint labels.
        fig, ax = plt.subplots(figsize=(14,7.4))
        fig.subplots_adjust(left=.085,right=.92,top=.81,bottom=.20)
        fig.suptitle(style.TITLES[0],x=.055,y=.97,ha='left',fontsize=20,weight='bold')
        fig.text(.055,.90,f'{title}  |  每月 18 日 · 28 天窗口',fontsize=11)
        style.draw_workdays(ax,teams)
        ax.spines[['top','right']].set_visible(False)
        ax.set(xlim=(min(teams['Overall Research']),END),ylim=(0,None))
        style.monthly_ticks(ax)
        if floored_teams:
            ax.text(.01,.88,'部分团队负趋势触及零边界，见参数记录；不宜直接用于分组预算',
                    transform=ax.transAxes,fontsize=9,color='#9B3535')
        save(fig,folder,'monthly_workdays',note)

        # Original nine-band area chart, circle legend and endpoint share labels.
        fig, ax = plt.subplots(figsize=(14,5.8))
        fig.subplots_adjust(left=.105,right=.875,bottom=.23,top=.78)
        fig.suptitle('研究员的 Agent 平均日峰值并发分布',x=.04,y=.97,ha='left',fontsize=20)
        fig.text(.04,.895,f'独立模型：{CONCURRENCY_LABELS[concurrency_method]} · 每月 18 日 · 28 天窗口',fontsize=11)
        style.draw_concurrency(ax,distribution,standalone=True)
        style.monthly_ticks(ax)
        ax.spines[['top','right','left']].set_visible(False)
        ax.grid(axis='y',color='white',alpha=.25)
        save(fig,folder,'monthly_concurrency','并发模型独立于总量模型；趋势模型回测未超过保持末值，不代表已验证的四年预测')

        # Original 18 task bands and right-hand grouped labels with connector lines.
        fig, ax = plt.subplots(figsize=(14,7.4))
        fig.subplots_adjust(left=.085,right=.76,top=.81,bottom=.20)
        fig.suptitle(style.TITLES[2],x=.055,y=.97,ha='left',fontsize=20,weight='bold')
        fig.text(.055,.90,f'{title}  |  每月 18 日 · 28 天窗口',fontsize=11)
        style.draw_tasks(ax,classified['tasks'])
        ax.set_xlim(min(classified['tasks'][KEYS[0]]),END)
        ax.set_ylim(0,max(sum(v[d] for v in classified['tasks'].values()) for d in classified['tasks'][KEYS[0]])*1.1)
        ax.spines[['top','right']].set_visible(False)
        style.monthly_ticks(ax)
        save(fig,folder,'monthly_tasks',note+'；非线性情景采用历史末 84 日类别份额')

        # Original six-column legend, September palette and dark total outline.
        fig, ax = plt.subplots(figsize=(15.6,8.2))
        fig.subplots_adjust(left=.091,right=.975,top=.62,bottom=.19)
        fig.suptitle('研究人员正在以全新方式使用编码智能体',x=.045,y=.977,ha='left',fontsize=20,weight='bold')
        fig.text(.046,.905,f'{title}  |  每名研究员每日输出 Token · 14 天窗口',fontsize=12)
        style.draw_token_legend(fig.add_axes([.04,.66,.94,.21]))
        output = classified['output']
        days = list(output[KEYS[0]])
        style.draw_token_stack(ax,days,[list(output[k].values()) for k in KEYS],data['output'][0][-1])
        style.monthly_ticks(ax)
        save(fig,folder,'monthly_output_tokens',note+'；非线性情景采用历史末 84 日类别份额')

    # Separate files per selected model make individual redraws non-destructive.
    for method in methods:
        if method == UNCERTAINTY_PRESET:
            continue  # The adapter has exported the actual centers and interval provenance.
        write_rows(root/method/'chart_data.csv',[r for r in exported if r['method']==method])
        write_rows(root/method/'team_parameters.csv',[r for r in parameters if r['method']==method])
    sections = []
    for method,(title,note) in PRESETS.items():
        if not (root/method/'monthly_workdays.png').exists():
            continue
        pictures = ''.join(f'<a href="{method}/{name}.pdf"><img src="{method}/{name}.png" alt="{name}"></a>'
                           for name in ('monthly_workdays','monthly_concurrency','monthly_tasks','monthly_output_tokens'))
        sections.append(f'<section id="{method}"><h2>{html.escape(title)}</h2><p>{html.escape(note)}</p>{pictures}</section>')
    navigation=' · '.join(f'<a href="#{m}">{html.escape(t)}</a>' for m,(t,_) in PRESETS.items())
    (root/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>原风格 · 多模型外推</title>'
        '<style>body{font-family:sans-serif;max-width:1400px;margin:24px auto;color:#222}img{width:100%}'
        'nav{position:sticky;top:0;background:white;padding:16px}section{scroll-margin-top:70px}</style>'
        '<h1>同一绘图风格下比较增长假设</h1><p>原图值不变；每套图对应一个预测方案（单模型或多模型融合）。'
        '并发采用独立模型。所有曲线延伸至 2030-11-18；非线性不等于更准确。</p>'
        f'<nav>{navigation}</nav>'+''.join(sections),encoding='utf8')
    print('Original-style chart sets:',root,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=HERE_NEW/'results')
    parser.add_argument('--method',choices=['all',*PRESETS],default='all')
    parser.add_argument('--concurrency-method',choices=list(CONCURRENCY_LABELS),default='legacy_log_complement')
    parser.add_argument('--hide-intervals',action='store_true',help='Hide interval bands and bounds on the four ensemble charts; keep all interval data')
    parser.add_argument('--hide-sample-paths',action='store_true',help='Hide example simulation paths on ensemble charts; keep all prediction data')
    args=parser.parse_args()
    render(args.results,None if args.method=='all' else [args.method],args.concurrency_method,
           show_intervals=not args.hide_intervals,show_sample_paths=not args.hide_sample_paths)
