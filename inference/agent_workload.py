"""Build one-Agent daily token workload without touching team-capacity logic."""
def build_daily_workload(*, online_hours, inference_duty, input_tokens_per_active_hour,
                         output_tokens_per_active_hour, prefix_cache_hit_rate,
                         context_tokens, peak_sequences=1, decode_batch_sequences=1):
    values=(online_hours,inference_duty,input_tokens_per_active_hour,output_tokens_per_active_hour)
    if any(float(v)<0 for v in values): raise ValueError("hours, duty and token rates must be non-negative")
    if online_hours>24: raise ValueError("online_hours cannot exceed 24")
    if not 0<=inference_duty<=1: raise ValueError("inference_duty must be in [0,1]")
    if not 0<=prefix_cache_hit_rate<=1: raise ValueError("prefix_cache_hit_rate must be in [0,1]")
    if context_tokens<1 or peak_sequences<1 or decode_batch_sequences<1:
        raise ValueError("context and sequence counts must be positive")
    active_hours=float(online_hours)*float(inference_duty)
    input_tokens=active_hours*float(input_tokens_per_active_hour)
    output_tokens=active_hours*float(output_tokens_per_active_hour)
    return {
      "input_tokens":input_tokens,"output_tokens":output_tokens,
      "prefix_cache_hit_rate":float(prefix_cache_hit_rate),
      "context_tokens":int(context_tokens),"peak_sequences":int(peak_sequences),
      "decode_batch_sequences":int(decode_batch_sequences),
      "online_hours":float(online_hours),"inference_active_duty":float(inference_duty),
      "inference_active_hours":active_hours
    }
