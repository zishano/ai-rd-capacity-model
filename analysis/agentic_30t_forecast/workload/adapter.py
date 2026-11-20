"""The existing inference kernel takes ONE task. Daily accounting stays outside it."""
def task_input(trace, peak_sequences, context_factor=1):
    return dict(input_tokens=int(trace['prompt']), output_tokens=int(trace['completion']),
                prefix_cache_hit_rate=int(trace['cache_read'])/int(trace['prompt']),
                context_tokens=round(int(trace['peak_request'])*context_factor),
                peak_sequences=peak_sequences)
