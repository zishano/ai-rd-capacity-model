"""Acceptance checks for the workload-only projection and existing service boundary."""
import csv
import hashlib
import json
import math
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

    def assert_forecast_matches_archive(self, actual, archive):
        # Python 3.12 improved sum() precision. Check computed floats numerically
        # while keeping counts, labels, structure and the source hashes exact.
        def compare(value, expected, location):
            self.assertIs(type(value), type(expected), location)
            if isinstance(expected, dict):
                self.assertEqual(value.keys(), expected.keys(), location)
                for key in expected:
                    compare(value[key], expected[key], f'{location}.{key}')
            elif isinstance(expected, list):
                self.assertEqual(len(value), len(expected), location)
                for i, (item, reference) in enumerate(zip(value, expected)):
                    compare(item, reference, f'{location}[{i}]')
            elif isinstance(expected, float):
                self.assertTrue(math.isclose(value, expected, rel_tol=1e-12, abs_tol=1e-12),
                                f'{location}: {value} != {expected}')
            else:
                self.assertEqual(value, expected, location)

        if archive.suffix == '.json':
            compare(json.loads(actual.read_text()), json.loads(archive.read_text()), archive.name)
            return
        self.assertEqual(archive.suffix, '.csv')
        with actual.open(newline='') as a, archive.open(newline='') as b:
            rows, reference = csv.reader(a), csv.reader(b)
            self.assertEqual(next(rows), next(reference), archive.name)
            for line, (row, ref) in enumerate(zip(rows, reference, strict=True), 2):
                for col, (field, expected) in enumerate(zip(row, ref, strict=True), 1):
                    if field == expected:
                        continue
                    location = f'{archive.name} row {line} column {col}'
                    if any(c in expected.lower() for c in '.e'):
                        try:
                            left, right = float(field), float(expected)
                        except ValueError:
                            pass
                        else:
                            compare(left, right, location)
                            continue
                    self.assertEqual(field, expected, location)

    def test_old_configuration_and_all_four_archives(self):
        out = Path(self.tmp.name)/'legacy'
        subprocess.run([sys.executable,'-B','analysis/agentic_40t_forecast/forecast.py','--config',
                        str(PARENT/'forecast_config.json'),'--output',str(out)],cwd=ROOT,check=True)
        for path in out.glob('*.csv'):
            self.assert_forecast_matches_archive(path, PARENT/path.name)
        self.assertEqual(len(list(out.glob('*.csv'))),4)

    def test_provenance_and_reproduction(self):
        for source in records(HERE/'sources.csv'):
            self.assertEqual(hashlib.sha256((HERE/source['file']).read_bytes()).hexdigest(),source['sha256'])
        tasks = forecast.measured_tasks()
        self.assertEqual((len(tasks),sum(len(t['contexts']) for t in tasks)),(23,1172))
        for p in self.out.rglob('*'):
            if p.is_file():
                self.assert_forecast_matches_archive(p, HERE/'results'/p.relative_to(self.out))

    def test_calibrated_researcher_day_and_kernel_input(self):
        out = self.out/'calibrated'
        coverage = records(out/'coverage.csv')
        self.assertEqual([(int(r['attempts']), int(r['reported_calls']), int(r['metered_calls']))
                          for r in coverage], [(500, 25589, 24687), (252, 12378, 12378), (248, 13211, 12309)])
        windows = [r for r in records(out/'matched_windows.csv') if r['category']=='all']
        self.assertEqual(len(windows), 4)
        for left, right in zip(windows, windows[1:]):
            self.assertLess(left['window_end'], right['window_start'])
        alpha = sum(float(r['output_per_day']) for r in windows)/sum(float(r['starts_per_day']) for r in windows)
        ratios = records(out/'output_intensity.csv')
        self.assertEqual(sum(r['pooled_output_per_start']=='' for r in ratios), 7)
        jobs = json.loads((out/'coding_inference_inputs.json').read_text())
        self.assertEqual(len(jobs), 3*252)
        for day in records(out/'researcher_day.csv')[-3:]:
            self.assertEqual(day['input_tokens'], '')
            self.assertAlmostEqual(float(day['output_if_pooled_intensity_transfers']), alpha*float(day['initiated_tasks']))
            batch = [j for j in jobs if j['rate_scenario']==day['scenario']]
            self.assertAlmostEqual(sum(j['tasks_per_researcher_day'] for j in batch), float(day['code_starts']))
            mix = next(r for r in records(out/'coding_sensitivity.csv') if r['date']==day['date']
                       and r['rate_scenario']==day['scenario'] and r['coding_mix']=='all_complete')
            for key, measured in [('prompt','input_tokens'), ('completion','output_tokens')]:
                self.assertAlmostEqual(sum(j['workload'][measured]*j['tasks_per_researcher_day'] for j in batch),
                                       float(mix[key]), places=5)
            self.assertAlmostEqual(sum(j['tasks_per_researcher_day']*j['workload']['input_tokens']*
                                       j['workload']['prefix_cache_hit_rate'] for j in batch),
                                   float(mix['cache_read']), places=5)
        job = jobs[0]['workload']
        self.assertEqual(set(job), {'input_tokens','output_tokens','prefix_cache_hit_rate','context_tokens','peak_sequences'})
        self.assertGreater(calculate(job, 'GB300_NVL72', ROOT/'config/models/moe_30t.json')['infer_gpu_h'], 0)

    def test_category_sum_and_focal_day_have_separate_denominators(self):
        out = self.out/'calibrated'
        categories = records(out/'category_token_ledger_2030.csv')
        focal = {r['scenario']: r for r in records(out/'focal_main_2030.csv')}
        totals = records(out/'researcher_18_categories_2030.csv')
        monthly = {r['series']: r for r in records(HERE/'results/monthly_output_and_task_starts.csv')
                   if r['date'] == '2030-11-18' and r['scenario'] == 'full_slope'}
        for row in totals:
            group = [r for r in categories if r['scenario'] == row['scenario']]
            self.assertEqual(len({r['category'] for r in group}), 18)
            known = [r for r in group if r['historical_intensity_available'] == 'True']
            self.assertEqual(len(known), 11)
            self.assertAlmostEqual(sum(float(r['starts']) for r in group), float(row['research_starts']))
            self.assertAlmostEqual(sum(float(r['output_per_researcher_day']) for r in known),
                                   float(row['forecast_output_historical_ratio_available']))
            for r in group:
                self.assertAlmostEqual(float(r['output_per_researcher_day']), float(monthly[r['category']]['output_tokens_28d']))
            self.assertAlmostEqual(float(row['forecast_output_zero_starts']), 6346.07467438024)
            for metric in ('input','cached','output','eflop'):
                daily = 0.
                for r in group:
                    amount = float(r[metric+'_per_researcher_day'])
                    if float(r['starts']) > 0:
                        self.assertAlmostEqual(float(r['starts'])*float(r[metric+'_per_start']), amount, places=5)
                    else:
                        self.assertEqual(r[metric+'_per_start'], '')
                    daily += amount
                self.assertAlmostEqual(daily, float(row['conditional_'+metric]), places=5)
            self.assertAlmostEqual(float(row['conditional_cached']) + float(row['conditional_uncached']),
                                   float(row['conditional_input']), places=5)
            self.assertAlmostEqual(float(row['conditional_input']) + float(row['conditional_output']),
                                   float(row['conditional_total_tokens']), places=5)
            main = focal[row['scenario']]
            self.assertAlmostEqual(float(main['session_minutes'])*float(main['sessions_per_researcher_day'])/60,
                                   float(main['researcher_agent_hours']))
            self.assertAlmostEqual(float(main['task_equivalents_per_main_day'])*float(main['output_per_issue']),
                                   float(main['output_per_main_day']))
        a,b,c = totals
        self.assertEqual(a['conditional_input'], b['conditional_input'])
        self.assertEqual(a['conditional_output'], c['conditional_output'])
        self.assertGreater(float(c['conditional_cached']), float(a['conditional_cached']))
        self.assertLess(float(c['conditional_eflop']), float(a['conditional_eflop']))
        self.assertAlmostEqual(float(c['conditional_eflop']), 5.0385889983497245)

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
        for path, expected in [(next((HERE/'figures').glob('*.pptx')), 10),
                               (HERE/'figures/calibration/task_calibration.pptx', 7)]:
            self.check_chart_workbooks(path, expected)

    def check_chart_workbooks(self, path, expected):
        with ZipFile(path) as z:
            charts=[k for k in z.namelist() if k.startswith('ppt/charts/chart') and k.endswith('.xml')]
            books=[k for k in z.namelist() if k.startswith('ppt/embeddings/') and k.endswith('.xlsx')]
            self.assertEqual((len(charts),len(books)),(expected,expected))
            for k in charts:
                root=ElementTree.fromstring(z.read(k))
                self.assertIsNotNone(root.find('.//{*}externalData'))
                self.assertTrue(root.findall('.//{*}ser'))
