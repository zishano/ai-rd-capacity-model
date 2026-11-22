"""Real-browser QA for selectable forecasting algorithms and their resource conversions."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import time

from cdp_helper import Chrome
from validate_explorer import CATEGORIES, CONTROLS, DIVISORS, ROOT, SNAPSHOT, TOP_FIELDS, annual_window_errors, close, millis, sha

HERE = Path(__file__).resolve().parent
OBSERVED = 'observed'
LEGACY = 'legacy_ols'
ENSEMBLE = 'ensemble_uncertainty'


def algorithms(item, label=False):
    key = 'labelAlgorithm' if label else 'algorithm'
    plural = 'labelAlgorithms' if label else 'algorithms'
    if item.get(key) == OBSERVED:
        return [OBSERVED]
    encoded = item.get(plural)
    if encoded:
        values = json.loads(encoded) if isinstance(encoded, str) else encoded
        if values:
            return values
    return [item.get(key)]


def month_number(day):
    return int(day[:4]) * 12 + int(day[5:7])


def label_text(value):
    places = 4 if abs(value) < .01 else 3 if abs(value) < 1 else 2 if abs(value) < 1000 else 0
    text = format(value, ',.' + str(places) + 'f')
    return text.rstrip('0').rstrip('.') if places else text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', type=Path, required=True)
    args = parser.parse_args()
    preview = args.preview.resolve()
    data = json.loads((HERE / 'dashboard_data.json').read_text())
    forecasts = json.loads((HERE / 'algorithm_forecasts.json').read_text())
    model_config = json.loads((HERE.parent / 'config/models/moe_30t.json').read_text())
    methods = [item['id'] for item in forecasts['methods']]
    names = {item['id']: item['name'] for item in forecasts['methods']}
    protected = (preview, HERE / 'team-resource-dashboard.html', HERE / 'dashboard_data.json',
                 HERE / 'dashboard_data.csv', HERE / 'algorithm_forecasts.json')
    original = {str(path): sha(path) for path in protected}
    report = dict(created_at_utc=datetime.now(timezone.utc).isoformat(), status='running',
                  method='Actual standalone Chrome interactions and independent forecast-to-resource arithmetic',
                  source_sha256=original, checks=[], snapshots=[], screenshots=[])
    browser = None
    started = time.monotonic()

    def check(ok, name, detail=None):
        report['checks'].append(dict(name=name, status='passed' if ok else 'failed', detail=detail))

    def source_rows(key, scenario):
        if key in ('agent_hours_per_team_day', 'mean_online_agent_equivalents'):
            source = data['monthly_trends']['agents']
        elif key == 'task_starts_per_team_day':
            source = data['monthly_tasks']
        else:
            source = data['monthly_resources']
        return sorted((row for row in source if row['scenario'] == scenario), key=lambda row: row['date'])

    def filtered(rows, controls):
        period = controls['range']
        if period in ('observed', 'forecast'):
            return [row for row in rows if row['phase'] == period]
        if period == 'custom':
            return [row for row in rows if controls['start'] <= row['date'] <= controls['end']]
        return rows

    def expected_value(row, key, method, controls):
        team = float(controls['team'])
        scale = team / float(row.get('researchers', 100))
        field = 'eflop_per_team_day' if key == 'compute_pflops_window' else key
        if method == OBSERVED:
            value = float(row[field]) * (1 if key == 'prefix_cache_hit_rate' else scale)
        elif key in ('agent_hours_per_team_day', 'mean_online_agent_equivalents'):
            hours = float(forecasts['forecasts'][method]['workdays'][row['date']]) * team * 8
            value = hours if key == 'agent_hours_per_team_day' else hours / 24
        elif key == 'task_starts_per_team_day':
            value = float(forecasts['forecasts'][method]['tasks'][row['date']]) * team
        elif key == 'prefix_cache_hit_rate':
            value = float(row[key])
        else:
            output = float(forecasts['forecasts'][method]['output'][row['date']]) * team
            value = output if key == 'output_tokens_per_team_day' else float(row[field]) / float(row['output_tokens_per_team_day']) * output
        if key == 'compute_pflops_window':
            value *= 1000 / (float(controls['window']) * 3600)
        return value

    def expected_points(snapshot):
        controls = snapshot['controls']
        category = controls['category']
        state = snapshot['state']
        scenarios = state['scenarios'] if len(CATEGORIES[category]) == 1 else [controls['scenario']]
        points = {}
        labels = {}
        for key in state['selectedMetrics']:
            for scenario in scenarios:
                rows = source_rows(key, scenario)
                visible = filtered(rows, controls)
                anchor = month_number(rows[0]['date'])
                for row in visible:
                    selected = [OBSERVED] if row['phase'] == 'observed' else state['algorithms']
                    for method in selected:
                        identity = (key, scenario, row['date'], method)
                        points[identity] = expected_value(row, key, method, controls)
                        if (month_number(row['date']) - anchor) % 3 == 0 or row['date'] == visible[-1]['date']:
                            labels[identity] = points[identity] / DIVISORS.get(key, 1)
        return points, labels

    check(len(methods) == 16 and len(set(methods)) == 16 and LEGACY in methods and ENSEMBLE in methods,
          'artifact exposes all 16 methods including the uncertainty ensemble with the original OLS default', methods)
    annual_errors=annual_window_errors(data)
    check(not annual_errors, 'annual outputs use native 14-day sources while retaining resource ratios and activity', annual_errors)
    check(forecasts['meta']['rolling_window_days']==dict(output=14,workdays=28,tasks=28),
          'algorithm metadata declares native 14-day output and unchanged 28-day task/Agent windows')

    archive = HERE.parent / 'analysis/agentic_30t_forecast/workload/trend_models/results/original_style/ensemble_uncertainty'
    def csv_rows(path):
        with path.open(newline='', encoding='utf-8-sig') as source:
            return list(csv.DictReader(source))
    native = {(row['metric'], row['date']): row for row in csv_rows(archive/'forecast.csv') if row['method']=='ensemble'}
    source_errors=[]
    for metric, days in forecasts['uncertainty'][ENSEMBLE].items():
        for day, quantiles in days.items():
            source = native[(metric,day)]
            if not close(forecasts['forecasts'][ENSEMBLE][metric][day], source['median']) or any(not close(quantiles[key],source[key]) for key in ('lower95','lower80','median','upper80','upper95')):
                source_errors.append(dict(metric=metric,date=day))
    check(not source_errors and sum(len(v) for v in forecasts['uncertainty'][ENSEMBLE].values())==150,
          '150 ensemble intervals and medians match archived native quantiles: output 14 days, task/Agent 28 days',source_errors)

    try:
        browser = Chrome(timeout=360)
        browser.call('Emulation.setDeviceMetricsOverride', dict(width=1280, height=1400, deviceScaleFactor=1, mobile=False))
        browser.call('Emulation.setEmulatedMedia', dict(features=[dict(name='prefers-color-scheme', value='light')]))
        context = None

        def navigate():
            nonlocal context
            browser.call('Page.navigate', dict(url=preview.as_uri()))
            context = None
            while context is None:
                browser.call('Page.getFrameTree')
                browser.enable_attached()
                for cid, info in list(browser.contexts.items()):
                    if not info.get('auxData', {}).get('isDefault'):
                        continue
                    try:
                        if browser.evaluate("document.getElementById('" + ROOT + "')?.dataset.ready==='true'", cid):
                            context = cid
                            break
                    except RuntimeError:
                        pass
                if context is None:
                    browser.remaining()
                    time.sleep(.05)
            evaluate("window.__qaErrors=[];addEventListener('error',e=>window.__qaErrors.push(e.message));addEventListener('unhandledrejection',e=>window.__qaErrors.push(String(e.reason)))")
            settled()

        def evaluate(js):
            return browser.evaluate(js, context)

        def settled():
            evaluate('new Promise(r=>setTimeout(()=>requestAnimationFrame(()=>requestAnimationFrame(r)),120))')

        def snapshot():
            result = evaluate(SNAPSHOT.replace('CONTROL_NAMES', json.dumps(CONTROLS)))
            result['algorithmOptions'] = evaluate("Array.from(document.querySelectorAll('#trd-algorithm-options input[data-algorithm]'),e=>({key:e.dataset.algorithm,checked:e.checked,disabled:e.disabled}))")
            result['algorithmSummary'] = evaluate("document.getElementById('trd-algorithms-summary')?.textContent||''")
            return result

        def change(name, value):
            if name == 'headline-algorithm':
                selector = 'input[data-headline-choice][value=' + json.dumps(str(value)) + ']'
                got = evaluate('(()=>{document.getElementById("trd-algorithms-menu").open=true;const e=document.querySelector(' + json.dumps(selector) + ');if(!e)return null;e.click();return e.checked?e.value:null})()')
            else:
                got = evaluate('(()=>{const e=document.getElementById(' + json.dumps('trd-' + name) + ');e.value=' + json.dumps(str(value)) + ';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));return e.value})()')
            if got != str(value):
                raise ValueError('Rejected control ' + name + '=' + str(value))
            settled()

        def toggle(kind, key):
            selector = 'input[data-' + kind + '=' + json.dumps(key) + ']'
            if not evaluate('(()=>{const e=document.querySelector(' + json.dumps(selector) + ');if(!e)return false;e.click();return true})()'):
                raise ValueError('Missing checkbox ' + selector)
            settled()

        def select_algorithms(wanted):
            current = snapshot()['state']['algorithms']
            if set(current) == set(wanted):
                return
            # Leave one wanted method selected before removing the remaining old choices.
            common = next((key for key in current if key in wanted), None)
            if common is None:
                for key in current[1:]:
                    toggle('algorithm', key)
                toggle('algorithm', wanted[0])
            for key in list(snapshot()['state']['algorithms']):
                if key not in wanted:
                    toggle('algorithm', key)
            for key in wanted:
                if key not in snapshot()['state']['algorithms']:
                    toggle('algorithm', key)

        def select_metrics(wanted):
            for key in wanted:
                if key not in snapshot()['state']['selectedMetrics']:
                    toggle('metric', key)
            for key in list(snapshot()['state']['selectedMetrics']):
                if key not in wanted:
                    toggle('metric', key)

        def select_scenarios(wanted):
            for key in wanted:
                if key not in snapshot()['state']['scenarios']:
                    toggle('scenario', key)
            for key in list(snapshot()['state']['scenarios']):
                if key not in wanted:
                    toggle('scenario', key)

        def headline(label, snap=None, layout=False):
            snap = snapshot() if snap is None else snap
            controls, state, meta = snap['controls'], snap['state'], snap['headline']
            method, endpoint = state.get('headlineAlgorithm'), forecasts['meta']['endpoint']
            check(method in methods
                  and meta['algorithm'] == method and meta['sourceAlgorithm'] == method and meta['date'] == endpoint
                  and [item['key'] for item in meta['options']] == methods
                  and [item['name'] for item in meta['options']] == [names[key] for key in methods]
                  and [item['key'] for item in meta['options'] if item['checked']] == [method]
                  and all(not item['disabled'] and item['type'] == 'radio' and item['group'] == 'trd-headline-choice' for item in meta['options'])
                  and not meta['legacySelectorPresent']
                  and names.get(method, '\0') in (meta.get('name') or '')
                  and names.get(method, '\0') in (meta.get('sourceName') or ''),
                  label + ': the unified menu has exactly one enabled headline radio selection and a matching readonly top label',
                  dict(method=method, selected=state['algorithms'], metadata=meta))
            if method not in forecasts['forecasts']:
                return snap
            fields = {**TOP_FIELDS, 'compute-pflops': 'compute_pflops_window', 'cache-hit-rate': 'prefix_cache_hit_rate'}
            wanted = {key: expected_value(next(row for row in source_rows(field, controls['scenario']) if row['date'] == endpoint), field, method, controls)
                      for key, field in fields.items()}
            wanted['weight-tb'] = float(data['model']['total_parameters']) * float(model_config['weights']['bytes_per_parameter']) / 1e12
            errors = [dict(metric=key, expected=value, actual=snap['values'].get(key), occurrences=meta['numericCounts'].get(key))
                      for key, value in wanted.items() if key not in snap['values'] or not close(snap['values'][key], value) or meta['numericCounts'].get(key) != 1]
            check(not errors, label + ': all headline resources, Agent activity and source details equal the algorithm endpoint', errors)
            if controls['view'] == 'trend' and snap['svg']:
                by_field = {field: key for key, field in fields.items()}
                marks = [mark for mark in snap['svg']['marks'] if mark.get('date') == endpoint and mark.get('scenario') == controls['scenario']
                         and method in algorithms(mark) and mark.get('series') in by_field]
                mismatches = [dict(series=mark['series'], curve=mark['value'], headline=snap['values'][by_field[mark['series']]])
                              for mark in marks if not close(mark['value'], snap['values'][by_field[mark['series']]])]
                check(not mismatches, label + ': visible curve endpoints and headline values agree', mismatches)
            if layout:
                boxes = evaluate("(()=>{const host=document.querySelector('[data-headline-algorithm]'),label=document.querySelector('[data-testid=\"headline-algorithm-name\"]');return {label:{width:label.getBoundingClientRect().width,parent:label.parentElement.getBoundingClientRect().width},overflow:Array.from(host.querySelectorAll('[data-testid][data-value]')).flatMap(e=>{const b=e.getBoundingClientRect(),card=e.closest('section').getBoundingClientRect();return b.left<card.left-1||b.right>card.right+1||b.top<card.top-1||b.bottom>card.bottom+1?[{metric:e.dataset.testid,width:b.width,card:card.width}]:[]})}})()")
                check(not boxes['overflow'] and 0 < boxes['label']['width'] <= boxes['label']['parent'] + 1,
                      label + ': headline numbers and readonly algorithm name fit their cards', boxes)
            return snap

        def chart(label, layout=False):
            snap = snapshot()
            headline(label, snap, layout=layout)
            svg = snap['svg']
            check(bool(svg) and not snap['runtime'] and not snap['error'] and not svg['invalid'],
                  label + ': finite plot without runtime errors', dict(error=snap['error'], runtime=snap['runtime']))
            if not svg:
                return snap
            wanted, wanted_labels = expected_points(snap)
            actual = {}
            errors = []
            physical_history = []
            for mark in svg['marks']:
                group = algorithms(mark)
                if not group or len(set(group)) != len(group):
                    errors.append(dict(reason='invalid algorithm membership', mark=mark))
                if mark.get('algorithm') == OBSERVED:
                    physical_history.append((mark.get('series'), mark.get('scenario'), mark.get('date')))
                    if mark.get('algorithms') and json.loads(mark['algorithms']) != []:
                        errors.append('public history unexpectedly belongs to a forecast method')
                for method in group:
                    identity = (mark.get('series'), mark.get('scenario'), mark.get('date'), method)
                    if identity in actual:
                        errors.append(dict(reason='duplicate numeric mark', identity=identity))
                    actual[identity] = mark
            if len(set(physical_history)) != len(physical_history):
                errors.append('public history is repeated for selected algorithms')
            if set(actual) != set(wanted):
                errors.append(dict(reason='method/date/metric selection differs', missing=list(set(wanted)-set(actual))[:4], extra=list(set(actual)-set(wanted))[:4]))
            axes = svg['axes']
            if len(axes) != 1 or float(axes[0]['min']) != 0:
                errors.append('expected one actual-unit axis starting at zero')
            else:
                axis = axes[0]
                x0, y0, width, height = (float(svg[k]) for k in ('plotX', 'plotY', 'plotWidth', 'plotHeight'))
                t0, t1 = float(svg['timeMin']), float(svg['timeMax'])
                for identity, value in wanted.items():
                    mark = actual.get(identity)
                    if mark is None:
                        continue
                    plotted = value / DIVISORS.get(identity[0], 1)
                    xx = x0 + (millis(identity[2])-t0)/(t1-t0)*width if t1 != t0 else x0 + width/2
                    yy = y0 + height - plotted/float(axis['max'])*height
                    if not close(mark['value'], value) or not close(mark['plotValue'], plotted) or abs(mark['cx']-xx) > .15 or abs(mark['cy']-yy) > .15:
                        errors.append(dict(identity=identity, actual=mark['value'], expected=value, plotted=mark['plotValue'], expected_plot=plotted))
            check(not errors, label + ': forecast-to-resource values, shared history and actual-unit geometry', errors[:8])

            actual_labels = {}
            label_errors = []
            for item in svg['labels']:
                for method in algorithms(item, label=True):
                    identity = (item.get('labelSeries'), item.get('labelScenario'), item.get('labelDate'), method)
                    if identity in actual_labels:
                        label_errors.append(dict(reason='duplicate quarterly label', identity=identity))
                    actual_labels[identity] = item
            if set(actual_labels) != set(wanted_labels):
                label_errors.append(dict(reason='quarterly algorithm label membership differs', missing=list(set(wanted_labels)-set(actual_labels))[:4], extra=list(set(actual_labels)-set(wanted_labels))[:4]))
            for identity, value in wanted_labels.items():
                item = actual_labels.get(identity)
                if item and (not close(item['labelValue'], value) or item['text'] != label_text(value)):
                    label_errors.append(dict(identity=identity, value=item['labelValue'], expected=value, text=item['text'], expected_text=label_text(value)))
            check(not label_errors, label + ': quarterly values and dates match each selected algorithm', label_errors[:8])
            if layout:
                check(not svg['clipping'] and not svg['overlaps'], label + ': all quarterly labels fit without collisions',
                      dict(clipping=svg['clipping'][:6], overlaps=svg['overlaps'][:6]))
                widths = evaluate("({viewport:innerWidth,page:document.documentElement.scrollWidth,chart:document.getElementById('trd-chart-main').clientWidth,chartScroll:document.getElementById('trd-chart-main').scrollWidth,overflow:getComputedStyle(document.getElementById('trd-chart-main')).overflowX})")
                check(widths['page'] <= widths['viewport']+1 and (widths['chartScroll'] <= widths['chart']+1 or widths['overflow'] in ('auto', 'scroll')),
                      label + ': dense charts scroll inside the page', widths)
            report['snapshots'].append(dict(label=label, state=snap['state'], marks=len(svg['marks']), labels=len(svg['labels']), expanded_forecast_points=sum(k[3] != OBSERVED for k in actual)))
            return snap

        def capture_csv():
            text = evaluate("(async()=>{const create=URL.createObjectURL,revoke=URL.revokeObjectURL,click=HTMLAnchorElement.prototype.click;let blob;URL.createObjectURL=b=>{blob=b;return 'blob:qa-csv-capture'};URL.revokeObjectURL=()=>{};HTMLAnchorElement.prototype.click=()=>{};try{document.getElementById('trd-download').click();return blob?await blob.text():null}finally{URL.createObjectURL=create;URL.revokeObjectURL=revoke;HTMLAnchorElement.prototype.click=click}})()")
            return list(csv.DictReader(io.StringIO((text or '').lstrip('\ufeff'))))

        def check_csv_values(label, snap, rows):
            metric_keys = evaluate("Object.fromEntries(Array.from(document.getElementById('trd-primary').options,e=>[e.textContent,e.value]))")
            wanted, _ = expected_points(snap)
            actual = {}
            problems = []
            for row in rows:
                identity = (metric_keys.get(row.get('指标')), row.get('情景'), row.get('日期'), row.get('算法ID'))
                if identity in actual:
                    problems.append(dict(reason='duplicate exported row', identity=identity))
                actual[identity] = row
                value = wanted.get(identity)
                if value is not None and (not close(row['原始值'], value) or not close(row['图表值'], value / DIVISORS.get(identity[0], 1))):
                    problems.append(dict(identity=identity, original=row['原始值'], plotted=row['图表值'], expected=value))
            if set(actual) != set(wanted):
                problems.append(dict(reason='CSV membership differs from selected source values', missing=list(set(wanted)-set(actual))[:4], extra=list(set(actual)-set(wanted))[:4]))
            check(not problems, label + ': downloaded raw and plotted values match every method and shared historical observation', problems[:6])

        def expected_intervals(snap):
            controls,state=snap['controls'],snap['state']
            if controls['view']!='trend' or not state.get('showIntervals') or ENSEMBLE not in state['algorithms'] or controls['category']=='cache':
                return {}
            scenarios=state['scenarios'] if len(CATEGORIES[controls['category']])==1 else [controls['scenario']]
            wanted={}
            for key in state['selectedMetrics']:
                metric='workdays' if key in CATEGORIES['agent_time']+CATEGORIES['agent_scale'] else 'tasks' if key in CATEGORIES['tasks'] else 'output'
                for scenario in scenarios:
                    rows=filtered(source_rows(key,scenario),controls)
                    for level in ('80','95'):
                        points=[]
                        for row in rows:
                            bounds=forecasts['uncertainty'][ENSEMBLE][metric].get(row['date'])
                            if row['phase']!='forecast' or not bounds:continue
                            team=float(controls['team'])
                            if metric=='workdays':factor=team*8/(24 if key=='mean_online_agent_equivalents' else 1)
                            elif metric=='tasks' or key=='output_tokens_per_team_day':factor=team
                            else:
                                field='eflop_per_team_day' if key=='compute_pflops_window' else key
                                factor=team*float(row[field])/float(row['output_tokens_per_team_day'])
                                if key=='compute_pflops_window':factor*=1000/(float(controls['window'])*3600)
                            points.append(dict(date=row['date'],lower=float(bounds['lower'+level])*factor,upper=float(bounds['upper'+level])*factor))
                        if points:wanted[(key,scenario,level)]=points
            return wanted

        def intervals(label,snap=None,export=False):
            snap=snapshot() if snap is None else snap
            expected=expected_intervals(snap);bands=snap['svg']['bands'] if snap['svg'] else []
            actual={(band.get('series') or band.get('key'),band.get('scenario'),band.get('interval')):band for band in bands}
            issues=[]
            if set(actual)!=set(expected) or len(actual)!=len(bands):
                issues.append(dict(reason='interval membership',expected=list(expected),actual=list(actual)))
            svg=snap['svg']
            if svg and (expected or bands):
                x0,y0,width,height=(float(svg[key]) for key in ('plotX','plotY','plotWidth','plotHeight'))
                t0,t1=float(svg['timeMin']),float(svg['timeMax']);axismax=float(svg['axes'][0]['max'])
                for identity,points in expected.items():
                    band=actual.get(identity)
                    if not band:continue
                    bounds=json.loads(band['bounds']);divisor=DIVISORS.get(identity[0],1)
                    if band.get('algorithm')!=ENSEMBLE or not close(band.get('divisor',math.nan),divisor) or len(bounds)!=len(points):
                        issues.append(dict(identity=identity,reason='invalid interval metadata'));continue
                    for got,want in zip(bounds,points):
                        if got['date']!=want['date'] or any(not close(got[field],want[field]) for field in ('lower','upper')):
                            issues.append(dict(identity=identity,reason='scaled source quantiles differ',expected=want,actual=got))
                    vertices=band['points'] or ([band['line'][:2],band['line'][2:]] if band['line'] else [])
                    wanted_vertices=[]
                    for point in points:
                        xx=x0+(millis(point['date'])-t0)/(t1-t0)*width if t1!=t0 else x0+width/2
                        for field in ('lower','upper'):
                            plotted=point[field]/divisor
                            yy=y0+height-plotted/axismax*height
                            wanted_vertices.append((xx,yy))
                            if plotted>axismax+1e-8:issues.append(dict(identity=identity,reason='interval clipped by axis'))
                    if len(vertices)!=len(wanted_vertices) or any(not any(abs(x-a)<=.15 and abs(y-b)<=.15 for a,b in vertices) for x,y in wanted_vertices):
                        issues.append(dict(identity=identity,reason='band geometry differs from actual-unit bounds',vertices=len(vertices),expected=len(wanted_vertices)))
            check(not issues,label+': nominal 80/95 bands match original units, team/window scaling, forecast dates and plot geometry',issues[:8])
            if export:
                exported=capture_csv();point_bounds={(key,scenario,p['date'],level):p for (key,scenario,level),points in expected.items() for p in points}
                metric_keys=evaluate("Object.fromEntries(Array.from(document.getElementById('trd-primary').options,e=>[e.textContent,e.value]))")
                csv_issues=[]
                for row in exported:
                    key=metric_keys.get(row.get('指标'))
                    for level in ('80','95'):
                        bound=point_bounds.get((key,row.get('情景'),row.get('日期'),level)) if row.get('算法ID')==ENSEMBLE else None
                        for field,label_part in (('lower','下界'),('upper','上界')):
                            cell=row.get('名义'+level+'%'+label_part)
                            if bound and (cell in ('',None) or not close(cell,bound[field])) or not bound and cell not in ('',None):
                                csv_issues.append(dict(date=row.get('日期'),metric=key,level=level,field=field,actual=cell,expected=bound))
                check(not csv_issues,label+': downloaded nominal intervals preserve actual units and do not attach to other algorithms or observations',csv_issues[:5])
            return snap

        def touch_scroll():
            browser.call('Emulation.setTouchEmulationEnabled', dict(enabled=True, maxTouchPoints=1))
            browser.call('Emulation.setDeviceMetricsOverride', dict(width=320, height=1000, deviceScaleFactor=1, mobile=True))
            settled()
            position = evaluate("(()=>{const h=document.getElementById('trd-chart-main');h.scrollIntoView({block:'center'});h.scrollLeft=0;const b=h.getBoundingClientRect();return {x:b.left+h.clientWidth*.8,y:Math.max(30,Math.min(innerHeight-30,b.top+h.clientHeight/2)),initial:h.scrollLeft,overflow:h.scrollWidth-h.clientWidth,touchAction:getComputedStyle(h.querySelector('svg')).touchAction}})()")
            browser.call('Input.synthesizeScrollGesture', dict(x=position['x'], y=position['y'], xDistance=-150, yDistance=0, speed=600, gestureSourceType='touch'))
            settled()
            offset = evaluate("document.getElementById('trd-chart-main').scrollLeft")
            mechanism = 'synthesizeScrollGesture touch'
            if offset <= position['initial']+8:
                # Some Chrome versions do not synthesize touch scrolling; use physical touch packets.
                point = dict(x=position['x'], y=position['y'], id=1, radiusX=2, radiusY=2, force=1)
                browser.call('Input.dispatchTouchEvent', dict(type='touchStart', touchPoints=[point]))
                for dx in (30, 65, 100, 140):
                    browser.call('Input.dispatchTouchEvent', dict(type='touchMove', touchPoints=[dict(point, x=position['x']-dx)]))
                    evaluate('new Promise(r=>setTimeout(r,45))')
                browser.call('Input.dispatchTouchEvent', dict(type='touchEnd', touchPoints=[]))
                settled()
                offset = evaluate("document.getElementById('trd-chart-main').scrollLeft")
                mechanism = 'dispatchTouchEvent start/move/end'
            check(position['overflow'] > 0 and offset > position['initial']+8,
                  '320px real touch swipe horizontally scrolls the dense chart', dict(**position, final=offset, mechanism=mechanism))

        def screenshot(filename, width, menu=False):
            browser.call('Emulation.setDeviceMetricsOverride', dict(width=width, height=1200, deviceScaleFactor=1, mobile=False))
            settled()
            evaluate("window.scrollTo(0,0);document.getElementById('trd-chart-main').scrollLeft=0;document.getElementById('trd-algorithms-menu').open=" + str(menu).lower())
            height = evaluate("Math.ceil(document.getElementById('" + ROOT + "').getBoundingClientRect().bottom)+24")
            browser.call('Emulation.setDeviceMetricsOverride', dict(width=width, height=max(700, height), deviceScaleFactor=1, mobile=False))
            settled()
            path = HERE / filename
            browser.screenshot(path, full_page=True)
            report['screenshots'].append(dict(file=filename, width=width, sha256=sha(path)))
            evaluate("document.getElementById('trd-algorithms-menu').open=false")

        navigate()
        initial = chart('original OLS default', layout=True)
        check(initial['intervals']['checked'] is False and not initial['intervals']['visible'] and not initial['svg']['bands'],
              'nominal uncertainty starts disabled and is unavailable for original OLS')
        check(initial['state']['algorithms'] == [LEGACY], 'the original OLS remains the only default algorithm')
        check(set(item['key'] for item in initial['algorithmOptions']) == set(methods), 'dropdown contains exactly the 16 supported methods')
        check(bool(initial['algorithmSummary']), 'algorithm dropdown exposes a readable selection summary', initial['algorithmSummary'])
        evaluate("document.getElementById('trd-algorithms-summary').click()")
        check(evaluate("document.getElementById('trd-algorithms-menu').open"), 'algorithm summary opens the multi-select dropdown')
        toggle('algorithm', LEGACY)
        check(snapshot()['state']['algorithms'] == [LEGACY], 'the last selected algorithm cannot be removed')

        # Regression: the default single curve must not lock or restrict the
        # headline selector. Every supported method can drive the top values.
        for method in methods:
            before = snapshot()
            change('headline-algorithm', method)
            after = headline('single-curve headline method ' + method)
            check(after['state']['algorithms'] == [LEGACY] and before['svg']['marks'] == after['svg']['marks']
                  and {key: value for key, value in before['state'].items() if key != 'headlineAlgorithm'} == {key: value for key, value in after['state'].items() if key != 'headlineAlgorithm'}
                  and before['headline']['baseline'] == after['headline']['baseline'] and before['values']['weight-tb'] == after['values']['weight-tb'],
                  'selecting headline ' + method + ' with one original OLS curve preserves the curve, other controls, public baseline and model weights')
        change('headline-algorithm', LEGACY)

        # Prefer distinct long-term forecasts, keeping OLS first. Imported
        # methods may legitimately coincide; identity still permits comparison.
        endpoint = forecasts['meta']['endpoint']
        distinct = []
        values = [forecasts['forecasts'][LEGACY]['output'][endpoint]]
        for method in methods:
            candidate = forecasts['forecasts'][method]['output'][endpoint]
            if method != LEGACY and all(not close(candidate, other) for other in values):
                distinct.append(method)
                values.append(candidate)
            if len(distinct) == 2:
                break
        selected = [LEGACY, *distinct]
        selected.extend(method for method in methods if method not in selected)
        selected = selected[:3]
        select_algorithms(selected)
        triple = chart('three distinct algorithms', layout=True)
        fourth = next(method for method in methods if method not in selected)
        disabled = {item['key']: item['disabled'] for item in triple['algorithmOptions']}
        check(all(disabled[method] for method in methods if method not in selected), 'a fourth algorithm is disabled while three are selected')
        toggle('algorithm', fourth)
        check(set(snapshot()['state']['algorithms']) == set(selected), 'clicking a disabled fourth method cannot select all algorithms')
        change('headline-algorithm', fourth)
        independent_fourth = headline('unplotted headline at three-curve limit')
        check(independent_fourth['state']['headlineAlgorithm'] == fourth
              and independent_fourth['state']['algorithms'] == triple['state']['algorithms']
              and independent_fourth['svg']['marks'] == triple['svg']['marks']
              and all(not item['disabled'] for item in independent_fourth['headline']['options']),
              'at three plotted methods, an unplotted algorithm remains selectable for the headline without adding a fourth curve')
        radio_selector = 'input[data-headline-choice][value=' + json.dumps(fourth) + ']'
        evaluate('document.querySelector(' + json.dumps(radio_selector) + ').focus()')
        radio_order = [item['key'] for item in independent_fourth['headline']['options']]
        arrow_method = radio_order[(radio_order.index(fourth) + 1) % len(radio_order)]
        browser.call('Input.dispatchKeyEvent', dict(type='rawKeyDown', key='ArrowRight', code='ArrowRight', windowsVirtualKeyCode=39))
        browser.call('Input.dispatchKeyEvent', dict(type='keyUp', key='ArrowRight', code='ArrowRight', windowsVirtualKeyCode=39))
        settled()
        arrow_selection = headline('headline radio keyboard arrow navigation')
        check(arrow_selection['state']['headlineAlgorithm'] == arrow_method
              and arrow_selection['state']['algorithms'] == triple['state']['algorithms']
              and arrow_selection['svg']['marks'] == triple['svg']['marks'],
              'native radio arrow navigation updates only the headline selection')
        evaluate('document.querySelector(' + json.dumps(radio_selector) + ').focus()')
        browser.call('Input.dispatchKeyEvent', dict(type='keyDown', key=' ', code='Space', windowsVirtualKeyCode=32, text=' ', unmodifiedText=' '))
        browser.call('Input.dispatchKeyEvent', dict(type='keyUp', key=' ', code='Space', windowsVirtualKeyCode=32))
        settled()
        space_selection = headline('headline radio keyboard Space selection')
        check(space_selection['state']['headlineAlgorithm'] == fourth
              and space_selection['state']['algorithms'] == triple['state']['algorithms'],
              'Space selects the unplotted headline radio without selecting its disabled curve checkbox')
        label_selector = 'input[data-headline-choice][value=' + json.dumps(arrow_method) + ']'
        evaluate('document.querySelector(' + json.dumps(label_selector) + ').closest("label").click()')
        settled()
        label_selection = headline('independent headline radio label activation')
        check(label_selection['state']['headlineAlgorithm'] == arrow_method
              and label_selection['state']['algorithms'] == triple['state']['algorithms'],
              'the headline radio label changes only the headline rather than toggling its curve checkbox')
        change('headline-algorithm', LEGACY)
        evaluate("document.getElementById('trd-algorithms-menu').open=false")

        check(triple['state']['headlineAlgorithm'] == LEGACY and triple['values'] == initial['values'],
              'adding comparison methods preserves the selected original OLS headline')
        for method in selected:
            before = snapshot()
            change('headline-algorithm', method)
            after = headline('headline method ' + method)
            check(before['svg']['marks'] == after['svg']['marks']
                  and {key: value for key, value in before['state'].items() if key != 'headlineAlgorithm'} == {key: value for key, value in after['state'].items() if key != 'headlineAlgorithm'}
                  and before['headline']['baseline'] == after['headline']['baseline'] and before['values']['weight-tb'] == after['values']['weight-tb'],
                  'switching headline to ' + method + ' preserves comparison curves, other controls, public baseline and model weights')
        removed = snapshot()['state']['headlineAlgorithm']
        before_removal = snapshot()
        toggle('algorithm', removed)
        reduced = headline('removing the headline method')
        check(len(reduced['state']['algorithms']) == 2 and reduced['state']['headlineAlgorithm'] == removed
              and removed not in reduced['state']['algorithms'] and reduced['values'] == before_removal['values']
              and removed in [item['key'] for item in reduced['headline']['options']],
              'removing a plotted method leaves the independent headline method and values unchanged')
        select_algorithms(selected)
        for view in ('scenarios', 'cache', 'compute', 'categories', 'growth'):
            before_headline = snapshot()
            select_algorithms([LEGACY])
            change('view', view)
            before = snapshot()['svg']['marks']
            select_algorithms(selected)
            after = snapshot()
            check(before == after['svg']['marks'] and after['state']['headlineAlgorithm'] == before_headline['state']['headlineAlgorithm']
                  and after['values'] == before_headline['values'],
                  view + ': curve algorithm choices leave annual analysis and the independent headline unchanged')
            change('headline-algorithm', selected[-1])
            headline(view + ' headline')
            check(evaluate("document.getElementById('trd-algorithms-menu').getClientRects().length>0"), view + ': algorithm selector remains available for the headline')
            check(before == snapshot()['svg']['marks'], view + ': changing the headline method leaves annual analysis marks unchanged')
        change('view', 'trend')

        for method in methods:
            select_algorithms([method])
            change('headline-algorithm', method)
            chart('output method ' + method)
        select_algorithms(selected)
        for category, keys in CATEGORIES.items():
            change('category', category)
            if len(keys) > 1:
                select_metrics(list(keys))
            chart('three methods, category ' + category, layout=True)
        # The ratio is method-independent; equivalent forecasts must merge without losing CSV mappings.
        merged = snapshot()
        forecast_marks = [mark for mark in merged['svg']['marks'] if mark.get('algorithm') != OBSERVED]
        check(bool(forecast_marks) and all(set(algorithms(mark)) == set(selected) for mark in forecast_marks),
              'identical cache-rate method forecasts share one curve with complete membership')
        rows = capture_csv()
        check_csv_values('merged cache-rate CSV', merged, rows)
        headers = set(rows[0]) if rows else set()
        algorithm_column = next((key for key in headers if '算法' in key), None)
        check(bool(algorithm_column) and '原始单位' in headers and '图表单位' in headers,
              'monthly CSV includes algorithms and both original and plotted units', sorted(headers))
        if algorithm_column:
            entries = {row[algorithm_column] for row in rows}
            check(all(any(method in value or names[method] in value for value in entries) for method in selected),
                  'CSV preserves each selected algorithm even when its curve is merged', sorted(entries))
            wanted, _ = expected_points(merged)
            check(len(rows) == len(wanted), 'CSV keeps one shared history row and every individual method forecast row', dict(rows=len(rows), expected=len(wanted)))

        change('category', 'tokens')
        select_metrics(list(CATEGORIES['tokens']))
        chart('maximum fifteen forecast curves', layout=True)
        rows = capture_csv()
        check_csv_values('fifteen-curve Token CSV', snapshot(), rows)
        check(len(rows) == len(expected_points(snapshot())[0]), 'five metrics by three methods CSV contains every forecast value exactly once')
        for scenario in 'ABC':
            change('scenario', scenario)
            chart('monthly scenario ratios preserved for ' + scenario)
        for team in (10, 1000, 100):
            change('team', team)
            chart('team scaling ' + str(team))
        change('category', 'rate')
        for window in (8, 12, 24):
            change('window', window)
            chart('processing-window scaling ' + str(window))
        select_scenarios(list('ABC'))
        chart('three scenarios by three rate algorithms', layout=True)
        change('category', 'tokens')
        select_metrics(list(CATEGORIES['tokens']))
        for period in ('observed', 'forecast'):
            change('range', period)
            chart('algorithm range ' + period, layout=True)
        change('range', 'custom')
        change('start', '2028-05-18')
        change('end', '2028-05-18')
        chart('single-date fifteen-series labels', layout=True)
        change('range', 'all')

        # Exercise uncertainty through real controls with all resource unit mappings.
        select_algorithms([ENSEMBLE,'naive'])
        select_metrics(['output_tokens_per_team_day'])
        before_intervals=snapshot()
        check(before_intervals['intervals']['visible'] and not before_intervals['svg']['bands'],
              'selecting the ensemble reveals an optional interval toggle without enabling it')
        evaluate("document.getElementById('trd-intervals').click()")
        settled()
        change('team',1000);change('window',8)
        for category,keys in CATEGORIES.items():
            change('category',category)
            select_metrics(list(keys))
            snap=chart('ensemble interval category '+category,layout=True)
            intervals('ensemble interval category '+category,snap,export=category!='cache')
            if category=='cache':
                check(not snap['intervals']['visible'],'assumed cache ratio offers no forecast uncertainty band')
        change('category','tokens');select_metrics(['output_tokens_per_team_day'])
        change('range','observed')
        observed=intervals('observed range excludes all uncertainty')
        check(not observed['intervals']['visible'] and not observed['svg']['bands'],
              'observed-only selection does not imply uncertainty in the official history')
        change('range','custom');change('start','2030-11-18');change('end','2030-11-18')
        single=chart('single-date ensemble intervals',layout=True)
        intervals('single-date ensemble intervals',single,export=True)
        check(all(band['tag']=='line' for band in single['svg']['bands']) and len(single['svg']['bands'])==2,
              'a single forecast date displays two visible vertical intervals')
        change('range','all')
        select_algorithms([LEGACY])
        unavailable=intervals('removing ensemble suppresses its intervals')
        check(not unavailable['intervals']['visible'] and not unavailable['svg']['bands'],
              'intervals cannot attach to a different selected algorithm')
        select_algorithms([ENSEMBLE]);change('view','scenarios')
        annual=intervals('archived annual view excludes uncertainty')
        check(not annual['intervals']['visible'] and not annual['svg']['bands'],
              'annual OLS reference charts do not inherit ensemble intervals')
        change('view','trend')
        intervals('return to ensemble intervals',export=True)
        note=evaluate("document.getElementById('trd-chart-note')?.textContent||document.getElementById('trd-chart-main').parentElement.textContent")
        check('名义' in note and '覆盖' in note and ('未' in note or '未经' in note),
              'visible interval explanation distinguishes nominal bands from validated long-horizon coverage',note)
        evaluate("document.getElementById('trd-intervals').click()")
        settled();change('team',100);change('window',24)

        # Exercise restored state through the actual browser initialization path.
        select_algorithms([LEGACY])
        change('headline-algorithm', selected[-1])
        persisted = snapshot()
        navigate()
        restored = headline('persisted single curve and independent headline selection')
        check(restored['state']['algorithms'] == persisted['state']['algorithms'] and restored['state']['headlineAlgorithm'] == persisted['state']['headlineAlgorithm']
              and restored['state']['headlineAlgorithm'] not in restored['state']['algorithms']
              and restored['values'] == persisted['values'], 'reload retains the headline method outside the single plotted curve and its endpoint values')
        select_algorithms([LEGACY])
        storage_key = evaluate("Object.keys(localStorage).find(k=>k.startsWith('" + ROOT + ":explorer-'))")
        if not storage_key:
            raise ValueError('Explorer did not persist its selection state')
        saved = snapshot()['state']
        for injected, expected_count, expected_set, label in (
                (methods, 3, set(methods), 'oversized persisted selection'),
                (['does_not_exist'], 1, {LEGACY}, 'invalid persisted selection'),
                ([], 1, {LEGACY}, 'empty persisted selection')):
            payload = dict(saved, algorithms=injected)
            evaluate('localStorage.setItem(' + json.dumps(storage_key) + ',' + json.dumps(json.dumps(payload)) + ')')
            navigate()
            got = snapshot()['state']['algorithms']
            check(len(got) == expected_count and len(set(got)) == len(got) and set(got) <= expected_set,
                  label + ': reload restores one to three valid methods', got)
            headline(label)

        for selected_methods, injected, expected, label in (
                (selected[1:], None, LEGACY, 'legacy saved state without a headline method'),
                (selected, 'does_not_exist', LEGACY, 'invalid saved headline method'),
                ([selected[0]], selected[-1], selected[-1], 'saved headline method outside selected curves')):
            payload = dict(saved, algorithms=selected_methods)
            if injected is None:
                payload.pop('headlineAlgorithm', None)
            else:
                payload['headlineAlgorithm'] = injected
            evaluate('localStorage.setItem(' + json.dumps(storage_key) + ',' + json.dumps(json.dumps(payload)) + ')')
            navigate()
            restored = headline(label)
            check(restored['state']['headlineAlgorithm'] == expected, label + ': initialization retains any valid headline method or uses original OLS for invalid or missing values')

        select_algorithms(selected)
        select_metrics(list(CATEGORIES['tokens']))
        chart('desktop fifteen-series labels', layout=True)
        browser.call('Emulation.setDeviceMetricsOverride', dict(width=320, height=1400, deviceScaleFactor=1, mobile=False))
        settled()
        chart('320px fifteen-series labels', layout=True)
        evaluate("document.getElementById('trd-algorithms-menu').open=true")
        settled()
        menu_geometry = evaluate("(()=>{const menu=document.getElementById('trd-algorithms-menu'),options=document.getElementById('trd-algorithm-options'),box=options.getBoundingClientRect(),rows=Array.from(options.querySelectorAll('.algorithm-option'));return {viewport:innerWidth,left:box.left,right:box.right,width:box.width,clientWidth:options.clientWidth,scrollWidth:options.scrollWidth,rows:rows.length,issues:rows.flatMap(row=>{const r=row.getBoundingClientRect(),checkbox=row.querySelector('input[data-algorithm]'),radio=row.querySelector('input[data-headline-choice]'),name=row.querySelector('.algorithm-name'),elements=[checkbox,radio,name];if(elements.some(e=>!e))return [{reason:'missing independent controls or algorithm name'}];const b=elements.map(e=>e.getBoundingClientRect());return b.some(e=>e.width<=0||e.height<=0||e.left<r.left-1||e.right>r.right+1)||b[0].right>b[1].left+1||b[1].right>b[2].left+1?[{reason:'row control overlap or overflow',text:row.textContent}]:[]})}})()")
        check(menu_geometry['rows'] == len(methods) and menu_geometry['width'] > 0
              and menu_geometry['left'] >= -1 and menu_geometry['right'] <= menu_geometry['viewport'] + 1
              and menu_geometry['scrollWidth'] <= menu_geometry['clientWidth'] + 1 and not menu_geometry['issues'],
              '320px unified menu fits the viewport with separate curve checkboxes, headline radios and readable algorithm names', menu_geometry)
        evaluate("document.getElementById('trd-algorithms-menu').open=false")
        touch_scroll()
        # Export a focused example; the three-algorithm limit is covered above.
        select_metrics(['output_tokens_per_team_day'])
        select_algorithms(['legacy_ols', 'damped_holt_hl365', 'logistic_cap4x'])
        change('headline-algorithm', 'damped_holt_hl365')
        browser.call('Emulation.setTouchEmulationEnabled', dict(enabled=False))
        chart('three-output-method presentation', layout=True)
        screenshot('dashboard_algorithms.png', 1280)
        screenshot('dashboard_algorithms_menu.png', 1280, menu=True)
        screenshot('dashboard_algorithms_mobile.png', 320)
        screenshot('dashboard_algorithms_menu_mobile.png', 320, menu=True)
        select_algorithms([ENSEMBLE]);change('headline-algorithm',ENSEMBLE)
        evaluate("document.getElementById('trd-intervals').click()")
        settled()
        chart('ensemble resource output screenshot',layout=True)
        intervals('ensemble resource output screenshot',export=True)
        screenshot('dashboard_ensemble.png',1280)
        check(all(sha(Path(path)) == digest for path, digest in original.items()), 'source and data hashes stay stable throughout algorithm QA')
        exceptions = [event['params'].get('exceptionDetails') for event in browser.events if event.get('method') == 'Runtime.exceptionThrown']
        check(not exceptions and not snapshot()['runtime'], 'no JavaScript errors throughout algorithm interactions', exceptions)
        report['status'] = 'passed' if all(item['status'] == 'passed' for item in report['checks']) else 'failed'
    except Exception as error:
        report.update(status='inconclusive' if isinstance(error, (TimeoutError, OSError)) else 'failed',
                      error=type(error).__name__ + ': ' + str(error))
    finally:
        if browser:
            browser.close()
    report['elapsed_seconds'] = time.monotonic() - started
    (HERE / 'algorithm_qa_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status=report['status'], checks=len(report['checks']), elapsed_seconds=report['elapsed_seconds'],
                          error=report.get('error'), failures=[item for item in report['checks'] if item['status'] == 'failed']), ensure_ascii=False))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
