"""AI R&D capacity and economic model (as of 2026-11-19).
Python 3.9+, standard library. Run: python model.py [output_dir] [overrides.json]
Overrides: {"AL4":{"agents":1.0},"fixed":{"gpu_price":5.0},"years":{"2030":1.8}}.
All scenarios use three workload archetypes, not claims of achieved autonomy.
All resource and cost scenario outputs are class C. Prices/hardware anchors in SOURCES.
"""
import csv
import json
import math
import sys
from pathlib import Path

# Parameter schema: name, label, unit, AL3, AL4, AL5, stress low/high, rationale.
ROWS = [
('agents','人均平均在线会话，含子会话','会话/人',.35,1.2,3,.1,6,'100人全天平均存量，和日峰值、启动次数不同'),
('duration','平均会话生存时间','h',1.5,6,18,.5,48,'含等待；结合会话小时求每日新建环境数'),
('duty','平均推理活跃占空比','比例',.15,.24,.32,.05,.65,'等待工具或实验时暂停生成；平均推理活跃会话为N×u'),
('exec_duty','执行代码占空比','比例',.25,.40,.55,.1,.8,'可与推理重叠；CPU只计执行期'),
('resident','驻留内存环境占比','比例',.6,.75,.9,.3,1,'保留内存的沙箱可多于执行代码的沙箱'),
('input','活跃时输入Token','token/h',60000,110000,160000,25000,250000,'包括命中前缀的输入；模型侧吞吐另计'),
('output','活跃时输出Token','token/h',5000,8000,10000,2000,22000,'含内部推理输出；模型端实测负载未披露'),
('cache','输入Token有效前缀命中率','比例',.35,.55,.70,.1,.85,'只扣减免做的前缀prefill；不能消除新查询的注意力计算'),
('tools','工具调用频率','次/会话存续h',3,8,15,1,40,'含异步提交、检出、状态查询与验证'),
('fanout','并行子会话占总在线会话的比例','比例',.05,.20,.35,0,.6,'会话已含子会话，可拆父子，禁止再乘扇出'),
('depth','典型连续决策深度','步/研究子任务',3,10,25,1,80,'仅用于解释轨迹、重放和干预的复杂性，不作乘数'),
('c','沙箱CPU配额','vCPU',2,4,8,1,16,'代码执行/编译/仿真情景；与GPU服务器主机配套资源分账'),
('m','沙箱内存配额','GiB',6,12,24,2,64,'按驻留内存估算'),
('s','沙箱本地临时SSD逻辑工作集','GB',8,20,50,2,100,'临时文件、依赖和构建缓存；排除独立持久存储'),
('context','活跃序列平均缓存上下文','token/序列',8192,16384,32768,4096,65536,'用于KV容量及注意力FLOPs；部署须按上下文分桶'),
('qin','有效prefill吞吐','新token/s/GPU',2100,1800,1450,800,3500,'70B稠密BF16、TP4、已含长上下文与批处理开销；非实测'),
('qout','有效decode吞吐','输出token/s/GPU',155,130,105,55,280,'连续批处理吞吐分摊到每卡，非单用户输出速率'),
('peak','并发峰均系数','倍',1.5,1.7,2,1.15,3,'针对交互服务HBM与沙箱峰值；异步实验另设队列'),
('head','单人日新实验候选数','候选/人日',.10,.40,.90,.025,2,'按工作组合设定；相对公开实验增长无法倒推基数'),
('g','单训练实验卡数','H100等效卡',2,8,16,1,64,'单任务固定gang，默认小规模方法实验，非完整基础模型预训练'),
('h','一次训练运行时长','h',1,3,6,.3,18,'失败及重试按相同均值保守处理；异构时改为E[GH]'),
('eg','单次评测GPU数','H100等效卡',1,2,4,1,16,'训练端点到候选验证的独立评测池'),
('eh','单次评测耗时','h',.4,.6,1.2,.15,4,'均值；应另测尾部'),
('evalreps','每次尝试的评测次数','次',1,2,3,1,6,'含重复验证；保守假设每次尝试均发生，即使最终失败'),
('success','单次运行技术成功概率','比例',.85,.80,.72,.5,.95,'可复现运行，失败并非反面科学结果'),
('retry','失败后再试1次的概率','比例',.4,.65,.8,.1,1,'最多重试一次，不将重试作为另一个候选成果'),
('valid','成功候选经预注册质量门槛的通过率','比例',.65,.65,.6,.35,.85,'单位有效成果是通过复验、达到预定标准的唯一候选'),
('synth','每次尝试生成的合成数据GPU工时','GPU·h',.10,.5,1.5,0,6,'仅下游独立合成作业，排除协作Agent本身推理'),
('ckpt','每次尝试写入检查点','GB',5,25,100,1,400,'仅实验增量；不含共享基础权重'),
('dataset','每个新候选生成的数据产物','GB',.5,3,10,.1,50,'独立于检查点和会话轨迹'),
('retention','对象存储保留期','天',7,21,45,3,90,'稳态窗口，含检查点、合成数据与日志'),
('f','持久数据压缩与去重后比例','比例',.75,.65,.6,.35,.95,'作用于新增唯一数据；不应用到GPU时间'),
('keep','工作区完成后保留期限','天',1,3,7,.25,30,'仅保留写时复制增量到共享文件系统'),
('private','单工作区保留增量占SSD工作集','比例',.15,.2,.25,.05,.5,'共享镜像不重复保存，独立于对象层去重 f'),
('review','每个候选平均人工复核时间','h',.50,.25,.10,.02,2,'含抽查和独立验收；AL5为任务完成后审核'),
('log','会话每小时文字/工具轨迹与日志','GB',.003,.008,.02,.001,.10,'不含工作区文件；监控数据计入对象层一次'),
('alpha_c','CPU共享系数','倍',1.25,1.5,1.75,1,2.5,'在活跃期内配额/物理等效比；不得替代实测CPU曲线'),
('alpha_m','内存共享系数','倍',1.05,1.1,1.15,1,1.35,'共享只读页；在驻留比例外单独作用'),
('alpha_s','SSD复用系数','倍',1.5,2,2.5,1,4,'对本地临时逻辑工作集去重，共享服务器镜像另计'),
]
FIXED_ROWS = [
('people','组织人数',100,'人',100,100,'统一基线'),('gpu_price','GPU预算单价',4.59,'USD/H100·h',2.5,8,'Lambda 8卡H100公开快照作归一单价，跨规模统一并非报价'),
('cpu_price','弹性沙箱CPU',.04048,'USD/vCPU·h',.02,.09,'AWS美东x86公开算例参考'),('ram_price','弹性沙箱RAM',.004445,'USD/GiB·h',.002,.009,'AWS美东公开算例，原价表GB为二进制GiB'),
('ssd_price','独立本地缓存层摊销',.08,'USD/GB月',.03,.16,'假设，避免将云附送临时盘重复计费'),
('fs_price','共享文件层单价',.10,'USD/GB月',.04,.30,'假设，独立持久增量层'),('obj_price','对象存储单价',.023,'USD/GiB月',.01,.05,'AWS美东公开算例，每GB为二进制GiB，供应商内部副本已含'),
('backup_price','备份层单价',.012,'USD/GB月',.003,.03,'假设，单个独立快照预算'),('net_price','可计费外部链路',.01,'USD/GB',0,.08,'假设，内部互联随GPU节点计费，未重复收费'),
('control_price','外置授权与审计服务',1.0,'USD/百万事务',.1,5,'假设，授权查询与状态事件；日志存储另计'),
('human_price','人工复核影子单价',65,'USD/h',35,150,'假设；不含100人全部工资，仅量化审核时间，应从既有编制中安排'),
('base_gb','共享基础权重与数据集',5000,'GB',1000,20000,'对象层固定结构；本报告容量仅一个组织，非前沿预训练语料'),
('backup_frac','对象层备份分数',.40,'比例',.1,1,'独立归档/副本，按逻辑备份容量计'),
('io_blocks','每工具调用随机读写操作',160,'IO/调用',10,1200,'计SSD元数据和小块操作；吞吐另外测量'),
('io_mb','每工具本地读写量',24,'MB/调用',2,200,'混合顺序与随机I/O，因此不以平均读写量反推块IOPS'),
('egress_frac','存储流量跨计费边界比例',.15,'比例',.01,.50,'其余留在本地/同域，内部有效传输亦需计带宽'),
('stg_read','每次尝试远端读取数据量',60,'GB/次',5,500,'包括未在缓存命中的训练输入与权重；与写入日志分开'),
('q_gpu','目标实验池占用率',.75,'比例',.55,.9,'基于作业分配时间，和GPU运算单元利用率不同'),
('q_infer','目标推理服务池负载',.72,'比例',.5,.88,'调度余量；阶段实际吞吐已经计入批处理、SLO等效率'),
('trans','每次工具对应控制事务',6,'事务/调用',3,14,'包括授权、提交、状态、审计，单独计算监督压力'),
('startsec','创建或恢复单环境秒数',8,'秒',1,45,'冷启动CPU按一个vCPU计；含销毁事件但不另收GPU'),
('recovery','每次会话附加恢复次数',.2,'次/会话',0,1,'临时中断及恢复；最终销毁一次'),
('weight_b','稠密模型参数',70,'十亿参数',7,120,'抽象代理，非Claude/GPT权重'),
('mem_gb','H100显存',80,'GB/卡',80,80,'NVIDIA H100 SXM；十进制'),
('hbmfrac','每副本可作权重和KV的HBM比例',.85,'比例',.7,.92,'余留激活、临时空间、碎片；部署须测P95'),
('tp','单推理副本TP',4,'卡',4,4,'70B BF16，示例每四卡为一个副本'),
('gpu_active_kw','分配负载的GPU均功率',.50,'kW',.30,.70,'0.70 kW为H100 SXM TDP，0.50 kW为假设'),
('gpu_idle_kw','GPU空闲功率',.08,'kW',.04,.14,'假设，不等于额定TDP'),
('pue','数据中心PUE',1.2,'倍',1.1,1.6,'只算GPU可归因用电，不含CPU等IT负载'),
('steps_h','训练步频',240,'步/h',60,600,'同质同步数据并行示例；前沿多维并行须改模型'),
('grad_gb','每卡每步稠密梯度',2,'GB',.25,8,'训练可为小模型或参数高效实验，非固定70B serving模型'),
('h2d_gb','每步每卡输入传输',.03,'GB',.002,.25,'CPU→GPU训练批数据，不含全梯度或拓扑重传'),
]
SOURCES={
 'NVIDIA':'https://www.nvidia.com/en-us/data-center/h100/',
 'Lambda':'https://lambda.com/pricing',
 'AWS':'https://docs.aws.amazon.com/solutions/latest/prebid-server-deployment-on-aws/cost1.html',
 'S3 units':'https://aws.amazon.com/s3/pricing/',
 'Fargate units':'https://aws.amazon.com/fargate/pricing/',
 'MLPerf':'https://docs.mlcommons.org/inference/index_gh/',
}
LEVELS=['AL3','AL4','AL5']
SCENES=['保守','基准','激进']
YEARS={2027:.75,2028:1.,2030:1.5}
def parameters():
    return [dict(key=k,label=l,unit=u,AL3=a,AL4=b,AL5=c,low=lo,high=hi,reason=reason,source='C·建模假设，非厂商内部参数') for k,l,u,a,b,c,lo,hi,reason in ROWS]
