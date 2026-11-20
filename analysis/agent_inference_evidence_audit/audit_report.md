# 10T MoE 单 Agent 推理模型：输入参数证据审计

**审计日期：2026-11-20**  
**范围：仅限单人单 Agent 直接 LLM 推理子模型及其独立参数配置。** 不修改团队主计算流程、团队业务参数、AL3–AL5 假设、训练/评测、CPU/RAM/SSD、团队存储、网络或团队成本汇总。

## 0. 审计结论

现有模型的主要问题不是 MoE 参数量公式，而是工作负载和 Serving 参数的证据不足：

1. OpenAI 已公开研究员 Agent 累计运行时、API 标价用量和日峰值并发；Anthropic 已公开一个内部平台约 30,000 Agent、研发自动化指数及部分计算分配。
2. 这些均是研究员或平台级数据，不是单 Agent 的模型调用日志，也不是单 Agent GPU-hours。
3. 当前 AL4 的 110k input tokens/活跃小时、8k output tokens/活跃小时、24% inference duty、55% prefix-cache hit 等参数均为 C 类假设，没有公开单 Agent trace 直接支持。
4. 现有 Serving 假设中的 compute 30%、HBM 70%、communication 50%、cross-node 50%、A2A 10 μs、expert reuse 1、EP group size 等均未被目标 10T 模型的公开 Profile 校准。
5. 硬件规格中 B200/GB300 FP8 峰值混淆稀疏与稠密口径：B200 应使用 4,500 TFLOPS dense，GB300 应使用 5,000 TFLOPS dense。模型代码使用 dense roofline，不能输入 sparse peak。

**因此：公开证据目前可以约束研究员级 Agent 工作规模和硬件规格；无法唯一识别单 Agent 的 Token 速率、推理活跃率和目标 10T 模型的有效算力/带宽/通信效率。** 对这些参数应保留区间，不应把某个点值写成“厂商实测”。

## 1. 最新头部厂商数据及其可用边界

### 1.1 OpenAI（2026-09 与 2026-11）

OpenAI 2026-09-06《Research acceleration: The view inside OpenAI》先披露了 mid-August 截面：中位研究员每天使用超过 $600 API list-price inference，P90 超过 $7,000；研究组织总 Agent 工作量为 3.1 agent-workdays / human workday。该报告同时指出研究员通常并发使用多个 Agent。

OpenAI 2026-11-18《Research acceleration: The jagged frontier》更新了口径和时间范围，披露：

| 指标 | 公开值 | 口径 | 可用于什么 |
|---|---:|---|---|
| Agent workdays / researcher / day | 0.5 → 5.7 | 每 8 小时 Agent 使用计 1 workday；多 Agent 累计 | 研究员级 Agent 运行时规模 |
| Agent 累计运行时 | 45.6 agent-hours / researcher / day | 5.7 × 8 小时 | 研究员级运行时约束，不是单 Agent 时长 |
| 日峰值并发 | >2/3 研究员峰值至少 4；>10% 至少 16 | 每人日峰值 | 并发压力阈值，不是平均活跃序列数 |
| API 标价用量中位数 | 9 月约 $1,500；10 月约 $2,400 / researcher / day | API list-price equivalent | API 费用交叉核验，不是硬件成本 |
| API 标价用量 P90 | 9 月约 $11,000；10 月约 $23,000 / researcher / day | API list-price equivalent | 高强度用户压力场景 |
| 内部部署计算份额 | 约 2%（9 月口径） | 内部 Codex、ChatGPT、API 使用的部署计算 | 说明内部推理部署占研究计算的比例；不是 GPU-hours/Agent |

