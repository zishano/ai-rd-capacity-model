# 单人单 Agent 推理模型：输入、计算过程与输出

> 计算边界：1 名研究员 → 1 个主 Agent → 1 项研发任务。只核算主 Agent 直接调用 LLM 的推理资源；工具执行、CPU 沙箱、训练/评测作业，以及子 Agent 的资源另行核算。

## 一、输入什么

配置文件：[`config/agent_inference.json`](../config/agent_inference.json)。

### A. 任务行为参数

| 参数 | 默认示例 | 单位 | 说明 |
|---|---:|---|---|
| 模型调用次数 | 100 | 次/任务 | 主 Agent 完成任务期间调用 LLM 的次数；不等于 Agent 数量 |
| 平均输入 Token | 10,000 | Token/次 | 每次请求实际发送的完整输入，包含携带的历史上下文 |
| 平均输出 Token | 2,000 | Token/次 | 每次模型响应生成的 Token |
| 输入前缀缓存命中率 | 0% | 比例 | 输入 Token 中可复用的比例；用于减少需要重新 Prefill 的 Token |
| 峰值上下文长度 | 10,000 | Token | 用于估算单条序列 KV Cache 的峰值占用 |
| 峰值并发序列 | 1 | 条 | 同时驻留 KV Cache 的序列数；顺序单 Agent 基线设为 1 |

### B. 模型结构参数

| 参数 | 默认示例 | 单位 | 说明 |
|---|---:|---|---|
| 模型规模 | 70B | 参数量 | 代表性模型，不是实测指定模型 |
| 权重精度 | BF16 | Byte/参数 | 每参数 2 Byte |
| Transformer 层数 | 80 | 层 | 需替换为真实模型配置 |
| KV Heads | 8 | 个 | 需替换为真实模型配置 |
| Head Dimension | 128 | 维 | 需替换为真实模型配置 |

### C. 推理硬件与服务参数

| 参数 | 默认示例 | 单位 | 说明 |
|---|---:|---|---|
| GPU | H100 80GB | — | 示例硬件 |
| 每个服务副本 GPU 数 | 4 | 张 | 示例 TP/部署规模 |
| 可用 HBM 比例 | 85% | 比例 | 为权重、KV 及其他运行时资源保留空间的简化假设 |
| Prefill 吞吐 | 10,000 | Token/s/完整副本 | 需用目标模型、引擎、硬件和并发压测 |
| Decode 吞吐 | 500 | Token/s/完整副本 | 同上 |
| GPU 小时价格 | 4.59 | USD/GPU·h | 示例价格输入，需按实际采购报价更新 |