def fixed_parameters():
    return [dict(key=k,label=l,value=v,unit=u,low=lo,high=hi,reason=r) for k,l,v,u,lo,hi,r in FIXED_ROWS]

def budgets(p,k,year=2028,scale=1,level='AL4'):
    people=k['people']
    N=people*p['agents']*scale
    ah=24*N
    life=ah/p['duration']
    cpuactive=N*p['exec_duty']
    ramresident=N*p['resident']
    active=N*p['duty']
    I=ah*p['duty']*p['input']
    O=ah*p['duty']*p['output']
    uncached=I*(1-p['cache'])
    prefill=uncached/p['qin']/3600
    decode=O/p['qout']/3600
    infer=prefill+decode
    peak=p['peak']
    # One live decoding sequence per active inference session as a conservative KV stock.
    # KV per token=2(K,V)*80 layers*8 KV heads*128 head_dim*2 bytes BF16.
    kv_b_per_tok=2*80*8*128*2
    kv_gb=active*peak*p['context']*kv_b_per_tok/1e9
    weight=k['weight_b']*2
    tp=int(k['tp'])
    kv_headroom=tp*k['mem_gb']*k['hbmfrac']-weight
    if kv_headroom <= 0: raise ValueError('Replica cannot host model weights')
    infer_rate_reps=math.ceil(infer/24*peak/(k['q_infer']*tp))
    # Whole-sequence slots, then whole replicas, not fractional KV paging capacity.
    seq_slots=math.floor(kv_headroom/(p['context']*kv_b_per_tok/1e9))
    if seq_slots<1: raise ValueError('Context too long for one sequence')
    infer_kv_reps=math.ceil(math.ceil(active*peak)/seq_slots)
    infer_cards=tp*max(1,infer_rate_reps,infer_kv_reps)
    # Simplified causal attention FLOPs; new tokens use measured mean attended prefix L.
    # FLOP proxy: 2P per token + 4*n_layer*d_model*mean_attended_length per token.
    flop_tok=2*k['weight_b']*1e9+4*80*8192*p['context']
    e=people*p['head']*scale
    attempts=e*(1+(1-p['success'])*p['retry'])
    accepted=e*p['success']*(1+(1-p['success'])*p['retry'])*p['valid']
    train=attempts*p['g']*p['h']
    ev=attempts*p['evalreps']*p['eg']*p['eh']
    synth=attempts*p['synth']
    indirect=train+ev+synth
    # One fixed-size pool for synchronous training, another fungible pool for evaluation + generation.
    tslots=math.ceil(attempts*p['h']/(24*k['q_gpu']))
    tcards=int(p['g'])*tslots
    auxcards=int(p['eg'])*math.ceil((ev+synth)/(24*k['q_gpu']*p['eg']))
    installed=infer_cards+tcards+auxcards
    peakcpu=cpuactive*peak*p['c']/p['alpha_c']
    peakram=ramresident*peak*p['m']/p['alpha_m']
    # SSD sized for retained *live* local environments; completed tasks use shared FS snapshots.
    ssd=N*peak*p['s']/p['alpha_s']
    cold_cpu=life*(1+k['recovery'])*k['startsec']/3600
    cpuh=cpuactive*24*p['c']/p['alpha_c']+cold_cpu
    ramh=ramresident*24*p['m']/p['alpha_m']
    # Include cold-start duty in average and provision an additional peak-scaled allowance.
    peakcpu+=cold_cpu/24*peak
    fs=life*p['keep']*p['s']*p['private']
    object_delta=attempts*p['ckpt']+e*p['dataset']+ah*p['log']
    obj=k['base_gb']+object_delta*p['retention']*p['f']
    backup=obj*k['backup_frac']
    durable=fs+obj+backup
    tools=ah*p['tools']
    ctrl=tools*k['trans']+life*(2+2*k['recovery'])
    stgread=attempts*k['stg_read']
    fswrite=life*p['s']*p['private']
    stgtraffic=stgread+object_delta+fswrite # client logical bytes prior to storage compression; backup copies excluded
    transfer=stgtraffic*k['egress_frac']
    gradsize=k['grad_gb']
    fabric=attempts*p['h']*k['steps_h']*2*(p['g']-1)*gradsize
    host_gpu=attempts*p['h']*k['steps_h']*p['g']*k['h2d_gb']
    time_approval=e*p['review']
    # Cost basis: GPU pools retained 24/7 including SLO/queues/fragmentation. Tool sandboxes elastic.
    # GPU provider's host CPU/RAM bundled; sandbox CPU/RAM additionally modelled on separate hosts.
    costs={'推理':infer_cards*24*k['gpu_price'],'实验':(tcards+auxcards)*24*k['gpu_price'],
        '存储':(ssd*k['ssd_price']+fs*k['fs_price']+obj/(2**30/1e9)*k['obj_price']+backup*k['backup_price'])/30,
        '执行环境':cpuh*k['cpu_price']+ramh*k['ram_price'],
        '网络':transfer*k['net_price'],'监督':ctrl/1e6*k['control_price']+time_approval*k['human_price']}
    total=sum(costs.values())
    gbusy=infer+indirect
    kwh=(gbusy*k['gpu_active_kw']+(24*installed-gbusy)*k['gpu_idle_kw'])*k['pue']
    return dict(year=year,level=level,scenario=SCENES[LEVELS.index(level)],scale=scale,online=N,parent_online=N*(1-p['fanout']),child_online=N*p['fanout'],active_infer=active,active_cpu=cpuactive,resident_ram=ramresident,peak_sandboxes=math.ceil(N*peak),mean_agent_h_per_person=ah/people,infer_active_h_per_person=ah*p['duty']/people,task_births=life,cold_starts=life*(1+k['recovery']),destroy_day=life,
        input_m=I/1e6,output_m=O/1e6,prefill_gpu_h=prefill,decode_gpu_h=decode,infer_gpu_h=infer,prefill_eflop=uncached*flop_tok/1e18,decode_eflop=O*flop_tok/1e18,
        kv_peak_gb=kv_gb,weights_gb_per_replica=weight,kv_slots_per_replica=seq_slots,kv_replicas=infer_kv_reps,throughput_replicas=infer_rate_reps,infer_cards=infer_cards,
        gpu_installed=installed,train_cards=tcards,eval_synth_cards=auxcards,exp_slots=tslots,train_gpu_h=train,eval_gpu_h=ev,synth_gpu_h=synth,indirect_gpu_h=indirect,total_gpu_h=gbusy,indirect_ratio=indirect/infer,
        new_exp_day=e,attempts_day=attempts,accepted_day=accepted,review_h_day=time_approval,train_pool_busy=train/(24*tcards),aux_pool_busy=(ev+synth)/(24*auxcards),infer_pool_busy=infer/(24*infer_cards),pooled_occupancy=gbusy/(24*installed),avg_exp_gpu=indirect/24,mean_train_conc=attempts*p['h']/24,
        cpu_peak=peakcpu,cpu_h=cpuh,ram_peak_tib=peakram/1024,ram_gib_h=ramh,ssd_peak_tb=ssd/1000,cpu_cold_h=cold_cpu,local_iops=tools*k['io_blocks']/86400,local_peak_iops=tools*k['io_blocks']/86400*peak,local_mbps=tools*k['io_mb']/86400,local_peak_mbps=tools*k['io_mb']/86400*peak,fs_tb=fs/1000,obj_tb=obj/1000,backup_tb=backup/1000,durable_tb=durable/1000,unique_persist_gb_day=object_delta*p['f'],raw_data_gb_day=object_delta,
        tool_calls_day=tools,control_qps=ctrl/86400,peak_control_qps=ctrl/86400*peak,auth_qps=tools/86400,storage_gb_day=stgtraffic,storage_avg_gbps=stgtraffic/86400,priced_net_gb_day=transfer,train_fabric_tb_day=fabric/1000,h2d_tb_day=host_gpu/1000,
        cost_day=total,cost_yr=total*365,cost_allocated_gpu=costs['推理']+costs['实验'],human_cost_day=time_approval*k['human_price'],infra_usd_day=total-time_approval*k['human_price'],cost_per_accepted=total/accepted,gpuh_per_accepted=gbusy/accepted,accepted_per_1000gpuh=accepted/gbusy*1000,
        gpu_facility_kwh_day=kwh,**{'cost_'+key:val for key,val in costs.items()})

