(()=>{
'use strict';
const root=document.getElementById('team-resource-dashboard-30t-v2');
if(!root)return;
const $=id=>root.querySelector('#'+id),out=name=>root.querySelector('[data-testid="'+name+'"]');
const data=JSON.parse($('trd-inline-data').textContent),years=[2026,2027,2028,2029,2030],ns='http://www.w3.org/2000/svg';
const metrics={
 output_tokens_per_team_day:{name:'输出Token',unit:'Token/日',display:'亿Token/日',divisor:1e8,source:'resources',group:'tokens',color:'var(--blue)'},
 input_tokens_per_team_day:{name:'输入Token',unit:'Token/日',display:'亿Token/日',divisor:1e8,source:'resources',group:'tokens',color:'var(--accent)'},
 cached_input_tokens_per_team_day:{name:'缓存输入',unit:'Token/日',display:'亿Token/日',divisor:1e8,source:'resources',group:'tokens',color:'var(--purple)'},
 uncached_input_tokens_per_team_day:{name:'未缓存输入 / Prefill',unit:'Token/日',display:'亿Token/日',divisor:1e8,source:'resources',group:'tokens',color:'var(--orange)'},
 total_tokens_per_team_day:{name:'输入＋输出Token',unit:'Token/日',display:'亿Token/日',divisor:1e8,source:'resources',group:'tokens',color:'var(--red)'},
 prefix_cache_hit_rate:{name:'Prefix Cache命中率',unit:'比例（0–1）',display:'%',divisor:.01,source:'resources',group:'cache',color:'var(--accent)',ratio:true},
 agent_hours_per_team_day:{name:'Agent活动时长',unit:'小时/日',display:'万小时/日',divisor:1e4,source:'agents',group:'agent_time',color:'var(--blue)'},
 mean_online_agent_equivalents:{name:'平均Agent活动当量',unit:'个活动当量',display:'个活动当量',divisor:1,source:'agents',group:'agent_scale',color:'var(--accent)'},
 task_starts_per_team_day:{name:'研发任务发起',unit:'项/日',display:'项/日',divisor:1,source:'tasks',group:'tasks',color:'var(--orange)'},
 eflop_per_team_day:{name:'总计算量',unit:'EFLOP/日',display:'EFLOP/日',divisor:1,source:'resources',group:'compute',color:'var(--purple)'},
 prefill_eflop_per_team_day:{name:'Prefill计算量',unit:'EFLOP/日',display:'EFLOP/日',divisor:1,source:'resources',group:'compute',color:'var(--accent)'},
 decode_eflop_per_team_day:{name:'Decode计算量',unit:'EFLOP/日',display:'EFLOP/日',divisor:1,source:'resources',group:'compute',color:'var(--orange)'},
 compute_pflops_window:{name:'窗口内平均计算速率',unit:'PFLOP/s',display:'PFLOP/s',divisor:1,source:'resources',group:'rate',color:'var(--purple)'}
};
const categories={
 tokens:{name:'Token用量',unit:'亿Token/日',keys:['input_tokens_per_team_day','output_tokens_per_team_day','cached_input_tokens_per_team_day','uncached_input_tokens_per_team_day','total_tokens_per_team_day'],default:'output_tokens_per_team_day',note:'输出沿用官方14日滑动平均口径；输入与缓存按该输出及代理比率估算。输入＝缓存输入＋未缓存输入；总量＝输入＋输出。'},
 compute:{name:'理论计算量',unit:'EFLOP/日',keys:['eflop_per_team_day','prefill_eflop_per_team_day','decode_eflop_per_team_day'],default:'eflop_per_team_day',note:'总计算量＝Prefill计算量＋Decode计算量，按团队自然日累计。'},
 rate:{name:'平均计算速率',unit:'PFLOP/s',keys:['compute_pflops_window'],default:'compute_pflops_window',note:'每日累计计算量按顶部所选处理窗口摊平；改变窗口只影响平均速率。'},
 agent_time:{name:'Agent累计活动时长',unit:'万小时/日',keys:['agent_hours_per_team_day'],default:'agent_hours_per_team_day',note:'沿用官方28日统计窗口，累加团队各Agent的活动小时，多个Agent可同时活动。'},
 agent_scale:{name:'Agent平均活动规模',unit:'个活动当量',keys:['mean_online_agent_equivalents'],default:'mean_online_agent_equivalents',note:'平均活动当量＝每日累计Agent小时÷24，不能解释为瞬时或峰值并发。'},
 tasks:{name:'研发任务量',unit:'项/日',keys:['task_starts_per_team_day'],default:'task_starts_per_team_day',note:'团队每天发起的研发任务数，沿用官方28日统计窗口。'},
 cache:{name:'缓存命中率',unit:'%',keys:['prefix_cache_hit_rate'],default:'prefix_cache_hit_rate',note:'缓存输入占累计输入Token的比例，按Token量加权。'}
};
const algorithmData=data.algorithm_forecasts,algorithmMethods=algorithmData.methods,algorithmById=Object.fromEntries(algorithmMethods.map(m=>[m.id,m]));
const algorithmColors=['var(--blue)','var(--purple)','var(--accent)'],algorithmDashes=['8 5','3 4','12 4 2 4'];
const defaults={year:2030,scenario:'C',team:100,window:24,model:data.model.id,view:'trend',category:'tokens',primary:'output_tokens_per_team_day',selectedMetrics:['output_tokens_per_team_day'],scenarios:['C'],algorithms:['legacy_ols'],headlineAlgorithm:'legacy_ols',showIntervals:false,range:'all',start:'2026-02-28',end:'2030-11-18',detailMode:'absolute'};
const controlIds={scenario:'trd-scenario',team:'trd-team',window:'trd-window',model:'trd-model',view:'trd-view',category:'trd-category',primary:'trd-primary',range:'trd-range',start:'trd-start',end:'trd-end',detailMode:'trd-detail-mode'};
const controls=Object.fromEntries(Object.entries(controlIds).map(([key,id])=>[key,$(id)])),storageKey=root.id+':explorer-v2';
const evidenceNames={observed:'公开观测换算',estimated:'条件估算',forecast:'预测'},scenarioNames={A:'增加会话',B:'延长会话',C:'混合增长'};
const scenarioColors={A:'var(--blue)',B:'var(--purple)',C:'var(--accent)'};
const fmt=(v,d=2)=>Number(v).toLocaleString('zh-CN',{maximumFractionDigits:d}),fixed=(v,d=2)=>Number(v).toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d});
const tick=v=>Math.abs(v)>=10000?fmt(v/10000,1)+'万':fmt(v,Math.abs(v)<1?3:2),stamp=date=>Date.parse(date+'T00:00:00Z');
function normalise(raw){
 const s={...defaults,...raw,year:2030};
 if(!['A','B','C'].includes(s.scenario))s.scenario='C';
 for(const [key,allowed]of[['team',[10,100,1000]],['window',[8,12,24]]])s[key]=allowed.includes(Number(s[key]))?Number(s[key]):defaults[key];
 s.model=data.model.id;delete s.precision;
 for(const [key,allowed]of[['view',['trend','scenarios','cache','compute','categories','growth']],['range',['all','observed','forecast','custom']],['detailMode',['absolute','share']]])if(!allowed.includes(s[key]))s[key]=defaults[key];
 if(!Object.hasOwn(categories,s.category))s.category=defaults.category;
 const group=categories[s.category];
 if(!group.keys.includes(s.primary))s.primary=group.default;
 s.selectedMetrics=group.keys.filter(k=>Array.isArray(s.selectedMetrics)&&s.selectedMetrics.includes(k));
 if(!s.selectedMetrics.length)s.selectedMetrics=[group.default];
 s.scenarios=['A','B','C'].filter(k=>Array.isArray(s.scenarios)&&s.scenarios.includes(k));
 if(!s.scenarios.length)s.scenarios=[s.scenario];
 s.algorithms=[...new Set(Array.isArray(s.algorithms)?s.algorithms.filter(k=>Object.hasOwn(algorithmById,k)):[])].slice(0,3);
 if(!s.algorithms.length)s.algorithms=['legacy_ols'];
 if(!Object.hasOwn(algorithmById,s.headlineAlgorithm))s.headlineAlgorithm=defaults.headlineAlgorithm;
 s.showIntervals=s.showIntervals===true;
 delete s.mode;delete s.compare;
 for(const key of['start','end'])if(typeof s[key]!=='string')s[key]=defaults[key];
 return s;
}
let saved=null;try{saved=JSON.parse(localStorage.getItem(storageKey)||'null');}catch(_){}
if(window.openai?.widgetState?.modelContent?.explorer===2)saved=window.openai.widgetState.modelContent;
try{const incoming=new URLSearchParams(location.hash.slice(1)).get('resource-state');if(incoming){saved=JSON.parse(incoming);try{history.replaceState(null,'',location.href.split('#')[0]);}catch(_){}}}catch(_){}
let state=normalise(saved),exportRows=[],exportColumns=[],resizeFrame=0;
function syncPageLink(){
 const filename=location.pathname.split('/').pop(),back=['resource-dashboard-preview.html','team-resource-dashboard.html'].includes(filename)?filename:'resource-dashboard-preview.html';
 const params=new URLSearchParams({return:back,'resource-state':JSON.stringify(state)});
 $('trd-raw-link').href='raw-data-dashboard.html#'+params.toString();
}
function persist(){const saved={...state,explorer:2};try{localStorage.setItem(storageKey,JSON.stringify(saved));window.openai?.setWidgetState?.({modelContent:saved,privateContent:null})?.catch(()=>{});}catch(_){}}
function selectOptions(select,items){const signature=items.map(i=>i.value).join('|');if(select.dataset.options===signature)return;select.replaceChildren();for(const item of items){const opt=document.createElement('option');opt.value=item.value;opt.textContent=item.name;select.append(opt);}select.dataset.options=signature;}
selectOptions(controls.category,Object.entries(categories).map(([value,c])=>({value,name:c.name+' · '+c.unit})));
selectOptions(controls.model,[{value:data.model.id,name:data.model.display_name}]);
function checkOptions(host,items,selected,attribute){
 const signature=items.map(i=>i.value).join('|');
 if(host.dataset.options!==signature){host.replaceChildren();for(const item of items){const label=document.createElement('label');label.className='metric-option';label.style.setProperty('--series-color',item.color);const input=document.createElement('input');input.type='checkbox';input.dataset[attribute]=item.value;input.value=item.value;const swatch=document.createElement('span');swatch.className='option-swatch';swatch.setAttribute('aria-hidden','true');const name=document.createElement('span');name.textContent=item.name;label.append(input,swatch,name);host.append(label);}host.dataset.options=signature;}
 for(const input of host.querySelectorAll('input')){input.checked=selected.includes(input.value);input.disabled=input.checked&&selected.length===1;input.closest('label').title=input.disabled?'至少保留一项；可先勾选其他项，再取消此项。':'';}
}
function syncAlgorithms(){
 const host=$('trd-algorithm-options');
 if(!host.childElementCount){
  const groups=new Map();
  for(const method of algorithmMethods){
   if(!groups.has(method.group)){const group=document.createElement('div');group.className='algorithm-group';group.setAttribute('role','group');group.setAttribute('aria-label',method.group);const title=document.createElement('div');title.className='algorithm-group-title';title.textContent=method.group;group.append(title);host.append(group);groups.set(method.group,group);}
   const row=document.createElement('div');row.className='algorithm-option';
   for(const [type,attribute,purpose]of[['checkbox','algorithm','折线对比'],['radio','headlineChoice','顶部预测']]){
    const label=document.createElement('label');label.className='algorithm-choice';
    const input=document.createElement('input');input.type=type;input.value=method.id;input.dataset[attribute]=method.id;input.dataset.algorithmName=method.name;
    if(type==='radio')input.name='trd-headline-choice';
    const accessibleName=document.createElement('span');accessibleName.className='sr-only';accessibleName.textContent=purpose+'：'+method.name;
    label.append(input,accessibleName);label.title=purpose+'：'+method.name;row.append(label);
   }
   const name=document.createElement('span');name.className='algorithm-name';name.textContent=method.name;row.append(name);groups.get(method.group).append(row);
  }
 }
 for(const input of host.querySelectorAll('input[data-algorithm]')){
  input.checked=state.algorithms.includes(input.value);input.disabled=input.checked?state.algorithms.length===1:state.algorithms.length>=3;
  input.closest('label').title=input.disabled?(input.checked?'至少保留一种折线算法；可先勾选其他算法。':'最多对比3种算法，请先取消一种；仍可选择右侧顶部预测。'):'折线对比：'+algorithmById[input.value].name;
 }
 for(const input of host.querySelectorAll('input[data-headline-choice]'))input.checked=input.value===state.headlineAlgorithm;
 const names=state.algorithms.map(id=>algorithmById[id].name).join('、'),headlineName=algorithmById[state.headlineAlgorithm].name;
 $('trd-algorithms-curves-summary').textContent='折线 '+state.algorithms.length+'/3 · '+names;
 $('trd-algorithms-headline-summary').textContent='顶部 · '+headlineName;
 $('trd-algorithms-menu').querySelector('summary').title='折线：'+names+'；顶部预测：'+headlineName;
 $('trd-algorithms-help').textContent='折线已选 '+state.algorithms.length+'/3；顶部独立单选，可选未加入折线的算法。';
}
const rowAt=(year,scenario=state.scenario)=>data.rows.find(r=>r.year===year&&r.scenario===scenario);
function value(row,key){if(key==='compute_pflops_window')return Number(row.eflop_per_team_day)*state.team/Number(row.researchers||100)*1000/(state.window*3600);return Number(row[key])*(metrics[key]?.ratio?1:state.team/Number(row.researchers||100));}
function baseline(key){return value(rowAt(2026),key);}
function sourceRows(key,scenario=state.scenario){const s=metrics[key].source;return(s==='agents'?data.monthly_trends.agents:s==='tasks'?data.monthly_tasks:data.monthly_resources).filter(r=>r.scenario===scenario);}
function algorithmRows(key,scenario,algorithm){
 const rows=sourceRows(key,scenario),prediction=algorithmData.forecasts[algorithm],source=metrics[key].source;
 // All algorithms may be refreshed from the resource prediction CSV. History,
 // cache ratios and the monthly scenario-C task-mix schedule remain unchanged.
 if(metrics[key].ratio)return rows;
 return rows.map(row=>{
  if(row.phase!=='forecast')return row;
  const field=source==='agents'?'workdays':source==='tasks'?'tasks':'output',perPerson=prediction[field][row.date];
  if(!Number.isFinite(perPerson)||perPerson<0)throw new Error('算法数据缺少有效月份：'+algorithm+' / '+row.date);
  const team=Number(row.researchers||100),baseField=source==='agents'?'agent_hours_per_team_day':source==='tasks'?'task_starts_per_team_day':'output_tokens_per_team_day',projected=perPerson*(source==='agents'?8:1)*team,original=row[baseField];
  // Keep exact original rows when round-off is the only difference (notably OLS).
  if(Math.abs(projected-original)<=Math.max(1e-9,1e-12*Math.max(Math.abs(projected),Math.abs(original))))return row;
  const result={...row};
  if(source==='agents'){result.agent_hours_per_team_day=perPerson*8*team;result.mean_online_agent_equivalents=result.agent_hours_per_team_day/24;}
  else if(source==='tasks')result.task_starts_per_team_day=perPerson*team;
  else{
   const output=perPerson*team,factor=output/row.output_tokens_per_team_day;
   for(const [name,metric]of Object.entries(metrics))if(metric.source==='resources'&&!metric.ratio&&Number.isFinite(row[name]))result[name]=row[name]*factor;
   result.output_tokens_per_team_day=output;
  }
  return result;
 });
}
function headlineRow(algorithm=state.headlineAlgorithm){
 const endpoint='2030-11-18',rows=['output_tokens_per_team_day','agent_hours_per_team_day','task_starts_per_team_day'].map(key=>{
  const row=algorithmRows(key,state.scenario,algorithm).find(row=>row.date===endpoint&&row.phase==='forecast');
  if(!row)throw new Error('顶部预测缺少终点数据：'+algorithm+' / '+metrics[key].name+' / '+endpoint);
  return row;
 });
 return Object.assign({},...rows);
}
function intervalValues(key,scenario,algorithm,day){
 const metric=metrics[key];if(metric.ratio)return null;
 const source=metric.source,field=source==='agents'?'workdays':source==='tasks'?'tasks':'output';
 const bounds=algorithmData.uncertainty?.[algorithm]?.[field]?.[day];
 if(!bounds)return null;
 // Scale from each saved per-person quantile, never divide by a potentially
 // zero median. Output uses native 14-day quantiles without further smoothing.
 const base=sourceRows(key,scenario).find(row=>row.date===day&&row.phase==='forecast');
 if(!base)return null;
 const factor=source==='agents'?state.team*8/(key==='mean_online_agent_equivalents'?24:1):source==='tasks'?state.team:value(base,key)/(base.output_tokens_per_team_day/Number(base.researchers||100));
 const result=Object.fromEntries(['lower80','upper80','lower95','upper95'].map(name=>[name,bounds[name]*factor]));
 if(!Object.values(result).every(v=>Number.isFinite(v)&&v>=0))throw new Error('名义区间数据无效：'+algorithm+' / '+day);
 return result;
}
function evidence(row,key){if(key==='compute_pflops_window')key='eflop_per_team_day';return row[key+'_evidence']||({output_tokens_per_team_day:row.output_evidence,input_tokens_per_team_day:row.input_evidence}[key])||row.resource_evidence||(row.phase==='observed'?'observed':'forecast');}
function annualEvidence(year,key){return year!==2026?'forecast':['output_tokens_per_team_day','agent_hours_per_team_day','mean_online_agent_equivalents','task_starts_per_team_day'].includes(key)?'observed':'estimated';}
function unit(key){return metrics[key].unit+(key==='compute_pflops_window'?'（'+state.window+'小时窗口）':'');}
function windowBasis(key){return metrics[key].source==='resources'?(metrics[key].ratio?'代理任务比率':key==='output_tokens_per_team_day'?'14日平均口径':'基于14日输出的条件估算'):'28日统计口径';}
function plotted(row,key){return value(row,key)/metrics[key].divisor;}
function nice(max){if(!(max>0))return 1;const p=10**Math.floor(Math.log10(max)),m=max/p;return[1,1.5,2,2.5,3,4,5,6,7,8,9,10].find(v=>v>=m)*p;}
function svgNode(tag,attrs={},parent,text){const e=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))if(v!==undefined&&v!==null)e.setAttribute(k,String(v));if(text!==undefined)e.textContent=text;if(parent)parent.append(e);return e;}
function text(g,x,y,value,anchor='start',attrs={}){return svgNode('text',{x,y,'text-anchor':anchor,...attrs},g,String(value));}
function line(g,x1,y1,x2,y2,attrs={}){return svgNode('line',{x1,y1,x2,y2,class:'grid-line',...attrs},g);}
function frame(height=410,dual=false,minWidth=0,minHeight=0){
 const host=$('trd-chart-main'),viewport=Math.max(1,Math.floor(host.getBoundingClientRect().width)),w=Math.max(viewport,Math.ceil(minWidth)),h=Math.max(minHeight,viewport<480?Math.min(height,330):height);
 const svg=svgNode('svg',{width:w,height:h,viewBox:'0 0 '+w+' '+h,role:'img','aria-label':$('trd-chart-title').textContent,'data-view':state.view});
 if(w>viewport)svg.style.width=w+'px';
 const b={x:w<400?44:60,y:44,w:w-(w<400?44:60)-(dual?(w<400?44:60):18),h:h-84};
 Object.entries({x:b.x,y:b.y,width:b.w,height:b.h}).forEach(([key,v])=>svg.setAttribute('data-plot-'+key,v));
 svgNode('title',{},svg,$('trd-chart-title').textContent);
 return{host,svg,w,h,b};
}
function mount(g){g.host.replaceChildren(g.svg);}
function axis(g,side,key,max,divisor=1,label='',ticks=4){
 const b=g.b,right=side==='right',x=right?b.x+b.w:b.x;
 const group=svgNode('g',{'data-axis':side,'data-series':key,'data-min':0,'data-max':max,'data-divisor':divisor},g.svg);
 line(group,x,b.y,x,b.y+b.h,{class:'axis-line','data-axis-line':'true'});
 for(let i=0;i<=ticks;i++){const y=b.y+b.h-b.h*i/ticks;if(!right)line(g.svg,b.x,y,b.x+b.w,y);text(group,x+(right?7:-7),y+4,tick(max*i/ticks),right?'start':'end',{class:'axis-label'});}
 text(group,right?g.w:0,20,label,right?'end':'start',{class:'axis-label'});
 line(g.svg,b.x,b.y+b.h,b.x+b.w,b.y+b.h,{class:'axis-line'});
}
function legend(items){const host=$('trd-legend');host.replaceChildren();items.forEach(item=>{const span=document.createElement('span');span.className='legend-item';let swatch;if(item.dash){swatch=svgNode('svg',{width:30,height:10,'aria-hidden':'true'});svgNode('line',{x1:0,y1:5,x2:30,y2:5,stroke:item.color,'stroke-width':3,'stroke-dasharray':item.dash},swatch);}else{swatch=document.createElement('i');swatch.className='legend-swatch';swatch.style.borderTopColor=item.color;}span.append(swatch,document.createTextNode(item.name));host.append(span);});}
function readout(parts){const host=$('trd-chart-readout');host.replaceChildren();parts.forEach((s,i)=>{const el=document.createElement(i===0?'strong':'span');el.textContent=s;host.append(el);});}
function bindMark(mark,parts){mark.addEventListener('pointerenter',()=>readout(parts));mark.addEventListener('click',()=>readout(parts));}
function setTable(columns,rows){exportColumns=columns;exportRows=rows;$('trd-data-count').textContent=rows.length+'条记录 · 保留原始数值和单位';$('trd-download').disabled=!rows.length;if($('trd-data-details').open)renderTable();}
function renderTable(){const table=$('trd-data-table');table.replaceChildren();const thead=table.createTHead(),header=thead.insertRow();exportColumns.forEach(c=>{const th=document.createElement('th');th.scope='col';th.textContent=c;header.append(th);});const body=table.createTBody();exportRows.forEach(row=>{const tr=body.insertRow();row.forEach(v=>{const td=tr.insertCell();td.textContent=String(v);});});}
function setError(message){$('trd-error').hidden=!message;$('trd-error').textContent=message||'';}
function filterRows(rows){return rows.filter(r=>state.range==='observed'?r.phase==='observed':state.range==='forecast'?r.phase==='forecast':state.range==='custom'?r.date>=state.start&&r.date<=state.end:true);}
function labelNumber(value){const n=Math.abs(value);return fmt(value,n<.01?4:n<1?3:n<1000?2:0);}
function quarterLabels(series,all,sets,start,end){
 const monthIndex=date=>Number(date.slice(0,4))*12+Number(date.slice(5,7))-1,measure=document.createElement('canvas').getContext('2d');
 measure.font='600 12px '+getComputedStyle(root).fontFamily;
 const groups=new Map();
 series.forEach((s,i)=>{
  const anchor=monthIndex(all[i][0].date),last=sets[i].at(-1).date;
  for(const row of sets[i])if(visiblePoint(s,row,i)&&((monthIndex(row.date)-anchor)%3===0||row.date===last)){
   const historical=row.phase==='observed',v=plotted(row,s.key),label=labelNumber(v),item={...s,algorithm:historical?'observed':s.algorithm,algorithms:historical?[]:s.algorithms,color:historical?s.historyColor:s.color,row,value:v,label,width:measure.measureText(label).width};
   if(!groups.has(row.date))groups.set(row.date,[]);groups.get(row.date).push(item);
  }
 });
 const columns=[...groups.entries()].sort(([a],[b])=>a.localeCompare(b)),span=end-start;let minPlotWidth=0;
 for(let i=1;i<columns.length;i++){
  const [before,after]=[columns[i-1],columns[i]],a=Math.max(...before[1].map(p=>p.width)),b=Math.max(...after[1].map(p=>p.width)),fraction=(stamp(after[0])-stamp(before[0]))/(span||1);
  const room=(a+b)/2+14+(i===1?a/2+5:0)+(i===columns.length-1?b/2+5:0);
  minPlotWidth=Math.max(minPlotWidth,room/fraction);
 }
 return {columns,minWidth:columns.length>1?minPlotWidth+78:0,minHeight:Math.max(...columns.map(([,items])=>(items.length-1)*18+110),0)};
}
function drawQuarterLabels(g,columns,x,max){
 const {b}=g,top=b.y+10,bottom=b.y+b.h-10,gap=18,layer=svgNode('g',{'data-layer':'quarterly-labels'},g.svg);
 for(const [date,items]of columns){
  const points=items.map(p=>({...p,cx:x(date),cy:b.y+b.h-p.value/max*b.h})).sort((a,c)=>a.cy-c.cy);
  points.forEach((p,i)=>{p.ly=Math.max(top,Math.min(bottom,p.cy-12),i?points[i-1].ly+gap:top);p.lx=Math.max(b.x+p.width/2+5,Math.min(b.x+b.w-p.width/2-5,p.cx));});
  if(points.at(-1).ly>bottom){points.at(-1).ly=bottom;for(let i=points.length-2;i>=0;i--)points[i].ly=Math.min(points[i].ly,points[i+1].ly-gap);}
  for(const p of points)if(Math.hypot(p.lx-p.cx,p.ly-p.cy)>8)line(layer,p.cx,p.cy,p.lx,p.ly+(p.ly<p.cy?8:-8),{class:'point-label-guide',style:'--label-color:'+p.color,'data-label-series':p.key,'data-label-scenario':p.scenario,'data-label-algorithm':p.algorithm,'data-label-algorithms':JSON.stringify(p.algorithms),'data-label-date':date,'data-source-x':p.cx,'data-source-y':p.cy});
  for(const p of points)text(layer,p.lx,p.ly+4,p.label,'middle',{class:'point-label',style:'--label-color:'+p.color,'data-label':'quarterly','data-label-series':p.key,'data-label-scenario':p.scenario,'data-label-algorithm':p.algorithm,'data-label-algorithms':JSON.stringify(p.algorithms),'data-label-date':date,'data-label-value':p.value});
 }
}
function visiblePoint(series,row,index){return row.phase==='observed'?series.historyLeader===index:series.forecastLeader===index;}
function renderTrend(){
 const group=categories[state.category],single=group.keys.length===1;
 const bases=single?state.scenarios.map(s=>({key:group.default,scenario:s,name:s+' · '+scenarioNames[s],color:scenarioColors[s]})):state.selectedMetrics.map(key=>({key,scenario:state.scenario,name:metrics[key].name,color:metrics[key].color}));
 const series=bases.flatMap(base=>state.algorithms.map((algorithm,a)=>({...base,baseName:base.name,algorithm,algorithms:[algorithm],historyColor:base.color,color:bases.length===1&&state.algorithms.length>1?algorithmColors[a]:base.color,dash:algorithmDashes[a],name:base.name+' · '+algorithmById[algorithm].name})));
 const keys=[...new Set(series.map(s=>s.key))];
 $('trd-chart-title').textContent=group.name+' · 月度趋势';
 const all=series.map(s=>algorithmRows(s.key,s.scenario,s.algorithm)),sets=all.map(filterRows);
 legend(series);
 if(state.range==='custom'&&(!Number.isFinite(stamp(state.start))||!Number.isFinite(stamp(state.end))||state.start>state.end)){setError('请选择有效的开始与结束日期，开始日期不能晚于结束日期。');$('trd-chart-main').replaceChildren();readout(['当前区间无可展示数据']);setTable([],[]);return;}
 if(sets.some(rows=>!rows.length)){setError('所选区间内至少一个指标没有月度数据，请扩大日期范围。');$('trd-chart-main').replaceChildren();readout(['当前区间无可展示数据']);setTable([],[]);return;}
 // Share history across algorithms. Merge a forecast only when its entire
 // visible series agrees for the same metric and scenario; exports retain each method.
 series.forEach((s,i)=>{
  s.historyLeader=series.findIndex(other=>other.key===s.key&&other.scenario===s.scenario);
  const future=sets[i].filter(r=>r.phase==='forecast');s.forecastLeader=i;
  for(let j=s.historyLeader;j<i;j++)if(series[j].key===s.key&&series[j].scenario===s.scenario&&series[j].forecastLeader===j){
   const other=sets[j].filter(r=>r.phase==='forecast');
   if(future.length&&future.length===other.length&&future.every((r,k)=>r.date===other[k].date&&Math.abs(value(r,s.key)-value(other[k],s.key))<=1e-10*Math.max(1,Math.abs(value(r,s.key))))){s.forecastLeader=j;series[j].algorithms.push(s.algorithm);break;}
  }
 });
 const futureVisible=sets.some(rows=>rows.some(r=>r.phase==='forecast'));
 legend(futureVisible?series.filter((s,i)=>s.forecastLeader===i).map(s=>({...s,name:s.baseName+' · '+s.algorithms.map(id=>algorithmById[id].name).join(' / ')})):bases.map(s=>({...s,name:s.name+' · 公共历史'})));
 const start=Math.min(...sets.map(rows=>stamp(rows[0].date))),end=Math.max(...sets.map(rows=>stamp(rows.at(-1).date))),span=end-start,labels=quarterLabels(series,all,sets,start,end),g=frame(410,false,labels.minWidth,labels.minHeight),b=g.b,x=date=>b.x+(span?(stamp(date)-start)/span:.5)*b.w;
 g.svg.setAttribute('data-time-min',start);g.svg.setAttribute('data-time-max',end);g.svg.setAttribute('data-mode','absolute');g.svg.setAttribute('data-category',state.category);g.svg.setAttribute('data-algorithms',JSON.stringify(state.algorithms));
 const intervals=series.map((s,i)=>sets[i].map(row=>row.phase==='forecast'?intervalValues(s.key,s.scenario,s.algorithm,row.date):null));
 const showBands=state.showIntervals&&intervals.some(rows=>rows.some(Boolean));
 const maximums=sets.flatMap((rows,i)=>rows.map((r,j)=>Math.max(plotted(r,series[i].key),showBands&&intervals[i][j]?intervals[i][j].upper95/metrics[series[i].key].divisor:0)));
 const max=metrics[keys[0]].ratio?100:nice(Math.max(...maximums)*1.1);
 g.svg.setAttribute('data-show-intervals',String(showBands));
 axis(g,'left',keys.join(','),max,metrics[keys[0]].divisor,group.unit+(state.category==='rate'?' · '+state.window+'小时窗口':''));
 const allDates=[...new Set(sets.flatMap(rows=>rows.map(r=>r.date)))].sort(),count=g.w>760?7:g.w>480?5:3,ticks=[...new Set(Array.from({length:Math.min(count,allDates.length)},(_,i)=>allDates[Math.round(i*(allDates.length-1)/(Math.min(count,allDates.length)-1||1))]))];
 ticks.forEach((date,i)=>text(g.svg,x(date),b.y+b.h+26,(g.w<480?date.slice(2,7):date.slice(0,7)).replace('-','.'),ticks.length===1?'middle':i===0?'start':i===ticks.length-1?'end':'middle',{class:'axis-label'}));
 const tableRows=[],boundaries=new Set();
 if(showBands)series.forEach((s,i)=>{
  // Preserve gaps when a custom point update no longer matches an archived
  // median: no invented interpolation across missing uncertainty estimates.
  const segments=[];let segment=[];
  sets[i].forEach((row,j)=>{const bounds=intervals[i][j];if(bounds)segment.push({date:row.date,...bounds});else if(segment.length){segments.push(segment);segment=[];}});
  if(segment.length)segments.push(segment);
  for(const points of segments)for(const level of [95,80]){
   const bounds=points.map(p=>({date:p.date,lower:p['lower'+level],upper:p['upper'+level]})),divisor=metrics[s.key].divisor,y=v=>b.y+b.h-v/divisor/max*b.h;
   const attrs={'data-interval':level,'data-series':s.key,'data-scenario':s.scenario,'data-algorithm':s.algorithm,'data-bounds':JSON.stringify(bounds),'data-divisor':divisor,'pointer-events':'none'};
   if(bounds.length===1){const p=bounds[0];svgNode('line',{...attrs,x1:x(p.date),x2:x(p.date),y1:y(p.lower),y2:y(p.upper),stroke:s.color,'stroke-width':level===95?10:5,opacity:level===95?.1:.2},g.svg);}
   else svgNode('polygon',{...attrs,points:[...bounds.map(p=>x(p.date)+','+y(p.upper)),...bounds.slice().reverse().map(p=>x(p.date)+','+y(p.lower))].join(' '),fill:s.color,opacity:level===95?.09:.18},g.svg);
  }
 });
 series.forEach((descriptor,i)=>{
  const {key,color,scenario,algorithm,algorithms,historyColor,dash}=descriptor,rows=sets[i],y=r=>b.y+b.h-plotted(r,key)/max*b.h,lastObserved=all[i].filter(r=>r.phase==='observed').at(-1),obs=rows.filter(r=>r.phase==='observed'),future=rows.filter(r=>r.phase==='forecast');
  const pointString=rr=>rr.map(r=>x(r.date)+','+y(r)).join(' ');
  if(lastObserved&&stamp(lastObserved.date)>=start&&stamp(lastObserved.date)<=end&&!boundaries.has(lastObserved.date)){line(g.svg,x(lastObserved.date),b.y,x(lastObserved.date),b.y+b.h,{'stroke-dasharray':'3 5','data-observed-end':lastObserved.date});boundaries.add(lastObserved.date);}
  if(obs.length&&descriptor.historyLeader===i)svgNode('polyline',{points:pointString(obs),stroke:historyColor,class:'curve','data-series':key,'data-scenario':scenario,'data-algorithm':'observed','data-algorithms':'[]','data-phase':'observed'},g.svg);
  if(future.length&&descriptor.forecastLeader===i){const connect=obs.length?[obs.at(-1),...future]:future;svgNode('polyline',{points:pointString(connect),stroke:color,class:'curve','stroke-dasharray':dash,'data-series':key,'data-scenario':scenario,'data-algorithm':algorithm,'data-algorithms':JSON.stringify(algorithms),'data-phase':'forecast'},g.svg);}
  rows.forEach(row=>{
   const historical=row.phase==='observed',method=historical?'observed':algorithm;
   if(historical&&descriptor.historyLeader!==i)return;
   const raw=value(row,key),plotValue=plotted(row,key),kind=evidence(row,key),cx=x(row.date),cy=y(row),attrs={fill:historical?historyColor:color,'data-key':key+'-'+scenario+'-'+method+'-'+row.date,'data-series':key,'data-scenario':scenario,'data-algorithm':method,'data-algorithms':JSON.stringify(historical?[]:algorithms),'data-date':row.date,'data-month':row.month,'data-value':raw,'data-plot-value':plotValue,'data-kind':kind};
   if(visiblePoint(descriptor,row,i)){
    if(kind==='estimated')svgNode('polygon',{...attrs,points:cx+','+(cy-2.8)+' '+(cx+2.8)+','+cy+' '+cx+','+(cy+2.8)+' '+(cx-2.8)+','+cy},g.svg);
    else svgNode('circle',{...attrs,cx,cy,r:2.5},g.svg);
   }
   const entry=[row.date,row.month,metrics[key].name,raw,unit(key),plotValue,metrics[key].display,evidenceNames[kind],scenario,state.team,method,historical?'公共历史':algorithmById[algorithm].name];
   if(showBands){const bounds=historical?null:intervalValues(key,scenario,algorithm,row.date);entry.push(...['lower80','upper80','lower95','upper95'].map(name=>bounds?bounds[name]:''),bounds?'名义模型分位；沿用原始单位；未经长期覆盖率校准':'');}
   tableRows.push(entry);
  });
 });
 function showMonth(month){
  const parts=[month];series.forEach((s,i)=>{const row=sets[i].find(r=>r.month===month);if(row&&visiblePoint(s,row,i)){const name=(single?s.baseName+' · ':'')+metrics[s.key].name,method=row.phase==='observed'?'公共历史':s.algorithms.map(id=>algorithmById[id].name).join(' / ');parts.push(name+' · '+method+' '+fmt(plotted(row,s.key),3)+' '+metrics[s.key].display+'（'+row.date+'，'+windowBasis(s.key)+'，'+evidenceNames[evidence(row,s.key)]+'）');}
   const bounds=showBands&&row?.phase==='forecast'?intervalValues(s.key,s.scenario,s.algorithm,row.date):null;
   if(bounds)parts.push((single?s.baseName+' · ':'')+metrics[s.key].name+' · 名义80% '+fmt(bounds.lower80/metrics[s.key].divisor,3)+'–'+fmt(bounds.upper80/metrics[s.key].divisor,3)+'；95% '+fmt(bounds.lower95/metrics[s.key].divisor,3)+'–'+fmt(bounds.upper95/metrics[s.key].divisor,3)+' '+metrics[s.key].display);
  });
  readout(parts);
 }
 drawQuarterLabels(g,labels.columns,x,max);
 const crosshair=line(g.svg,b.x,b.y,b.x,b.y+b.h,{class:'axis-line',visibility:'hidden','stroke-dasharray':'3 4'});
 const overlay=svgNode('rect',{x:b.x,y:b.y,width:b.w,height:b.h,fill:'transparent','data-interaction':'monthly-readout'},g.svg);
 const move=event=>{const box=g.svg.getBoundingClientRect(),px=event.clientX-box.left,date=allDates.reduce((a,d)=>Math.abs(x(d)-px)<Math.abs(x(a)-px)?d:a,allDates[0]);crosshair.setAttribute('x1',x(date));crosshair.setAttribute('x2',x(date));crosshair.setAttribute('visibility','visible');showMonth(date.slice(0,7));};
 overlay.addEventListener('pointermove',move);overlay.addEventListener('click',move);overlay.addEventListener('pointerleave',()=>crosshair.setAttribute('visibility','hidden'));
 const counts=[...new Set(sets.map(rr=>rr.length))];
 const scrollable=g.w>g.host.clientWidth+1;
 const curveCount=futureVisible?series.filter((s,i)=>s.forecastLeader===i).length:bases.length;
 $('trd-chart-context').textContent=allDates[0]+' — '+allDates.at(-1)+' · '+curveCount+'条曲线 · '+state.algorithms.length+'种算法 · 每条'+counts.join('/')+'个点'+(single?'':' · 情景'+state.scenario)+(scrollable?' · 可横向滑动查看全部标注':'');
 const cutoffs=[...new Set(all.map(rr=>rr.filter(r=>r.phase==='observed').at(-1)?.date).filter(Boolean))].join('、');
 const merged=series.filter(s=>s.algorithms.length>1),scenarioOverlap=single&&state.scenarios.includes('A')&&state.scenarios.includes('B');
 $('trd-chart-note').textContent='数值从各指标首个数据月起每隔3个月标注，另保留区间终点；单位与纵轴一致。所有曲线共用从0开始的纵轴。实线为公共观测期，虚线为各算法预测；菱形为条件估算。历史截止日期：'+cutoffs+'。悬浮或点击查看当月取值。'+(series.length>1?' 可取消勾选大值曲线，放大查看小值变化。':'')+(merged.length?' 同一指标、情景下数值相同的算法已合并绘制，图例保留算法名称，数据导出仍逐算法列出。':'')+(scenarioOverlap?' A/B在当前口径下数值相同，曲线重合。':'');
 $('trd-chart-note').textContent+=' 输出观测已按官方14日滑动平均平滑，预测延续该口径，不对月度点重复平滑；Agent与任务保留28日窗口。';
 if(state.algorithms.includes('ensemble_uncertainty'))$('trd-chart-note').textContent+=' 融合曲线为预测分布中位数，输出采用原14日分布。'+(showBands?'浅色为名义95%、深色为80%分位带，未校准四年覆盖率；输入和计算量的区间仍条件于固定资源比率。':'可开启名义区间查看模型分歧；默认关闭以便比较趋势。')+(algorithmData.meta.uncertainty_omitted_points?.length?' 部分中心值已自定义更新，与归档中位数不一致的月份不显示旧区间。':'');
 const columns=['日期','月份','指标','原始值','原始单位','图表值','图表单位','证据','情景','团队人数','算法ID','算法'];
 if(showBands)columns.push('名义80%下界','名义80%上界','名义95%下界','名义95%上界','区间口径');
 setTable(columns,tableRows);
 mount(g);showMonth(allDates.at(-1).slice(0,7));
}
function annualChart(key,title,stackedKeys=null){
 $('trd-chart-title').textContent=title;const stacked=!!stackedKeys,keys=stackedKeys||[key],share=stacked&&state.detailMode==='share',rows=state.view==='scenarios'?years.flatMap(year=>'ABC'.split('').map(s=>rowAt(year,s))):years.map(year=>rowAt(year));
 const g=frame(),b=g.b,divisor=metrics[keys[0]].divisor,max=share||metrics[keys[0]].ratio?100:nice(Math.max(...rows.map(r=>keys.reduce((sum,k)=>sum+value(r,k),0)/divisor))*1.14),step=b.w/(state.view==='scenarios'?15:5),width=Math.min(state.view==='scenarios'?26:68,step*.65);
 axis(g,'left',keys.join(','),max,share?1:divisor,share?'占比 / %':metrics[keys[0]].display);
 legend(state.view==='scenarios'?['A','B','C'].map((s,i)=>({name:s+' · '+scenarioNames[s],color:['var(--blue)','var(--purple)','var(--accent)'][i]})):keys.map((k,i)=>({name:metrics[k].name,color:i?'var(--orange)':metrics[k].color})));
 const table=[];
 rows.forEach((row,i)=>{
  const x=b.x+step*(i+.5),total=keys.reduce((sum,k)=>sum+value(row,k),0);let acc=0;
  keys.forEach((k,j)=>{
   const raw=value(row,k),pl=share?(total?raw/total*100:0):raw/divisor,y=b.y+b.h-(acc+pl)/max*b.h,color=state.view==='scenarios'?{A:'var(--blue)',B:'var(--purple)',C:'var(--accent)'}[row.scenario]:j?'var(--orange)':metrics[k].color;
   const rect=svgNode('rect',{x:x-width/2,y,width,height:pl/max*b.h,fill:color,opacity:state.view==='scenarios'&&row.scenario!==state.scenario?.6:1,'data-key':row.year+'-'+row.scenario+'-'+k,'data-series':k,'data-year':row.year,'data-scenario':row.scenario,'data-value':raw,'data-plot-value':pl,'data-kind':annualEvidence(row.year,k)},g.svg);
   bindMark(rect,[String(row.year)+' · '+row.scenario+' '+scenarioNames[row.scenario],metrics[k].name+' '+fmt(raw,2)+' '+unit(k),windowBasis(k),share?fmt(pl,2)+'%':'']);
   table.push([row.year,row.date,row.scenario,metrics[k].name,raw,unit(k),share?pl:'',evidenceNames[annualEvidence(row.year,k)],state.team]);acc+=pl;
  });
  if(state.view==='scenarios'){
   text(g.svg,x,b.y+b.h+17,row.scenario,'middle',{class:'axis-label'});
   if(row.scenario==='B')text(g.svg,x,b.y+b.h+34,g.w<480?String(row.year).slice(2):row.year,'middle',{class:'axis-label'});
   if(row.scenario===state.scenario&&g.w>600)text(g.svg,x,b.y+b.h-acc/max*b.h-9,fmt(acc,1),'middle');
  }else{text(g.svg,x,b.y+b.h+25,row.year,'middle',{class:'axis-label'});text(g.svg,x,b.y+b.h-acc/max*b.h-9,share?'100%':fmt(acc,g.w<400?0:1),'middle');}
 });
 $('trd-chart-context').textContent='原始 OLS 基准 · 2026–2030 · '+(state.view==='scenarios'?'每年A/B/C，共15根柱':'情景'+state.scenario+' · '+scenarioNames[state.scenario]);
 $('trd-chart-note').textContent='2026为各指标最新公开观测或对应条件估算；2027–2030均为当年11月18日预测。输出及资源采用14日输出口径；Agent与任务保留28日。'+(state.view==='cache'?'缓存输入为每日累计复用量，不是KV驻留容量。':'')+(state.view==='scenarios'?'同一指标共用纵轴；A/B在当前团队聚合口径下数值相同。':'');
 const row=rowAt(2030);readout(['2030-11-18 · '+state.scenario, ...keys.map(k=>metrics[k].name+' '+fmt(value(row,k),2)+' '+unit(k))]);
 setTable(['年度','数据日期','情景','指标','原始团队日量','单位','占比%','证据','团队人数'],table);mount(g);
}
function renderCategories(){
 $('trd-chart-title').textContent='18类研发活动 · 输出Token构成';const g=frame(),rows=data.category_mix.filter(r=>r.year===2030&&r.scenario===state.scenario),cols=g.w>=700?2:1,gap=34,colW=(g.w-gap*(cols-1))/cols,count=Math.ceil(rows.length/cols),rowH=36,height=count*rowH+52,max=nice(Math.max(...rows.map(r=>r.share))*100*1.08);
 g.h=height;g.svg.setAttribute('height',height);g.svg.setAttribute('viewBox','0 0 '+g.w+' '+height);
 const names=['研发方向','项目去留','资源决策','实验规划','技术规范','研究代码','数据集','训练评估','集群运维','服务可靠性','实验分析','模型分析','用量分析','研究审查','研究文档','支持审查','状态日志','决策发布'],table=[];
 rows.forEach((r,i)=>{
  const c=Math.floor(i/count),x=c*(colW+gap),y=24+(i%count)*rowH,raw=r.output_tokens_per_team_day*state.team/100,label=r.category_label.split(' ')[0]+' '+names[i];
  text(g.svg,x,y,label);text(g.svg,x+colW,y,fixed(r.share*100,2)+'%','end');
  svgNode('rect',{x,y:y+8,width:colW,height:7,fill:'var(--soft)'},g.svg);
  const bar=svgNode('rect',{x,y:y+8,width:r.share*100/max*colW,height:7,fill:'var(--accent)','data-series':'output_share','data-category':r.category,'data-value':r.share,'data-raw-value':raw},g.svg);
  bindMark(bar,[r.category_label,fmt(raw,2)+' Token/日',fixed(r.share*100,3)+'%']);table.push([r.category_label,r.share,raw,'Token/日','2030-11-18',state.scenario,state.team]);
 });
 for(let c=0;c<cols;c++)[0,.5,1].forEach(t=>text(g.svg,c*(colW+gap)+t*colW,height-8,fmt(max*t,1)+'%',t===0?'start':t===1?'end':'middle',{class:'axis-label'}));
 legend([{name:'输出Token占比',color:'var(--accent)'}]);$('trd-chart-context').textContent='原始 OLS 基准 · 2030-11-18 · '+state.scenario+' · '+state.team+'人';
 $('trd-chart-note').textContent='18类输出合计为100%；使用官方14日输出统计及既有OLS预测方法。所有条形使用相同尺度。';readout(['2030-11-18','全部输出 '+fmt(value(rowAt(2030),'output_tokens_per_team_day'),2)+' Token/日 · 14日平均口径']);
 setTable(['活动类别','占比','团队日量','单位','日期','情景','团队人数'],table);mount(g);
}
function renderGrowth(){
 $('trd-chart-title').textContent='相对2026的资源需求倍数';const keys=['input_tokens_per_team_day','output_tokens_per_team_day','task_starts_per_team_day','agent_hours_per_team_day','mean_online_agent_equivalents','eflop_per_team_day'],labels=['输入Token','输出Token','研发任务','Agent时长','活动当量','理论计算'],g=frame(),left=g.w<400?70:100,top=38,step=(g.w-left-2)/5,rowH=g.w<400?42:48,height=top+rowH*keys.length+34,table=[];
 g.svg.setAttribute('height',height);g.svg.setAttribute('viewBox','0 0 '+g.w+' '+height);
 const max=Math.max(...years.flatMap(year=>keys.map(key=>value(rowAt(year),key)/baseline(key))));
 years.forEach((year,i)=>text(g.svg,left+step*(i+.5),20,g.w<400?String(year).slice(2):year,'middle',{class:'axis-label'}));
 keys.forEach((key,j)=>{
  text(g.svg,left-8,top+rowH*(j+.5)+4,labels[j],'end',{class:'axis-label'});
  years.forEach((year,i)=>{
   const raw=value(rowAt(year),key),base=baseline(key),ratio=raw/base,x=left+i*step+2,y=top+j*rowH+2,alpha=15+45*(ratio-1)/(max-1||1);
   const rect=svgNode('rect',{x,y,width:step-4,height:rowH-4,fill:'color-mix(in srgb,var(--blue) '+alpha+'%,var(--surface))','data-series':key,'data-year':year,'data-value':ratio,'data-raw-value':raw,'data-baseline-value':base},g.svg);
   bindMark(rect,[String(year),metrics[key].name+' '+fmt(ratio,3)+'×',fmt(raw,2)+' '+unit(key),'2026基线 '+fmt(base,2)]);
   text(g.svg,x+(step-4)/2,y+(rowH-4)/2+4,fmt(ratio,g.w<400?1:2)+(g.w<400?'':'×'),'middle',{'pointer-events':'none'});
   table.push([year,metrics[key].name,ratio,raw,base,unit(key),state.scenario,state.team]);
  });
 });
 legend([{name:'浅 → 深：增长倍数增加',color:'var(--blue)'}]);$('trd-chart-context').textContent='原始 OLS 基准 · 同情景、同人数 · 各指标自身2026最新基线＝1';
 $('trd-chart-note').textContent='指标的2026观测截止日期分别保留；输出及资源采用14日输出口径，Agent与任务保留28日。倍数反映各自相对变化，不代表不同指标的绝对规模相同。';readout(['2030-11-18',...keys.filter(k=>k==='output_tokens_per_team_day'||k==='agent_hours_per_team_day').map(k=>metrics[k].name+' '+fmt(value(rowAt(2030),k)/baseline(k),2)+'×')]);
 setTable(['年度','指标','相对2026倍数','团队日量','2026基线','单位','情景','团队人数'],table);mount(g);
}
function valueOut(name,raw,shown){const e=out(name);if(e){e.dataset.value=String(raw);e.textContent=shown;}}
function summary(){
 const row=headlineRow(),input=value(row,'input_tokens_per_team_day'),output=value(row,'output_tokens_per_team_day'),hours=value(row,'agent_hours_per_team_day'),ef=value(row,'eflop_per_team_day');
 root.querySelector('.headline-stats').dataset.headlineAlgorithm=state.headlineAlgorithm;root.querySelector('.headline-stats').dataset.headlineDate=row.date;
 $('trd-source-predictions').dataset.sourceAlgorithm=state.headlineAlgorithm;out('source-algorithm-name').textContent=algorithmById[state.headlineAlgorithm].name;out('source-scenario').textContent=state.scenario;
 valueOut('input-tokens',input,fixed(input/1e8));valueOut('output-tokens',output,fixed(output/1e8));valueOut('total-tokens',input+output,fixed((input+output)/1e8));
 valueOut('agent-hours',hours,fmt(hours,0));valueOut('agent-equivalents',hours/24,fmt(hours/24,0));valueOut('tasks',value(row,'task_starts_per_team_day'),fmt(value(row,'task_starts_per_team_day'),0));
 valueOut('compute-eflop',ef,fixed(ef));valueOut('compute-pflops',value(row,'compute_pflops_window'),fixed(value(row,'compute_pflops_window')));
 valueOut('cache-hit-rate',row.prefix_cache_hit_rate,fixed(row.prefix_cache_hit_rate*100));const weightTB=data.model.total_parameters*data.model.weights.bytes_per_parameter/1e12;valueOut('weight-tb',weightTB,fixed(weightTB));
 out('weight-format').textContent=data.model.weights.format;
 for(const [name,key,divisor]of[['cached-input-tokens','cached_input_tokens_per_team_day',1e8],['uncached-input-tokens','uncached_input_tokens_per_team_day',1e8],['prefill-eflop','prefill_eflop_per_team_day',1],['decode-eflop','decode_eflop_per_team_day',1]])valueOut(name,value(row,key),fixed(value(row,key)/divisor));
 out('window-summary').textContent=state.window+'小时窗口';out('selection-summary').textContent='2030-11-18最终预测 · '+state.scenario+' '+scenarioNames[state.scenario]+' · '+state.team+'人'+(state.headlineAlgorithm==='ensemble_uncertainty'?' · 中位预测':'');
 out('headline-algorithm-name').textContent=algorithmById[state.headlineAlgorithm].name;
 out('model-summary').textContent=fmt(data.model.total_parameters/1e12,2)+'T MoE · 激活'+fixed(data.model.active_parameters/1e9)+'B · Top'+data.model.experts_per_token;
 const bm=data.baseline_metadata,factor=state.team/100;
 out('baseline-output').textContent=bm.output_14d.date+'：'+fmt(bm.output_14d.value_per_team_day*factor/1e4,0)+'万Token/日 · 官方14日平均';
 out('baseline-output').dataset.value14d=String(bm.output_14d.value_per_team_day*factor);
 out('baseline-activity').textContent=bm.agent_hours.date+'：Agent '+fmt(bm.agent_hours.value_per_team_day*factor,0)+'小时/日 · 任务 '+fmt(bm.task_starts.value_per_team_day*factor,0)+'项/日 · 28日口径';
}
function syncControls(){
 const group=categories[state.category],single=group.keys.length===1;
 selectOptions(controls.primary,group.keys.map(value=>({value,name:metrics[value].name})));
 for(const [key,c]of Object.entries(controls))c.value=String(state[key]);
 const trend=state.view==='trend',comparison=state.view==='scenarios',decompose=['cache','compute'].includes(state.view);
 $('trd-intervals-field').hidden=!(trend&&state.algorithms.includes('ensemble_uncertainty')&&state.category!=='cache'&&state.range!=='observed');
 $('trd-intervals').checked=state.showIntervals;
 $('trd-category-field').hidden=!(trend||comparison);$('trd-primary-field').hidden=!comparison;$('trd-range-field').hidden=!trend;$('trd-detail-mode-field').hidden=!decompose;
 $('trd-algorithms-field').hidden=false;syncAlgorithms();
 $('trd-metrics-field').hidden=!(trend&&!single);$('trd-scenarios-field').hidden=!(trend&&single);$('trd-category-note').hidden=false;
 root.querySelector('.explorer-controls').hidden=false;$('trd-date-controls').hidden=!(trend&&state.range==='custom');
 checkOptions($('trd-metric-options'),group.keys.map(value=>({value,name:metrics[value].name,color:metrics[value].color})),state.selectedMetrics,'metric');
 checkOptions($('trd-scenario-options'),['A','B','C'].map(value=>({value,name:value+' · '+scenarioNames[value],color:scenarioColors[value]})),state.scenarios,'scenario');
 $('trd-category-note').textContent=trend?group.note+(single?' 本类只有一个指标，可勾选多个情景；顶部取值仍按“增长情景”计算。':' 可多选同类指标，至少保留一项；勾选后使用相同单位和刻度。')+' “外推算法”中，方框选择对比曲线，圆钮独立指定顶部2030-11-18预测。':(comparison?group.note+' 每次比较一个指标的2026–2030年A/B/C情景。 ':'')+'本图保留原始 OLS 基准；仍可在“外推算法”的“顶部”列切换顶部预测，折线选择仅用于月度趋势。';
}
function render(announce=false){
 try{setError('');syncControls();syncPageLink();summary();$('trd-chart-context').textContent='';$('trd-chart-note').textContent='';
  if(state.view==='trend')renderTrend();
  else if(state.view==='scenarios')annualChart(state.primary,metrics[state.primary].name+' · 年度情景比较');
  else if(state.view==='cache')annualChart('input_tokens_per_team_day','输入Token · 缓存分解',['cached_input_tokens_per_team_day','uncached_input_tokens_per_team_day']);
  else if(state.view==='compute')annualChart('eflop_per_team_day','理论计算 · Prefill / Decode分解',['prefill_eflop_per_team_day','decode_eflop_per_team_day']);
  else if(state.view==='categories')renderCategories();
  else renderGrowth();
  root.dataset.state=JSON.stringify(state);root.dataset.ready='true';if(announce)$('trd-live-summary').textContent=$('trd-chart-title').textContent+'已更新。'+$('trd-chart-context').textContent;
 }catch(error){setError('图表暂时无法显示：'+error.message);root.dataset.ready='error';console.error(error);}
}
for(const [key,control]of Object.entries(controls))control.addEventListener('change',()=>{
 const next={...state,[key]:control.value};
 if(key==='category'){const group=categories[control.value];next.primary=group.default;next.selectedMetrics=[group.default];next.scenarios=[state.scenario];}
 if(key==='scenario'&&state.scenarios.length===1)next.scenarios=[control.value];
 state=normalise(next);render(true);persist();
});
$('trd-intervals').addEventListener('change',()=>{state=normalise({...state,showIntervals:$('trd-intervals').checked});render(true);persist();});
for(const [id,key,attribute]of[['trd-metric-options','selectedMetrics','metric'],['trd-scenario-options','scenarios','scenario']])$(id).addEventListener('change',event=>{
 const input=event.target;if(!input.matches('input[type="checkbox"]'))return;
 const chosen=input.dataset[attribute],selected=input.checked?[...state[key],chosen]:state[key].filter(k=>k!==chosen);
 state=normalise({...state,[key]:selected});render(true);persist();
});
$('trd-algorithm-options').addEventListener('change',event=>{
 const input=event.target;
 if(input.matches('input[data-headline-choice]')){
  if(!input.checked)return;
  state=normalise({...state,headlineAlgorithm:input.value});render(true);persist();
  $('trd-live-summary').textContent='顶部预测已切换为'+algorithmById[state.headlineAlgorithm].name+'，对比曲线选择保持不变。';return;
 }
 if(!input.matches('input[data-algorithm]'))return;
 const selected=input.checked?[...state.algorithms,input.value]:state.algorithms.filter(id=>id!==input.value);
 if(selected.length<1||selected.length>3){syncAlgorithms();return;}
 state=normalise({...state,algorithms:selected});render(true);persist();
});
const algorithmMenu=$('trd-algorithms-menu');
document.addEventListener('pointerdown',event=>{if(algorithmMenu.open&&!algorithmMenu.contains(event.target))algorithmMenu.open=false;});
algorithmMenu.addEventListener('keydown',event=>{if(event.key==='Escape'&&algorithmMenu.open){event.preventDefault();algorithmMenu.open=false;algorithmMenu.querySelector('summary').focus();}});
algorithmMenu.addEventListener('focusout',()=>setTimeout(()=>{if(!algorithmMenu.contains(document.activeElement))algorithmMenu.open=false;},0));
$('trd-data-details').addEventListener('toggle',()=>{if($('trd-data-details').open)renderTable();});
$('trd-download').addEventListener('click',()=>{const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"',csv='\ufeff'+[exportColumns,...exportRows].map(row=>row.map(quote).join(',')).join('\r\n'),url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})),link=document.createElement('a');link.href=url;link.download='team-'+state.team+'-'+state.view+'-'+state.category+'-'+(state.view==='trend'&&categories[state.category].keys.length===1?state.scenarios.join(''):state.scenario)+'.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),2000);});
for(const [title,url]of[['OpenAI研究员输出统计','https://openai.com/zh-Hans-CN/index/research-acceleration-view-inside-openai/#chart-4QLdZ4iw0n4L9rYGTvteZK'],['OpenAI Agent活动统计','https://openai.com/index/research-acceleration-jagged-frontier/#agent-workdays-research'],['公开编码代理轨迹','https://github.com/SWE-bench/experiments/tree/main/evaluation/verified/20260217_mini-v2.0.0_kimi-k2-5-high']]){const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=title;$('trd-source-links').append(a);}
window.addEventListener('openai:set_globals',event=>{const s=event.detail?.globals?.widgetState?.modelContent;if(s?.explorer===2){state=normalise(s);render();}});
let lastWidth=0;const observer=new ResizeObserver(entries=>{const width=entries[0]?.contentRect.width;if(!width||Math.abs(width-lastWidth)<1)return;lastWidth=width;cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(()=>render());});observer.observe($('trd-chart-main'));
render();
})();
