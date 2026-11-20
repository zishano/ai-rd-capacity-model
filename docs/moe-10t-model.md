# Synthetic 10T MoE 单 Agent 推理模型

## 范围与兼容性
本模块只替换推理计算，不修改团队业务工作负载、AL3/AL4/AL5、训练/评测/合成、CPU/RAM/SSD、持久存储、网络控制平面、人工复核或资源汇总公式。默认 `settings.inference_engine=dense`，原 Dense 路径保持默认。在 40T 分支上复现此 10T 模型时，将 `settings.inference_engine.value` 设为 `moe_10t`，并将 `settings.moe_model_config.value` 设为 `config/models/moe_10t.json`。

输入直接来自既有模型计算出的团队每日 Input/Output Tokens、Prefix Cache 命中率、上下文长度和峰值活跃序列数，不另行定义 Agent 业务参数。

## 合成模型结构
结构模板参考 Kimi K2：61 层、7168 hidden、384 Routed Experts、Top-8、每专家 intermediate 2048、1 个 Shared Expert、MLA（KV LoRA rank 512、RoPE 维度 64）。本项目将 routed experts 扩展为 3780 个，构造约 10T 参数的 **Synthetic 10T MoE**。这不是 Kimi 官方模型，也不是任何已发布的 10T 模型。

参考：
- Kimi K2: https://github.com/MoonshotAI/Kimi-K2
- Kimi K2 config: https://huggingface.co/moonshotai/Kimi-K2-Instruct/blob/main/config.json
- DeepSeek V3: https://github.com/deepseek-ai/DeepSeek-V3

参数核算：
`P_expert = 3 × hidden_size × expert_intermediate_size × num_moe_layers`
`P_routed = P_expert × num_routed_experts`
`P_total = P_routed + P_non_routed`
`P_active = P_non_routed + P_expert × top_k`

默认推导：Routed Expert 总参数约 9.9883T，总参数 10.000T，每 Token 激活参数约 32.82B。10.058752B non-routed 参数预算包含 attention、embedding、首层 Dense、shared expert 等，不含单独计算的 router 参数，属于 C 类假设；若有真实 10T 模型结构，应逐层替换。

## Token 到 FLOPs
权重矩阵近似：`F_weights/token ≈ 2 × P_active`。
Router 近似：`P_router = hidden_size × num_routed_experts × num_moe_layers`，`F_router/token = 2 × P_router`。矩阵乘 FLOPs 使用 `2 × (P_active - P_router)`，避免 Router 权重被重复计数。Attention 投影权重已包含在 non-routed 参数中；显式 Attention 公式只计 QK 与 AV 的上下文相关计算，避免重复计数。
MLA Attention 单独计量，Prefill 使用因果可见前缀平均长度，Decode 使用完整上下文。当前公式是 L1 架构近似，未逐算子展开 RMSNorm、RoPE、softmax、router top-k、量化/反量化、padding、expert token permutation、MTP 等细节。

## HBM 与 MLA KV Cache
权重容量：`M_weights = P_total × weight_bytes × (1 + scale_metadata_overhead)`。
Kimi-style MLA 不套标准 GQA 的 `2 × KV heads × head_dim` 公式。本模型近似按每层 `kv_lora_rank + qk_rope_head_dim` 存储：
`M_KV = num_layers × (kv_lora_rank + rope_dim) × kv_bytes × context × sequences`。
当前部署下界只计权重、KV 和按权重比例预留的 runtime HBM；未显式计入 CUDA Graph、activation、all-to-all buffer、碎片、专家副本、量化 scale 精确布局。因此 GPU 数是容量下界按 TP×EP 组取整，不是已验证的可运行部署配置。

## Compute / HBM / EP Roofline
Prefill 与 Decode 分别计算：
- Compute 时间下界 = FLOPs / (GPU 数 × FP8 峰值算力 × compute efficiency)
- HBM 时间下界 = (权重流量 + KV 流量) / (GPU 数 × HBM 带宽 × HBM efficiency)
- EP 通信时间下界 = dispatch/combine bytes / 有效互联带宽 + 每层 collective latency