def queue_mm_c(arrivals_day,c=8,h=3,g=8):
    """Steady-state mean FCFS wait. Homogeneous independent jobs, Poisson arrival, exponential service."""
    a=arrivals_day*h/24
    rho=a/c
    if rho>=1:
        w=pwait=None
    else:
        tail=a**c/math.factorial(c)/(1-rho)
        pwait=tail/(sum(a**j/math.factorial(j) for j in range(c))+tail)
        w=pwait/(c/h-arrivals_day/24)
    return dict(arrivals_day=arrivals_day,utilization=rho,slots=c,gpus_per_job=g,hours_per_job=h,wait_h=w,p_wait=pwait,capacity_gpu=c*g,stable=rho<1)

def calculate(overrides=None):
    params=parameters()
    const=fixed_parameters()
    base={r['key']:r['value'] for r in const}
    profiles={lv:{r['key']:r[lv] for r in params} for lv in LEVELS}
    years=dict(YEARS)
    for who,values in (overrides or {}).items():
        if who=='years':
            for yr,mult in values.items():
                if float(mult)<=0: raise ValueError('Year multiplier must be >0')
                years[int(yr)]=float(mult)
            continue
        target=base if who=='fixed' else profiles[who]
        unknown=values.keys()-target.keys()
        if unknown: raise KeyError(unknown)
        target.update(values)
    for p in profiles.values():
        for key in ['duty','exec_duty','resident','cache','fanout','success','retry','valid','f','private']:
            if not 0<=p[key]<=1: raise ValueError(f'{key} must fall between 0 and 1')
        for key,value in p.items():
            if value<0 or not math.isfinite(value): raise ValueError(f'Invalid {key}')
        for key in ['agents','duration','success','valid','qin','qout','head','g','h','eg','eh','evalreps','alpha_c','alpha_m','alpha_s']:
            if p[key]<=0: raise ValueError(f'{key} must be positive')
        if any(p[key]!=int(p[key]) for key in ['g','eg','evalreps']): raise ValueError('GPU gang counts and eval repeats must be integers')
    if any(base[key]<=0 for key in ['tp','mem_gb','people','q_infer','q_gpu','hbmfrac']): raise ValueError('Invalid system capacity')
    for row in params:
        row.update({lv:profiles[lv][row['key']] for lv in LEVELS})
    for row in const: row['value']=base[row['key']]
    forecasts=[budgets(profiles[lv],base,year,scale,lv) for year,scale in sorted(years.items()) for lv in LEVELS]
    ref=[x for x in forecasts if x['year']==2028]
    costs=[{'level':x['level'],'category':cat,'usd_day':x['cost_'+cat],'share':x['cost_'+cat]/x['cost_day']} for x in ref for cat in ['推理','实验','存储','执行环境','网络','监督']]
    p=profiles['AL4']
    # n means active sandbox count: at chart level all sandboxes are live AND executing; exclusive units.
    concurrency=[]
    for n in [10,25,50,100,200,400]:
        cpu=n*p['c']/p['alpha_c']
        ram=n*p['m']/p['alpha_m']/1024
        ssd=n*p['s']/p['alpha_s']/1000
        concurrency.append(dict(n=n,cpu=cpu,ram_tib=ram,ssd_tb=ssd,cpu_peak=cpu*p['peak'],ram_peak_tib=ram*p['peak'],ssd_peak_tb=ssd*p['peak']))
    queue=[queue_mm_c(x) for x in [12,24,32,40,44,48,52,56,60,62,63,64,68,72]]
    sens=[]
    for key,factors in {'agents':[.5,2],'head':[.5,2],'h':[.5,2],'retention':[1/3,2],'keep':[1/3,2],'qout':[.5,2],'alpha_s':[.5,2],'cache':[.30,.75],'duty':[.5,1.5],'success':[.60,.90],'peak':[1.2,2.5],'gpu_price':[.65,1.5]}.items():
        for f in factors:
            cp=p.copy();cf=base.copy()
            if key=='gpu_price': cf[key]*=f
            elif key in ['cache','success','peak']: cp[key]=f
            else: cp[key]*=f
            new=budgets(cp,cf,scale=years[2028])
            sens.append(dict(input=key,value=(cf if key in cf else cp)[key],base=(base if key in base else p)[key],
                infer_gpu_h=new['infer_gpu_h'],indirect_gpu_h=new['indirect_gpu_h'],gpu_installed=new['gpu_installed'],durable_tb=new['durable_tb'],ssd_peak_tb=new['ssd_peak_tb'],cost_day=new['cost_day'],unit_cost=new['cost_per_accepted'],pct_unit_cost_change=new['cost_per_accepted']/ref[1]['cost_per_accepted']-1))
    return dict(sources=SOURCES,years=years,parameters=params,fixed_parameters=const,profiles=ref,forecasts=forecasts,concurrency=concurrency,queue=queue,costs=costs,sensitivity=sens)

