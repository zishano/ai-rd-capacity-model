"""Focused Chrome QA for the standalone metric explorer; no dependencies installed."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from cdp_helper import Chrome

HERE=Path(__file__).resolve().parent
ROOT='team-resource-dashboard-30t-v2'
CONTROLS=('scenario','team','window','model','view','category','primary','range','start','end','detail-mode')
VIEWS=('trend','scenarios','cache','compute','categories','growth')
CATEGORIES={
 'tokens':('output_tokens_per_team_day','input_tokens_per_team_day','cached_input_tokens_per_team_day','uncached_input_tokens_per_team_day','total_tokens_per_team_day'),
 'compute':('eflop_per_team_day','prefill_eflop_per_team_day','decode_eflop_per_team_day'),
 'rate':('compute_pflops_window',),'agent_time':('agent_hours_per_team_day',),
 'agent_scale':('mean_online_agent_equivalents',),'tasks':('task_starts_per_team_day',),
 'cache':('prefix_cache_hit_rate',)}
DIVISORS={**dict.fromkeys(CATEGORIES['tokens'],1e8),'agent_hours_per_team_day':1e4,'prefix_cache_hit_rate':.01}
TOP_FIELDS={'input-tokens':'input_tokens_per_team_day','output-tokens':'output_tokens_per_team_day',
 'cached-input-tokens':'cached_input_tokens_per_team_day','uncached-input-tokens':'uncached_input_tokens_per_team_day',
 'total-tokens':'total_tokens_per_team_day','agent-hours':'agent_hours_per_team_day','agent-equivalents':'mean_online_agent_equivalents',
 'tasks':'task_starts_per_team_day','compute-eflop':'eflop_per_team_day','prefill-eflop':'prefill_eflop_per_team_day','decode-eflop':'decode_eflop_per_team_day'}
RATES={'prefix_cache_hit_rate','tail_share','output_share'}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def millis(day):return datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()*1000
def close(a,b):return math.isfinite(float(a)) and math.isclose(float(a),float(b),rel_tol=1e-8,abs_tol=1e-7)

def annual_window_errors(data):
    """Check the new output window against independent raw-chart and old ratio sources."""
    errors=[]
    raw=json.loads((HERE/'raw_research_data.json').read_text())
    output=raw['metrics']['output']
    forecast=output['forecast']['legacy_ols']
    native={day:math.fsum(values) for day,values in zip(forecast['dates'],forecast['values'])}
    reference=json.loads((HERE/'qa_reference_forecasts_v1.json').read_text())
    scaled={'input_tokens_per_team_day','cached_input_tokens_per_team_day','uncached_input_tokens_per_team_day',
            'output_tokens_per_team_day','total_tokens_per_team_day','eflop_per_team_day',
            'prefill_eflop_per_team_day','decode_eflop_per_team_day','compute_pflops_24h'}
    if len(data['rows'])!=15 or output['windowDays']!=14:errors.append({'reason':'annual row count or native output window'})
    for old in reference['rows']:
        if old['year']<2027:continue
        actual=next((row for row in data['rows'] if (row['year'],row['scenario'])==(old['year'],old['scenario'])),{})
        expected_output=native[old['date']]*old['researchers']
        factor=expected_output/old['output_tokens_per_team_day']
        for key,value in old.items():
            expected=value*factor if key in scaled else value
            current=actual.get(key)
            ok=current is not None and (close(current,expected) if isinstance(expected,(int,float)) else current==expected)
            if not ok:errors.append(dict(year=old['year'],scenario=old['scenario'],field=key,expected=expected,actual=current))
    source=HERE.parent/'output_openai_researcher_forecast/official_data/output_tokens_14d.csv'
    with source.open(newline='',encoding='utf-8-sig') as stream:official=list(csv.DictReader(stream))
    latest=max(row['date'] for row in official)
    baseline=math.fsum(float(row['value']) for row in official if row['date']==latest)
    metadata=data['baseline_metadata']['output_14d']
    if metadata['date']!=latest or metadata['rolling_window_days']!=14 or not close(metadata['value_per_researcher_day'],baseline):
        errors.append({'reason':'baseline does not match native official 14-day observation'})
    for row in data['rows']:
        if row['year']==2026 and not close(row['output_tokens_per_team_day'],baseline*row['researchers']):
            errors.append(dict(year=2026,scenario=row['scenario'],field='output_tokens_per_team_day'))
    return errors

SNAPSHOT=r"""(()=>{const root=document.getElementById('team-resource-dashboard-30t-v2'),svg=root.querySelector('#trd-chart-main svg');
const controls=Object.fromEntries(CONTROL_NAMES.map(k=>[k,document.getElementById('trd-'+k)?.value]));
const result={controls,state:JSON.parse(root.dataset.state||'{}'),ready:root.dataset.ready,
 metricOptions:Array.from(root.querySelectorAll('#trd-metric-options [data-metric]'),e=>({key:e.dataset.metric,checked:e.checked,disabled:e.disabled})),
 scenarioOptions:Array.from(root.querySelectorAll('#trd-scenario-options [data-scenario]'),e=>({key:e.dataset.scenario,checked:e.checked,disabled:e.disabled})),
 primaryOptions:Array.from(document.getElementById('trd-primary').options,e=>e.value),
 values:Object.fromEntries(Array.from(root.querySelectorAll('[data-testid][data-value]'),e=>[e.dataset.testid,Number(e.dataset.value)])),
 headline:{algorithm:root.querySelector('[data-headline-algorithm]')?.dataset.headlineAlgorithm,date:root.querySelector('[data-headline-date]')?.dataset.headlineDate,
 sourceAlgorithm:root.querySelector('[data-source-algorithm]')?.dataset.sourceAlgorithm,sourceName:root.querySelector('[data-testid="source-algorithm-name"]')?.textContent,
 options:Array.from(root.querySelectorAll('#trd-algorithm-options input[data-headline-choice]'),e=>({key:e.value,name:e.dataset.algorithmName,checked:e.checked,disabled:e.disabled,type:e.type,group:e.name})),
 legacySelectorPresent:!!document.getElementById('trd-headline-algorithm'),name:root.querySelector('[data-testid="headline-algorithm-name"]')?.textContent,
 baseline:Array.from(root.querySelectorAll('[data-testid="baseline-output"],[data-testid="baseline-activity"],[data-testid="model-summary"]'),e=>e.textContent),
 numericCounts:Array.from(root.querySelectorAll('[data-testid][data-value]')).reduce((counts,e)=>{counts[e.dataset.testid]=(counts[e.dataset.testid]||0)+1;return counts},{})},
 error:document.querySelector('#trd-error')?.hidden?'':document.querySelector('#trd-error')?.textContent||'',
 readout:document.querySelector('#trd-chart-readout')?.textContent||'',runtime:window.__qaErrors||[]};
result.intervals={checked:document.getElementById('trd-intervals')?.checked,visible:!!document.getElementById('trd-intervals-field')?.getClientRects().length,
 text:document.getElementById('trd-intervals-field')?.textContent||''};
if(!svg)return {...result,svg:null};
const box=svg.getBoundingClientRect(),texts=Array.from(svg.querySelectorAll('text')).map(e=>{const b=e.getBoundingClientRect();return {text:e.textContent,x:b.x,y:b.y,w:b.width,h:b.height}}).filter(b=>b.w&&b.h);
const clipping=Array.from(svg.querySelectorAll('text,tspan')).flatMap(e=>{const b=e.getBoundingClientRect();return b.width&&b.height&&(b.left<box.left-1||b.right>box.right+1||b.top<box.top-1||b.bottom>box.bottom+1)?[{text:e.textContent,left:b.left-box.left,right:b.right-box.right,top:b.top-box.top,bottom:b.bottom-box.bottom}]:[]});
const overlaps=[];for(let i=0;i<texts.length;i++)for(let j=i+1;j<texts.length;j++){const a=texts[i],b=texts[j],w=Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x),h=Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y);if(w>1.5&&h>1.5&&w*h>5)overlaps.push({first:a.text,second:b.text,w,h});}
const invalid=Array.from(svg.querySelectorAll('*')).flatMap(e=>Array.from(e.attributes).filter(a=>/^(d|points|x|y|x1|x2|y1|y2|cx|cy|width|height|transform)$/.test(a.name)&&/NaN|Infinity|undefined|null/.test(a.value)).map(a=>({tag:e.tagName,attribute:a.name,value:a.value})));
return {...result,svg:{...svg.dataset,width:box.width,height:box.height,clipping,overlaps,invalid,
 labels:Array.from(svg.querySelectorAll('text.point-label[data-label="quarterly"]'),e=>{const b=e.getBBox();return {...e.dataset,text:e.textContent,hasValue:e.hasAttribute('data-value'),box:{x:b.x,y:b.y,w:b.width,h:b.height}}}),
 guides:Array.from(svg.querySelectorAll('line.point-label-guide'),e=>({...e.dataset,x1:Number(e.getAttribute('x1')),y1:Number(e.getAttribute('y1')),x2:Number(e.getAttribute('x2')),y2:Number(e.getAttribute('y2'))})),
 viewport:{width:document.getElementById('trd-chart-main').clientWidth,scrollWidth:document.getElementById('trd-chart-main').scrollWidth,overflowX:getComputedStyle(document.getElementById('trd-chart-main')).overflowX},
 axes:Array.from(svg.querySelectorAll('[data-axis]'),e=>{const line=e.tagName==='line'?e:e.querySelector('line[data-axis-line]')||e.querySelector('line'),b=line?.getBBox();return {...e.dataset,line:b?{x:b.x,y:b.y,w:b.width,h:b.height}:null};}),
 marks:Array.from(svg.querySelectorAll('[data-value]'),e=>{const b=e.getBBox();return {...e.dataset,tag:e.tagName,x:b.x,y:b.y,w:b.width,h:b.height,cx:b.x+b.width/2,cy:b.y+b.height/2};}),
 bands:Array.from(svg.querySelectorAll('[data-interval]'),e=>({...e.dataset,tag:e.tagName,points:e.points?Array.from({length:e.points.numberOfItems},(_,i)=>{const p=e.points.getItem(i);return [p.x,p.y]}):[],line:e.tagName==='line'?[Number(e.getAttribute('x1')),Number(e.getAttribute('y1')),Number(e.getAttribute('x2')),Number(e.getAttribute('y2'))]:null})),
 curves:Array.from(svg.querySelectorAll('polyline[data-series],path[data-series]'),e=>({...e.dataset,length:e.getTotalLength(),points:e.points?Array.from({length:e.points.numberOfItems},(_,i)=>{const p=e.points.getItem(i);return [p.x,p.y]}):[]}))}}})()"""

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--preview',type=Path,required=True)
    args=parser.parse_args();preview=args.preview.resolve();data=json.loads((HERE/'dashboard_data.json').read_text())
    algorithms=json.loads((HERE/'algorithm_forecasts.json').read_text())
    model_config=json.loads((HERE.parent/'config/models/moe_30t.json').read_text())
    original={str(p):sha(p) for p in (preview,HERE/'team-resource-dashboard.html',HERE/'dashboard_data.json',HERE/'dashboard_data.csv',HERE/'algorithm_forecasts.json')}
    report=dict(created_at_utc=datetime.now(timezone.utc).isoformat(),status='running',method='Chrome with actual standalone DOM events, numeric/geometric source checks and responsive views',
                source_sha256=original,checks=[],snapshots=[],layouts=[],screenshots=[])
    started=time.monotonic();browser=None
    def check(ok,name,detail=None):report['checks'].append(dict(name=name,status='passed' if ok else 'failed',detail=detail))
    changed=annual_window_errors(data)
    check(not changed,'annual outputs match native 14-day observations/OLS; resource ratios and 28-day activity remain unchanged',changed)
    collections=list(data.get('monthly_trends',{}).values())+[data.get('monthly_resources',[]),data.get('monthly_tasks',[])]
    def rows_for(field,scenario):
        source='eflop_per_team_day' if field=='compute_pflops_window' else field
        for rows in collections:
            selected=[r for r in rows if r.get('scenario')==scenario and source in r]
            if selected:return sorted(selected,key=lambda r:r['date'])
        return []
    def raw(row,field,c,method='legacy_ols'):
        source='eflop_per_team_day' if field=='compute_pflops_window' else field
        value=float(row[source])
        # Default monthly OLS is editable independently of the frozen annual
        # reference. Annual rows use row_type, never the monthly phase marker.
        if row.get('phase')=='forecast' and field not in RATES:
            forecast=algorithms['forecasts'][method];team=float(row.get('researchers',100))
            if field in ('agent_hours_per_team_day','mean_online_agent_equivalents'):
                value=float(forecast['workdays'][row['date']])*8*team
                if field=='mean_online_agent_equivalents':value/=24
            elif field=='task_starts_per_team_day':value=float(forecast['tasks'][row['date']])*team
            else:
                output=float(forecast['output'][row['date']])*team
                value=output if field=='output_tokens_per_team_day' else value/float(row['output_tokens_per_team_day'])*output
        value*=1 if field in RATES else float(c['team'])/float(row.get('researchers',100))
        if field=='compute_pflops_window':value*=1000/(float(c['window'])*3600)
        return value
    def filtered(rows,c):
        if c['range'] in ('observed','forecast'):return [r for r in rows if r.get('phase')==c['range']]
        if c['range']=='custom':return [r for r in rows if c['start']<=r['date']<=c['end']]
        return rows
    try:
        browser=Chrome(timeout=110)
        browser.call('Emulation.setDeviceMetricsOverride',dict(width=1280,height=1200,deviceScaleFactor=1,mobile=False))
        browser.call('Emulation.setEmulatedMedia',dict(features=[dict(name='prefers-color-scheme',value='light')]))
        legacy_script=browser.call('Page.addScriptToEvaluateOnNewDocument',dict(source="window.openai={widgetState:{modelContent:{explorer:2,precision:2}}};"))['identifier']
        browser.call('Page.navigate',dict(url=preview.as_uri()));context=None
        while context is None:
            browser.call('Page.getFrameTree');browser.enable_attached()
            for cid,info in list(browser.contexts.items()):
                if not info.get('auxData',{}).get('isDefault'):continue
                try:
                    if browser.evaluate("document.getElementById('"+ROOT+"')?.dataset.ready==='true'",cid):context=cid;break
                except RuntimeError:pass
            if context is None:browser.remaining();time.sleep(.05)
        report['execution_context']=context
        check(browser.evaluate("!!document.getElementById('"+ROOT+"')&&!document.querySelector('iframe')"),'standalone document contains the working explorer directly')
        def evaluate(js):return browser.evaluate(js,context)
        migrated=evaluate("JSON.parse(document.getElementById('"+ROOT+"').dataset.state)")
        check('precision' not in migrated and migrated.get('model')==model_config['model_id'],
              'legacy BF16 widget state migrates to the configured 30T model without a precision override',migrated)
        browser.call('Page.removeScriptToEvaluateOnNewDocument',dict(identifier=legacy_script));evaluate('delete window.openai')
        evaluate("window.__qaErrors=[];addEventListener('error',e=>window.__qaErrors.push(e.message));addEventListener('unhandledrejection',e=>window.__qaErrors.push(String(e.reason)))")
        def settled():evaluate('new Promise(r=>setTimeout(()=>requestAnimationFrame(()=>requestAnimationFrame(r)),260))')
        def change(name,value):
            if name=='headline-algorithm':
                selector='input[data-headline-choice][value='+json.dumps(str(value))+']'
                got=evaluate('(()=>{document.getElementById("trd-algorithms-menu").open=true;const e=document.querySelector('+json.dumps(selector)+');if(!e)return null;e.click();return e.checked?e.value:null})()')
            else:
                got=evaluate('(()=>{const e=document.getElementById('+json.dumps('trd-'+name)+');if(!e)return null;e.value='+json.dumps(str(value))+';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));return e.value})()')
            if got!=str(value):raise ValueError('Control rejected '+name+'='+str(value)+': '+str(got))
            settled()
        def snapshot():return evaluate(SNAPSHOT.replace('CONTROL_NAMES',json.dumps(CONTROLS)))
        def click_month(month):
            pointer=evaluate("(()=>{const host=document.getElementById('trd-chart-main'),svg=host.querySelector('svg'),e=svg.querySelector('[data-month='+"+json.dumps(json.dumps(month))+"+']'),b=e.getBBox();host.scrollIntoView({block:'center'});host.scrollLeft=Math.max(0,b.x+b.width/2-host.clientWidth/2);const r=svg.getBoundingClientRect();return {x:r.x+b.x+b.width/2,y:r.y+Number(svg.dataset.plotY)+Number(svg.dataset.plotHeight)/2}})()")
            browser.call('Input.dispatchMouseEvent',dict(type='mousePressed',button='left',clickCount=1,**pointer))
            browser.call('Input.dispatchMouseEvent',dict(type='mouseReleased',button='left',clickCount=1,**pointer));settled()
            return snapshot()['readout']
        def toggle(kind,key):
            selector='#trd-'+('metric-options [data-metric=' if kind=='metric' else 'scenario-options [data-scenario=')+json.dumps(key)+']'
            if not evaluate('(()=>{const e=document.querySelector('+json.dumps(selector)+');if(!e)return false;e.click();return true})()'):
                raise ValueError('Missing '+kind+' checkbox '+key)
            settled()
        def select_metrics(keys):
            for key in keys:
                if key not in snapshot()['state']['selectedMetrics']:toggle('metric',key)
            for key in list(snapshot()['state']['selectedMetrics']):
                if key not in keys:toggle('metric',key)
        def select_scenarios(keys):
            for key in keys:
                if key not in snapshot()['state']['scenarios']:toggle('scenario',key)
            for key in list(snapshot()['state']['scenarios']):
                if key not in keys:toggle('scenario',key)
        def selection(label):
            s=snapshot();category=s['controls']['category'];keys=s['state']['selectedMetrics'];allowed=set(CATEGORIES[category])
            check(bool(keys) and len(keys)==len(set(keys)) and set(keys)<=allowed and s['controls']['primary'] in allowed and set(s['primaryOptions'])==allowed,
                  label+': nonempty selections and annual selector stay inside category',dict(category=category,selected=keys,annual=s['primaryOptions']))
            scenarios=s['state']['scenarios'];check(bool(scenarios) and len(scenarios)==len(set(scenarios)) and set(scenarios)<=set('ABC'),label+': nonempty valid scenario selection',scenarios)
        def top(label):
            s=snapshot();c=s['controls'];method=s['state'].get('headlineAlgorithm');endpoint=algorithms['meta']['endpoint']
            fields={**TOP_FIELDS,'compute-pflops':'compute_pflops_window','cache-hit-rate':'prefix_cache_hit_rate'}
            expected={key:raw(next(r for r in rows_for(field,c['scenario']) if r['date']==endpoint),field,c,method) for key,field in fields.items()}
            expected['weight-tb']=float(data['model']['total_parameters'])*float(model_config['weights']['bytes_per_parameter'])/1e12
            bad=[dict(metric=k,actual=s['values'].get(k),expected=v) for k,v in expected.items() if k not in s['values'] or not close(s['values'][k],v)]
            check(not bad,label+': headline and source details match the selected algorithm at the 2030 endpoint',bad)
            headline=s['headline'];methods=[item['id'] for item in algorithms['methods']]
            check(method in methods and headline['algorithm']==method and headline['sourceAlgorithm']==method and headline['date']==endpoint
                  and [item['key'] for item in headline['options']]==methods
                  and [item['key'] for item in headline['options'] if item['checked']]==[method]
                  and all(not item['disabled'] and item['type']=='radio' and item['group']=='trd-headline-choice' for item in headline['options'])
                  and not headline['legacySelectorPresent'] and bool(headline['name'])
                  and all(headline['numericCounts'].get(key)==1 for key in expected),
                  label+': one independent headline algorithm can be selected from all supported methods',dict(method=method,headline=headline));return s
        def chart(label,labels=False):
            s=snapshot();c=s['controls'];svg=s['svg'];issues=[]
            if not svg or not svg['marks'] or svg['width']<=0:issues.append('missing rendered marks')
            if s['error'] or s['runtime']:issues.append(dict(error=s['error'],runtime=s['runtime']))
            if svg:
                issues.extend(svg['invalid'])
                issues.extend(dict(reason='nonfinite mark',mark=m) for m in svg['marks'] if not math.isfinite(float(m['value'])))
            check(not issues,label+': visible finite plot without runtime errors',issues[:6])
            if not svg:return
            if labels:check(not svg['clipping'] and not svg['overlaps'],label+': labels fit without collisions',dict(clipping=svg['clipping'][:6],overlaps=svg['overlaps'][:6]))
            problems=[]
            if c['view']=='trend':
                keys=s['state']['selectedMetrics'];scenarios=s['state']['scenarios'] if len(CATEGORIES[c['category']])==1 else [c['scenario']]
                expected={(key,scenario,r['date']):r for key in keys for scenario in scenarios for r in filtered(rows_for(key,scenario),c)}
                actual={(m.get('series'),m.get('scenario'),m.get('date')):m for m in svg['marks']}
                if set(actual)!=set(expected):problems.append(dict(reason='date/series filter mismatch',missing=list(set(expected)-set(actual))[:4],extra=list(set(actual)-set(expected))[:4]))
                if len(actual)!=len(svg['marks']) or len(set(m.get('key') for m in svg['marks']))!=len(svg['marks']):problems.append('monthly marker identities collide across scenarios')
                axes=svg['axes'];axis=axes[0] if axes else {}
                if len(axes)!=1 or float(axis.get('min',math.nan))!=0 or float(axis.get('max',0))<=0 or not axis.get('line'):problems.append('expected exactly one shared physical zero-start axis')
                if set(axis.get('series','').split(','))!=set(keys):problems.append('axis does not cover exactly the selected metrics')
                if svg.get('mode')!='absolute':problems.append('trend mode is not absolute')
                if not close(axis.get('divisor',math.nan),DIVISORS.get(keys[0],1)):problems.append('display divisor is not the category actual unit')
                if c['category']=='cache' and not close(axis.get('max',math.nan),100):problems.append('percentage scale is not zero to 100')
                x0=float(svg.get('plotX',math.nan));y0=float(svg.get('plotY',math.nan));w=float(svg.get('plotWidth',math.nan));h=float(svg.get('plotHeight',math.nan))
                t0=float(svg.get('timeMin',math.nan));t1=float(svg.get('timeMax',math.nan))
                if not all(math.isfinite(v) for v in (x0,y0,w,h,t0,t1)) or w<=0 or h<=0 or t1<t0:problems.append('invalid shared plot or date-domain metadata')
                for pair,row in expected.items():
                    mark=actual.get(pair)
                    if mark is None:continue
                    key,scenario,day=pair;value=raw(row,key,c);plot=value/float(axis.get('divisor',1))
                    yy=y0+h-plot/float(axis.get('max',math.nan))*h;xx=x0+(millis(day)-t0)/(t1-t0)*w if t1!=t0 else x0+w/2
                    if not close(mark['value'],value) or not close(mark.get('plotValue',math.nan),plot) or abs(mark['cx']-xx)>.15 or abs(mark['cy']-yy)>.15:
                        problems.append(dict(series=key,scenario=scenario,date=day,actual=mark['value'],expected=value,plot_actual=mark.get('plotValue'),plot_expected=plot,actual_xy=[mark['cx'],mark['cy']],expected_xy=[xx,yy]))
                if t1>t0 and not any(curve['length']>0 for curve in svg['curves']):problems.append('no nondegenerate curve')
                for curve in svg['curves']:
                    series_marks=[m for m in svg['marks'] if m.get('series')==curve.get('series') and m.get('scenario')==curve.get('scenario')]
                    if any(not any(abs(x-m['cx'])<=.15 and abs(y-m['cy'])<=.15 for m in series_marks) for x,y in curve['points']):problems.append(dict(series=curve.get('series'),reason='curve vertex does not match its numeric marker'))
                check(not problems,label+': exact source values, time filter and zero-axis geometry',problems[:6])
                expected_labels={}
                for key in keys:
                    for scenario in scenarios:
                        all_rows=rows_for(key,scenario);visible=filtered(all_rows,c)
                        if not visible:continue
                        anchor=datetime.fromisoformat(all_rows[0]['date']);anchor_month=anchor.year*12+anchor.month
                        for row in visible:
                            day=datetime.fromisoformat(row['date']);month_delta=day.year*12+day.month-anchor_month
                            if month_delta%3==0 or row['date']==visible[-1]['date']:
                                expected_labels[(key,scenario,row['date'])]=raw(row,key,c)/DIVISORS.get(key,1)
                actual_labels={(m.get('labelSeries'),m.get('labelScenario'),m.get('labelDate')):m for m in svg['labels']};bad_labels=[]
                guides={(m.get('labelSeries'),m.get('labelScenario'),m.get('labelDate')):m for m in svg['guides']}
                if set(actual_labels)!=set(expected_labels):bad_labels.append(dict(reason='quarterly dates differ from source-month anchor plus visible endpoint',missing=list(set(expected_labels)-set(actual_labels))[:6],extra=list(set(actual_labels)-set(expected_labels))[:6]))
                if len(actual_labels)!=len(svg['labels']):bad_labels.append('duplicate quarterly labels')
                if not set(guides)<=set(expected_labels) or len(guides)!=len(svg['guides']):bad_labels.append('label guides are duplicated or do not belong to a visible quarterly label')
                for identity,wanted in expected_labels.items():
                    item=actual_labels.get(identity)
                    if item is None:continue
                    places=4 if abs(wanted)<.01 else 3 if abs(wanted)<1 else 2 if abs(wanted)<1000 else 0
                    display=format(wanted,',.'+str(places)+'f')
                    if places:display=display.rstrip('0').rstrip('.')
                    if item['hasValue'] or not close(item.get('labelValue',math.nan),wanted) or item['text']!=display:
                        bad_labels.append(dict(identity=identity,value=item.get('labelValue'),expected=wanted,text=item['text'],expected_text=display,has_value=item['hasValue']))
                    guide=guides.get(identity);mark=actual.get(identity)
                    if guide and mark and (abs(guide['x1']-mark['cx'])>.15 or abs(guide['y1']-mark['cy'])>.15 or not close(guide.get('sourceX',math.nan),guide['x1']) or not close(guide.get('sourceY',math.nan),guide['y1']) or not all(math.isfinite(guide[k]) for k in ('x2','y2'))):
                        bad_labels.append(dict(identity=identity,reason='label guide is disconnected from its source marker'))
                    if not guide and mark:
                        b=item['box'];distance=math.hypot(max(b['x']-mark['cx'],mark['cx']-b['x']-b['w'],0),max(b['y']-mark['cy'],mark['cy']-b['y']-b['h'],0))
                        if distance>8:bad_labels.append(dict(identity=identity,reason='displaced label lacks a guide',distance=distance))
                check(not bad_labels,label+': quarterly labels retain anchored dates, real units and readable precision',bad_labels[:6])
                viewport=svg['viewport'];scroll_ok=svg['width']<=viewport['width']+1 or viewport['overflowX'] in ('auto','scroll')
                check(scroll_ok and viewport['scrollWidth']+1>=svg['width'],label+': wide labeled plots remain inside a scrollable chart viewport',viewport)
            else:
                for mark in svg['marks']:
                    field=mark.get('series');year=int(mark.get('year',2030));scenario=mark.get('scenario',c['scenario']);value=float(mark['value'])
                    row=next((r for r in data['rows'] if r['year']==year and r['scenario']==scenario),{})
                    if field in row or field=='compute_pflops_window':
                        wanted=raw(row,field,c)
                        if c['view']=='growth':wanted/=raw(next(r for r in data['rows'] if r['year']==2026 and r['scenario']==scenario),field,c)
                        if not close(value,wanted):problems.append(dict(series=field,year=year,actual=value,expected=wanted))
                        if c['view'] in ('cache','compute','scenarios') and mark['tag']=='rect' and svg['axes']:
                            axis=svg['axes'][0];plotted=wanted/float(axis.get('divisor',1))
                            if c['detail-mode']=='share' and c['view'] in ('cache','compute'):
                                total='input_tokens_per_team_day' if c['view']=='cache' else 'eflop_per_team_day'
                                plotted=100*wanted/raw(row,total,c)
                            expected_height=plotted/float(axis['max'])*float(svg['plotHeight'])
                            if not close(mark.get('plotValue',math.nan),plotted) or abs(mark['h']-expected_height)>.15:problems.append(dict(series=field,year=year,reason='bar height or plotted share differs from source',actual_height=mark['h'],expected_height=expected_height))
                    elif field=='output_share' and mark.get('category'):
                        category=next((r for r in data['category_mix'] if r['year']==2030 and r['scenario']==scenario and r['category']==mark['category']),None)
                        if category is None or not close(value,category['share']):problems.append(dict(category=mark['category'],actual=value))
                check(not problems,label+': analysis marks retain source values',problems[:6])
            report['snapshots'].append(dict(label=label,controls=c,view=svg.get('view'),marks=len(svg['marks']),axes=svg['axes']))

        settled();default=top('default');chart('default',True);selection('default')
        options=evaluate("Object.fromEntries(['view','category'].map(k=>[k,Array.from(document.getElementById('trd-'+k).options,o=>o.value)]))")
        check(set(VIEWS)==set(options['view']),'all six analysis views are available',options['view'])
        check(set(CATEGORIES)==set(options['category']),'all seven approved metric categories are available',options['category'])
        check(default['controls']['category']=='tokens' and default['state']['selectedMetrics']==['output_tokens_per_team_day'] and default['state']['scenarios']==['C'],'default shows one actual-unit output-Token series')
        model_options=evaluate("Array.from(document.getElementById('trd-model').options,e=>({value:e.value,text:e.textContent}))")
        check([item['value'] for item in model_options]==[model_config['model_id']] and default['controls']['model']==model_config['model_id'] and evaluate("!document.getElementById('trd-precision')"),
              'model selector exposes only the actual configured 30T model and replaces the precision selector',model_options)
        check(evaluate("!document.getElementById('trd-mode')&&!document.getElementById('trd-compare')"),'old normalization and cross-category comparison controls are removed')
        for category,fields in CATEGORIES.items():
            change('category',category);selection('category '+category)
            for field in fields:
                if len(fields)>1:select_metrics([field])
                chart('metric '+field)
            if len(fields)>1:
                select_metrics(fields);chart(category+' all same-unit curves',True)
                check(set(snapshot()['state']['selectedMetrics'])==set(fields),category+': multiple checkboxes retain every selected metric')
                select_metrics([fields[0]]);toggle('metric',fields[0]);selection(category+' last checkbox guard')
                check(snapshot()['state']['selectedMetrics']==[fields[0]],category+': last metric cannot be removed')
            else:
                select_scenarios(list('ABC'));chart(category+' three scenarios',True)
                check(set(snapshot()['state']['scenarios'])==set('ABC'),category+': independent A/B/C curves are selected')
                select_scenarios(['C']);toggle('scenario','C');selection(category+' last scenario guard')
                check(snapshot()['state']['scenarios']==['C'],category+': last scenario cannot be removed')
            change('view','scenarios')
            for field in fields:
                change('primary',field);chart('annual '+field)
                check(len(snapshot()['svg']['marks'])==15,'annual '+field+': all five years and three scenarios are present')
            change('view','trend')
        change('category','tokens');select_metrics(list(CATEGORIES['tokens']));change('category','compute');selection('Token to computation transition')
        check(not set(snapshot()['state']['selectedMetrics'])&set(CATEGORIES['tokens']),'category changes clear incompatible Token selections')
        change('category','tokens');select_metrics(['output_tokens_per_team_day','input_tokens_per_team_day','uncached_input_tokens_per_team_day'])
        readout=click_month('2026-08')
        check('2026-08-15' in readout and '2026-08-31' not in readout,'Token readout preserves the actual August 15 observation date',readout)
        evaluate("document.getElementById('trd-data-details').open=true");settled()
        table=evaluate("({headers:Array.from(document.querySelectorAll('#trd-data-table th'),e=>e.textContent),rows:Array.from(document.querySelectorAll('#trd-data-table tbody tr'),e=>Array.from(e.cells,c=>c.textContent))})")
        check(not any('倍' in x for x in table['headers']) and {'原始单位','图表单位'}<=set(table['headers']) and len(table['rows'])==len(snapshot()['svg']['marks']),'monthly table and CSV schema contain actual units without normalized values',dict(headers=table['headers'],rows=len(table['rows'])))
        csv_text=evaluate("(async()=>{const create=URL.createObjectURL,revoke=URL.revokeObjectURL,click=HTMLAnchorElement.prototype.click;let blob;URL.createObjectURL=b=>{blob=b;return 'blob:qa-csv-capture'};URL.revokeObjectURL=()=>{};HTMLAnchorElement.prototype.click=()=>{};try{document.getElementById('trd-download').click();return blob?await blob.text():null}finally{URL.createObjectURL=create;URL.revokeObjectURL=revoke;HTMLAnchorElement.prototype.click=click}})()")
        csv_lines=csv_text.splitlines() if csv_text else []
        check(bool(csv_lines) and '单位' in csv_lines[0] and '倍' not in csv_lines[0] and len(csv_lines)==len(table['rows'])+1 and any('Token/日' in line for line in csv_lines[1:]),'actual download serializes selected monthly values with original units',dict(header=csv_lines[0] if csv_lines else None,rows=max(0,len(csv_lines)-1)))
        evaluate("document.getElementById('trd-data-details').open=false")
        for mode in ('observed','forecast'):change('range',mode);chart(mode+' filter',True)
        change('range','custom');change('start','2028-01-01');change('end','2028-12-31');chart('custom 2028 filter',True)
        change('start','2028-05-18');change('end','2028-05-18');chart('single-date actual-unit series',True)
        change('start','2028-05-19');change('end','2028-05-20')
        empty=snapshot();check(not empty['svg'] and bool(empty['error']) and evaluate("document.getElementById('trd-download').disabled"),'empty interval provides a message and disables data export',empty['error'])
        change('start','2029-01-01');change('end','2028-12-31')
        invalid=snapshot();check(not invalid['svg'] and bool(invalid['error']) and not invalid['runtime'],'reversed date interval is handled without runtime errors',invalid['error'])
        change('range','all')
        for scenario in 'ABC':change('scenario',scenario);top('scenario '+scenario);chart('scenario '+scenario)
        for team in (10,1000,100):change('team',team);top('team '+str(team));chart('team '+str(team))
        change('window',8);top('8-hour processing window');change('category','rate');chart('8-hour actual PFLOP/s')
        select_scenarios(list('ABC'));chart('8-hour rate, three scenarios');change('window',12);chart('12-hour actual PFLOP/s');change('window',24)
        before_model=snapshot();change('model',model_config['model_id']);after_model=top('configured model weights')
        check(before_model['state']==after_model['state'] and before_model['values']==after_model['values'] and before_model['svg']['marks']==after_model['svg']['marks'],
              'selecting the configured model preserves other controls and plotted values')
        change('category','cache');select_scenarios(list('ABC'));change('team',1000);chart('cache percentages do not scale with team size');change('team',100)
        change('category','tokens');select_metrics(list(CATEGORIES['tokens']))
        for width in (736,320):
            browser.call('Emulation.setDeviceMetricsOverride',dict(width=width,height=1400,deviceScaleFactor=1,mobile=False));settled()
            for view in VIEWS:
                change('view',view);chart(str(width)+' '+view,True)
                if view in ('cache','compute'):change('detail-mode','share');chart(str(width)+' '+view+' share',True);change('detail-mode','absolute')
                layout=evaluate("({viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,rootWidth:document.getElementById('"+ROOT+"').getBoundingClientRect().width})")
                check(layout['documentWidth']<=layout['viewport']+1,str(width)+' '+view+': no horizontal overflow',layout);report['layouts'].append(dict(view=view,**layout))
            change('view','trend');change('category','compute');select_metrics(list(CATEGORIES['compute']));chart(str(width)+' three computation curves',True)
            change('category','cache');select_scenarios(list('ABC'));chart(str(width)+' cache scenario comparison',True)
            change('category','tokens');select_metrics(list(CATEGORIES['tokens']))
            if width==320:
                for month,day in (('2026-08','2026-08-15'),('2030-11','2030-11-18')):
                    readout=click_month(month)
                    check(day in readout,'320px horizontal scrolling preserves pointer readout for '+month,readout)
        browser.call('Emulation.setEmulatedMedia',dict(features=[dict(name='prefers-color-scheme',value='dark')]))
        browser.call('Emulation.setDeviceMetricsOverride',dict(width=1024,height=1400,deviceScaleFactor=1,mobile=False));settled();chart('dark same-unit multi-curve chart',True)
        for key,value in default['controls'].items():
            if key in ('scenario','team','window','model','view','category','range'):change(key,value)
        select_metrics(['output_tokens_per_team_day'])
        def screenshot(filename,width,theme):
            browser.call('Emulation.setEmulatedMedia',dict(features=[dict(name='prefers-color-scheme',value=theme)]))
            browser.call('Emulation.setDeviceMetricsOverride',dict(width=width,height=1000,deviceScaleFactor=1,mobile=False));settled()
            evaluate("window.scrollTo(0,0);document.getElementById('trd-chart-main').scrollLeft=0")
            height=evaluate("Math.ceil(document.getElementById('"+ROOT+"').getBoundingClientRect().bottom)+24")
            browser.call('Emulation.setDeviceMetricsOverride',dict(width=width,height=max(700,height),deviceScaleFactor=1,mobile=False));settled()
            evaluate("window.scrollTo(0,0);document.getElementById('trd-chart-main').scrollLeft=0")
            path=HERE/filename;browser.screenshot(path,full_page=True);report['screenshots'].append(dict(file=filename,width=width,height=max(700,height),theme=theme,sha256=sha(path)))
        screenshot('dashboard_default.png',1280,'light');screenshot('dashboard_mobile.png',320,'light');screenshot('dashboard_dark.png',1024,'dark');screenshot('dashboard_tablet.png',736,'light')
        select_metrics(['output_tokens_per_team_day','input_tokens_per_team_day','uncached_input_tokens_per_team_day']);screenshot('dashboard_compare.png',1280,'light')
        change('category','compute');select_metrics(list(CATEGORIES['compute']));screenshot('dashboard_compute.png',1280,'light')
        change('category','cache');select_scenarios(list('ABC'));screenshot('dashboard_scenarios.png',1280,'light')
        exceptions=[e['params'].get('exceptionDetails') for e in browser.events if e.get('method')=='Runtime.exceptionThrown']
        check(not exceptions and not snapshot()['runtime'],'no JavaScript exceptions throughout standalone interactions',exceptions)
        check(all(sha(Path(p))==digest for p,digest in original.items()),'source and data unchanged throughout QA')
        report['status']='passed' if all(c['status']=='passed' for c in report['checks']) else 'failed'
    except Exception as error:report.update(status='inconclusive' if isinstance(error,(TimeoutError,OSError)) else 'failed',error=f'{type(error).__name__}: {error}')
    finally:
        if browser:browser.close()
    report['elapsed_seconds']=time.monotonic()-started
    (HERE/'qa_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=report['status'],checks=len(report['checks']),elapsed_seconds=report['elapsed_seconds'],error=report.get('error'),failures=[c for c in report['checks'] if c['status']=='failed']),ensure_ascii=False))
    return 0 if report['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
