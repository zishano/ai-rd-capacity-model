"""Acceptance checks for the workload-only projection and existing service boundary."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from collections import defaultdict
from datetime import date
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from analysis.agentic_30t_forecast.workload import forecast
from analysis.agentic_30t_forecast.workload.observations import HERE, PARENT, ROOT, records, series
from analysis.agentic_30t_forecast.workload.trends import fit
from analysis.agentic_40t_forecast.forecast import workload as old_input
from inference.moe import calculate


class WorkloadForecastTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)/'new'
        cls.config = json.loads((HERE/'settings.json').read_text())
        forecast.run(cls.config,cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_old_configuration_and_all_four_archives(self):
        out = Path(self.tmp.name)/'legacy'
        subprocess.run([sys.executable,'-B','analysis/agentic_40t_forecast/forecast.py','--config',
                        str(PARENT/'forecast_config.json'),'--output',str(out)],cwd=ROOT,check=True)
        for path in out.glob('*.csv'):
            self.assertEqual(path.read_bytes(),(PARENT/path.name).read_bytes())
        self.assertEqual(len(list(out.glob('*.csv'))),4)

    def test_provenance_and_reproduction(self):
        for source in records(HERE/'sources.csv'):
            self.assertEqual(hashlib.sha256((HERE/source['file']).read_bytes()).hexdigest(),source['sha256'])
        tasks = forecast.measured_tasks()
        self.assertEqual((len(tasks),sum(len(t['contexts']) for t in tasks)),(23,1172))
        for p in self.out.iterdir():
            self.assertEqual(p.read_bytes(), (HERE/'results'/p.name).read_bytes())

    def test_trend_equations(self):
        obs = series(PARENT/'observed_agent_workdays.csv','agent_workdays_per_researcher_day')
        for name,slope in [('ols',.03449281487743),('last56',.04161312371839),('last84',.04354257365597)]:
            self.assertAlmostEqual(fit(obs,name).slope,slope)
        for method in self.config['models']:
            m = fit(obs,method,48)
            if method=='nonnegative':
                self.assertTrue(all(m.predict(d)>=0 for d,_ in obs))
            if method=='bounded':
                self.assertLessEqual(m.predict(date(2100,1,1)),48)
            if method=='piecewise':
                self.assertEqual(m.knot,84)
                self.assertGreater(m.slope_change,0)
            for r in records(self.out/'trends.csv'):
                if r['method']==method:
                    y=m.predict(date.fromisoformat(r['date']))
                    self.assertAlmostEqual(float(r['usage']),y)
                    self.assertAlmostEqual(float(r['usage_multiplier']),y/m.predict(date(2026,11,18)))

    def test_accounting_and_scenario_isolation(self):
        data=records(self.out/'workload.csv')
        self.assertEqual(len(data),90)
        grouped=defaultdict(list)
        for r in data:
            f=lambda k:float(r[k])
            grouped[r['date'],r['method']].append(r)
            for daily,per_task in [('input_tokens_day','input_tokens_per_task'),
                                   ('output_tokens_day','output_tokens_per_task'),
                                   ('cached_input_tokens_day','cached_input_tokens_per_task'),
                                   ('calls_per_day','calls_per_task')]:
                self.assertAlmostEqual(f(daily),f(per_task)*f('tasks_per_day'))
            self.assertAlmostEqual(f('uncached_input_tokens_day')+f('cached_input_tokens_day'),f('input_tokens_day'))
            self.assertLessEqual(f('cached_input_tokens_day'),f('input_tokens_day'))
            self.assertAlmostEqual(f('prefix_cache_hit_rate'),f('cached_input_tokens_day')/f('input_tokens_day'))
            self.assertAlmostEqual(f('session_count_per_day')*f('mean_session_duration_hours'),f('session_hours_per_day'))
            self.assertAlmostEqual(f('average_online_sessions'),f('session_hours_per_day')/24)
            self.assertAlmostEqual(f('average_inference_concurrency'),f('main_session_hours_per_day')*f('inference_duty_proxy')/24)
            self.assertTrue(0<=f('average_inference_concurrency')<=f('peak_inference_concurrency')==1)
        for group in grouped.values():
            a,b,c=group
            self.assertEqual(a['session_hours_per_day'],b['session_hours_per_day'])
            self.assertEqual(a['session_hours_per_day'],c['session_hours_per_day'])
            self.assertAlmostEqual(float(a['tasks_per_day']),1)
            self.assertAlmostEqual(float(b['tasks_per_day']),float(b['usage_multiplier']))

    def test_adapter_and_fixed_kernel_outputs(self):
        tasks={t['instance']:t for t in forecast.measured_tasks()}
        totals=defaultdict(lambda:[0.,0.,0.])
        jobs=json.loads((self.out/'inference_inputs.json').read_text())
        self.assertEqual(len(jobs),345)
        for j in jobs:
            actual=j['workload']
            expected=old_input(tasks[j['instance']])
            self.assertEqual(actual,expected)
            total=totals[j['year'],j['scenario']]
            for i,field in enumerate(('input_tokens','output_tokens')):
                total[i]+=j['tasks_per_day']*actual[field]
            total[2]+=j['tasks_per_day']
            if j['scenario']=='A' and j['year']==2026:
                model=ROOT/'config/models/moe_30t.json'
                for hw in ('H100_SXM','GB300_NVL72'):
                    # Full dictionary includes stage FLOPs, HBM, KV, GPU-hours and replica size.
                    self.assertEqual(calculate(actual,hw,model),calculate(expected,hw,model))
        for r in records(self.out/'workload.csv'):
            if r['method']=='ols':
                for n,k in zip(totals[int(r['date'][:4]),r['workload_scenario']],
                               ('input_tokens_day','output_tokens_day','tasks_per_day')):
                    self.assertAlmostEqual(n,float(r[k]))

    def test_frozen_kernel_reference(self):
        # Captured by running inference/moe.py from e0fec24, with the same
        # model and hardware files and the published Django task.
        job = next(j for j in json.loads((self.out/'inference_inputs.json').read_text())
                   if j['instance']=='django__django-16667')
        for sku, hours, cards in [('H100_SXM',0.8006160792891795,576),
                                   ('GB300_NVL72',0.21324039315552906,144)]:
            z = calculate(job['workload'],sku,ROOT/'config/models/moe_30t.json')
            expected = dict(prefill_eflop=0.0037482665461760025,decode_eflop=0.001391091879936,
                            weights_gb_per_replica=30901.055985664,kv_peak_gb=1.58147136,
                            infer_gpu_h=hours,deployment_gpus_per_replica=cards)
            for field,value in expected.items():
                self.assertAlmostEqual(z[field],value,places=12,msg=field)

    def test_native_chart_workbooks(self):
        path=next((HERE/'figures').glob('*.pptx'))
        with ZipFile(path) as z:
            charts=[k for k in z.namelist() if k.startswith('ppt/charts/chart') and k.endswith('.xml')]
            books=[k for k in z.namelist() if k.startswith('ppt/embeddings/') and k.endswith('.xlsx')]
            self.assertEqual((len(charts),len(books)),(10,10))
            for k in charts:
                root=ElementTree.fromstring(z.read(k))
                self.assertIsNotNone(root.find('.//{*}externalData'))
                self.assertTrue(root.findall('.//{*}ser'))
