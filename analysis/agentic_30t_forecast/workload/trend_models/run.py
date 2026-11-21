"""Run independent trend experiments. No source snapshots or existing results are overwritten."""
import argparse
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.special import expit, logit, softmax

from ..observations import HERE, PARENT, records, write_rows
from ..calibration.daily_tables import task_mix_weights
from ..adapter import task_input
from ..monthly_research_usage import trend
from .models import METHODS, fit_predict

HERE_NEW = Path(__file__).resolve().parent
END = date(2030,11,18)
KEYS = [f'task{g}_{i}' for g,n in enumerate((3,2,2,3,4,4),1) for i in range(1,n+1)]


def inputs():
    source = records(HERE/'observed_openai_research_usage.csv')
    output = records(HERE/'calibration/observed_output_tokens.csv')
    data = {}
    for name, rows, field in [('workdays',source,'workdays'),('tasks',source,'task1_1'),('output',output,'task1_1')]:
        subset = [r for r in rows if r[field] and r['date'] <= '2026-10-18']
        days = [date.fromisoformat(r['date']) for r in subset]
        values = [float(r[field]) if name=='workdays' else sum(float(r[k]) for k in KEYS) for r in subset]
        assert len(days)==(days[-1]-days[0]).days+1
        data[name] = (days, np.array(values), subset)
    bins = [r for r in source if r['bin_0'] and r['date'] <= '2026-10-18']
    return data, bins


def dates_after(last):
    return [date(y,m,18) for y in range(last.year,2031) for m in range(1,13) if last<date(y,m,18)<=END]


def evaluate(data, out):
    detail, params = [], []
    for name,(days,y,_) in data.items():
        # Non-overlap applies to the complete target window, not to the sample index.
        window = 14 if name=='output' else 28
        for fraction in (.6,.7,.8):
            n = int(len(y)*fraction)
            for method in METHODS:
                available = [h for h in (14,28,56) if n+h<=len(y)]
                if not available:
                    continue
                horizons = np.arange(1,max(available)+1)
                estimates, parameters, interval = fit_predict(y[:n],horizons,method)
                params.append(dict(metric=name, origin=str(days[n-1]), method=method, parameters=json.dumps(parameters)))
                for h in available:
                    actual, estimate = y[n:n+h], estimates[:h]
                    for mode,start in [('rolling_target',0),('new_underlying_days',window-1)]:
                        if start>=h:
                            continue
                        truth, pred = actual[start:], estimate[start:]
                        error = pred-truth
                        denom = np.sum(np.abs(truth))
                        scale = np.mean(np.abs(np.diff(y[:n])))
                        coverage = None if interval is None else float(np.mean(
                            (truth>=interval[start:h,0]) & (truth<=interval[start:h,1])))
                        detail.append(dict(metric=name,method=method,origin=days[n-1],horizon=h,
                                           scoring=mode,first_lead=start+1,n=len(truth),
                                           mae=float(np.mean(abs(error))),rmse=float(np.sqrt(np.mean(error**2))),
                                           wape=float(np.sum(abs(error))/denom) if denom else None,
                                           mase=float(np.mean(abs(error))/scale) if scale else None,
                                           gaussian_95_coverage=coverage,
                                           gaussian_95_width=None if interval is None else float(np.mean(interval[start:h,1]-interval[start:h,0]))))
    write_rows(out/'backtest.csv',detail)
    write_rows(out/'backtest_parameters.csv',params)
    return detail