EP 字节近似：`2 × TopK × hidden_size × activation_bytes × num_moe_layers`。当前通信模型未模拟真实拓扑路由、节点内/节点间分组、拥塞、token dropping、专家负载偏斜、All-to-All 算法与调度重叠。跨节点比例、有效带宽效率、batch reuse 和每层 collective latency 均为 C 类假设。瓶颈标签仅代表当前简化 roofline 模型中最大的时间下界。

## 硬件规格与证据等级
硬件配置来自 NVIDIA 公布的容量、HBM 带宽、Tensor Core 峰值和 NVLink 规格：
- H100: https://resources.nvidia.com/en-us-gpu/h100-datasheet-24306
- H200: https://www.nvidia.com/en-us/data-center/h200/
- HGX H100/H200/B200: https://docs.nvidia.com/enterprise-reference-architectures/hgx-ai-factory-h100-h200-b200/latest/components.html
- Blackwell Ultra: https://resources.nvidia.com/en-us-gpu-resources/blackwell-ultra-datasheet
- GB300 NVL72: https://www.nvidia.com/en-us/data-center/gb300-nvl72/

A 类：公开模型配置或厂商硬件规格。B 类：由公开结构按公式推导的参数量、权重容量和 KV 字节。C 类：合成 10T 扩展、batch reuse、compute/HBM/communication efficiency、跨节点流量比例、collective latency。当前模型属于 L1-L3，不是 L4 实测 serving profile。

## 运行
默认 Dense：
```bash
python model.py
```
启用合成 10T MoE：在 `config/assumptions.json` 将 `settings.inference_engine.value` 设为 `moe_10t`，并选择 `settings.moe_hardware.value`（H100_SXM / H200_SXM / B200_SXM / GB300_NVL72），再运行相同命令。

独立单 Agent 估算：
```python
from inference.moe import calculate
r = calculate({
  "input_tokens": 633600,
  "output_tokens": 46080,
  "prefix_cache_hit_rate": 0.55,
  "context_tokens": 16384,
  "peak_sequences": 1
}, hardware_name="H100_SXM")
```
这些 Token 值由现有 AL4 业务参数计算而来，不是头部厂商的单 Agent trace 实测。


## 额外建模边界

MoE 权重流量不应把所有激活参数简单除以 batch size。当前把每 Token 权重读取拆为 routed expert 和 non-routed/shared 两部分：

`W_token = P_routed_active / expert_weight_batch_reuse_factor + P_shared_active / batch_size`

默认 `expert_weight_batch_reuse_factor=1.0`，不假设不同 Token 会复用同一专家权重；真实复用取决于路由分布、专家命中频率、权重缓存和 kernel 调度，应使用 profiler 校准。Prefill/Decode collective latency 分别按 batch rounds 计数，不再把每个 Token 误当成独立 collective。计算、HBM、通信时间是简化下界，未建模真实通信重叠、专家负载偏斜、热点专家复制、token permutation、拥塞和引擎 Buffer，不能标记为实测性能。


## Low / Base / High 激活参数场景

为满足激活参数敏感性分析，提供三种模型配置。三者保持 10T 总参数、层数、隐藏维度、专家数量和权重精度不变，只改变每 Token 激活的 Routed Experts 数量：

| 场景 | Top-K | 近似激活参数 |
|---|---:|---:|
| Low Active | 4 | 22.25B |
| Base Active | 8 | 32.82B |
| High Active | 16 | 53.97B |

这是结构敏感性场景，不是三个真实发布模型，也不代表 Top-K 增加后质量或性能必然按比例变化。运行硬件扫描：

```bash
python scripts/moe_hardware_sweep.py
```

默认输出 `modelout/moe_hardware_sweep.csv`，比较三种激活场景与 H100/H200/B200/GB300 的参数量、部署 GPU 下界、FLOPs、GPU-hours、KV 和瓶颈标签。
