"""Single-person, single-Agent direct LLM inference demand model.

Usage:
  python agent_inference.py
  python agent_inference.py --config config/agent_inference.json --output modelout/agent_inference.json

The model estimates direct model-serving work only. Tool execution, CPU sandboxes,
training/evaluation jobs launched by the Agent, and queueing are accounted separately.
Python 3.9+, standard library only.
"""
import argparse
import json
import math
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config" / "agent_inference.json"


def load_config(path=DEFAULT_CONFIG):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    task, model, serving = data["task"], data["model"], data["serving"]
    positive = {
        "task.model_calls": task["model_calls"],
        "task.avg_input_tokens_per_call": task["avg_input_tokens_per_call"],
        "task.avg_output_tokens_per_call": task["avg_output_tokens_per_call"],
        "task.peak_context_tokens": task["peak_context_tokens"],
        "task.peak_concurrent_sequences": task["peak_concurrent_sequences"],
        "model.parameters_billion": model["parameters_billion"],
        "model.precision_bytes": model["precision_bytes"],
        "model.layers": model["layers"],
        "model.kv_heads": model["kv_heads"],
        "model.head_dimension": model["head_dimension"],
        "serving.gpus_per_replica": serving["gpus_per_replica"],
        "serving.gpu_memory_gb": serving["gpu_memory_gb"],
        "serving.prefill_tokens_per_second_per_replica": serving["prefill_tokens_per_second_per_replica"],
        "serving.decode_tokens_per_second_per_replica": serving["decode_tokens_per_second_per_replica"],
    }
    for key, value in positive.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be a positive finite number")
    if int(task["model_calls"]) != task["model_calls"] or int(task["peak_concurrent_sequences"]) != task["peak_concurrent_sequences"]:
        raise ValueError("model_calls and peak_concurrent_sequences must be integers")
    for key in ("input_prefix_cache_hit_rate",):
        value = task[key]
        if not 0 <= value <= 1:
            raise ValueError(f"task.{key} must be between 0 and 1")
    if not 0 < serving["usable_hbm_fraction"] <= 1:
        raise ValueError("serving.usable_hbm_fraction must be in (0, 1]")
    if serving["gpu_price_usd_per_hour"] < 0:
        raise ValueError("gpu_price_usd_per_hour cannot be negative")
    return data


def calculate(config):
    t, m, s = config["task"], config["model"], config["serving"]
    calls = int(t["model_calls"])
    input_tokens = calls * t["avg_input_tokens_per_call"]
    output_tokens = calls * t["avg_output_tokens_per_call"]
    cached_tokens = input_tokens * t["input_prefix_cache_hit_rate"]
    prefill_tokens_to_compute = input_tokens - cached_tokens

    # Throughput is explicitly per complete serving replica (not per GPU).
    prefill_seconds = prefill_tokens_to_compute / s["prefill_tokens_per_second_per_replica"]
    decode_seconds = output_tokens / s["decode_tokens_per_second_per_replica"]
    serial_service_seconds = prefill_seconds + decode_seconds
    replica_gpu_hours = serial_service_seconds * s["gpus_per_replica"] / 3600
    gpu_hours = replica_gpu_hours

    # Approximate BF16/FP8 weight footprint and standard Transformer KV footprint.
    weight_gb_total = m["parameters_billion"] * 1e9 * m["precision_bytes"] / 1e9
    tp = s["gpus_per_replica"]
    weight_gb_per_gpu = weight_gb_total / tp
    kv_bytes_per_token_total = (
        2 * m["layers"] * m["kv_heads"] * m["head_dimension"] * m["precision_bytes"]
    )
    kv_bytes_total = (
        kv_bytes_per_token_total
        * t["peak_context_tokens"]
        * t["peak_concurrent_sequences"]
    )
    kv_gb_total = kv_bytes_total / 1e9
    if s["kv_cache_sharded_across_tensor_parallel"]:
        kv_gb_per_gpu = kv_gb_total / tp
    else:
        kv_gb_per_gpu = kv_gb_total
    usable_hbm_gb = s["gpu_memory_gb"] * s["usable_hbm_fraction"]
    estimated_hbm_per_gpu = weight_gb_per_gpu + kv_gb_per_gpu
    hbm_headroom_gb = usable_hbm_gb - estimated_hbm_per_gpu

    # This is a lower-bound fit check; runtime buffers, activations, fragmentation,
    # communication buffers, and engine-specific allocations need measured overhead.
    hbm_fits_lower_bound = hbm_headroom_gb >= 0
    cost_usd = gpu_hours * s["gpu_price_usd_per_hour"]

    return {
        "task": {
            "model_calls": calls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cached_input_tokens": cached_tokens,
            "uncached_prefill_tokens": prefill_tokens_to_compute,
            "peak_context_tokens": t["peak_context_tokens"],
            "peak_concurrent_sequences": t["peak_concurrent_sequences"],
        },
        "latency": {
            "prefill_service_seconds": prefill_seconds,
            "decode_service_seconds": decode_seconds,
            "serial_model_service_seconds": serial_service_seconds,
            "note": "不含工具等待、排队、Agent 思考间隔、重试和多请求并行调度；批处理共享时需重新测量。",
        },
        "gpu": {
            "gpus_per_replica": tp,
            "gpu_hours_per_task": gpu_hours,
            "gpu_price_usd_per_hour": s["gpu_price_usd_per_hour"],
            "estimated_direct_inference_cost_usd": cost_usd,
        },
        "hbm": {
            "weight_gb_total": weight_gb_total,
            "weight_gb_per_gpu": weight_gb_per_gpu,
            "kv_gb_total": kv_gb_total,
            "kv_gb_per_gpu": kv_gb_per_gpu,
            "usable_hbm_gb_per_gpu": usable_hbm_gb,
            "estimated_weight_plus_kv_gb_per_gpu": estimated_hbm_per_gpu,
            "remaining_hbm_headroom_gb_per_gpu": hbm_headroom_gb,
            "lower_bound_fits": hbm_fits_lower_bound,
            "caveat": "仅权重+KV 的下界估算；未计激活、运行时 buffer、通信 buffer、碎片和引擎开销。KV 按配置决定是否 TP 分片。",
        },
        "assumptions": {
            "prefill_tokens_per_second_per_replica": s["prefill_tokens_per_second_per_replica"],
            "decode_tokens_per_second_per_replica": s["decode_tokens_per_second_per_replica"],
            "throughput_scope": "per complete serving replica",
            "evidence_kind": config.get("evidence", {}).get("kind", "C"),
            "evidence_note": config.get("evidence", {}).get("note", ""),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    config = load_config(args.config)
    result = calculate(config)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
