"""Reproduce evidence-audit scenario GPU-hours; does not call or modify team model."""
import argparse,csv,json,tempfile
from pathlib import Path
from inference.moe import calculate,DEFAULT_MODEL,DEFAULT_HARDWARE
from inference.agent_workload import build_daily_workload

ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--config",type=Path,default=ROOT/"config/agent_inference_evidence.json")
 p.add_argument("--model",type=Path,default=DEFAULT_MODEL)
 p.add_argument("--hardware-config",type=Path,default=DEFAULT_HARDWARE)
 p.add_argument("--output",type=Path,default=ROOT/"analysis/agent_inference_evidence_audit/scenario_gpu_hours.csv")
 args=p.parse_args()
 cfg=json.loads(args.config.read_text(encoding="utf-8"))
 model=json.loads(args.model.read_text(encoding="utf-8"))
 rows=[]
 with tempfile.TemporaryDirectory() as td:
  mpath=Path(td)/"model.json"
  for name,s in cfg["single_agent_scenarios"].items():
   m=json.loads(json.dumps(model))
   sa=m["serving_assumptions"]
   sa.update({"prefill_batch_tokens":s["prefill_batch_tokens"],
      "decode_batch_sequences":s["decode_batch_sequences"],"compute_efficiency":s["compute_efficiency"],
      "hbm_bandwidth_efficiency":s["hbm_efficiency"],
      "communication_bandwidth_efficiency":s["communication_efficiency"],
      "cross_node_traffic_fraction":s["cross_node_traffic_fraction"],
      "all_to_all_latency_us_per_moe_layer":s["a2a_latency_us_per_moe_layer"],
      "expert_weight_batch_reuse_factor":s["expert_weight_reuse_factor"]})
   m["architecture"]["experts_per_token"]=s["top_k"]
   mpath.write_text(json.dumps(m),encoding="utf-8")
   w=build_daily_workload(online_hours=s["online_hours_per_day"],
      inference_duty=s["inference_active_duty"],
      input_tokens_per_active_hour=s["input_tokens_per_inference_active_hour"],
      output_tokens_per_active_hour=s["output_tokens_per_inference_active_hour"],
      prefix_cache_hit_rate=s["prefix_cache_hit_rate"],context_tokens=s["context_tokens"])
   z=calculate(w,s["hardware"],model_path=mpath,hardware_path=args.hardware_config)
   rows.append({"scenario":name,**w,"top_k":s["top_k"],"hardware":s["hardware"],
      "prefill_gpu_h":z["prefill"]["gpu_hours"],"decode_gpu_h":z["decode"]["gpu_hours"],
      "gpu_hours_per_agent_day":z["infer_gpu_h"],
      "hbm_capacity_lower_bound_gpus":z["hbm_capacity_lower_bound_gpus"],
      "group_rounded_gpus_per_replica":z["deployment_gpus_per_replica"],
      "prefill_bottleneck":z["prefill"]["bottleneck"],"decode_bottleneck":z["decode"]["bottleneck"],
      "evidence":"C scenario; not measured single-Agent trace"})
 args.output.parent.mkdir(parents=True,exist_ok=True)
 with args.output.open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 print(f"Wrote {len(rows)} rows to {args.output}")
if __name__=="__main__":main()