def projections(data,out):
    rows, parameters, sensitivities, categories = [], [], [], []
    for name,(days,y,source) in data.items():
        future = dates_after(days[-1])
        h = [(d-days[-1]).days for d in future]
        fit_future = sorted(set(future + ([d-timedelta(days=14) for d in future
                            if d-timedelta(days=14)>days[-1]] if name=='output' else [])))
        fit_h = [(d-days[-1]).days for d in fit_future]
        specs = [(m,None) for m in METHODS]
        specs.append(('legacy_ols',None))
        specs += [(f'damped_holt_hl{half_life}',None) for half_life in (90,365,730)]
        specs += [(m,k*max(y)) for m in ('logistic','gompertz') for k in (2,4,8)]
        for method,cap in specs:
            label = method if cap is None else f'{method}_cap{cap/max(y):.0f}x'
            if method == 'legacy_ols':
                if name == 'output':
                    predicted = np.zeros(len(fit_future))
                    for key in KEYS:
                        observed = {d:float(r[key]) for d,r in zip(days,source)}
                        fitted = trend(observed,False)
                        predicted += [max(0.,observed[days[-1]]+fitted(d)-fitted(days[-1])) for d in fit_future]
                else:
                    fitted = trend(dict(zip(days,y)),False)
                    predicted = np.array([fitted(d) for d in fit_future])
                parameter = {'basis':'original monthly_research_usage.trend',
                             'anchor':'last observed category values' if name=='output' else 'fitted level'}
                interval = None
            elif method.startswith('damped_holt_hl'):
                predicted, parameter, interval = fit_predict(y,fit_h,'damped_holt',
                                      half_life=int(method.split('hl')[-1]))
                parameter['basis'] = 'fixed half-life conditional scenario, not selected by backtest'
            else:
                predicted, parameter, interval = fit_predict(y,fit_h,method,cap)
            all_values = dict(zip(days,y)) | dict(zip(fit_future,predicted))
            indices = [fit_future.index(d) for d in future]
            predicted = predicted[indices]
            if interval is not None:
                interval = interval[indices]
            parameters.append(dict(metric=name,method=label,origin=days[-1],parameters=json.dumps(parameter)))
            for i,(day,value) in enumerate(zip(future,predicted)):
                rows.append(dict(metric=name,date=day,method=label,value=float(value),
                                 output_tokens_28d=(float(value+all_values[day-timedelta(days=14)])/2
                                                    if name=='output' else None),
                                 lower95=None if interval is None else float(interval[i,0]),
                                 upper95=None if interval is None else float(interval[i,1]),
                                 interval_basis='Gaussian ARIMA conditional on fitted parameters' if interval is not None else 'not estimated'))
            if name!='workdays':
                for length in (28,84):
                    matrix = np.array([[float(r[k]) for k in KEYS] for r in source[-length:]])
                    shares = matrix.sum(axis=0)/matrix.sum()
                    for day,value in zip(future,predicted):
                        for k,share in zip(KEYS,shares):
                            categories.append(dict(metric=name,date=day,method=label,composition_window=length,
                                                   category=k,share=float(share),value=float(value*share)))
        for length in (84,len(y)):
            for method in ('ols','piecewise','damped_holt'):
                v,p,_ = fit_predict(y[-length:],[(END-days[-1]).days],method)
                sensitivities.append(dict(metric=name,method=method,fit_days=length,half_life=None,value2030=float(v[0])))
        for half_life in (30,90,365,730):
            v,p,_=fit_predict(y,[(END-days[-1]).days],'damped_holt',half_life=half_life)
            sensitivities.append(dict(metric=name,method='damped_holt',fit_days=len(y),half_life=half_life,value2030=float(v[0])))
        # Bottom-up OLS is an explicit competitor to total-first forecasting.
        if name!='workdays':
            for k in KEYS:
                v,_,_=fit_predict([float(r[k]) for r in source],h,'ols')
                for d,value in zip(future,v):
                    categories.append(dict(metric=name,date=d,method='bottom_up_ols',composition_window=0,
                                           category=k,share=None,value=float(value)))
    write_rows(out/'forecast.csv',rows)
    write_rows(out/'parameters.csv',parameters)
    write_rows(out/'sensitivity.csv',sensitivities)
    write_rows(out/'categories.csv',categories)
    return rows


def bin_predict(days,values,future,method):
    x=np.array([(d-days[0]).days for d in days],dtype=float)
    z=np.array([(d-days[0]).days for d in future],dtype=float)
    if method=='naive':
        return np.tile(values[-1],(len(future),1))
    def line(y):
        return np.polyval(np.polyfit(x,y,1),z)
    p=values[:,4:].sum(axis=1)
    q=values[:,6:].sum(axis=1)/p
    if method=='joint_logratio':
        # Half of the published .1 percentage-point resolution, sensitivity documented.
        logits=np.log(np.maximum(values,.0005))
        predicted=softmax(np.column_stack([line(logits[:,i]) for i in range(9)]),axis=1)
        return predicted
    if method=='conditional_logistic':
        a=expit(line(logit(np.clip(p,.0005,.9995))))
        b=a*expit(line(logit(np.clip(q,.0005,.9995))))
    else:
        a=1-np.exp(line(np.log1p(-p)))
        b=1-np.exp(line(np.log1p(-values[:,6:].sum(axis=1))))
        if np.any((b>a)|(a>1)|(b<0)):
            raise ValueError('Legacy threshold forecasts violate probability constraints')
    groups=[values[-1,:4],values[-1,4:6],values[-1,6:]]
    mass=np.column_stack((1-a,a-b,b))
    return np.column_stack([mass[:,i]*v/group.sum() for i,group in enumerate(groups) for v in group])


