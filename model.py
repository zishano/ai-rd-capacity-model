"""AI R&D capacity model. Run: python model.py [output_dir] [overrides.json] [--config FILE]."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory

from assumptions import (DEFAULT_CONFIG, LEVELS, check_value, effective_config, load_config,
                         read_inputs, read_json, setting_values)

SCENES = ['保守', '基准', '激进']


def _scenario_rows(config):
    rows = []
    for key, entry in config['scenarios'].items():
        ev = entry['evidence']
        kinds = [ev.get('by_level', {}).get(level, {}).get('kind', ev['kind']) for level in LEVELS]
        if all(kind == 'C' for kind in kinds):
            source = 'C·建模假设，非厂商内部参数'
        elif len(set(kinds)) == 1:
            source = f"{kinds[0]}·详见 input_sources.csv"
        else:
            source = ' / '.join(f'{level}={kind}' for level, kind in zip(LEVELS,kinds))
        rows.append(dict(key=key, label=entry['label'], unit=entry['unit'],
                         **entry['values'], low=entry['low'], high=entry['high'],
                         reason=entry['reason'], source=source))
    return rows


def parameters(config_path=DEFAULT_CONFIG, *, base_config_path=None):
    return _scenario_rows(load_config(config_path, base_config_path))


def _fixed_rows(config):
    return [dict(key=key, label=entry['label'], value=entry['value'], unit=entry['unit'],
                 low=entry['low'], high=entry['high'], reason=entry['reason'])
            for key, entry in config['fixed'].items()]


def fixed_parameters(config_path=DEFAULT_CONFIG, *, base_config_path=None):
    return _fixed_rows(load_config(config_path, base_config_path))


def _team_volume(people, rate, scale):
    total = people * rate * scale
    nearest = round(total)
    # Division to a per-person rate followed by rescaling can produce 100.00000000000001.
    if nearest > 0 and total != nearest and abs(total - nearest) <= 2 * math.ulp(total):
        return float(nearest)
    return total


def budgets(p, k, year=None, scale=1, level='AL4', *, settings=None):
    if settings is None:
        settings = setting_values(load_config())
    if year is None:
        year = settings['reference_year']
    people=k['people']
    N=_team_volume(people, p['agents'], scale)
    ah=24*N
    life=ah/p['duration']
    cpuactive=N*p['exec_duty']
    ramresident=N*p['resident']
    active=N*p['duty']
    I=ah*p['duty']*p['input']
    O=ah*p['duty']*p['output']
    peak=p['peak']
    peak_sequences = active * peak * settings['kv_sequences']
    moe_extra={}
    if settings.get('inference_engine','dense') == 'moe_10t':
        from inference.moe import calculate as calculate_moe
        model_path=Path(__file__).resolve().parent / settings['moe_model_config']
        moe_result=calculate_moe(
            {'input_tokens': I, 'output_tokens': O, 'prefix_cache_hit_rate': p['cache'],
             'context_tokens': p['context'], 'peak_sequences': peak_sequences, 'decode_batch_sequences': peak_sequences},
            hardware_name=settings['moe_hardware'], model_path=model_path,
            tensor_parallel_size=settings['moe_tensor_parallel_size'])
        uncached=I*(1-p['cache'])
        prefill=moe_result['prefill']['gpu_hours']
        decode=moe_result['decode']['gpu_hours']
        infer=moe_result['infer_gpu_h']
        prefill_eflop=moe_result['prefill_eflop']
        decode_eflop=moe_result['decode_eflop']
        kv_gb=moe_result['kv_peak_gb']
        weight=moe_result['weights_gb_per_replica']
        tp=int(settings.get('moe_tensor_parallel_size',4))
        infer_rate_reps=moe_result['throughput_replicas']
        seq_slots=moe_result['kv_slots_per_replica']
        infer_kv_reps=moe_result['kv_replicas']
        infer_cards=moe_result['infer_cards']
        moe_extra={key:moe_result[key] for key in (
            'total_parameters','active_parameters','parameter_stats','uncached_input_tokens',
            'deployment_gpus_per_replica','deployment_replicas','per_gpu_memory',
            'communication','evidence_type')}
    else:
        uncached=I*(1-p['cache'])
        prefill=uncached/p['qin']/3600
        decode=O/p['qout']/3600
        infer=prefill+decode
        # Two arrays per layer (keys and values), sized using the configured architecture.
        kv_b_per_tok = 2 * settings['layer_count'] * settings['kv_heads'] * settings['head_dimension'] * settings['precision_bytes']
        kv_gb=peak_sequences*p['context']*kv_b_per_tok/1e9
        weight=k['weight_b']*settings['precision_bytes']
        tp=int(k['tp'])
        kv_headroom=tp*k['mem_gb']*k['hbmfrac']-weight
        if kv_headroom <= 0: raise ValueError('Replica cannot host model weights')
        infer_rate_reps=math.ceil(infer/24*peak/(k['q_infer']*tp))
        seq_slots=math.floor(kv_headroom/(p['context']*kv_b_per_tok/1e9))
        if seq_slots<1: raise ValueError('Context too long for one sequence')
        infer_kv_reps=math.ceil(math.ceil(peak_sequences)/seq_slots)
        infer_cards=tp*max(1,infer_rate_reps,infer_kv_reps)
        flop_tok=2*k['weight_b']*1e9+4*settings['layer_count']*settings['model_width']*p['context']
        prefill_eflop=uncached*flop_tok/1e18
        decode_eflop=O*flop_tok/1e18
    e=_team_volume(people, p['head'], scale)
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
    cold_cpu=life*(1+k['recovery'])*k['startsec']*settings['cold_start_vcpu']/3600
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
    ctrl=tools*k['trans']+life*(settings['lifecycle_events']['create_destroy']+settings['lifecycle_events']['restore']*k['recovery'])
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
        '存储':(ssd*k['ssd_price']+fs*k['fs_price']+obj/(2**30/1e9)*k['obj_price']+backup*k['backup_price'])/settings['billing_window']['month_days'],
        '执行环境':cpuh*k['cpu_price']+ramh*k['ram_price'],
        '网络':transfer*k['net_price'],'监督':ctrl/1e6*k['control_price']+time_approval*k['human_price']}
    total=sum(costs.values())
    gbusy=infer+indirect
    kwh=(gbusy*k['gpu_active_kw']+(24*installed-gbusy)*k['gpu_idle_kw'])*k['pue']
    return dict(year=year,level=level,scenario=SCENES[LEVELS.index(level)],scale=scale,online=N,parent_online=N*(1-p['fanout']),child_online=N*p['fanout'],active_infer=active,active_cpu=cpuactive,resident_ram=ramresident,peak_sandboxes=math.ceil(N*peak),mean_agent_h_per_person=ah/people,infer_active_h_per_person=ah*p['duty']/people,task_births=life,cold_starts=life*(1+k['recovery']),destroy_day=life,
        input_m=I/1e6,output_m=O/1e6,prefill_gpu_h=prefill,decode_gpu_h=decode,infer_gpu_h=infer,prefill_eflop=prefill_eflop,decode_eflop=decode_eflop,
        kv_peak_gb=kv_gb,weights_gb_per_replica=weight,kv_slots_per_replica=seq_slots,kv_replicas=infer_kv_reps,throughput_replicas=infer_rate_reps,infer_cards=infer_cards,
        gpu_installed=installed,train_cards=tcards,eval_synth_cards=auxcards,exp_slots=tslots,train_gpu_h=train,eval_gpu_h=ev,synth_gpu_h=synth,indirect_gpu_h=indirect,total_gpu_h=gbusy,indirect_ratio=(indirect/infer if infer else None),
        new_exp_day=e,attempts_day=attempts,accepted_day=accepted,review_h_day=time_approval,train_pool_busy=train/(24*tcards),aux_pool_busy=(ev+synth)/(24*auxcards),infer_pool_busy=infer/(24*infer_cards),pooled_occupancy=gbusy/(24*installed),avg_exp_gpu=indirect/24,mean_train_conc=attempts*p['h']/24,
        cpu_peak=peakcpu,cpu_h=cpuh,ram_peak_tib=peakram/1024,ram_gib_h=ramh,ssd_peak_tb=ssd/1000,cpu_cold_h=cold_cpu,local_iops=tools*k['io_blocks']/86400,local_peak_iops=tools*k['io_blocks']/86400*peak,local_mbps=tools*k['io_mb']/86400,local_peak_mbps=tools*k['io_mb']/86400*peak,fs_tb=fs/1000,obj_tb=obj/1000,backup_tb=backup/1000,durable_tb=durable/1000,unique_persist_gb_day=object_delta*p['f'],raw_data_gb_day=object_delta,
        tool_calls_day=tools,control_qps=ctrl/86400,peak_control_qps=ctrl/86400*peak,auth_qps=tools*settings['auth_events']/86400,storage_gb_day=stgtraffic,storage_avg_gbps=stgtraffic/86400,priced_net_gb_day=transfer,train_fabric_tb_day=fabric/1000,h2d_tb_day=host_gpu/1000,
        cost_day=total,cost_yr=total*settings['billing_window']['year_days'],cost_allocated_gpu=costs['推理']+costs['实验'],human_cost_day=time_approval*k['human_price'],infra_usd_day=total-time_approval*k['human_price'],cost_per_accepted=total/accepted,gpuh_per_accepted=gbusy/accepted,accepted_per_1000gpuh=accepted/gbusy*1000,**moe_extra,
        gpu_facility_kwh_day=kwh,**{'cost_'+key:val for key,val in costs.items()})

def queue_mm_c(arrivals_day,c=None,h=None,g=None):
    """Steady-state mean FCFS wait. Homogeneous independent jobs, Poisson arrival, exponential service."""
    if c is None or h is None or g is None:
        baseline = setting_values(load_config())['queue_baseline']
        c = baseline['slots'] if c is None else c
        h = baseline['hours_per_job'] if h is None else h
        g = baseline['gpu_per_job'] if g is None else g
    c = int(c)
    a=arrivals_day*h/24
    rho=a/c
    if rho>=1:
        w=pwait=None
    else:
        try:
            tail=a**c/math.factorial(c)/(1-rho)
            pwait=tail/(sum(a**j/math.factorial(j) for j in range(c))+tail)
        except OverflowError:
            # Equivalent Erlang-B recursion for large configured slot counts.
            blocking = 1.0
            for j in range(1, c + 1):
                blocking = a * blocking / (j + a * blocking)
            pwait = blocking / (1 - rho + rho * blocking)
        w=pwait/(c/h-arrivals_day/24)
    return dict(arrivals_day=arrivals_day,utilization=rho,slots=c,gpus_per_job=g,hours_per_job=h,wait_h=w,p_wait=pwait,capacity_gpu=c*g,stable=rho<1)


def calculate(overrides=None, config_path=DEFAULT_CONFIG, *, base_config_path=None):
    return _calculate(effective_config(load_config(config_path, base_config_path), overrides))


def _calculate(config):
    params = _scenario_rows(config)
    const = _fixed_rows(config)
    base = {r['key']:r['value'] for r in const}
    profiles = {lv:{r['key']:r[lv] for r in params} for lv in LEVELS}
    settings = setting_values(config)
    years = {int(k):v for k,v in settings['years'].items()}
    reference_year = settings['reference_year']
    forecasts=[budgets(profiles[lv],base,year,scale,lv,settings=settings) for year,scale in sorted(years.items()) for lv in LEVELS]
    ref=[x for x in forecasts if x['year']==reference_year]
    costs=[{'level':x['level'],'category':cat,'usd_day':x['cost_'+cat],'share':(x['cost_'+cat]/x['cost_day'] if x['cost_day'] else None)} for x in ref for cat in ['推理','实验','存储','执行环境','网络','监督']]
    p=profiles['AL4']
    # n means active sandbox count: at chart level all sandboxes are live AND executing; exclusive units.
    concurrency=[]
    for n in settings['sandbox_grid']:
        cpu=n*p['c']/p['alpha_c']
        ram=n*p['m']/p['alpha_m']/1024
        ssd=n*p['s']/p['alpha_s']/1000
        concurrency.append(dict(n=n,cpu=cpu,ram_tib=ram,ssd_tb=ssd,cpu_peak=cpu*p['peak'],ram_peak_tib=ram*p['peak'],ssd_peak_tb=ssd*p['peak']))
    q = settings['queue_baseline']
    queue = [queue_mm_c(x, c=q['slots'], h=q['hours_per_job'], g=q['gpu_per_job'])
             for x in settings['queue_grid']]
    sens=[]
    for key, instruction in settings['sensitivity'].items():
        for point in instruction['points']:
            cp, cf = p.copy(), base.copy()
            pool = cf if key in cf else cp
            group = 'fixed' if key in cf else 'scenarios'
            pool[key] = point if instruction['mode'] == 'set' else pool[key] * point
            row = dict(input=key, value=pool[key], base=(base if key in base else p)[key])
            outputs = ('infer_gpu_h','indirect_gpu_h','gpu_installed','durable_tb','ssd_peak_tb','cost_day')
            try:
                check_value(group, key, pool[key], f'settings.sensitivity.{key}')
                new = budgets(cp, cf, reference_year, years[reference_year], settings=settings)
            except (ValueError, OverflowError) as exc:
                # A stress point may become infeasible after the base workload is recalibrated.
                row.update(dict.fromkeys(outputs + ('unit_cost', 'pct_unit_cost_change')))
                row['error'] = str(exc)
            else:
                row.update({name:new[name] for name in outputs})
                row['unit_cost'] = new['cost_per_accepted']
                unit_cost = ref[1]['cost_per_accepted']
                row['pct_unit_cost_change'] = row['unit_cost'] / unit_cost - 1 if unit_cost else None
            sens.append(row)
    if any('error' in row for row in sens):
        for row in sens:
            row.setdefault('error', '')
    return dict(sources=config['sources'],years=years,parameters=params,fixed_parameters=const,profiles=ref,forecasts=forecasts,concurrency=concurrency,queue=queue,costs=costs,sensitivity=sens)

def _check_results(z):
    """Check accounting identities for the actual run, including alternate configs."""
    assert len(z['forecasts']) == len(z['years']) * len(LEVELS)
    for row in z['forecasts']:
        assert math.isclose(row['infer_gpu_h'] + row['indirect_gpu_h'], row['total_gpu_h'])
        assert row['attempts_day'] >= row['new_exp_day']
        assert row['accepted_day'] <= row['new_exp_day'] * (1 + 1e-12)
        assert row['gpu_installed'] % 1 == 0 and row['gpu_installed'] + 1e-9 >= row['total_gpu_h'] / 24
        assert math.isclose(row['fs_tb'] + row['obj_tb'] + row['backup_tb'], row['durable_tb'], abs_tol=1e-9)
        assert math.isclose(row['cost_per_accepted'], row['cost_day'] / row['accepted_day'])
    for lv in LEVELS:
        shares = [x['share'] for x in z['costs'] if x['level'] == lv and x['share'] is not None]
        assert not shares or math.isclose(sum(shares), 1)
    assert math.isclose(queue_mm_c(6, c=1, h=2, g=1)['wait_h'], 2)


def tests(config_path=DEFAULT_CONFIG, *, base_config_path=None):
    _check_results(calculate(config_path=config_path, base_config_path=base_config_path))


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def write(out, overrides=None, config_path=DEFAULT_CONFIG, *, base_config_path=None):
    from input_sources import source_rows
    config, manifest = read_inputs(config_path, base_config_path)
    effective = effective_config(config, overrides)
    z = _calculate(effective)
    _check_results(z)
    sources = source_rows(config, overrides)
    snapshot = _json_bytes(effective)
    manifest.update(config_as_of=config['as_of'],
                    effective_config_sha256=hashlib.sha256(snapshot).hexdigest(),
                    overrides=overrides or {})
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    # Stage full, validated files before publication; publish the run manifest last.
    with TemporaryDirectory(dir=out) as staging:
        stage = Path(staging)
        (stage/'results.json').write_text(json.dumps(z, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        (stage/'effective_config.json').write_bytes(snapshot)
        for name, rows in dict(z, input_sources=sources).items():
            if not isinstance(rows, list):
                continue
            with (stage/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
        for file in stage.iterdir():
            file.replace(out/file.name)
        (stage/'run_manifest.json').write_bytes(_json_bytes(manifest))
        (stage/'run_manifest.json').replace(out/'run_manifest.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir', nargs='?', type=Path, default=Path(__file__).resolve().parent/'modelout')
    parser.add_argument('overrides', nargs='?', type=Path, help='optional temporary parameter overrides')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG, help='five business assumptions or a complete model configuration')
    parser.add_argument('--base-config', type=Path, help='advanced settings to pair with business assumptions')
    args = parser.parse_args()
    try:
        changes = read_json(args.overrides.read_bytes()) if args.overrides is not None else None
        write(args.output_dir, changes, args.config, base_config_path=args.base_config)
    except (ValueError, OSError) as exc:
        parser.exit(2, f'model.py: {exc}\n')
