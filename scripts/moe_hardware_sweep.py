"""Sweep active-parameter variants across supported GPU profiles."""
import argparse,csv
from pathlib import Path
from inference.moe import calculate,DEFAULT_MODEL

ROOT=Path(__file__).resolve().parents[1]
MODELS={
 "low_active":ROOT/"config/models/moe_10t_low_active.json",
 "base_active":ROOT/"config/models/moe_10t.json",
 "high_active":ROOT/"config/models/moe_10t_high_active.json",
}
HARDWARE=("H100_SXM","H200_SXM","B200_SXM","GB300_NVL72")

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--input-tokens",type=float,default=633600)
 p.add_argument("--output-tokens",type=float,default=46080)
 p.add_argument("--cache-hit",type=float,default=.55)
 p.add_argument("--context",type=int,default=16384)
 p.add_argument("--sequences",type=int,default=1)
 p.add_argument("--output",type=Path,default=ROOT/"modelout/moe_hardware_sweep.csv")
 a=p.parse_args()
 workload={"input_tokens":a.input_tokens,"output_tokens":a.output_tokens,
  "prefix_cache_hit_rate":a.cache_hit,"context_tokens":a.context,
  "peak_sequences":a.sequences,"decode_batch_sequences":a.sequences}
 rows=[]
 for variant,model in MODELS.items():
  for hw in HARDWARE:
   z=calculate(workload,hw,model_path=model)
   rows.append({
    "variant":variant,"hardware":hw,"total_parameters":z["total_parameters"],
    "active_parameters":z["active_parameters"],
    "deployment_gpus_per_replica":z["deployment_gpus_per_replica"],
    "deployment_replicas":z["deployment_replicas"],"infer_cards":z["infer_cards"],
    "prefill_eflop":z["prefill_eflop"],"decode_eflop":z["decode_eflop"],
    "prefill_gpu_h":z["prefill"]["gpu_hours"],"decode_gpu_h":z["decode"]["gpu_hours"],
    "infer_gpu_h":z["infer_gpu_h"],"kv_peak_gb":z["kv_peak_gb"],
    "weights_gb_per_replica":z["weights_gb_per_replica"],
    "prefill_bottleneck":z["prefill"]["bottleneck"],
    "decode_bottleneck":z["decode"]["bottleneck"]})
 a.output.parent.mkdir(parents=True,exist_ok=True)
 with a.output.open("w",encoding="utf-8",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 print(f"Wrote {len(rows)} rows to {a.output}")
if __name__=="__main__":main()
