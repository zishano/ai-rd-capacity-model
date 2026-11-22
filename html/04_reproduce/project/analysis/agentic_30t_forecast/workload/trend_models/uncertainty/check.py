"""Check exported accounting and distribution semantics, including downward paths."""
import json
from collections import defaultdict
from datetime import date
from math import isclose

import numpy as np

from ...observations import HERE,records
from .probabilistic import COMPONENTS, composition, forecast,legacy_concurrency_bands
from .run import ROOT


def run():
    out=ROOT/'results'
    rows=records(out/'forecast.csv')
    predictions={}
    for r in rows:
        q=[float(r[k]) for k in ('lower95','lower80','median','upper80','upper95')]
        assert 0<=q[0]<=q[1]<=q[2]<=q[3]<=q[4]
        assert all(np.isfinite(q))
        assert 0<=float(r['zero_mass'])<=1
        predictions[r['metric'],r['method'],r['date']]=float(r['median'])
    for r in records(out/'backtest.csv'):
        if r['scoring']=='new_underlying_days':
            assert int(r['first_lead'])>=(14 if r['metric']=='output' else 28)
        assert 0<=float(r['coverage95'])<=1
    totals=defaultdict(float)
    for r in records(out/'chart_data.csv'):
        if r['status']!='forecast' or (r['metric']=='workdays' and r['series']!='Overall Research'):
            continue
        totals[r['metric'],r['date']]+=float(r['value'])
    for (metric,day),value in totals.items():
        assert isclose(value,predictions[metric,'ensemble',day],rel_tol=1e-10)
    bins=defaultdict(float)
    for r in records(out/'concurrency.csv'):
        bins[r['method'],r['date']]+=float(r['center'])
    assert all(isclose(v,1,abs_tol=1e-12) for v in bins.values())
    assert {r['threshold'] for r in records(out/'concurrency_thresholds.csv')}=={'4','16'}
    # The single main concurrency chart must preserve the previous algorithm exactly.
    legacy={(r['date'],i):float(r[f'bin_{i}']) for r in records(HERE/'trend_models/results/concurrency.csv')
            if r['method']=='legacy_log_complement' for i in range(9)}
    for r in records(out/'main_concurrency.csv'):
        for i in range(9):
            assert isclose(float(r[f'bin_{i}']),legacy[r['date'],i],abs_tol=1e-12)
    for r in records(out/'main_concurrency_bands.csv'):
        q=[float(r[k]) for k in ('boundary_p025','boundary_p10','boundary_p90','boundary_p975')]
        assert 0<=q[0]<=q[1]<=q[2]<=q[3]<=1+1e-12
        assert isclose(float(r['boundary_center'])+float(r['center_share']),1,abs_tol=1e-12)
    from ..run import inputs,dates_after
    _,observed_bins=inputs()
    days=[date.fromisoformat(r['date']) for r in observed_bins]
    shares=np.array([[float(r[f'bin_{i}']) for i in range(9)] for r in observed_bins])
    joint,_,metadata=legacy_concurrency_bands(days,shares,dates_after(days[-1]),draws=120,seed=7)
    assert np.all(joint>=0) and np.allclose(joint.sum(2),1,atol=1e-12)
    assert np.all(joint[:,:,6:].sum(2)<=joint[:,:,4:].sum(2)+1e-12)
    assert metadata['block_days']==28
    saved=np.load(out/'predictive_paths.npz')
    for method in ('composition_rw','composition_damped'):
        p=saved[method+'_paths']
        assert np.isfinite(p).all() and np.all(p>=0) and np.allclose(p.sum(2),1,atol=1e-12)
        assert np.all(p[:,:,6:].sum(2)<=p[:,:,4:].sum(2)+1e-12)
        assert np.any(np.diff(p[:,:,6:].sum(2),axis=1)<0)
    for metric in ('workdays','tasks','output'):
        p=saved[metric+'_paths']
        assert np.isfinite(p).all() and np.all(p>=0)
        assert np.any(np.diff(p,axis=1)<0)
    scenario_rows=records(out/'scenarios.csv')
    for metric in ('workdays','tasks','output'):
        r=[v for v in scenario_rows if v['metric']==metric and v['date']>'2028-01-18']
        assert np.all(np.diff([float(v['contraction10']) for v in r])<0)
        assert np.allclose([float(v['plateau']) for v in r],float(r[0]['plateau']))
    # A falling observed series must be allowed to produce a falling center.
    declining=np.linspace(30,10,169)
    a,_=forecast(declining,28,[28,56],'ols_spaced',draws=120,seed=7)
    assert np.median(a[:,1])<np.median(a[:,0])<declining[-1]
    a,_=forecast(declining,28,[28,56],'ensemble',draws=120,seed=7)
    pieces=[forecast(declining,28,[28,56],m,draws=120,seed=7+i*103)[0] for i,m in enumerate(COMPONENTS)]
    np.testing.assert_array_equal(a,np.concatenate(pieces))
    # The underlying rows, scenario files and forecast medians are all reproducible.
    b,_=forecast(declining,28,[28,56],'ensemble',draws=120,seed=7)
    np.testing.assert_array_equal(a,b)
    manifest=json.loads((out/'manifest.json').read_text())
    assert manifest['scenario_assumptions']['probabilities'] is None
    for name in ('monthly_workdays','monthly_concurrency','monthly_tasks','monthly_output_tokens'):
        assert (out/'figures'/f'{name}.png').exists()
    print('Passed quantiles, downward paths, simplex constraints, scenario separation, chart totals and deterministic simulation checks')


if __name__=='__main__':
    run()
