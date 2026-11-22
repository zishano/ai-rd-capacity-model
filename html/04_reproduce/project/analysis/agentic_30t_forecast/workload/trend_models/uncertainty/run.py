"""Generate uncertainty-aware workload forecasts without changing resource-model inputs."""
import argparse
from datetime import date, timedelta
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from ...observations import HERE, records, write_rows
from ..run import END, dates_after, inputs
from .probabilistic import METHODS, forecast, composition, spaced

ROOT=Path(__file__).resolve().parent
SEED=20261122
SCENARIO_START=date(2028,1,18)


def summary(paths):
    q=np.quantile(paths,[.025,.1,.5,.9,.975],axis=0)
    return dict(lower95=q[0],lower80=q[1],median=q[2],upper80=q[3],upper95=q[4],
                mean=paths.mean(axis=0),zero_mass=(paths==0).mean(axis=0))


def score(paths,truth,point=None):
    s=summary(paths)
    median=s['median'] if point is None else point
    e=median-truth
    def interval_score(alpha):
        lo,hi=(s['lower80'],s['upper80']) if alpha==.2 else (s['lower95'],s['upper95'])
        return hi-lo+2/alpha*np.maximum(lo-truth,0)+2/alpha*np.maximum(truth-hi,0)
    return dict(mae=float(np.mean(abs(e))),rmse=float(np.sqrt(np.mean(e*e))),
                wape=float(np.sum(abs(e))/np.sum(abs(truth))) if np.any(truth) else None,
                coverage80=float(np.mean((truth>=s['lower80'])&(truth<=s['upper80']))),
                coverage95=float(np.mean((truth>=s['lower95'])&(truth<=s['upper95']))),
                width95=float(np.mean(s['upper95']-s['lower95'])),
                wis=float(np.mean((.5*abs(e)+.1*interval_score(.2)+.025*interval_score(.05))/2.5)))


