# Chart notes — Synthetic 10T MoE single-Agent forecast

Future workload and serving-efficiency values are C-class assumptions. Public architecture/hardware facts are A; formula-derived values are B. The 10T model is synthetic, not a released model.

1. **Token workload:** Input/Output Tokens/day = online hours × inference duty × active-hour token rate. Base total grows 0.340M→1.177M/day (3.46×); Aggressive 2030 reaches 3.524M/day.
2. **Dense vs MoE:** 70B Dense BF16 weights ≈140GB; Synthetic 10T MoE FP8 weights ≈10.3TB; Top-8 active parameters ≈32.82B. Resident weights and activated compute are distinct.
3. **FLOPs composition:** Routed experts dominate weight-matrix work; Router and MLA Attention are separate terms. L1 approximation, not kernel-level measured FLOPs.
4. **Hardware:** 2028 Base/Top-8/32K/FP4 weights/FP8 KV capacity lower bounds: H100 192, H200 128, B200 96, GB300 72 GPUs. Modelled GPU-hours/day: 2.41, 1.62, 1.17, 0.92. Not measured serving results.
5. **Context:** MLA KV grows approximately linearly with context. Attention FLOPs and HBM/KV traffic also rise; bottleneck is selected by max(compute, HBM, EP communication).
6. **Top-K:** Fixed 10T total; Top-K 4/8/16 yields ≈22.25B/32.82B/53.96B active parameters. GPU-hours need not grow linearly because HBM/communication can dominate.
7. **GPU-hours:** Base 2026→2030 Token growth 3.46×, GPU-hours 1.28×; Conservative 2030 ≈0.51 GPU·h/day; Aggressive ≈5.90.
8. **Efficiency waterfall:** Base 2026 1.109 GPU·h/day; workload-only replacement 4.379; context 4.478; GB300 1.740; FP4 weights, FP8 KV and serving efficiency 1.419. Sequential decomposition is path-dependent.
9. **Cost:** Base 2030 shared allocation ≈$5.80/day; dedicated 72-GPU replica reserved 24h ≈$7,068/day. Both use normalized H100 $4.09/GPU·h, not GB300 pricing.
10. **Bottleneck map:** Batch×Context cells are labelled by whichever modelled time is largest: compute, HBM or communication. Requires target-cluster profiling.

Sources:
- Kimi K2: https://github.com/MoonshotAI/Kimi-K2
- NVIDIA H100/H200/B200: https://docs.nvidia.com/enterprise-reference-architectures/hgx-ai-factory-h100-h200-b200/latest/components.html
- NVIDIA GB300: https://resources.nvidia.com/en-us-gpu-resources/blackwell-ultra-datasheet
- Lambda prices (effective 2026-11-16): https://lambda.com/instances