def concurrency(bins,out):
    days=[date.fromisoformat(r['date']) for r in bins]
    values=np.array([[float(r[f'bin_{i}']) for i in range(9)] for r in bins])
    values=values/values.sum(axis=1,keepdims=True)
    methods=('naive','legacy_log_complement','conditional_logistic','joint_logratio')
    forecast, checks = [], []
    for method in methods:
        future=dates_after(days[-1])
        pred=bin_predict(days,values,future,method)
        assert np.all(pred>=0) and np.allclose(pred.sum(axis=1),1)
        for d,row in zip(future,pred):
            forecast.append(dict(date=d,method=method,**{f'bin_{i}':float(v) for i,v in enumerate(row)}))
        for fraction in (.6,.7,.8):
            n=int(len(days)*fraction)
            for h in (14,28,56):
                indices=[i for i in range(n,len(days)) if 0<(days[i]-days[n-1]).days<=h]
                if not indices or (days[-1]-days[n-1]).days<h:
                    continue
                predicted=bin_predict(days[:n],values[:n],[days[i] for i in indices],method)
                observed=values[indices]
                checks.append(dict(method=method,origin=days[n-1],horizon=h,
                                   average_bin_mae_pp=float(np.mean(abs(predicted-observed))*100),
                                   threshold4_mae_pp=float(np.mean(abs(predicted[:,4:].sum(1)-observed[:,4:].sum(1)))*100),
                                   threshold16_mae_pp=float(np.mean(abs(predicted[:,6:].sum(1)-observed[:,6:].sum(1)))*100),
                                   total_variation=float(np.mean(abs(predicted-observed).sum(1)/2))))
    write_rows(out/'concurrency.csv',forecast)
    write_rows(out/'concurrency_backtest.csv',checks)


def workload(rows,out):
    tasks=[r for r in records(HERE/'calibration/public_tasks.csv') if r['complete']=='1']
    jobs, summary=[],[]
    by_key={(r['metric'],str(r['date']),r['method']):r['value'] for r in rows}
    aligned={(str(r['date']),r['method']):r['output_tokens_28d'] for r in rows if r['metric']=='output'}
    for method in METHODS:
        for year in range(2026,2031):
            day=f'{year}-11-18'
            output=aligned[day,method]
            for scenario,tail in [('A',0.),('B',0.),('C',.5)]:
                weights=task_mix_weights(tasks,tail)
                factor=output/sum(w*int(t['completion']) for w,t in zip(weights,tasks))
                total={k:sum(factor*w*int(t[k]) for w,t in zip(weights,tasks)) for k in ('prompt','completion','cache_read')}
                summary.append(dict(date=day,method=method,scenario=scenario,scope='researcher_calendar_day',
                                    output_window_days=28,output_tokens_14d=by_key['output',day,method],
                                    workdays=by_key['workdays',day,method],
                                    agent_hours=8*by_key['workdays',day,method],
                                    average_agent_equivalents=by_key['workdays',day,method]/3,
                                    initiated_tasks=by_key['tasks',day,method],
                                    coding_task_equivalents=sum(factor*w for w in weights),
                                    input_tokens=total['prompt'],output_tokens=total['completion'],
                                    cached_tokens=total['cache_read'],uncached_tokens=total['prompt']-total['cache_read']))
                for t,w in zip(tasks,weights):
                    jobs.append(dict(date=day,method=method,scenario=scenario,instance=t['instance'],
                                     tasks_per_researcher_day=factor*w,workload=task_input(t,1)))
    write_rows(out/'workload.csv',summary)
    (out/'inference_inputs.json').write_text(json.dumps(jobs,ensure_ascii=False,indent=2)+'\n')


def run(out):
    out.mkdir(parents=True,exist_ok=True)
    data,bins=inputs()
    audit=[]
    for metric,(days,y,_) in data.items():
        audit.append(dict(metric=metric,start=str(days[0]),end=str(days[-1]),points=len(days),
                          window=14 if metric=='output' else 28,missing=0))
    audit.append(dict(metric='concurrency',start=bins[0]['date'],end=bins[-1]['date'],points=len(bins),
                      window=28,missing=7))
    (out/'audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    print('Running rolling-origin evaluation',flush=True)
    evaluate(data,out)
    print('Fitting final projections and sensitivities',flush=True)
    rows=projections(data,out)
    concurrency(bins,out)
    workload(rows,out)
    from .visualize import render
    render(out,data,bins)
    from .original_style import render as render_original_style
    render_original_style(out)
    import importlib.metadata
    source_paths=[HERE/'observed_openai_research_usage.csv',HERE/'calibration/observed_output_tokens.csv',
                  HERE/'calibration/public_tasks.csv',HERE/'observed_workdays_by_team.csv']
    manifest=dict(packages={p:importlib.metadata.version(p) for p in ('numpy','scipy','statsmodels','matplotlib','python-pptx')},
                  sources={str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
                  end=str(END),models=list(METHODS),cap_multipliers=[2,4,8],conditional_half_lives_days=[90,365,730])
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Completed',out,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=HERE_NEW/'results')
    run(parser.parse_args().output)