def run(out,draws=2400):
    out.mkdir(parents=True,exist_ok=True)
    data,bins=inputs()
    forecasts=[];parameters=[];backtests=[];alignment=[];scenarios=[];sensitivity=[]
    caches={};saved={}
    for metric,(days,y,_) in data.items():
        stride=14 if metric=='output' else 28
        future=dates_after(days[-1])
        h=np.array([(d-days[-1]).days for d in future])
        requested=sorted(set(h.tolist()+([int(v-14) for v in h if v>14] if metric=='output' else [])))
        index=[requested.index(int(v)) for v in h]
        for j,method in enumerate(METHODS):
            print('Forecast',metric,method,flush=True)
            allpaths,p=forecast(y,stride,requested,method,draws=draws,seed=SEED+j)
            paths=allpaths[:,index]
            s=summary(paths)
            if method=='naive_rw':s['median']=np.full(len(h),y[-1])
            parameters.append(dict(metric=metric,method=method,origin=days[-1],parameters=json.dumps(p)))
            for i,d in enumerate(future):
                forecasts.append(dict(metric=metric,method=method,date=d,window_days=stride,
                         effective_points=p['effective_points'],**{k:float(v[i]) for k,v in s.items()}))
            if metric=='output':
                lag=np.column_stack([allpaths[:,requested.index(int(v-14))] if v>14
                                      else np.full(len(allpaths),y[len(y)-1+v-14]) for v in h])
                aligned=summary((paths+lag)/2)
                for i,d in enumerate(future):
                    alignment.append(dict(method=method,date=d,window_days=28,
                                **{k:float(v[i]) for k,v in aligned.items()}))
            if method=='ensemble':
                caches[metric]=dict(dates=future,paths=paths,summary=s)
                saved[metric+'_paths']=paths
                saved[metric+'_dates']=np.array([str(d) for d in future])
                # Explicit intervention scenarios, separate from statistical prediction bands.
                base=float(np.interp(SCENARIO_START.toordinal(),[d.toordinal() for d in future],s['median']))
                for i,d in enumerate(future):
                    years=max(0,(d-SCENARIO_START).days/365.2425)
                    scenarios.append(dict(metric=metric,date=d,reference=s['median'][i],
                         plateau=s['median'][i] if years==0 else base,
                         contraction10=s['median'][i] if years==0 else base*.9**years,
                         contraction20=s['median'][i] if years==0 else base*.8**years,
                         intervention_start=SCENARIO_START,basis='hypothetical intervention; no assigned probability'))
        for half in (90,365,730):
            paths,p=forecast(y,stride,[int(h[-1])],'damped_local_linear',draws=draws,seed=SEED,half_life=half)
            s=summary(paths)
            sensitivity.append(dict(metric=metric,parameter='half_life_days',value=half,
                                    **{k:float(v[0]) for k,v in s.items()}))
        for fraction in (.6,.7,.8):
            n=int(len(y)*fraction)
            available=[v for v in (14,28,56) if n+v<=len(y)]
            if not available or len(spaced(y[:n],stride))<4:continue
            for j,method in enumerate(METHODS):
                paths,p=forecast(y[:n],stride,range(1,max(available)+1),method,draws=800,seed=SEED+j+n)
                parameters.append(dict(metric=metric,method=method,origin=days[n-1],parameters=json.dumps(p)))
                for horizon in available:
                    for mode,start in [('rolling_target',0),('new_underlying_days',stride-1)]:
                        if start>=horizon:continue
                        truth=y[n+start:n+horizon]
                        point=np.full(len(truth),y[n-1]) if method=='naive_rw' else None
                        backtests.append(dict(metric=metric,method=method,origin=days[n-1],horizon=horizon,
                            scoring=mode,first_lead=start+1,n=len(truth),effective_train_points=p['effective_points'],
                            **score(paths[:,start:horizon],truth,point)))

    bindays=[date.fromisoformat(r['date']) for r in bins]
    shares=np.array([[float(r[f'bin_{i}']) for i in range(9)] for r in bins])
    shares/=shares.sum(axis=1,keepdims=True)
    future=dates_after(bindays[-1]);cr=[];thresholds=[];cb=[]
    bin_cache={}
    for method in ('composition_rw','composition_damped'):
        paths,center,p=composition(bindays,shares,future,method,draws=draws,seed=SEED)
        parameters.append(dict(metric='concurrency',method=method,origin=bindays[-1],parameters=json.dumps(p)))
        bin_cache[method]=(future,paths,center)
        saved[method+'_paths']=paths
        for b in range(9):
            s=summary(paths[:,:,b])
            for i,d in enumerate(future):
                cr.append(dict(method=method,date=d,bin=b,center=float(center[i,b]),
                               **{k:float(v[i]) for k,v in s.items()}))
        for start in (4,6):
            s=summary(paths[:,:,start:].sum(axis=2))
            for i,d in enumerate(future):
                thresholds.append(dict(method=method,date=d,threshold=4 if start==4 else 16,center=float(center[i,start:].sum()),
                                       **{k:float(v[i]) for k,v in s.items()}))
        for fraction in (.6,.7,.8):
            n=int(len(bindays)*fraction)
            for horizon in (14,28,56):
                if (bindays[-1]-bindays[n-1]).days<horizon:continue
                ids=[i for i in range(n,len(bindays)) if (bindays[i]-bindays[n-1]).days<=horizon]
                pp,cc,pr=composition(bindays[:n],shares[:n],[bindays[i] for i in ids],method,draws=800,seed=SEED+n)
                truth=shares[ids]
                s=summary(pp)
                cb.append(dict(method=method,origin=bindays[n-1],horizon=horizon,n=len(ids),
                      effective_train_points=pr['effective_points'],
                      bin_mae_pp=float(np.mean(abs(cc-truth))*100),
                      coverage80=float(np.mean((truth>=s['lower80'])&(truth<=s['upper80']))),
                      coverage95=float(np.mean((truth>=s['lower95'])&(truth<=s['upper95']))),
                      threshold4_mae_pp=float(np.mean(abs(cc[:,4:].sum(1)-truth[:,4:].sum(1)))*100),
                      threshold16_mae_pp=float(np.mean(abs(cc[:,6:].sum(1)-truth[:,6:].sum(1)))*100)))
    for shrink in (.25,.5,.75):
        pp,cc,_=composition(bindays,shares,future,'composition_damped',draws=draws,seed=SEED,shrinkage=shrink)
        s=summary(pp[:,:,6:].sum(axis=2))
        sensitivity.append(dict(metric='concurrency_ge16',parameter='covariance_shrinkage',value=shrink,
                                **{k:float(v[-1]) for k,v in s.items()}))
    for name,rows in [('forecast',forecasts),('parameters',parameters),('backtest',backtests),
                      ('output_aligned28',alignment),('scenarios',scenarios),('sensitivity',sensitivity),
                      ('concurrency',cr),('concurrency_thresholds',thresholds),('concurrency_backtest',cb)]:
        write_rows(out/(name+'.csv'),rows)
    np.savez_compressed(out/'predictive_paths.npz',**saved)
    sources=[HERE/'observed_openai_research_usage.csv',HERE/'calibration/observed_output_tokens.csv',
             HERE/'observed_workdays_by_team.csv']
    manifest=dict(seed=SEED,draws_per_component=draws,ensemble_draws=draws*3,models=list(METHODS),
       effective_points={k:len(spaced(v[1],14 if k=='output' else 28)) for k,v in data.items()},
       packages={p:importlib.metadata.version(p) for p in ('numpy','scipy','statsmodels','matplotlib')},
       sources={str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
       interval_basis='conditional simulation, not verified four-year coverage; includes zero censoring',
       scenario_assumptions=dict(start=str(SCENARIO_START),annual_contraction=[.1,.2],probabilities=None))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    from .visualize import render
    render(out,data,bins,caches,bin_cache,draws)
    print('Completed',out,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results')
    parser.add_argument('--draws',type=int,default=2400)
    args=parser.parse_args()
    run(args.output,args.draws)
