"""Browser QA for the original daily research data and independent forecast views."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlparse, urlencode

from cdp_helper import Chrome
from validate_explorer import close, millis, sha

HERE = Path(__file__).resolve().parent
ROOT = 'raw-research-dashboard-v1'
RESOURCE_ROOT = 'team-resource-dashboard-30t-v2'
VIEWS = ('workdays', 'concurrency', 'tasks', 'output')
CONTROLS = ('view', 'method', 'concurrency-method', 'range', 'start', 'end')
ALLOWED_RETURNS = {'resource-dashboard-preview.html', 'team-resource-dashboard.html'}

SNAPSHOT = r"""(()=>{const root=document.getElementById('raw-research-dashboard-v1'),host=document.getElementById('raw-chart'),svg=host.querySelector('svg');
const result={state:JSON.parse(root.dataset.state||'{}'),ready:root.dataset.ready,
 controls:Object.fromEntries(CONTROL_NAMES.map(k=>[k,document.getElementById('raw-'+k)?.value])),
 readout:document.getElementById('raw-readout')?.textContent||'',runtime:window.__rawQaErrors||[],
 uncertainty:{checked:document.getElementById('raw-show-uncertainty')?.checked,visible:!!document.getElementById('raw-uncertainty-controls')?.getClientRects().length,note:document.getElementById('raw-chart-note')?.textContent||''},
 pageWidth:document.documentElement.scrollWidth,viewport:innerWidth};
if(!svg)return {...result,svg:null};const box=svg.getBoundingClientRect();
const texts=Array.from(svg.querySelectorAll('text'),e=>{const b=e.getBoundingClientRect();return {text:e.textContent,x:b.x,y:b.y,w:b.width,h:b.height}}).filter(b=>b.w&&b.h);
const clipping=texts.filter(b=>b.x<box.left-1||b.x+b.w>box.right+1||b.y<box.top-1||b.y+b.h>box.bottom+1);
const overlaps=[];for(let i=0;i<texts.length;i++)for(let j=i+1;j<texts.length;j++){const a=texts[i],b=texts[j],w=Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x),h=Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y);if(w>1.5&&h>1.5&&w*h>5)overlaps.push({first:a.text,second:b.text,w,h});}
const invalid=Array.from(svg.querySelectorAll('*')).flatMap(e=>Array.from(e.attributes).filter(a=>/^(d|points|x|y|x1|x2|y1|y2|cx|cy|width|height|transform)$/.test(a.name)&&/NaN|Infinity|undefined|null/.test(a.value)).map(a=>({tag:e.tagName,attribute:a.name,value:a.value})));
return {...result,svg:{...svg.dataset,width:box.width,height:box.height,clipping,overlaps,invalid,
 viewport:{width:host.clientWidth,scrollWidth:host.scrollWidth,overflow:getComputedStyle(host).overflowX},
 axes:Array.from(svg.querySelectorAll('[data-axis]'),e=>({...e.dataset})),
 marks:Array.from(svg.querySelectorAll('[data-value]'),e=>{const b=e.getBBox();return {...e.dataset,tag:e.tagName,cx:b.x+b.width/2,cy:b.y+b.height/2}}),
 bands:Array.from(svg.querySelectorAll('[data-uncertainty-band]'),e=>({...e.dataset,d:e.getAttribute('d'),length:e.getTotalLength()})),
 quantiles:Array.from(svg.querySelectorAll('[data-uncertainty-point]'),e=>({...e.dataset,cx:Number(e.getAttribute('cx')),cy:Number(e.getAttribute('cy'))})),
 paths:Array.from(svg.querySelectorAll('path[data-series],polyline[data-series]'),e=>({...e.dataset,d:e.getAttribute('d')||'',points:e.getAttribute('points')||'',fill:e.getAttribute('fill'),length:e.getTotalLength()}))}}})()"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--page', type=Path, required=True)
    parser.add_argument('--resource-page', type=Path, default=HERE/'resource-dashboard-preview.html')
    args = parser.parse_args()
    page, resource_page = args.page.resolve(), args.resource_page.resolve()
    data = json.loads((HERE/'raw_research_data.json').read_text())
    methods = [item['id'] for item in data['methods']]
    concurrency_methods = [item['id'] for item in data['concurrencyMethods']]
    protected = (page, resource_page, HERE/'team-resource-dashboard.html', HERE/'raw_research_data.json',
                 HERE/'dashboard_data.json', HERE/'dashboard_data.csv')
    original = {str(path): sha(path) for path in protected}
    report = dict(created_at_utc=datetime.now(timezone.utc).isoformat(), status='running',
                  method='Standalone Chrome with actual navigation, daily source checks, stacked geometry, CSV and touch gestures',
                  source_sha256=original, checks=[], snapshots=[], screenshots=[])
    browser = None
    started = time.monotonic()

    def check(ok, name, detail=None):
        report['checks'].append(dict(name=name, status='passed' if ok else 'failed', detail=detail))

    def source_rows(snap):
        controls = snap['controls']; view = controls['view']; metric = data['metrics'][view]
        method = controls['concurrency-method'] if view == 'concurrency' else controls['method']
        rows = [dict(date=day, values=values, phase='observed') for day, values in zip(metric['history']['dates'], metric['history']['values'])]
        forecast = metric['forecast'][method]
        rows += [dict(date=day, values=values, phase='forecast') for day, values in zip(forecast['dates'], forecast['values'])]
        period = controls['range']
        if period in ('observed', 'forecast'):
            rows = [row for row in rows if row['phase'] == period]
        elif period == 'custom':
            rows = [row for row in rows if controls['start'] <= row['date'] <= controls['end']]
        return metric, method, rows

    check(set(data['metrics']) == set(VIEWS), 'raw artifact exposes the four requested source charts')
    check(len(methods) == 6 and 'legacy_ols' in methods and 'ensemble_uncertainty' in methods,
          'six total-volume methods include the uncertainty ensemble and retain the original OLS default', methods)
    check(len(concurrency_methods) == 5 and 'legacy_log_complement' in concurrency_methods and 'ensemble_uncertainty' in concurrency_methods,
          'five concurrency-share methods include the uncertainty ensemble and use their independent default', concurrency_methods)
    check(data['metrics']['output']['windowDays'] == 14 and all(data['metrics'][key]['windowDays'] == 28 for key in VIEWS if key != 'output'),
          'raw output keeps its official 14-day window while other charts retain 28 days')
    check(len(data['metrics']['workdays']['series']) == 5 and len(data['metrics']['concurrency']['series']) == 9,
          'workdays contain five overlapping research groups and concurrency contains nine bins')

    archive=HERE.parent/'analysis/agentic_30t_forecast/workload/trend_models/results/original_style/ensemble_uncertainty'
    def archived_rows(name):
        with (archive/name).open(newline='',encoding='utf-8-sig') as source:return list(csv.DictReader(source))
    native={(row['metric'],row['date']):row for row in archived_rows('forecast.csv') if row['method']=='ensemble'}
    boundaries={(int(row['threshold']),row['date']):row for row in archived_rows('main_concurrency_bands.csv')}
    source_errors=[]
    for metric in VIEWS:
        uncertainty=data['metrics'][metric]['uncertainty']['ensemble_uncertainty']
        if uncertainty['calibrated'] is not False:source_errors.append((metric,'incorrect calibration claim'))
        for band in uncertainty['bands']:
            for point in band['points']:
                source=boundaries[(band['threshold'],point['date'])] if metric=='concurrency' else native[(metric,point['date'])]
                mapping={'lower95':'boundary_p025','lower80':'boundary_p10','center':'boundary_center','upper80':'boundary_p90','upper95':'boundary_p975'} if metric=='concurrency' else {'lower95':'lower95','lower80':'lower80','center':'median','upper80':'upper80','upper95':'upper95'}
                if any(not close(point[key],source[field]) for key,field in mapping.items()):source_errors.append((metric,band['id'],point['date']))
        if metric=='concurrency':
            old=data['metrics'][metric]['forecast']['legacy_log_complement']['values']
            new=data['metrics'][metric]['forecast']['ensemble_uncertainty']['values']
            if len(old)!=len(new) or any(not close(a,b) for left,right in zip(old,new) for a,b in zip(left,right)):
                source_errors.append((metric,'dual-threshold central composition changed'))
        else:
            forecast=data['metrics'][metric]['forecast']['ensemble_uncertainty']
            overall=next((i for i,series in enumerate(data['metrics'][metric]['series']) if series['id']=='Overall Research'),None)
            for day,values in zip(forecast['dates'],forecast['values']):
                center=values[overall] if metric=='workdays' else sum(values)
                if not close(center,native[(metric,day)]['median']):source_errors.append((metric,day,'source median total'))
    check(not source_errors,'ensemble raw medians and bounds match original 14/28-day sources while concurrency preserves its dual-threshold center',source_errors[:8])

    try:
        browser = Chrome(timeout=240)
        browser.call('Emulation.setDeviceMetricsOverride', dict(width=1280, height=1400, deviceScaleFactor=1, mobile=False))
        browser.call('Emulation.setEmulatedMedia', dict(features=[dict(name='prefers-color-scheme', value='light')]))
        context = None

        def evaluate(js):
            return browser.evaluate(js, context)

        def settled():
            evaluate('new Promise(r=>setTimeout(()=>requestAnimationFrame(()=>requestAnimationFrame(r)),140))')

        def ready(root_id):
            nonlocal context
            context = None
            while context is None:
                browser.call('Page.getFrameTree'); browser.enable_attached()
                for cid, info in list(browser.contexts.items()):
                    if not info.get('auxData', {}).get('isDefault'):
                        continue
                    try:
                        if browser.evaluate("document.getElementById('"+root_id+"')?.dataset.ready==='true'", cid):
                            context = cid; break
                    except RuntimeError:
                        pass
                if context is None:
                    browser.remaining(); time.sleep(.05)
            evaluate("window.__rawQaErrors=[];addEventListener('error',e=>window.__rawQaErrors.push(e.message));addEventListener('unhandledrejection',e=>window.__rawQaErrors.push(String(e.reason)))")
            settled()

        def navigate(url, root_id=ROOT):
            browser.call('Page.navigate', dict(url=url)); ready(root_id)

        def click_navigation(selector, root_id):
            evaluate('document.querySelector('+json.dumps(selector)+').click()'); ready(root_id)

        def change(name, value, prefix='raw-'):
            if prefix == 'trd-' and name == 'headline-algorithm':
                selector = 'input[data-headline-choice][value='+json.dumps(str(value))+']'
                got = evaluate('(()=>{document.getElementById("trd-algorithms-menu").open=true;const e=document.querySelector('+json.dumps(selector)+');if(!e)return null;e.click();return e.checked?e.value:null})()')
            else:
                got = evaluate('(()=>{const e=document.getElementById('+json.dumps(prefix+name)+');if(!e)return null;e.value='+json.dumps(str(value))+';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));return e.value})()')
            if got != str(value):
                raise ValueError('Rejected control '+prefix+name+'='+str(value))
            settled()

        def snapshot():
            return evaluate(SNAPSHOT.replace('CONTROL_NAMES', json.dumps(CONTROLS)))

        def chart(label, layout=False):
            snap = snapshot(); svg = snap['svg']; metric, method, rows = source_rows(snap)
            check(bool(svg) and not snap['runtime'] and not svg['invalid'], label+': finite chart without JavaScript errors', snap['runtime'])
            if not svg:
                return snap
            stacked = snap['controls']['view'] != 'workdays'; divisor = float(metric['divisor'])
            wanted = {}
            for row in rows:
                bottom = 0.0
                for descriptor, raw in zip(metric['series'], row['values']):
                    value = float(raw)
                    wanted[(descriptor['id'], row['date'])] = dict(value=value, phase=row['phase'], bottom=bottom, top=bottom+value)
                    bottom += value
            actual = {(mark.get('series'), mark.get('date')): mark for mark in svg['marks']}
            issues = []
            if set(actual) != set(wanted) or len(actual) != len(svg['marks']):
                issues.append(dict(reason='daily/monthly source membership mismatch', missing=list(set(wanted)-set(actual))[:4], extra=list(set(actual)-set(wanted))[:4]))
            axes = svg['axes']
            if len(axes) != 1 or not close(axes[0].get('min', math.nan), 0) or not close(axes[0].get('divisor', math.nan), divisor):
                issues.append('expected one actual-unit zero-start axis')
            else:
                axis = axes[0]
                x0, y0, width, height = (float(svg[key]) for key in ('plotX','plotY','plotWidth','plotHeight'))
                t0, t1 = float(svg['timeMin']), float(svg['timeMax'])
                for identity, expected in wanted.items():
                    mark = actual.get(identity)
                    if mark is None:
                        continue
                    plot = expected['value']/divisor
                    xx = x0+(millis(identity[1])-t0)/(t1-t0)*width if t1 != t0 else x0+width/2
                    yy = y0+height-(expected['top'] if stacked else expected['value'])/divisor/float(axis['max'])*height
                    if not close(mark['value'], expected['value']) or not close(mark['plotValue'], plot) or mark.get('phase') != expected['phase'] or abs(mark['cx']-xx)>.15 or abs(mark['cy']-yy)>.15:
                        issues.append(dict(identity=identity, expected=expected, actual=mark))
                    if stacked and (not close(mark.get('stackBottom', math.nan), expected['bottom']) or not close(mark.get('stackTop', math.nan), expected['top'])):
                        issues.append(dict(reason='stack boundaries differ from cumulative source values', identity=identity))
                if snap['controls']['view'] == 'concurrency':
                    if not close(axis['max'], 100) or any(not math.isclose(sum(row['values']), 1, abs_tol=1e-6) for row in rows):
                        issues.append('nine concurrency shares do not total 100% on a zero-to-100 axis')
            check(not issues, label+': raw source values, original dates and stack geometry match', issues[:4])
            check(not rows or any(path['length']>0 for path in svg['paths']) or len(rows)==1,
                  label+': chart draws visible source trajectories')
            if layout:
                check(not svg['clipping'] and not svg['overlaps'], label+': labels remain inside the plot without collisions',
                      dict(clipping=svg['clipping'][:4], overlaps=svg['overlaps'][:4]))
                check(snap['pageWidth']<=snap['viewport']+1 and (svg['viewport']['scrollWidth']<=svg['viewport']['width']+1 or svg['viewport']['overflow'] in ('auto','scroll')),
                      label+': any horizontal scrolling stays inside the chart', dict(page=snap['pageWidth'], viewport=snap['viewport'], chart=svg['viewport']))
            report['snapshots'].append(dict(label=label, controls=snap['controls'], dates=len(rows), series=len(metric['series']), marks=len(svg['marks']), method=method))
            return snap

        def uncertainty(label,snap=None):
            snap=snapshot() if snap is None else snap
            metric,method,rows=source_rows(snap);view=snap['controls']['view']
            selected=metric.get('uncertainty',{}).get(method)
            dates={row['date'] for row in rows if row['phase']=='forecast'}
            expected={(band['id'],point['date']):point for band in (selected['bands'] if selected and snap['state'].get('showUncertainty') else []) for point in band['points'] if point['date'] in dates}
            actual={(point['bandSeries'],point['date']):point for point in snap['svg']['quantiles']}
            issues=[]
            if set(actual)!=set(expected) or len(actual)!=len(snap['svg']['quantiles']):issues.append('nominal interval point membership differs')
            svg=snap['svg'];divisor=float(metric['divisor']);axismax=float(svg['axes'][0]['max'])
            x0,y0,width,height=(float(svg[key]) for key in ('plotX','plotY','plotWidth','plotHeight'))
            t0,t1=float(svg['timeMin']),float(svg['timeMax'])
            def xy(day,value):return (x0+(millis(day)-t0)/(t1-t0)*width if t1!=t0 else x0+width/2,y0+height-value/divisor/axismax*height)
            for identity,point in expected.items():
                got=actual.get(identity)
                if not got:continue
                xx,yy=xy(identity[1],point['center'])
                if any(not close(got[key],point[key]) for key in ('lower95','lower80','center','upper80','upper95')) or not close(got['divisor'],divisor) or abs(got['cx']-xx)>.15 or abs(got['cy']-yy)>.15:
                    issues.append(dict(identity=identity,reason='raw bounds or center geometry differ'))
                if point['upper95']/divisor>axismax+1e-8:issues.append(dict(identity=identity,reason='upper interval clipped'))
            expected_bands={(key[0],level) for key in expected for level in ('80','95')}
            actual_bands={(band['bandSeries'],band['uncertaintyBand']):band for band in svg['bands']}
            if set(actual_bands)!=expected_bands:issues.append('missing or unexpected interval paths')
            for identity,band in actual_bands.items():
                points=[point for (series,day),point in expected.items() if series==identity[0]]
                wanted=[xy(point['date'],point[side+identity[1]]) for point in points for side in ('lower','upper')]
                numbers=[float(value) for value in re.findall(r'-?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][+-]?\d+)?',band['d'])]
                vertices=list(zip(numbers[::2],numbers[1::2]))
                if band['method']!='ensemble_uncertainty' or len(vertices)!=len(wanted) or any(not any(abs(x-a)<=.15 and abs(y-b)<=.15 for a,b in vertices) for x,y in wanted):
                    issues.append(dict(identity=identity,reason='band path does not use source quantile geometry'))
            check(not issues,label+': nominal bounds and polygons use correct daily window, scope, original units and axis geometry',issues[:8])
            if selected:
                check('名义' in snap['uncertainty']['note'] and '未经长期覆盖率校准' in snap['uncertainty']['note'],
                      label+': nominal uncertainty is explicitly identified as uncalibrated')
            return snap

        def capture_csv():
            text = evaluate("(async()=>{const create=URL.createObjectURL,revoke=URL.revokeObjectURL,click=HTMLAnchorElement.prototype.click;let blob;URL.createObjectURL=b=>{blob=b;return 'blob:raw-qa-csv'};URL.revokeObjectURL=()=>{};HTMLAnchorElement.prototype.click=()=>{};try{document.getElementById('raw-download').click();return blob?await blob.text():null}finally{URL.createObjectURL=create;URL.revokeObjectURL=revoke;HTMLAnchorElement.prototype.click=click}})()")
            return list(csv.DictReader(io.StringIO((text or '').lstrip('\ufeff'))))

        def check_csv(label, snap):
            metric, method, rows = source_rows(snap); exported = capture_csv()
            expected = {(series['id'], row['date']):(float(value), row['phase']) for row in rows for series,value in zip(metric['series'],row['values'])}
            actual = {}; issues = []
            for row in exported:
                key = (row.get('系列ID'), row.get('日期'))
                if key in actual:
                    issues.append(dict(reason='duplicated CSV row', key=key))
                actual[key] = row; source = expected.get(key)
                if source and (not close(row['原始值'], source[0]) or not close(row['图表值'], source[0]/float(metric['divisor'])) or row['原始单位']!=metric['unit'] or row['图表单位']!=metric['display'] or row['阶段']!=source[1] or row['算法ID']!=('observed' if source[1]=='observed' else method)):
                    issues.append(dict(key=key, row=row, expected=source))
            if set(actual) != set(expected):
                issues.append(dict(reason='CSV daily/monthly membership differs', rows=len(actual), expected=len(expected)))
            check(not issues, label+': downloaded CSV preserves every source value and its actual units', issues[:4])

        def click_date(day):
            position = evaluate("(()=>{const host=document.getElementById('raw-chart'),svg=host.querySelector('svg'),point=svg.querySelector('[data-date='+"+json.dumps(json.dumps(day))+"+']'),b=point.getBBox();host.scrollIntoView({block:'center'});host.scrollLeft=Math.max(0,b.x+b.width/2-host.clientWidth/2);const r=svg.getBoundingClientRect();return {x:r.left+b.x+b.width/2,y:r.top+Number(svg.dataset.plotY)+Number(svg.dataset.plotHeight)/2}})()")
            browser.call('Input.dispatchMouseEvent', dict(type='mousePressed',button='left',clickCount=1,**position))
            browser.call('Input.dispatchMouseEvent', dict(type='mouseReleased',button='left',clickCount=1,**position)); settled()
            readout = snapshot()['readout']; check(day in readout,'pointer readout retains the actual source date '+day,readout)

        def screenshot(filename, width):
            browser.call('Emulation.setDeviceMetricsOverride',dict(width=width,height=1200,deviceScaleFactor=1,mobile=False)); settled()
            evaluate("window.scrollTo(0,0);document.getElementById('raw-chart').scrollLeft=0")
            height = evaluate("Math.ceil(document.getElementById('"+ROOT+"').getBoundingClientRect().bottom)+24")
            browser.call('Emulation.setDeviceMetricsOverride',dict(width=width,height=max(height,700),deviceScaleFactor=1,mobile=False)); settled()
            path = HERE/filename; browser.screenshot(path,full_page=True)
            report['screenshots'].append(dict(file=filename,width=width,sha256=sha(path)))

        def touch_scroll():
            browser.call('Emulation.setTouchEmulationEnabled',dict(enabled=True,maxTouchPoints=1))
            browser.call('Emulation.setDeviceMetricsOverride',dict(width=320,height=1000,deviceScaleFactor=1,mobile=True)); settled()
            p = evaluate("(()=>{const h=document.getElementById('raw-chart');h.scrollIntoView({block:'center'});h.scrollLeft=0;const b=h.getBoundingClientRect();return{x:b.left+h.clientWidth*.8,y:Math.max(30,Math.min(innerHeight-30,b.top+h.clientHeight/2)),initial:h.scrollLeft,overflow:h.scrollWidth-h.clientWidth}})()")
            point = dict(x=p['x'],y=p['y'],id=1,radiusX=2,radiusY=2,force=1)
            browser.call('Input.dispatchTouchEvent',dict(type='touchStart',touchPoints=[point]))
            for dx in (30,65,100,140):
                browser.call('Input.dispatchTouchEvent',dict(type='touchMove',touchPoints=[dict(point,x=p['x']-dx)])); evaluate('new Promise(r=>setTimeout(r,45))')
            browser.call('Input.dispatchTouchEvent',dict(type='touchEnd',touchPoints=[])); settled()
            offset = evaluate("document.getElementById('raw-chart').scrollLeft")
            check(p['overflow']>0 and offset>p['initial']+8,'320px real touch gesture horizontally scrolls the raw chart',dict(**p,final=offset))
            browser.call('Emulation.setTouchEmulationEnabled',dict(enabled=False))

        # Enter through the actual resource-page button with a nondefault state.
        navigate(resource_page.as_uri(), RESOURCE_ROOT)
        for name,value in (('scenario','B'),('team',1000),('category','compute'),('headline-algorithm','naive')):
            change(name,value,'trd-')
        evaluate("document.querySelector('input[data-metric=\"prefill_eflop_per_team_day\"]').click()")
        saved_resource = evaluate("JSON.parse(document.getElementById('"+RESOURCE_ROOT+"').dataset.state)")
        target = evaluate("document.getElementById('trd-raw-link').href")
        check(Path(urlparse(target).path).name==page.name and 'resource-state=' in urlparse(target).fragment,
              'resource-page button links to raw views with an explicit restorable state', target)
        evaluate("Object.keys(localStorage).filter(k=>k.startsWith('"+RESOURCE_ROOT+"')).forEach(k=>localStorage.removeItem(k))")
        click_navigation('#trd-raw-link',ROOT)
        default = chart('raw default workdays',layout=True)
        check(default['uncertainty']['checked'] is False and not default['uncertainty']['visible'] and not default['svg']['bands'],
              'raw uncertainty is opt-in and unavailable for the default historical OLS method')
        check(default['controls']['view']=='workdays' and default['controls']['method']=='legacy_ols' and default['controls']['concurrency-method']=='legacy_log_complement',
              'raw page starts with original methods and a separate workdays view',default['controls'])
        available = evaluate("Object.fromEntries(['view','method','concurrency-method'].map(k=>[k,Array.from(document.getElementById('raw-'+k).options,e=>e.value)]))")
        check(set(available['view'])==set(VIEWS) and set(available['method'])==set(methods) and set(available['concurrency-method'])==set(concurrency_methods),
              'all four views and their independent algorithms are selectable',available)
        for view in VIEWS:
            change('view',view)
            choices = concurrency_methods if view=='concurrency' else methods
            control = 'concurrency-method' if view=='concurrency' else 'method'
            for method in choices:
                change(control,method); chart(view+' / '+method,layout=True)
            change(control,'legacy_log_complement' if view=='concurrency' else 'legacy_ols')
            snap = chart(view+' original full series'); check_csv(view,snap)
            metric = data['metrics'][view]
            for period in ('observed','forecast'):
                change('range',period); chart(view+' '+period)
                # Daily dates can be less than one physical pixel apart over five
                # years. Use their observed interval for an unambiguous real click.
                if period=='observed':
                    click_date(metric['history']['dates'][len(metric['history']['dates'])//2])
            change('range','custom')
            day = metric['history']['dates'][len(metric['history']['dates'])//2]
            change('start',day); change('end',day); chart(view+' single actual observation',layout=True)
            change('range','all')
            screenshot('raw_dashboard_'+view+'.png',1280)
        for view in VIEWS:
            change('view',view)
            change('concurrency-method' if view=='concurrency' else 'method','ensemble_uncertainty')
            if not snapshot()['state'].get('showUncertainty'):
                evaluate("document.getElementById('raw-show-uncertainty').click()");settled()
            snap=chart('ensemble nominal intervals '+view,layout=True)
            uncertainty('ensemble nominal intervals '+view,snap)
            change('range','observed')
            historical=uncertainty('ensemble observed range '+view)
            check(not historical['svg']['bands'] and not historical['svg']['quantiles'],
                  view+': uncertainty never attaches to original observations')
            change('range','all')
            change('concurrency-method' if view=='concurrency' else 'method','legacy_log_complement' if view=='concurrency' else 'legacy_ols')
            unavailable=uncertainty('non-ensemble excludes intervals '+view)
            check(not unavailable['uncertainty']['visible'] and not unavailable['svg']['bands'],
                  view+': intervals disappear when another algorithm is selected')
        change('view','output');change('method','ensemble_uncertainty')
        chart('ensemble raw output screenshot',layout=True);uncertainty('ensemble raw output screenshot')
        screenshot('raw_dashboard_ensemble.png',1280)
        evaluate("document.getElementById('raw-show-uncertainty').click()");settled()
        change('method',methods[-1]); change('view','concurrency'); change('concurrency-method',concurrency_methods[-1])
        change('view','workdays'); check(snapshot()['controls']['method']==methods[-1],'volume method selection survives switching to concurrency and back')
        change('view','concurrency'); check(snapshot()['controls']['concurrency-method']==concurrency_methods[-1],'concurrency method selection is independent of volume methods')
        change('concurrency-method','legacy_log_complement')
        browser.call('Emulation.setDeviceMetricsOverride',dict(width=320,height=1400,deviceScaleFactor=1,mobile=False)); settled()
        for view in VIEWS:
            change('view',view); chart('320px '+view,layout=True)
            dates=data['metrics'][view]['history']['dates']; day=dates[len(dates)//2]
            change('range','custom'); change('start',day); change('end',day)
            single=chart('320px '+view+' single observation',layout=True)
            visible=evaluate("(()=>{const h=document.getElementById('raw-chart'),svg=h.querySelector('svg'),r=h.getBoundingClientRect();return {scrollLeft:h.scrollLeft,bars:Array.from(svg.querySelectorAll('[data-shape=single-date-stack]'),e=>{const b=e.getBoundingClientRect();return {left:b.left-r.left,right:b.right-r.left,height:b.height}})}})()")
            check(single['svg']['width']<=single['svg']['viewport']['width']+1 and visible['scrollLeft']==0
                  and all(0<=mark['cx']<=single['svg']['viewport']['width'] for mark in single['svg']['marks'])
                  and (view=='workdays' or bool(visible['bars']) and all(0<=bar['left']<bar['right']<=single['svg']['viewport']['width']+1 for bar in visible['bars'])),
                  '320px '+view+': a single date is visible immediately without horizontal scrolling',visible)
            change('range','all')
        change('method','legacy_ols'); touch_scroll(); screenshot('raw_dashboard_mobile.png',320)

        back = evaluate("document.getElementById('raw-back').href")
        check(Path(urlparse(back).path).name==resource_page.name and Path(urlparse(back).path).parent==resource_page.parent,
              'raw back link uses the whitelisted resource entry in the same folder',back)
        click_navigation('#raw-back',RESOURCE_ROOT)
        restored = evaluate("JSON.parse(document.getElementById('"+RESOURCE_ROOT+"').dataset.state)")
        check(restored==saved_resource,'actual return navigation restores the exact resource state without localStorage',dict(expected=saved_resource,actual=restored))

        # The fragment entry is also allowed; arbitrary external return URLs are rejected.
        fragment = HERE/'team-resource-dashboard.html'
        navigate(fragment.as_uri(),RESOURCE_ROOT)
        click_navigation('#trd-raw-link',ROOT)
        fragment_back = evaluate("document.getElementById('raw-back').href")
        check(Path(urlparse(fragment_back).path).name==fragment.name,'fragment entry returns to the fragment rather than changing the entry file',fragment_back)
        hostile = page.as_uri()+'#'+urlencode({'return':'https://example.invalid/redirect','resource-state':json.dumps(saved_resource)})
        navigate(hostile)
        safe = evaluate("document.getElementById('raw-back').href")
        check(urlparse(safe).scheme=='file' and Path(urlparse(safe).path).name in ALLOWED_RETURNS and Path(urlparse(safe).path).parent==HERE,
              'untrusted return URL falls back to a local whitelisted resource file',safe)
        check(all(sha(Path(path))==digest for path,digest in original.items()),'source and data hashes remain unchanged throughout raw QA')
        exceptions = [event['params'].get('exceptionDetails') for event in browser.events if event.get('method')=='Runtime.exceptionThrown']
        check(not exceptions and not snapshot()['runtime'],'no JavaScript errors throughout raw charts, downloads and navigation',exceptions)
        report['status']='passed' if all(item['status']=='passed' for item in report['checks']) else 'failed'
    except Exception as error:
        report.update(status='inconclusive' if isinstance(error,(TimeoutError,OSError)) else 'failed',error=type(error).__name__+': '+str(error))
    finally:
        if browser:browser.close()
    report['elapsed_seconds']=time.monotonic()-started
    (HERE/'raw_qa_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=report['status'],checks=len(report['checks']),elapsed_seconds=report['elapsed_seconds'],error=report.get('error'),failures=[item for item in report['checks'] if item['status']=='failed']),ensure_ascii=False))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