**默认参数证据等级：** 调用次数、Token、模型结构组合、吞吐、TP、可用 HBM 比例均为 C 类建模示例；BF16 每元素 2 Byte 属于格式规格；H100 产品规格可参考 [NVIDIA H100](https://www.nvidia.com/en-us/data-center/h100/)；性能测试方法可参考 [MLPerf Inference](https://mlcommons.org/benchmarks/inference-datacenter/)。这些来源不证明 10,000/500 Token/s 是 H100 上 70B 模型的通用性能。

## 二、怎么算

### 1. Token 总量

设调用次数为 (N_c)，平均每次输入、输出分别为 (T_{in})、(T_{out})：

[
T_{input}=N_c T_{in},\qquad T_{output}=N_c T_{out}
]

默认示例：

- 输入：(100 	imes 10,000=1,000,000) Token
- 输出：(100 	imes 2,000=200,000) Token
- 合计：1,200,000 Token

注意：若上下文逐轮累积，平均输入 Token 必须统计每次请求实际发送的完整 prompt，不能把初始 prompt 长度重复代替。

### 2. Prefill 与 Decode 时间

令输入缓存命中率为 (h)，完整服务副本的 Prefill / Decode 有效吞吐分别为 (R_p)、(R_d)：

[
t_{prefill}=rac{T_{input}(1-h)}{R_p}
]

[
t_{decode}=rac{T_{output}}{R_d}
]

默认示例，(h=0)、(R_p=10,000)、(R_d=500)：

- Prefill：(1,000,000/10,000=100) 秒
- Decode：(200,000/500=400) 秒
- 串行模型服务时间：500 秒

吞吐口径是完整四卡服务副本，而不是单 GPU。应使用同模型、精度、推理引擎、上下文长度、并发和硬件的实测 profile。

### 3. GPU-hours

若每个服务副本使用 (G) 张 GPU，且上述请求按串行服务时间估算：

[
GPUh_{task}=rac{G(t_{prefill}+t_{decode})}{3600}
]

默认示例：

[
GPUh=rac{4	imes500}{3600}=0.556 GPUcdot h
]

这是模型实际服务工作量估算，不含工具等待、排队、Agent 思考间隔、失败重试和并行调度。多 Agent 共享批处理副本时，应按服务系统实际设备时间分摊，避免重复计算同一副本的时间。

### 4. HBM：权重与 KV Cache

权重显存简化估算：

[
M_{weights}=P	imes b
]

70B BF16 的总权重数据约 140 GB；四卡均匀张量并行时约 35 GB/GPU。

标准 Transformer KV Cache：

[
M_{KV}=2L H_{KV}D_h S B b
]

其中 (L) 为层数、(H_{KV}) 为 KV Heads、(D_h) 为 Head Dimension、(S) 为上下文长度、(B) 为同时驻留序列数、(b) 为每元素字节数。

默认示例：

[
M_{KV}=2	imes80	imes8	imes128	imes10,000	imes1	imes2
=3.2768 GB
]

若 KV 在四个 TP Rank 间均匀分片，则约 0.8192 GB/GPU。权重与 KV 合计下界约 35.82 GB/GPU。

这是权重+KV 的下界，不包含激活、CUDA Graph、通信 Buffer、临时 Workspace、碎片及推理引擎开销。真实模型可能采用不同 KV 布局、GQA/MQA、滑动窗口、量化或非标准 Attention，必须读取实际架构配置并用运行时显存 Profile 校准。

### 5. 直接推理成本

[
Cost_{task}=GPUh_{task}	imes Price_{GPUh}
]

默认示例：

[
0.556	imes4.59approx2.55 USD
]

这是按示例 GPU 小时价格估算的自托管 GPU 成本，不等于 OpenAI / Anthropic API Token 账单。API 价格应按输入、输出和缓存 Token 分别计费。

## 三、输出什么

默认示例运行后输出：

| 输出 | 示例值 | 含义 |
|---|---:|---|
| Input Tokens | 1,000,000 | 任务累计输入量 |
| Output Tokens | 200,000 | 任务累计输出量 |
| Prefill 服务时间 | 100 秒 | 未命中缓存的输入处理估算 |
| Decode 服务时间 | 400 秒 | 输出生成估算 |
| 串行模型服务时间 | 500 秒 | 不含工具等待和排队 |
| GPU-hours | 0.556 GPU·h | 四卡副本的直接推理工作量 |
| 权重显存 | 35 GB/GPU | 四卡均分的权重估算 |
| KV Cache | 0.819 GB/GPU | 四卡均分的单序列 KV 估算 |
| 权重 + KV | 35.82 GB/GPU | 显存需求下界 |
| 直接推理成本 | 约 2.55 USD | 按示例 GPU 小时价格 |

模型暂未输出可靠的 TTFT / TPOT，因为缺少调度排队、首 Token 延迟、逐 Token 时间和实际批处理观测；也不把任务墙钟时间等同于 GPU 忙碌时间。

## 四、从单任务扩展到单人和团队

若每人每天完成 (n_{task}) 项同类任务：

[
GPUh_{person/day}=n_{task}	imes GPUh_{task}
]

若团队有 (N_{researchers}) 名研究员：

[
GPUh_{team/day}=N_{researchers}	imes n_{task}	imes GPUh_{task}
]

这仍是 GPU 工作量，不直接等于采购卡数。采购容量还要考虑任务到达峰值、请求并发、连续批处理效率、SLO、可用率和共享比例。主 Agent 启动的子 Agent 应另行计数；其训练、评测和数据生成作业归入总模型的派生实验资源池，不能混入直接推理账。

## 五、如何校准

1. **Agent Trace：** 统计每任务调用数、每次实际 input/output tokens、上下文长度、cache-read tokens、并发序列和模型路由。
2. **推理 Profile：** 对指定模型、精度、GPU 数、推理引擎、上下文和并发，测 Prefill / Decode 吞吐、TTFT、TPOT、显存曲线。
3. **调度日志：** 获取实际 GPU 分配时间；API 响应时延不能直接当成 GPU 忙碌时间。
4. **模型配置：** 读取真实层数、KV Heads、Head Dimension、权重精度和 TP/KV 分片方式。
5. **成本数据：** 使用实际采购报价或 API 账单，分别更新 GPU 小时价格和 Token 单价。

## 六、运行

```bash
python agent_inference.py
```

指定配置与输出路径：

```bash
python agent_inference.py --config config/agent_inference.json --output modelout/agent_inference.json
```

默认配置、计算程序和自动化测试分别见 [config/agent_inference.json](../config/agent_inference.json)、[agent_inference.py](../agent_inference.py)、[tests/test_agent_inference.py](../tests/test_agent_inference.py)。
