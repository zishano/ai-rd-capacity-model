"""Validate probabilities, accounting, out-of-sample dates and native chart data."""
import json
from collections import defaultdict
from datetime import date
from math import isclose
from zipfile import ZipFile
from xml.etree import ElementTree

from ..observations import ROOT, records
from inference.moe import calculate
from .run import HERE_NEW


def run():
    out=HERE_NEW/'results'
    fc=records(out/'forecast.csv')
    assert all(float(r['value'])>=0 for r in fc)
    assert all(r['date']<='2030-11-18' for r in fc)
    for r in records(out/'concurrency.csv'):
        v=[float(r[f'bin_{i}']) for i in range(9)]
        assert min(v)>=0 and isclose(sum(v),1,abs_tol=1e-12)
        assert sum(v[6:])<=sum(v[4:])+1e-12
    audit={r['metric']:r for r in json.loads((out/'audit.json').read_text())}
    for r in records(out/'backtest.csv'):
        cutoff=date.fromisoformat(r['origin'])
        assert (date.fromisoformat(audit[r['metric']]['end'])-cutoff).days>=int(r['horizon'])
        if r['scoring']=='new_underlying_days':
            assert int(r['first_lead'])>=audit[r['metric']]['window']
    predicted={(r['metric'],r['date'],r['method']):float(r['value']) for r in fc}
    aligned={(r['date'],r['method']):float(r['output_tokens_28d']) for r in fc if r['metric']=='output'}
    # Preserve the published old endpoint while exposing the different fitted-level baseline.
    assert isclose(predicted['output','2030-11-18','legacy_ols'],4730001.7547,abs_tol=.01)
    assert isclose(predicted['tasks','2030-11-18','legacy_ols'],168.9583869734,abs_tol=1e-8)
    groups=defaultdict(float)
    for r in records(out/'categories.csv'):
        if r['method']!='bottom_up_ols':
            groups[r['metric'],r['date'],r['method'],r['composition_window']]+=float(r['value'])
    for (metric,day,method,_),total in groups.items():
        assert isclose(total,predicted[metric,day,method],rel_tol=1e-12)
    # Original-style figures must use the same monthly totals as the exported models.
    from .original_style import PRESETS
    from .uncertainty import PRESET as UNCERTAINTY_PRESET
    for method in PRESETS:
        folder=out/'original_style'/method
        if method == UNCERTAINTY_PRESET:
            centers={(r['metric'],r['date']):float(r['median'])
                     for r in records(folder/'forecast.csv') if r['method']=='ensemble'}
            metadata=json.loads((folder/'preset.json').read_text())
            assert metadata['concurrency_method']=='legacy_log_complement'
            assert not metadata['resource_inputs_updated']
            # The adapter must export the approved concurrency center, not a new baseline.
            old={r['date']:r for r in records(out/'concurrency.csv')
                 if r['method']=='legacy_log_complement'}
            for r in records(folder/'main_concurrency.csv'):
                assert all(isclose(float(r[f'bin_{i}']),float(old[r['date']][f'bin_{i}']),abs_tol=1e-12)
                           for i in range(9))
        totals=defaultdict(float)
        for r in records(folder/'chart_data.csv'):
            assert r['method']==method
            assert float(r['value'])>=0
            if r['status']!='forecast' or (r['metric']=='workdays' and r['series']!='Overall Research'):
                continue
            totals[r['metric'],r['date']]+=float(r['value'])
        for (metric,day),total in totals.items():
            target=(1. if metric=='concurrency' else centers[metric,day]
                    if method==UNCERTAINTY_PRESET else predicted[metric,day,method])
            assert isclose(total,target,rel_tol=1e-10,abs_tol=1e-9)
        for name in ('monthly_workdays','monthly_concurrency','monthly_tasks','monthly_output_tokens'):
            assert (folder/(name+'.png')).is_file() and (folder/(name+'.pdf')).is_file()
    jobs=json.loads((out/'inference_inputs.json').read_text())
    totals=defaultdict(lambda:[0.,0.,0.])
    for j in jobs:
        v=j['workload'];w=j['tasks_per_researcher_day']
        assert set(v)=={'input_tokens','output_tokens','prefix_cache_hit_rate','context_tokens','peak_sequences'}
        a=totals[j['date'],j['method'],j['scenario']]
        for i,n in enumerate((v['input_tokens'],v['output_tokens'],v['input_tokens']*v['prefix_cache_hit_rate'])):
            a[i]+=n*w
    for r in records(out/'workload.csv'):
        assert r['output_window_days']=='28'
        assert isclose(float(r['output_tokens']),aligned[r['date'],r['method']],rel_tol=1e-12)
        a=totals[r['date'],r['method'],r['scenario']]
        for actual,key in zip(a,('input_tokens','output_tokens','cached_tokens')):
            assert isclose(actual,float(r[key]),rel_tol=1e-12)
        assert isclose(float(r['input_tokens'])-float(r['cached_tokens']),float(r['uncached_tokens']),rel_tol=1e-12)
        assert isclose(float(r['agent_hours'])/24,float(r['average_agent_equivalents']),rel_tol=1e-12)
    assert calculate(jobs[0]['workload'],'GB300_NVL72',ROOT/'config/models/moe_30t.json')['infer_gpu_h']>=0
    with ZipFile(out/'figures/trend_comparison.pptx') as z:
        charts=[n for n in z.namelist() if n.startswith('ppt/charts/chart') and n.endswith('.xml')]
        books=[n for n in z.namelist() if n.startswith('ppt/embeddings/') and n.endswith('.xlsx')]
        assert len(charts)==len(books)==13
        assert all(ElementTree.fromstring(z.read(n)).find('.//{*}externalData') is not None for n in charts)
    print(f'Passed probability, category, window, workload, adapter, 13 native charts and {len(PRESETS)} original-style chart sets')


if __name__=='__main__':
    run()