def tests():
    z=calculate()
    assert len(z['forecasts'])==9
    for row in z['forecasts']:
        assert row['infer_gpu_h']+row['indirect_gpu_h']==row['total_gpu_h']
        assert row['attempts_day']>=row['new_exp_day']>=row['accepted_day']
        assert row['gpu_installed']%1==0 and row['gpu_installed']>=row['total_gpu_h']/24
        assert row['ssd_peak_tb']>0 and abs(row['fs_tb']+row['obj_tb']+row['backup_tb']-row['durable_tb'])<1e-8
        assert row['cost_day']>row['infra_usd_day']>0 and row['cost_per_accepted']==row['cost_day']/row['accepted_day']
    for lv in LEVELS:
        assert abs(sum(x['share'] for x in z['costs'] if x['level']==lv)-1)<1e-9
    assert queue_mm_c(64)['wait_h'] is None and queue_mm_c(48)['wait_h']<queue_mm_c(60)['wait_h']
    assert abs(queue_mm_c(6,c=1,h=2)['wait_h']-2)<1e-10
    assert calculate({'years':{'2030':2.}})['forecasts'][7]['online']==2*z['profiles'][1]['online']
    assert calculate({'AL4':{'agents':2.4}})['profiles'][1]['infer_gpu_h']==2*z['profiles'][1]['infer_gpu_h']

def write(out,overrides=None):
    tests()
    out.mkdir(parents=True,exist_ok=True)
    z=calculate(overrides)
    (out/'results.json').write_text(json.dumps(z,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    for name,rows in z.items():
        if not isinstance(rows,list): continue
        with (out/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)
if __name__=='__main__':
    out=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).parent/'modelout'
    overrides=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')) if len(sys.argv)>2 else None
    write(out,overrides)
