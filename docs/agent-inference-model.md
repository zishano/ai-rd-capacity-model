# 单人单 Agent 推理子模型

本模块是 AI Research Capacity Model 的独立子模型，只计算一个主 Agent 为完成一次研发任务而直接调用 LLM 的资源。它不把工具执行、CPU 沙箱、训练/评测作业或 Agent 派生的子 Agent 资源混入直接推理账。

## 1. 计算边界

统计对象：**1 名研究员 → 1 个主 Agent → 1 项研发任务**。主 Agent 可以进行多轮模型调用；调用次数不是 Agent 数量。若主 Agent 启动子 Agent，应把子 Agent 作为额外 Agent 实例建模，不能把它们隐含在模型调用次数中。

## 2. 输入参数与来源等级

配置入口为 [config/agent_inference.json](../config/agent_inference.json)。默认值是一组可复算的示例，不是某家公司的内部测量。

| 参数 | 默认值 | 单位 | 依据/选择理由 | 证据等级 |
|---|---:|---|---|---|
| 模型调用次数 | 100 | 次/任务 | 用户给出的示例任务假设；真实值应由 Agent trace 统计 | C |
| 平均输入 Token | 10,000 | Token/次 | 用户给出的示例假设；应统计每次 API 请求实际发送的 prompt token，含携带的历史上下文 | C |
| 平均输出 Token | 2,000 | Token/次 | 用户给出的示例假设；应统计每次 API 响应生成 token | C |
| 输入前缀缓存命中率 | 0% | 比例 | 为避免默认假设缓存收益，先按无缓存节省计算；生产环境用服务端 cache-read / cache-hit token 统计替换 | C |
| 峰值上下文长度 | 10,000 | Token | 与示例平均输入量对齐的简化值；真实任务应取每次请求上下文长度分布的 P95/P99 | C |
| 峰值并发序列 | 1 | 条 | 单主 Agent 顺序调用的基线；并行工具/子 Agent 另建实例 | C |
| 模型规模 | 70B | 参数 | 代表性模型选择，不声称实际使用该模型 | C |
| 权重精度 | BF16 | Byte/参数 | BF16 每参数 2 bytes 的格式定义 | spec |
| Transformer 层数 | 80 | 层 | 示例 70B 架构参数；必须替换为目标模型配置 | C |
| KV Heads | 8 | 个 | 示例 GQA 架构参数；必须替换为目标模型配置 | C |
| Head Dimension | 128 | 维 | 示例架构参数；必须替换为目标模型配置 | C |
| GPU | H100 80GB | GPU | 作为硬件示例；实际 SKU / SXM / PCIe 需明确 | spec |
| 每副本 GPU 数 | 4 | 张 | 示例 TP/部署规格，不是模型推导值 | C |
| Prefill 吞吐 | 10,000 | Token/s/副本 | 示例服务吞吐假设；应以目标推理引擎的 profile 在相同 prompt 长度和并发下测量 | C |
| Decode 吞吐 | 500 | Token/s/副本 | 示例服务吞吐假设；应以相同模型、硬件、量化、上下文、并发压测 | C |
| 可用 HBM 比例 | 85% | 比例 | 为权重和 KV 预留显存空间的工程假设；真实值受引擎与 buffer 配置影响 | C |
| GPU 小时价格 | 4.59 | USD/GPU·h | 仅为配置示例的供应商价格输入；应按采购地区、实例类型和时间更新 | C |

## 3. 核心计算

### 3.1 Token 总量

设一次任务包含 (N_c) 次模型调用，平均每次输入和输出分别为 (T_{in})、(T_{out})：

[
T_{input}=N_c T_{in},qquad T_{output}=N_c T_{out}
]

默认示例：

- 输入：(100 	imes 10,000 = 1,000,000) Token
- 输出：(100 	imes 2,000 = 200,000) Token
- 合计：1,200,000 Token

若上下文逐轮累积，(T_{in}) 必须是每次调用实际发送的完整输入平均值，不能只统计初始用户 prompt。

### 3.2 Prefill / Decode 服务时间

设输入缓存命中率为 (h)，副本级实测 Prefill / Decode 吞吐分别为 (R_p)、(R_d)：

[
t_{prefill}=rac{T_{input}(1-h)}{R_p}
]