来源：[OpenAI 9 月 6 日报告](https://openai.com/index/research-acceleration-view-inside-openai/)；[OpenAI 11 月 18 日报告](https://openai.com/index/research-acceleration-jagged-frontier/)。

11 月报告进一步说明：Agent workdays 指每 8 小时 Agent 使用累计为一个 workday；研究员范围包括部分研究基础设施、项目管理和支持人员；并发峰值包含用户直接启动的 Agent 与下游 subagents。报告还指出，2026-08-21 的临时 Harness 效率改进曾明显压低输入 Token 使用量，9 月 10 日起逐步回退后 Token spend 快速上升。这说明 API 标价费用不仅受 Agent 活动量影响，也会被模型选择和 Harness 的 Token 效率影响。

**关键限制：** 45.6 小时是多 Agent 的累计 wall-clock 工作时长；不能等同 LLM active time，也不能等同 GPU busy time。API 标价用量包含模型选择、价格和 Harness 行为变化，不能直接换算成真实输入输出 Token。

### 1.2 OpenAI API spend → Token 等价量（条件推导 B/C）

当前公开 API 价格示例（每百万 Token）：

| 模型 | Input | Cached input | Output |
|---|---:|---:|---:|
| GPT-6.2 Astra | $8 | $0.40 | $40 |
| GPT-6.2 Sol | $2 | $0.10 | $10 |

来源：[OpenAI API Pricing（Standard 价格表）](https://developers.openai.com/api/docs/pricing)。

为展示 API spend 能约束到什么程度，采用一个**明确标记为假设**的转换条件：Input:Output=10:1，输入前缀缓存命中率 55%。

`P_in_eff=(1-0.55)P_in+0.55P_cached`

`P_blended=(10P_in_eff+P_out)/11`

`T_equiv=API_list_price_spend/P_blended`

结果：

| 费用口径 | Astra 等价 Token | Sol 等价 Token |
|---|---:|---:|
| 9 月中位数 $1,500/日 | 211M/日 | 844M/日 |
| 10 月中位数 $2,400/日 | 338M/日 | 1,350M/日 |
| 10 月 P90 $23,000/日 | 3,235M/日 | 12,941M/日 |

这不是公开测得的 Token 数。它只说明：在给定模型价格、缓存率和输入输出比例下，API 标价用量对应的 Token 等价区间有多宽。实际模型混用、缓存写入、工具费、长上下文价格和 reasoning token 口径都会改变结果。当前价格表中还存在 30 分钟/12 小时 cache-write 费用；本次简化公式只计缓存命中后的 cached-input 读取价，未计 cache-write。**不得把这张表直接当作单 Agent Token 输入。**

### 1.3 Anthropic（2026）

Anthropic 2026 年 R&D Automation Index 披露：

- 2026 年 8 月，最常用内部平台同时约 30,000 个研发/工程 Agent。
- AL4 重要性加权研发工作比例约 26%；超过 90% 的研发工作至少达到 AL3；测量任务中未观察到 AL5。
- 2026-07-13 至 07-20 的计算快照：AI R&D compute 中约 6% 用于 Safety；AI-driven AI R&D compute 中约 12% 用于 Safety。
- 约 15,000 个细粒度任务；542 个任务树节点、378 个叶子任务。按人时代理任务权重。

来源：[Anthropic R&D Automation Index](https://www.anthropic.com/institute/measuring-pace-of-ai-development)。

**关键限制：**
- 30,000 是单个平台瞬时 Agent 数，不是全公司总数，也不是 30,000 个同时生成 Token 的活跃推理序列。
- AL4 26% 是按 person-time proxy 加权的任务自动化覆盖，不是 Token、GPU 或工作时间占比。
- 6%/12% 是计算资源分配比例，不提供绝对推理 GPU-hours。
- Anthropic 方法说明，任务权重基于人员每周任务分配；标签来自自动化分类器和 best-effort workload tags，存在误分类风险。

## 2. 公开 Serving Profile 能约束什么？

### 2.1 Kimi K2 结构（A）

Kimi K2 公开配置：1T 总参数、32B 激活参数、61 层、384 Routed Experts、Top-8、Hidden 7168、Expert Intermediate 2048、MLA、KV LoRA Rank 512、RoPE 维度 64、FP8 block quantization（128×128 block）、上下文 128K。Kimi K2 Thinking 有 256K 上下文和 INT4 QAT 变体。

来源：[Kimi K2 model card](https://huggingface.co/moonshotai/Kimi-K2-Instruct)，[官方 config](https://huggingface.co/moonshotai/Kimi-K2-Instruct/blob/main/config.json)。

这些是 10T 合成模型的结构模板，不是 10T 模型的实测数据。当前 3,780 Experts 和 10T total parameters 是 C 类扩展假设。

### 2.2 SGLang / vLLM 公开 Serving Profile（A）

SGLang Kimi K2 B200 8-GPU benchmark（TP8、Attention-DP4，吞吐场景 EP4，SGLang 0.5.6.post1）：

| 场景 | Max concurrency | Input tok/s | Output tok/s | Mean TTFT | Mean TPOT |
|---|---:|---:|---:|---:|---:|
| 延迟敏感 | 1 | 43.42 | 61.32 | 141 ms | 18.40 ms |
| 吞吐敏感 | 100（平均 89.6） | 1,703.73 | 1,113.25 | 457 ms | 97.23 ms |

来源：[SGLang Kimi K2 benchmark](https://github.com/sgl-project/sglang/blob/main/docs/cookbook/autoregressive/Moonshotai/Kimi-K2.mdx)。

vLLM Kimi K2 recipe 给出 16×H800/H200 FP8 作为 128K 上下文的部署示例，max-num-batched-tokens 常见配置 8,192，prompt-heavy 场景可提高至 32,768，max-num-seqs 示例为 256，GPU memory utilization 示例为 0.85。

来源：[vLLM Kimi K2 deployment recipe](https://github.com/vllm-project/recipes/blob/main/moonshotai/Kimi-K2.md)。

**可用于：** 为 batch、TP、EP、KV 精度和实际 TTFT/TPOT 建立真实系统测试范围。  
**不能用于：** 直接把 1T Kimi K2 的吞吐当成 10T 合成 MoE 的吞吐，或从端到端 TPOT 唯一反推出 compute/HBM/All-to-All 效率。

## 3. 输入参数审计结论

完整 47 项参数台账见同目录 `parameter_ledger.csv`。主要结论：

| 参数组 | 当前问题 | 审计处理 |
|---|---|---|
| Agent runtime | 有研究员级观测，无单 Agent 分布 | 保留研究员级外部约束，不转换成 GPU 时间 |
| Input/Output rate | 当前 110k/8k 每活跃小时无公开单 Agent trace | 保留 C 类宽区间；用 API spend 做条件交叉核验 |
| Duty | 24% 无公开直接测量 | 保留 5%-65% 敏感性 |
| Cache hit | 55% 无公开 Agent trace | 保留 10%-85%，按 token-weighted hit 校准 |
| Context | 16K 是规划点，不是使用分布 | 8K/16K/64K，128K stress |
| Decode batch | 单 Agent=1；共享服务可能远高于 1 | 1/4/16/64/100 敏感性 |
| Prefill batch | 当前 64 缺少依据 | 参考公开 Kimi recipe 测试 1,024/8,192/32,768 |
| Compute/HBM/Comm efficiency | 30/70/50% 均无目标模型 Profile | 保留 C 类范围并要求实测校准 |
| EP group / cross-node traffic | 当前 48/32/24/18 与 50% 跨节点比例均为设计假设 | 不再称为最优或实测；按拓扑/微基准更新 |
| A2A latency | 10 μs/层无目标集群实测 | 5/10/50 μs 做敏感性，不宣称真实区间 |
| Expert reuse | 1 是无复用保守假设 | 1/2/4/8/16 敏感性 |
| 权重元数据 | 当前 3% 没有量化格式依据 | 128×128 block、FP32 单 scale 的理论比例为 0.0244%；实际布局另测 |

## 4. 公开数据到单 Agent 工作负载的推导

当前模型工作负载公式：

[
T_{in}=H_{online}	imes u_{infer}	imes r_{in}
]

[
T_{out}=H_{online}	imes u_{infer}	imes r_{out}
]

其中：
- (H_{online})：单 Agent 每日在线小时；
- (u_{infer})：在线时间中模型推理活跃的比例；
- (r_{in},r_{out})：每推理活跃小时输入/输出 Token 速率。

当前 AL4 单 Agent 示例：

[
24	imes0.24	imes110,000=633,600
]

[
24	imes0.24	imes8,000=46,080
]

这两个结果是 B 类公式推导，但三个输入因子均为 C 类假设。

### API spend 交叉核验

当前 AL4 单 Agent 负载（633.6K input、46.08K output、55% cache）按 GPT-6.2 Sol 标价估算约 $1.07/日，按 GPT-6.2 Astra 标价约 $4.26/日。

OpenAI 报告的研究员中位数为 $2,400/日，但它包含一个研究员的多 Agent、多模型和多种工具使用。因此两者**不能直接比较为同一口径**。差距说明现有单 Agent token 率尚未通过头部实验室使用强度校准，不能声称已经被公开数据验证。

## 5. 有证据约束的三种单 Agent 情景

以下保留原有 AL4 参数作为基准，并用已有配置区间构造保守和激进场景。它们是 C 类情景，不是厂商实测：

| 参数 | 保守 | 基准 | 激进 |
|---|---:|---:|---:|
| 在线小时/日 | 12 | 24 | 24 |
| 推理活跃占空比 | 10% | 24% | 50% |
| Input Token/活跃小时 | 60K | 110K | 250K |
| Output Token/活跃小时 | 5K | 8K | 22K |
| Input Tokens/day | 72K | 633.6K | 3.0M |
| Output Tokens/day | 6K | 46.08K | 264K |
| Prefix Cache 命中 | 35% | 55% | 70% |
| Context | 8K | 16K | 64K |
| Top-K | 4 | 8 | 16 |

硬件统一 H100 SXM、10T FP8 合成模型，以便隔离 Agent 负载差异。Serving efficiency、A2A latency 和 expert reuse 的场景值详见 `scenario_parameters.json`，不能视为实测。

## 6. GPU-hours 区间与敏感性

按当前 L1-L3 Roofline 模型、H100、10T Synthetic MoE、上述三种情景计算：

| 情景 | Input/日 | Output/日 | Prefill GPU·h | Decode GPU·h | 合计 GPU·h/日 |
|---|---:|---:|---:|---:|---:|
| 保守 | 72K | 6K | 0.084 | 0.384 | 0.469 |
| 基准 | 633.6K | 46.08K | 0.733 | 1.478 | 2.212 |
| 激进 | 3.0M | 264K | 4.159 | 8.484 | 12.642 |

这些不是置信区间，而是给定三组 C 类参数后的模型输出。真正的预测区间必须对工作负载、batch、A2A latency、expert reuse、效率和拓扑联合采样。

### 基准场景的关键敏感性

| 参数变化 | GPU·h/日 | Decode 瓶颈 |
|---|---:|---|
| Decode batch=1 | 2.212 | Communication |
| Decode batch=4 | 1.106 | Communication |
| Decode batch=16 | 0.859 | HBM |
| Decode batch=64 | 0.856 | HBM |
| Decode batch=100 | 0.856 | HBM |
| A2A=5 μs/层 | 1.474 | Communication |
| A2A=10 μs/层 | 2.212 | Communication |
| A2A=50 μs/层 | 8.110 | Communication |
| Expert reuse=1 | 2.212 | Communication |
| Expert reuse=4 | 1.676 | Communication |
| Expert reuse=16 | 1.542 | Communication |

最重要的发现：**单 Agent 独立服务和多 Agent 共享模型副本的 GPU-hours 不能混为一谈。** Decode batch 从 1 增至 16 后，当前模型从通信瓶颈转为 HBM 瓶颈，GPU-hours 约从 2.21 降到 0.86。真实服务还会有排队和 TPOT 变化，因此需要同时报告 GPU-hours 与延迟。

### 容量和工作量必须分开

- H100 10T FP8 权重 + 运行时预留 + KV 的原始 HBM 容量下界约 162 张卡（采用 0.0244% scale-only 元数据假设）。
- 当前 TP4×EP48 的 group-rounded 配置为 192 张卡。
- 192 张卡是一个模型副本的候选驻留容量，不是一个 Agent 每天消耗 192 张卡，也不是已验证可运行的部署方案。
- GPU-hours 是 Agent 工作量对应的设备时间分配；部署卡数是模型常驻容量和服务池容量。两者不能互相替代。

## 7. 硬件参数纠正

当前 `config/hardware/gpus.json` 使用 FP8 dense peak，因此：
- H100：1,979 TFLOPS dense（3,958 sparse）
- H200：1,979 TFLOPS dense（3,958 sparse）
- B200：4,500 TFLOPS dense（9,000 sparse）
- GB300：5,000 TFLOPS dense（10,000 sparse）

NVIDIA 官方来源：[H100](https://resources.nvidia.com/en-us-gpu-resources/h100-datasheet-24306)、[H200](https://www.nvidia.com/en-us/data-center/h200/)、[HGX B200](https://www.nvidia.com/en-au/data-center/hgx/)、[Blackwell Ultra](https://resources.nvidia.com/en-us-gpu-resources/blackwell-ultra-datasheet)。

Inter-node per-GPU bandwidth 50/100 GB/s 不是 GPU 官方规格，必须由真实 NIC、rail、oversubscription 和拓扑配置给出。

## 8. 主要缺失数据及校准计划

| 缺失数据 | 为什么重要 | 需要采集什么 |
|---|---|---|
| 单 Agent request trace | 决定真实输入/输出 Token 与 duty | session_id、request_id、timestamp、input/output/cache tokens、model id |
| Agent runtime trace | 区分在线、工具等待、LLM 活跃 | agent start/stop、tool spans、LLM spans、idle gaps |
| Prefix cache token hit | 影响 Prefill 工作量 | matched prefix tokens / total input tokens |
| 实际 decode batch | 改变专家权重复用和 collective rounds | 每个 decode step 的 batch size |
| 10T 专家路由分布 | 决定专家复用与通信 fanout | 每层 top-k expert ids、rank placement、tokens/expert |
| A2A profile | 决定通信瓶颈 | dispatch/combine bytes、latency、remote bytes、overlap |
| HBM profile | 决定权重/KV实际流量 | HBM read/write bytes、achieved BW、KV hit |
| Compute profile | 决定有效算力 | per-op FLOPs、kernel time、achieved TFLOPS |
| 实际量化布局 | 决定权重驻留 | scale dtype、group size、padding、block metadata |

建议优先用真实 Agent trace 校准输入/输出 Token，再用 LLMCompass 做模型算子 Profile，最后使用 SGLang/vLLM 的实际部署配置测量 TP/EP、Batch、A2A 和 HBM。不要先调一个总效率系数去拟合最终 GPU-hours。

## 9. 不确定性展示方法

不要只给一个 GPU-hours 点值。建议采用：

1. **单因素敏感性**：每次只改变一个参数，识别主要驱动因素。
2. **联合情景抽样**：对 duty、Token rate、context、cache、Top-K、batch、efficiency、A2A latency、expert reuse 联合采样，报告 P10/P50/P90。
3. **结构不确定性**：把 10T 模型专家布局、非路由参数预算、EP 通信模型作为不同模型版本，而不只是参数区间。
4. **校准不确定性**：有实测 profile 后，用 measured/estimated ratio 校准各阶段，并保留 benchmark workload 与目标 Agent workload 的分布差异。

当前保守/基准/激进三点只是情景，不应被称为 P10/P50/P90。

## 10. 修改范围与兼容性

本次证据审计只涉及：
- `inference/moe.py`
- `config/models/moe_10t.json`
- `config/hardware/gpus.json`
- 新增 `config/agent_inference_evidence.json`
- 新增 `analysis/agent_inference_evidence_audit/`

不修改 `model.py`、`assumptions.py`、`config/assumptions.json`、训练/评测、CPU/RAM/SSD、存储和团队成本汇总公式。Dense 默认路径不变。所有非推理资源结果必须继续通过现有回归测试。


### API spend 与当前 AL4 单 Agent 点值的交叉核验

当前 AL4 单 Agent 示例为 633,600 input Token/day、46,080 output Token/day，prefix cache 命中 55%。按 GPT-6.2 Sol Standard 价格计算：

`cost = 633600×0.45×$2/M + 633600×0.55×$0.1/M + 46080×$10/M ≈ $1.07/day`。

按 GPT-6.2 Astra Standard 价格约为 $4.26/day。OpenAI 报告的 $2,400/day 是每名研究员的多 Agent API list-price equivalent，包含模型混用、subagents、不同 Harness 和多种任务。两者不是同一统计单位，不能用比例直接修正单 Agent Token 率；但这个数量级差异足以说明当前 AL4 点值尚未被头部实验室使用强度校准。


## 11. Public Serving Benchmark sanity check：当前 Decode 下界偏乐观

SGLang 的 Kimi K2 公开 B200 8-GPU benchmark 给出：
- max concurrency=1：mean TPOT 18.40 ms，median 15.63 ms，P99 39.88 ms；
- max concurrency=100（实测平均 concurrency 89.6）：mean TPOT 97.23 ms，median 85.61 ms，P99 435.95 ms。

当前 10T 模型 Base 单 Agent 情景，Decode GPU-hours=1.478 GPU·h，部署候选为 192 张 H100；模型对应的 Decode wall time 为：

`1.478 × 3600 / 192 = 27.72 seconds`

`27.72 / 46,080 output tokens ≈ 0.602 ms/output token`

0.602 ms/token 比 Kimi K2 单并发实测 mean TPOT 18.40 ms 快约 30.6 倍。两者模型规模、硬件和部署拓扑不同，不能直接当成同口径性能对比；但这个差异是明确的模型风险信号：当前 L1 Roofline 只计入 60 层 × 10 μs 的 collective latency，并没有覆盖完整逐 Token 的 kernel launch、调度、专家 dispatch/combine、同步和运行时开销。当前 decode 公式可能严重低估单序列实际 TPOT。

此外，当前 decode batch 敏感性只减少 collective rounds 和共享权重流量，没有完整建模 Continuous Batching 下的队列、batch formation、step-time 增长和 per-sequence latency。SGLang 的 concurrency 100 结果中，TPOT 比 concurrency 1 明显更高，说明吞吐改善和单请求延迟不是同一指标。

**因此，当前 0.469 / 2.212 / 12.642 GPU·h/day 只能称为当前 L1-L3 Roofline 参数下的条件性模型输出，不是经过实测校准的 GPU-hours 预测区间，也不能作为采购承诺。** 在将其升级为可信预测前，需要为目标模型和目标 GPU 建立实测的 Prefill throughput、Decode TPOT/throughput、EP dispatch/combine latency、HBM bandwidth 与 batch-size profile。
