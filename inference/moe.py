"""L1-L3 first-order MoE inference model. No measured serving claims."""
import json, math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_MODEL=ROOT/"config/models/moe_10t.json"
DEFAULT_HARDWARE=ROOT/"config/hardware/gpus.json"

def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def _ceil_multiple(n,m):
    return int(math.ceil(n/m)*m)

def validate_model(m):
    a=m["architecture"]; s=m["serving_assumptions"]
    if a["experts_per_token"]>a["num_routed_experts"] or a["num_moe_layers"]>a["num_hidden_layers"]:
        raise ValueError("invalid MoE architecture counts")
    for k in ("usable_hbm_fraction","target_gpu_pool_utilization","compute_efficiency","hbm_bandwidth_efficiency","communication_bandwidth_efficiency"):
        if not 0 < s[k] <= 1: raise ValueError(f"{k} must be in (0,1]")

def architecture_stats(model):
    a=model["architecture"]
    per=a["expert_mlp_matrices"]*a["hidden_size"]*a["expert_intermediate_size"]*a["num_moe_layers"]
    routed=per*a["num_routed_experts"]
    active=per*a["experts_per_token"]
    router=a["hidden_size"]*a["num_routed_experts"]*a["num_moe_layers"]
    total=routed+router+a["non_routed_parameters"]
    return {"expert_params_per_expert_all_layers":per,"routed_expert_total_parameters":routed,
            "routed_expert_active_parameters":active,"router_parameters":router,"total_parameters_derived":total,
            "active_parameters_derived":active+router+a["non_routed_parameters"],
            "target_total_parameters":a["target_total_parameters"],
            "total_parameter_error_fraction":total/a["target_total_parameters"]-1}

def _attn_flops_token(a,context,phase):
    # MLA: QK uses qk_nope+qk_rope; AV uses v_head_dim.
    dims=a["num_attention_heads"]*(a["qk_nope_head_dim"]+a["qk_rope_head_dim"]+a["v_head_dim"])
    return (2 if phase=="prefill" else 4)*a["num_hidden_layers"]*dims*context