[
t_{decode}=rac{T_{output}}{R_d}
]

吞吐的单位是 **Token/s/完整服务副本**，不是每张 GPU 的吞吐。它必须来自相同模型、精度、GPU 数、引擎、上下文和并发条件下的实测 profile。不能用 GPU 理论峰值 FLOPS 直接替代。

### 3.3 GPU-hours

若一个副本包含 (G) 张 GPU，且任务调用顺序执行：

[
GPUh_{task}=rac{G(t_{prefill}+t_{decode})}{3600}
]

默认示例：输入 100 万 Token、输出 20 万 Token；假设 Prefill 10,000 Token/s、Decode 500 Token/s：

- Prefill：100 秒
- Decode：400 秒
- 服务时间：500 秒
- 4 张 GPU 的直接推理工作量：(4 	imes 500 / 3600 = 0.556) GPU·h

该估算不含工具等待、排队、Agent 思考间隔、失败重试和并行请求。若多轮调用与工具执行交错，任务墙钟时间会更长，但 GPU-hours 只累计模型实际服务时间。批处理共享 GPU 时，应按服务系统实际分摊的设备时间核算，避免把同一副本时间重复计入每个 Agent。

## 4. HBM 估算

权重显存的简化下界：

[
M_{weights}=P	imes b
]

70B BF16 约为 140 GB 总权重数据；四卡张量并行下约 35 GB/GPU（忽略额外副本与布局差异）。

标准 Transformer KV Cache：

[
M_{KV}=2L H_{KV}D_h S B b
]

其中 (L) 为层数、(H_{KV}) 为 KV heads、(D_h) 为 head dimension、(S) 为上下文长度、(B) 为并发序列、(b) 为每元素字节数。若 KV 在 TP ranks 间均匀分片，单卡 KV 近似除以 TP；若模型引擎复制 KV，则不能除以 TP。

默认示例：80 层、8 KV heads、128 head dimension、BF16、10k context、1 条序列，总 KV 约 3.28 GB；四卡均匀分片约 0.82 GB/GPU。加上约 35 GB/GPU 权重，权重+KV 的下界约 35.82 GB/GPU。

这只是显存下界，不包含 activation、CUDA graph、通信 buffer、临时 workspace、碎片和引擎预留。必须使用实际模型架构和运行时显存 profile 校准。

## 5. 成本

[
Cost_{task}=GPUh_{task}	imes Price_{GPUh}
]

默认价格 4.59 USD/GPU·h 只是可更新的报价输入，不代表实际采购价或 API token 价格。若采用 API 服务，应单独按输入、输出及缓存 Token 的实际计价规则计算，不能把云 GPU 成本和 API 账单混为一谈。

## 6. 从单 Agent 扩展到组织

单人每日：

[
GPUh_{person/day}=N_{tasks/day}	imes GPUh_{task}
]

团队直接推理工作量：

[
GPUh_{team/day}=N_{researchers}	imes N_{tasks/person/day}	imes GPUh_{task}
]

这仍是工作量，不是采购 GPU 数。采购容量还需要峰值并发、批处理效率、SLO、可用率和资源共享率。子 Agent 应单独计数；Agent 发起的训练、评测和数据生成作业归入“派生实验资源”，不要重复计入直接推理。

## 7. 校准顺序

1. 从 Agent trace 统计每任务模型调用数、每次 input/output tokens、上下文长度、cache-read tokens。
2. 从推理引擎 profile 获取相同模型/硬件/精度/并发下的 Prefill 与 Decode 吞吐、TTFT、TPOT、显存曲线。
3. 从 GPU 调度器获取实际 GPU 分配时间，避免将 API 响应延迟等同 GPU 忙碌时间。
4. 从模型配置文件读取真实层数、KV heads、head dimension、权重精度与 TP 布局。
5. 用供应商账单或内部成本核算更新 GPU 小时单价。

## 8. 与总容量模型的接口

本模块输出每项任务的输入/输出 Token、Prefill/Decode 服务时间、GPU·h、权重与 KV 显存下界、直接推理成本。总模型再乘以每日任务量和研究员数量，并加入峰值并发与共享调度。训练/评测 GPU-hours、CPU 沙箱、RAM、SSD、数据存储和网络仍由总模型其他模块独立计算。
