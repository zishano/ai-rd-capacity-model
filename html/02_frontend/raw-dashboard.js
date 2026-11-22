(()=>{
'use strict';
const root=document.getElementById('raw-research-dashboard-v1');if(!root)return;
const $=id=>root.querySelector('#'+id),data=JSON.parse($('raw-inline-data').textContent),ns='http://www.w3.org/2000/svg';
const storageKey=root.id+':state-v1',defaults={view:'workdays',method:'legacy_ols',concurrencyMethod:'legacy_log_complement',range:'all',start:'2026-01-20',end:'2030-11-18',showUncertainty:false};
const controlIds={view:'raw-view',method:'raw-method',concurrencyMethod:'raw-concurrency-method',range:'raw-range',start:'raw-start',end:'raw-end'};
const controls=Object.fromEntries(Object.entries(controlIds).map(([key,id])=>[key,$(id)]));
const fmt=(v,d=2)=>Number(v).toLocaleString('zh-CN',{maximumFractionDigits:d}),fixed=(v,d=2)=>Number(v).toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d});
const stamp=date=>Date.parse(date+'T00:00:00Z'),sum=values=>values.reduce((a,b)=>a+b,0),monthIndex=date=>Number(date.slice(0,4))*12+Number(date.slice(5,7))-1;
const methodName=(id,concurrent=false)=>(concurrent?data.concurrencyMethods:data.methods).find(m=>m.id===id)?.name||id;
function normalise(raw){
 const s={...defaults,...raw};
 if(!Object.hasOwn(data.metrics,s.view))s.view=defaults.view;
 if(!data.methods.some(m=>m.id===s.method))s.method=defaults.method;
 if(!data.concurrencyMethods.some(m=>m.id===s.concurrencyMethod))s.concurrencyMethod=defaults.concurrencyMethod;
 if(!['all','observed','forecast','custom'].includes(s.range))s.range='all';
 s.showUncertainty=s.showUncertainty===true;
 for(const k of ['start','end'])if(typeof s[k]!=='string')s[k]=defaults[k];return s;
}
let saved;try{saved=JSON.parse(localStorage.getItem(storageKey));}catch(_){}
let state=normalise(saved),exportRows=[],exportColumns=[],resizeFrame=0;
for(const [key,methods]of [['method',data.methods],['concurrencyMethod',data.concurrencyMethods]])for(const method of methods){const option=document.createElement('option');option.value=method.id;option.textContent=method.name;controls[key].append(option);}
// Only these two sibling files may receive the return link. The state is inert
// JSON in the fragment, so local file navigation also works without web storage.
const navigation=new URLSearchParams(location.hash.slice(1)),requestedReturn=navigation.get('return');
const returnFile=['resource-dashboard-preview.html','team-resource-dashboard.html'].includes(requestedReturn)?requestedReturn:'resource-dashboard-preview.html';
let returnState;try{const parsed=JSON.parse(navigation.get('resource-state'));if(parsed&&typeof parsed==='object'&&!Array.isArray(parsed))returnState=parsed;}catch(_){}
$('raw-back').href=returnFile+(returnState?'#'+new URLSearchParams({'resource-state':JSON.stringify(returnState)}).toString():'');
function persist(){try{localStorage.setItem(storageKey,JSON.stringify(state));}catch(_){}}
function rowsFor(metric){
 const selected=metric==='concurrency'?state.concurrencyMethod:state.method,m=data.metrics[metric];
 return [['observed',m.history],['forecast',m.forecast[selected]]].flatMap(([phase,series])=>series.dates.map((date,i)=>({date,values:series.values[i],phase,method:phase==='observed'?'observed':selected}))).sort((a,b)=>a.date.localeCompare(b.date));
}
function uncertaintyFor(metric=state.view){const m=data.metrics[metric],method=metric==='concurrency'?state.concurrencyMethod:state.method;return m.uncertainty?.[method];}
function filtered(rows){return rows.filter(r=>state.range==='observed'?r.phase==='observed':state.range==='forecast'?r.phase==='forecast':state.range==='custom'?r.date>=state.start&&r.date<=state.end:true);}
function svgNode(tag,attrs={},parent,content){const e=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))if(v!==undefined&&v!==null)e.setAttribute(k,String(v));if(content!==undefined)e.textContent=content;if(parent)parent.append(e);return e;}
function text(g,x,y,content,anchor='start',attrs={}){return svgNode('text',{x,y,'text-anchor':anchor,...attrs},g,String(content));}
function line(g,x1,y1,x2,y2,attrs={}){return svgNode('line',{x1,y1,x2,y2,class:'grid-line',...attrs},g);}
function nice(value){if(!(value>0))return 1;const p=10**Math.floor(Math.log10(value)),m=value/p;return [1,1.5,2,2.5,3,4,5,6,7,8,9,10].find(n=>n>=m)*p;}
function readout(parts){const host=$('raw-readout');host.replaceChildren();parts.forEach((part,i)=>{const e=document.createElement(i?'span':'strong');e.textContent=part;host.append(e);});}
function summary(){
 const end=metric=>rowsFor(metric).at(-1).values,work=data.metrics.workdays.series.findIndex(s=>s.id==='Overall Research');
 const summaries={'raw-workdays':end('workdays')[work],'raw-tasks':sum(end('tasks')),'raw-output':sum(end('output')),'raw-peak-ge16':sum(end('concurrency').slice(6))};
 for(const [id,value]of Object.entries(summaries)){const node=root.querySelector('[data-testid="'+id+'"]');node.dataset.value=String(value);node.textContent=fixed(value/(id==='raw-output'?1e4:id==='raw-peak-ge16'?.01:1));}
}
function legend(metric){
 const host=$('raw-legend'),m=data.metrics[metric],grouped=['tasks','output'].includes(metric);host.replaceChildren();const groups=new Map();
 for(const series of m.series){let target=host;
  if(grouped){const key=series.group||'其他';if(!groups.has(key)){const group=document.createElement('div');group.className='raw-legend-group';const heading=document.createElement('div');heading.className='raw-legend-group-title';heading.textContent=key;group.append(heading);host.append(group);groups.set(key,group);}target=groups.get(key);}
  const item=document.createElement('span');item.className='legend-item';const swatch=document.createElement('i');swatch.className='legend-swatch';swatch.style.borderTopColor=series.color;if(metric==='workdays'&&series.id!=='Overall Research')swatch.style.borderTopStyle='dashed';item.append(swatch,document.createTextNode(series.name));target.append(item);
 }
 host.classList.toggle('raw-grouped-legend',grouped);
}
function error(message){$('raw-error').textContent=message||'';$('raw-error').hidden=!message;}
function setTable(rows){
 exportColumns=['日期','系列ID','系列','原始值','原始单位','图表值','图表单位','阶段','算法ID','图表'];exportRows=rows;
 $('raw-data-count').textContent=rows.length+'条记录 · 保留原始日观测与月度预测';$('raw-download').disabled=!rows.length;if($('raw-data-details').open)renderTable();
}
function renderTable(){const table=$('raw-data-table');table.replaceChildren();const header=table.createTHead().insertRow();for(const name of exportColumns){const cell=document.createElement('th');cell.scope='col';cell.textContent=name;header.append(cell);}const body=table.createTBody();for(const row of exportRows){const tr=body.insertRow();for(const value of row)tr.insertCell().textContent=String(value);}}
function quarterDates(all,rows){
 const anchor=monthIndex(all[0].date),lastInMonth=new Map();for(const row of rows)lastInMonth.set(row.date.slice(0,7),row.date);
 return rows.filter(r=>(monthIndex(r.date)-anchor)%3===0&&lastInMonth.get(r.date.slice(0,7))===r.date||r===rows.at(-1));
}
function labelNumber(value){return fmt(value,Math.abs(value)<1?3:2);}
function labelsFor(metric,all,rows){
 if(metric==='concurrency')return [];
 const m=data.metrics[metric];return quarterDates(all,rows).map(row=>({date:row.date,items:metric==='workdays'?row.values.map((v,i)=>({value:v/m.divisor,color:m.series[i].color,series:m.series[i].id})): [{value:sum(row.values)/m.divisor,color:'var(--fg)',series:'total'}]}));
}
function renderChart(){
 const metric=state.view,m=data.metrics[metric],all=rowsFor(metric),rows=filtered(all),stacked=metric!=='workdays',active=metric==='concurrency'?state.concurrencyMethod:state.method;
 const uncertainty=uncertaintyFor(metric),visibleDates=new Set(rows.filter(row=>row.phase==='forecast').map(row=>row.date)),bands=state.showUncertainty&&uncertainty?uncertainty.bands.map(band=>({...band,points:band.points.filter(point=>visibleDates.has(point.date))})).filter(band=>band.points.length):[];
 $('raw-uncertainty-controls').hidden=!uncertainty;$('raw-show-uncertainty').checked=state.showUncertainty;
 $('raw-chart-title').textContent=m.title;legend(metric);
 $('raw-chart-context').textContent='';$('raw-chart-note').textContent='';
 if(state.range==='custom'&&(!Number.isFinite(stamp(state.start))||!Number.isFinite(stamp(state.end))||state.start>state.end)||!rows.length){error('当前日期区间没有数据，请调整开始与结束日期。');$('raw-chart').replaceChildren();readout(['当前区间无可展示数据']);setTable([]);return;}
 const start=stamp(rows[0].date),end=stamp(rows.at(-1).date),span=end-start,labels=labelsFor(metric,all,rows);
 const measure=document.createElement('canvas').getContext('2d');measure.font='600 12px '+getComputedStyle(root).fontFamily;
 for(const column of labels){for(const item of column.items){item.label=labelNumber(item.value);item.width=measure.measureText(item.label).width;}column.width=Math.max(...column.items.map(item=>item.width));}
 // Reserve space for the labels themselves, not for their nearest date gap.
 // Endpoint labels can move inward without stretching a five-year plot.
 const labelGap=16,minWidth=Math.max(rows.length===1?0:900,sum(labels.map(column=>column.width))+Math.max(0,labels.length-1)*labelGap+96);
 const host=$('raw-chart'),viewport=host.clientWidth,w=Math.max(viewport,Math.ceil(minWidth)),h=viewport<480?370:430,b={x:68,y:40,w:w-88,h:h-84};
 const svg=svgNode('svg',{width:w,height:h,viewBox:'0 0 '+w+' '+h,role:'img','aria-label':m.title,'data-view':metric,'data-method':active,'data-time-min':start,'data-time-max':end,'data-plot-x':b.x,'data-plot-y':b.y,'data-plot-width':b.w,'data-plot-height':b.h});if(w>viewport)svg.style.width=w+'px';
 svgNode('title',{},svg,m.title+'；'+m.display+'；'+m.windowDays+'日窗口');
 const max=metric==='concurrency'?100:nice(Math.max(...rows.map(row=>stacked?sum(row.values):Math.max(...row.values)),...bands.flatMap(band=>band.points.map(point=>point.upper95)))/m.divisor*1.14);
 const x=day=>b.x+(span?(stamp(day)-start)/span:.5)*b.w,y=value=>b.y+b.h-value/max*b.h;
 const axis=svgNode('g',{'data-axis':'left','data-min':0,'data-max':max,'data-divisor':m.divisor},svg);
 for(let i=0;i<=4;i++){const value=max*i/4,yy=y(value);line(svg,b.x,yy,b.x+b.w,yy);text(axis,b.x-8,yy+4,fmt(value,Math.abs(value)<1?3:2),'end',{class:'axis-label'});}
 line(axis,b.x,b.y,b.x,b.y+b.h,{class:'axis-line','data-axis-line':'true'});line(svg,b.x,b.y+b.h,b.x+b.w,b.y+b.h,{class:'axis-line'});text(axis,0,19,m.display,'start',{class:'axis-label'});
 const tickCount=Math.min(7,rows.length),ticks=[...new Set(Array.from({length:tickCount},(_,i)=>rows.reduce((a,r)=>Math.abs(stamp(r.date)-(start+span*i/(tickCount-1||1)))<Math.abs(stamp(a.date)-(start+span*i/(tickCount-1||1)))?r:a,rows[0]).date))];
 ticks.forEach((date,i)=>text(svg,x(date),b.y+b.h+26,date.slice(0,7).replace('-','.'),i===0?'start':i===ticks.length-1?'end':'middle',{class:'axis-label'}));
 const markLayer=svgNode('g',{'data-layer':'points'},svg),table=[];
 m.series.forEach((series,index)=>{
  const totalBefore=row=>sum(row.values.slice(0,index)),plot=row=>row.values[index]/m.divisor;
  if(stacked){const upper=rows.map(row=>x(row.date)+','+y((totalBefore(row)+row.values[index])/m.divisor)),lower=[...rows].reverse().map(row=>x(row.date)+','+y(totalBefore(row)/m.divisor));svgNode('path',{d:'M'+upper.join(' L')+' L'+lower.join(' L')+' Z',fill:series.color,'data-series':series.id,'data-method':active,'data-shape':'stacked-area'},svg);if(rows.length===1){const row=rows[0],top=(totalBefore(row)+row.values[index])/m.divisor;svgNode('rect',{x:x(row.date)-18,y:y(top),width:36,height:plot(row)/max*b.h,fill:series.color,'data-series':series.id,'data-shape':'single-date-stack'},svg);}}
  else for(const phase of ['observed','forecast']){const points=rows.filter(r=>r.phase===phase);if(!points.length)continue;if(phase==='forecast'){const previous=rows.filter(r=>r.phase==='observed').at(-1);if(previous)points.unshift(previous);}svgNode('polyline',{points:points.map(row=>x(row.date)+','+y(plot(row))).join(' '),stroke:series.color,class:'curve','stroke-dasharray':series.id==='Overall Research'?null:'5 4','data-series':series.id,'data-method':phase==='observed'?'observed':active,'data-phase':phase},svg);}
  for(const row of rows){const value=row.values[index],bottom=stacked?totalBefore(row):0,top=bottom+value;svgNode('circle',{cx:x(row.date),cy:y(top/m.divisor),r:stacked?1:row.phase==='forecast'?1.8:.8,fill:series.color,opacity:stacked?0:1,'pointer-events':'none','data-series':series.id,'data-date':row.date,'data-value':value,'data-plot-value':value/m.divisor,'data-phase':row.phase,'data-method':row.method,'data-stack-bottom':stacked?bottom:undefined,'data-stack-top':stacked?top:undefined},markLayer);table.push([row.date,series.id,series.name,value,m.unit,value/m.divisor,m.display,row.phase,row.method,metric]);}
 });
 if(stacked&&metric!=='concurrency')svgNode('polyline',{points:rows.map(row=>x(row.date)+','+y(sum(row.values)/m.divisor)).join(' '),class:'curve',stroke:'var(--fg)','stroke-width':1.5,'data-series':'total','data-method':active},svg);
 const bandLayer=svgNode('g',{'data-layer':'uncertainty','pointer-events':'none'},svg);
 for(const band of bands){
  const color=metric==='concurrency'?(band.threshold===4?'#173e82':'#5b378f'):'#315a75';
  for(const level of [95,80]){const upper=band.points.map(point=>x(point.date)+','+y(point['upper'+level]/m.divisor)),lower=[...band.points].reverse().map(point=>x(point.date)+','+y(point['lower'+level]/m.divisor));svgNode('path',{d:'M'+upper.join(' L')+' L'+lower.join(' L')+' Z',fill:color,'fill-opacity':level===95?.10:.18,stroke:color,'stroke-opacity':.3,'stroke-width':.65,'data-uncertainty-band':level,'data-band-series':band.id,'data-method':active},bandLayer);if(band.points.length===1){const point=band.points[0],top=y(point['upper'+level]/m.divisor),bottom=y(point['lower'+level]/m.divisor);svgNode('rect',{x:x(point.date)-18,y:top,width:36,height:bottom-top,fill:color,'fill-opacity':level===95?.10:.18,'data-uncertainty-singlepoint':level},bandLayer);}}
  if(metric==='concurrency')svgNode('polyline',{points:band.points.map(point=>x(point.date)+','+y(point.center/m.divisor)).join(' '),fill:'none',stroke:color,'stroke-width':1.5,'stroke-dasharray':'4 3','data-boundary-center':band.id},bandLayer);
  for(const point of band.points)svgNode('circle',{cx:x(point.date),cy:y(point.center/m.divisor),r:0,'data-uncertainty-point':'true','data-band-series':band.id,'data-date':point.date,'data-lower95':point.lower95,'data-lower80':point.lower80,'data-center':point.center,'data-upper80':point.upper80,'data-upper95':point.upper95,'data-divisor':m.divisor},bandLayer);
 }
 // Bring line markers above the areas while retaining their raw component values.
 svg.append(markLayer);
 if(stamp(m.cutoff)>=start&&stamp(m.cutoff)<=end){line(svg,x(m.cutoff),b.y,x(m.cutoff),b.y+b.h,{class:'axis-line','stroke-dasharray':'3 5','data-observed-end':m.cutoff});const atEnd=x(m.cutoff)>b.x+b.w-70;text(svg,atEnd?b.x+b.w-5:x(m.cutoff)+6,b.y+13,rows.some(r=>r.phase==='forecast')?'预测 →':'观测截止',atEnd?'end':'start',{class:'axis-label'});}
 const labelLayer=svgNode('g',{'data-layer':'quarterly-labels'},svg);
 labels.forEach((column,i)=>{const previous=labels[i-1];column.lx=Math.max(b.x+4+column.width/2,x(column.date),previous?previous.lx+(previous.width+column.width)/2+labelGap:0);});
 for(let i=labels.length-1;i>=0;i--){const column=labels[i],next=labels[i+1];column.lx=Math.min(column.lx,b.x+b.w-4-column.width/2,next?next.lx-(next.width+column.width)/2-labelGap:Infinity);}
 for(const column of labels){const points=column.items.map(item=>({...item,cx:x(column.date),cy:y(item.value)})).sort((a,c)=>a.cy-c.cy);const top=b.y+26,bottom=b.y+b.h-10;
  points.forEach((p,i)=>{p.ly=Math.max(top,Math.min(bottom,p.cy-12),i?points[i-1].ly+18:top);p.lx=column.lx;});if(points.at(-1).ly>bottom){points.at(-1).ly=bottom;for(let i=points.length-2;i>=0;i--)points[i].ly=Math.min(points[i].ly,points[i+1].ly-18);}
  for(const p of points){if(Math.hypot(p.lx-p.cx,p.ly-p.cy)>8)line(labelLayer,p.cx,p.cy,p.lx,p.ly+(p.ly<p.cy?8:-8),{class:'point-label-guide',style:'--label-color:'+p.color});text(labelLayer,p.lx,p.ly+4,p.label,'middle',{class:'point-label',style:'--label-color:'+p.color,'data-label-date':column.date,'data-label-series':p.series,'data-label-value':p.value});}
 }
 function showRow(row){const parts=[row.date+' · '+(row.phase==='observed'?'公开观测':'条件外推')+' · '+m.windowDays+'日窗口'];if(metric==='workdays')parts.push('各团队分别统计，不作加总');else if(metric==='concurrency')parts.push('九档合计 '+fixed(sum(row.values)*100)+'%');else parts.push('18类合计 '+fmt(sum(row.values)/m.divisor,3)+' '+m.display);for(const band of bands){const point=band.points.find(point=>point.date===row.date);if(point)parts.push(band.name+' · 名义80% '+fmt(point.lower80/m.divisor)+'–'+fmt(point.upper80/m.divisor)+'；95% '+fmt(point.lower95/m.divisor)+'–'+fmt(point.upper95/m.divisor)+' '+m.display+'（未校准）');}m.series.forEach((series,i)=>parts.push(series.name+' '+fmt(row.values[i]/m.divisor,3)+' '+m.display));readout(parts);}
 const crosshair=line(svg,b.x,b.y,b.x,b.y+b.h,{class:'axis-line',visibility:'hidden','stroke-dasharray':'3 4'}),overlay=svgNode('rect',{x:b.x,y:b.y,width:b.w,height:b.h,fill:'transparent','data-interaction':'raw-readout'},svg);
 const move=event=>{const px=event.clientX-svg.getBoundingClientRect().left,row=rows.reduce((a,r)=>Math.abs(x(r.date)-px)<Math.abs(x(a.date)-px)?r:a,rows[0]);crosshair.setAttribute('x1',x(row.date));crosshair.setAttribute('x2',x(row.date));crosshair.setAttribute('visibility','visible');showRow(row);};
 overlay.addEventListener('pointermove',move);overlay.addEventListener('click',move);overlay.addEventListener('pointerleave',()=>crosshair.setAttribute('visibility','hidden'));
 $('raw-chart-context').textContent=rows[0].date+' — '+rows.at(-1).date+' · '+rows.filter(r=>r.phase==='observed').length+'个原始观测日 / '+rows.filter(r=>r.phase==='forecast').length+'个月度预测点 · '+methodName(active,metric==='concurrency')+(w>viewport?' · 图内可横向滑动':'');
 const descriptions={workdays:'1个Agent工作日＝8小时。五类团队各自统计，不能相加当作总体；纵轴是实际工作日量，并非相对基线倍数。',concurrency:'九档表示研究员的平均日峰值并发所属区间，占比合计100%；最高档[64,∞)为开口区间，不能由此还原平均并发或GPU需求。并发算法独立于总量算法。',tasks:'18类任务按原始28日口径堆叠，合计为每名研究员每天发起的任务数。',output:'18类输出沿用官方14日滑动平均，合计为每名研究员每日输出；已平滑的数据不重复处理。资源探索页采用相同14日窗口，再乘团队人数；比较时需选择同一算法与日期。'};
 const method=data.methods.find(m=>m.id===state.method),concurrency=data.concurrencyMethods.find(m=>m.id===state.concurrencyMethod);
 $('raw-chart-note').textContent=descriptions[metric]+' 历史保留原始发布日值，预测每月18日一个点；观测截止 '+m.cutoff+'。'+(metric==='concurrency'?(concurrency.note||''):(method.note||''))+(metric==='workdays'&&state.method==='damped_holt_hl365'?' “其他”团队的负趋势触及零边界，不表示未来停止使用Agent。':'')+(['tasks','output'].includes(metric)&&state.method!=='legacy_ols'?' 类别构成沿用历史末84日份额。':'')+(metric!=='concurrency'?' 每隔3个月标注工作日或总量，并保留区间终点。':'');
 if(uncertainty)$('raw-chart-note').textContent+=' '+(metric==='workdays'?'区间仅属于总体研究员，分团队未提供区间。':metric==='concurrency'?'阴影表示<4与<16个Agent累计占比边界的分位范围，不是九档独立区间。':'阴影属于18类合计总量，不是逐类区间相加。')+' 浅色为名义95%，深色为名义80%；均未经长期覆盖率校准。'+(state.showUncertainty&&metric!=='concurrency'?'纵轴已扩展至区间上界，关闭区间可恢复中心趋势尺度。':'');
 host.replaceChildren(svg);setTable(table);showRow(rows.at(-1));
}
function render(announce=false){try{error('');for(const [key,control]of Object.entries(controls))control.value=state[key];$('raw-date-controls').hidden=state.range!=='custom';summary();renderChart();root.dataset.state=JSON.stringify(state);root.dataset.ready='true';if(announce)$('raw-live-summary').textContent=$('raw-chart-title').textContent+'已更新。';}catch(err){root.dataset.ready='error';error('图表暂时无法显示：'+err.message);console.error(err);}}
for(const [key,control]of Object.entries(controls))control.addEventListener('change',()=>{state=normalise({...state,[key]:control.value});render(true);persist();});
$('raw-show-uncertainty').addEventListener('change',()=>{state=normalise({...state,showUncertainty:$('raw-show-uncertainty').checked});render(true);persist();});
$('raw-data-details').addEventListener('toggle',()=>{if($('raw-data-details').open)renderTable();});
$('raw-download').addEventListener('click',()=>{const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"',csv='\ufeff'+[exportColumns,...exportRows].map(row=>row.map(quote).join(',')).join('\r\n'),url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})),link=document.createElement('a');link.href=url;link.download='researcher-original-'+state.view+'-'+(state.view==='concurrency'?state.concurrencyMethod:state.method)+'.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),2000);});
let lastWidth=0;new ResizeObserver(entries=>{const width=entries[0]?.contentRect.width;if(!width||Math.abs(width-lastWidth)<1)return;lastWidth=width;cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(()=>render());}).observe($('raw-chart'));
render();
})();