def calculate(workload,hardware_name="H100_SXM",model_path=DEFAULT_MODEL,hardware_path=DEFAULT_HARDWARE):
    m=_read(model_path); hwdb=_read(hardware_path)["hardware"]; validate_model(m)
    if hardware_name not in hwdb: raise ValueError(f"unknown hardware: {hardware_name}")
    a=m["architecture"]; w=m["weights"]; kv=m["kv_cache"]; s=m["serving_assumptions"]; hw=hwdb[hardware_name]
    stats=architecture_stats(m); total_p=stats["total_parameters_derived"]; active_p=stats["active_parameters_derived"]
    I=float(workload["input_tokens"]); O=float(workload["output_tokens"]); cache=float(workload.get("prefix_cache_hit_rate",0))
    context=int(workload["context_tokens"]); seq=max(1,int(math.ceil(workload.get("peak_sequences",1))))
    if not 0<=cache<=1: raise ValueError("cache hit rate must be [0,1]")
    uncached=I*(1-cache)
    weight_gb=total_p*w["bytes_per_parameter"]*(1+w["scale_metadata_overhead_fraction"])/1e9
    kv_dim=a["kv_lora_rank"]+a["qk_rope_head_dim"]
    kv_bpt=a["num_hidden_layers"]*kv_dim*kv["bytes_per_element"]
    kv_gb=kv_bpt*context*seq/1e9
    tp=int(s["tensor_parallel_size"]); ep=int(s["expert_parallel_by_hardware"][hardware_name]); group=tp*ep
    usable=hw["memory_gb"]*s["usable_hbm_fraction"]
    runtime_gb=weight_gb*s["runtime_hbm_reserve_fraction"]
    min_gpus=math.ceil((weight_gb+kv_gb+runtime_gb)/usable)
    ngpu=_ceil_multiple(min_gpus,group)
    router_params=stats["router_parameters"]
    router=2*router_params
    matmul=2*(active_p-router_params)
    pf_flop_tok=matmul+_attn_flops_token(a,context,"prefill")+router
    dc_flop_tok=matmul+_attn_flops_token(a,context,"decode")+router
    pf_flops=uncached*pf_flop_tok; dc_flops=O*dc_flop_tok
    pf_weight=active_p*w["bytes_per_parameter"]/max(1,s["prefill_batch_tokens"])
    dc_weight=active_p*w["bytes_per_parameter"]/max(1,s["decode_batch_sequences"])
    pf_kv=kv_bpt*context/2; dc_kv=kv_bpt*context
    ep_bytes=2*a["experts_per_token"]*a["hidden_size"]*2*a["num_moe_layers"]
    cross=s["cross_node_traffic_fraction"]
    local=hw["nvlink_per_gpu_tb_s"]*1e12; remote=hw["inter_node_per_gpu_gb_s"]*1e9
    link=1/(cross/remote+(1-cross)/local)
    comm_bw=ngpu*link*s["communication_bandwidth_efficiency"]
    comm_latency=a["num_moe_layers"]*s["all_to_all_latency_us_per_moe_layer"]*1e-6
    hbm_bw=ngpu*hw["hbm_bandwidth_tb_s"]*1e12*s["hbm_bandwidth_efficiency"]
    compute=ngpu*hw["fp8_dense_peak_tflops"]*1e12*s["compute_efficiency"]
    def phase(tokens,flops_tok,weight_bytes,kv_bytes,latency_per_token):
        if tokens<=0: return {"tokens":0,"compute_seconds":0,"hbm_seconds":0,"communication_seconds":0,"service_seconds":0,"gpu_hours":0,"tokens_per_second":0,"bottleneck":"none"}
        c=tokens*flops_tok/compute; h=tokens*(weight_bytes+kv_bytes)/hbm_bw
        n=tokens*ep_bytes/comm_bw+tokens*latency_per_token
        bottleneck=max(((c,"compute"),(h,"hbm"),(n,"communication")))[1]
        sec=max(c,h,n)
        return {"tokens":tokens,"compute_seconds":c,"hbm_seconds":h,"communication_seconds":n,"service_seconds":sec,"gpu_hours":sec*ngpu/3600,"tokens_per_second":tokens/sec if sec else 0,"bottleneck":bottleneck}
    pre=phase(uncached,pf_flop_tok,pf_weight,pf_kv,comm_latency/max(1,prefill_batch)); dec=phase(O,dc_flop_tok,dc_weight,dc_kv,comm_latency/max(1,decode_batch))
    infer_gpu_h=pre["gpu_hours"]+dec["gpu_hours"]
    replicas=max(1,math.ceil((pre["service_seconds"]+dec["service_seconds"])/(86400*s["target_gpu_pool_utilization"])))
    cards=ngpu*replicas
    return {"hardware":hardware_name,"model_id":m["model_id"],"model_name":m["model_name"],
      "total_parameters":total_p,"active_parameters":active_p,"parameter_stats":stats,
      "input_tokens":I,"output_tokens":O,"uncached_input_tokens":uncached,
      "prefill":pre,"decode":dec,"prefill_eflop":pf_flops/1e18,"decode_eflop":dc_flops/1e18,
      "infer_gpu_h":infer_gpu_h,"infer_cards":cards,"deployment_gpus_per_replica":ngpu,"deployment_replicas":replicas,
      "weights_gb_per_replica":weight_gb,"kv_peak_gb":kv_gb,"kv_bytes_per_token":kv_bpt,
      "kv_slots_per_replica":max(0,int((ngpu*usable-weight_gb-runtime_gb)*1e9/(kv_bpt*context))),
      "kv_replicas":replicas,"throughput_replicas":replicas,
      "per_gpu_memory":{"weights_gb":weight_gb/ngpu,"kv_gb":kv_gb/ngpu,"runtime_reserve_gb":runtime_gb/ngpu,"usable_hbm_gb":usable},
      "communication":{"ep_bytes_per_token":ep_bytes,"effective_link_bandwidth_bytes_s_per_gpu":link,"cross_node_fraction":cross,"latency_seconds_per_token":comm_latency},
      "evidence_type":"C: synthetic model and serving efficiencies; vendor specs and public Kimi/DeepSeek configs are references, not measured performance."}
