# 40T 单人单主 Agent 输入审计 · 2026-11-20

计量对象是一个主 Agent 的直接模型调用。计入重复发送的历史上下文、计入 completion 的推理 Token；排除子 Agent、工具执行、实验、训练与评测。GPU·h 是模型服务时各设备分摊工作的总和。副本全天保留另按 24 × 副本卡数计。本文先登记原独立预测的输入、可识别程度和采用规则，再据此复算 40T。

## 来源、观察窗与统计分母

|证据|公开观察与原文位置|可以推导或排除的用途|
|---|---|---|
|O9 · OpenAI，9 月 6 日，Coding agents are reshaping daily work|8 月中旬，研究组织合计每人类工作日 3.1 个 Agent 工作日，每日推理按 API 牌价计，研究员中位数超过 $600，P90 超过 $7,000。|3.1 × 8 = 24.8 累计 Agent 小时/人类工作日，可包含重叠会话。缺少每个主 Agent 的请求时间线。 [原文](https://openai.com/index/research-acceleration-view-inside-openai/)|
|O11 · OpenAI，11 月 18 日，Agent workdays / Concurrent agent use / Internal agent usage|截至 10 月中旬，平均 5.7 个八小时 Agent 日/研究员日，通常只覆盖交互使用。超过 2/3 的纳入者日峰值并发平均至少 4，超过 10% 至少 16，包含子 Agent。9→10 月研究员日牌价中位数 $1,500→2,400，P90 $11,000→23,000。|5.7 × 8 = 45.6 Agent 小时/人日；按完整日历日摊平约 1.9 个同时工作 Agent。这个积分均值和日峰分位不能给出单主 Agent 的推理占空比。9 月报告的工作日分母与此处日历日应分别标注。 [原文](https://openai.com/index/research-acceleration-jagged-frontier/)|
|A26 · Anthropic，9 月 17 日，Measuring AI-led R&D / oversight / compute allocation 及方法附录|7 月逐部门逐周抽 20% 人员，约 15,000 项工作汇成 378 个叶类。固定篮子、按员工任务加权，8 月 AL4 为 26%。最常用研发工程平台约 30,000 个同时工作 Agent。7 月 13–20 日近万次训练评测运行，约 14% 按算力偏向大作业抽样。安全工作占全部 AI 研发算力约 6%，占 AI 驱动研发算力约 12%。|分母依次为加权任务、平台 Agent、作业及两种不同口径的组织算力。推理活跃序列 ≤ 同时工作 Agent 仅在每个 Agent 最多一条在途请求的附加条件下成立。缺少每 Agent 请求数与共享服务占用。 [原文](https://www.anthropic.com/institute/measuring-pace-of-ai-development)|
|T · SWE-bench Verified 公开轨迹|mini v2.0.0，Kimi K2.5 high；一个仓库 issue 的一次 Agent 运行。使用逐条 assistant 消息 extra.response.usage。500 条中按完整 S3 key 的 SHA256 升序取前 40，不按成功与否筛选。逐行 URL、原始文件 SHA256 和调用覆盖见 trace_sample.csv。|只取 metered_calls = reported_calls、缓存字段齐全的 23 条用于成组建模。其余 17 条保留作缺失审计；缺失与长轨迹可能相关，筛后分位有偏。一次请求累计 prompt 包含重复上下文，cached_tokens 是其子集；completion 包含供应商计入的 reasoning，不重复加。 [公开目录](https://swe-bench-submissions.s3.amazonaws.com/?list-type=2&prefix=bash-only/20260217_mini-v2.0.0_kimi-k2-5-high/trajs/)|
|T0 · SWE-bench 不同版本交叉检查|mini v1.7.0 + Kimi K2 Instruct，Verified 单次尝试，元数据报告平均 37.52 次调用/题、43.8% resolved；有逐题 calls/cost，一条已核轨迹仅有对话文本。|用来对照调用量量级。不得把工具动作逐个算作 LLM 调用，也不从文本长度猜 Token。 [提交元数据](https://github.com/SWE-bench/experiments/tree/main/evaluation/verified/20250807_mini-v1.7.0_kimi-k2-instruct)|
|K · Kimi K2 Instruct 官方配置|单个公开 checkpoint 的结构、量化和上下文窗口。384 个 routed experts，Top-8，最大位置 131,072。|模板可核查；迁移到 40T 是结构外推，K2.5 的计量轨迹与 K2 结构分别使用。 [模型配置](https://huggingface.co/moonshotai/Kimi-K2-Instruct/blob/main/config.json)|
|N · NVIDIA 设备规格|HGX Table 1/2 的每卡容量、带宽、互联；H100 稀疏峰值，HGX 与 GB300 NVL72 的整机聚合峰值，不能混用每卡/整机、稀疏/稠密。|用于算力、流量及容量下界。 [HGX 参考架构](https://docs.nvidia.com/enterprise-reference-architectures/hgx-ai-factory-h100-h200-b200/latest/components.html) · [H100](https://www.nvidia.com/en-us/data-center/h100/) · [HGX](https://www.nvidia.com/en-us/data-center/hgx/) · [GB300](https://www.nvidia.com/en-us/data-center/gb300-nvl72/)|
|M · MLPerf Inference v5.1，NVIDIA Closed，DeepSeek-R1|8 × B200 SXM 180 GB，TensorRT，Offline，run_1 VALID，8.93431 samples/s、33,379 tokens/s，整机聚合。|同一 benchmark 工况约 4,172 tokens/s/GPU。它证明吞吐测量必须指定模型、并发、软硬件与场景；缺少同请求长度和同 40T 拓扑的测量，不能作为单会话解码速率或反推本模型三种效率。 [实测日志](https://github.com/mlcommons/inference_results_v5.1/blob/main/closed/NVIDIA/results/B200-SXM-180GBx8_TRT/deepseek-r1/Offline/performance/run_1/mlperf_log_summary.txt)|

## 从公开量到工作负载

对主 Agent 的调用 j 取 I=Σprompt_j、O=Σcompletion_j、C=Σcached_j，未缓存输入 U=I−C；cache=C/I。只计一次 completion。取 L=max(prompt_j+completion_j) 作为峰值请求长度；把 L 用作整次任务的代表上下文是偏保守的外推。源服务计费缓存与目标服务可用 KV 的差异单独做无缓存压力测试。

23 个完整任务按 nearest rank（排序后第 ceil(qn) 个）求边际 P10/P50/P90：

|观测量/题|P10|P50|P90|
|---|---:|---:|---:|
|模型调用数|28|46|81|
|输入 Token|213,797|678,015|1,492,152|
|输出 Token|2,990|7,535|15,558|
|缓存输入占比|76.6%|92.2%|95.7%|
|峰值请求 Token|12,412|22,505|37,811|

情景按 completion 分位选**整条**轨迹，保留输入、输出、缓存和上下文之间的相关性。表中各列的边际分位不应拼成一条轨迹。样本观察是公开计量；将同样 Token 序列映射到 40T 的 tokenizer、任务质量、缓存与路由是跨模型外推。样本仅覆盖公开代码修复，不能建立前沿研究员真实人日用量的经验上下界。

对已知价目 p、同一计费窗、同一账户、同一模型、可比计费类别，API 列价金额 V=Σ p_i T_i / 10⁶。若全部 Token 均以正价计费且 p_min、p_max 已知，总量满足 10⁶V/p_max ≤ ΣT_i ≤ 10⁶V/p_min。研究员级金额欠缺模型和缓存结构、调用归属及折扣，无法用中位金额除以平均 Agent 时长得到单 Agent tokens/h；也不能从 V 直接反演物理 GPU·h 或成本。对于推理占空比，若有按 Agent 的 wall-time 和请求区间，d=请求区间并集时长/观测时长；缺少它们只能给出 0≤d≤1。平台并发和 AL4 任务份额不能缩窄此界。

## 逐项台账

下表中的“观”指原对象的公开观察或规格，“推”指可重算的算术，“迁”指跨对象外推，“景”指未来或压力情景。表中同一行并列的字段共享所列来源和判断。数值范围若仅来自历史配置，不代表公开实测范围。

|输入及单位|原独立预测默认 → 40T 采用值|证据、范围判断和检验|
|---|---|---|
|online_hours、inference_duty，单 Agent 日在线时长与其中推理活跃比例|2026 保/基/激 10/12/14 h，0.20/.24/.28；2030 为 14/18/22 h、.23/.30/.45。各年完整输入见同目录配置。|景。单 Agent 自然日 0–24h、占比 0–1；原值可行，O9/O11/A26 无法验证区间位置。只以历史联合变化作增长倍率。|
|input/output_tokens_per_active_hour，活跃小时输入/输出量|2026 为 90k/6k、110k/8k、140k/12k；2030 为 120k/9k、200k/18k、320k/36k。|景。T 的单位为每题，缺少同口径活跃时长，无法验证绝对速率。去除原绝对 Token 强度，以 T 校准起点。|
|2026 任务当量/日与未来增长|原预测隐含于上述乘积；新基准单位为每个主 Agent 日处理 1 个选中 issue 当量。|景。1 是归一单位，非人日实测。D_y=(h·d·(r_in+r_out))_y / 同情景 2026 值。一个当量保持整条轨迹的输入/输出比。给定实际日任务量时线性缩放结果。无法给无条件的人日区间。|
|调用次数、输入/输出、缓存、峰值长度、同时序列|原配置无 calls、cache、峰值序列显式值；历史 context 为 16,384–262,144。新方案使用整条 T 记录；顺序单 Agent，1 条序列。|观→推→迁。T 支持每题边际范围和配对观察；缓存传递以 0 命中为压力端。旧 262,144 超过 K 的 131,072 窗口，不能直接由模板支持。峰值不等于平均长度。|
|目标总参数、专家数、非 routed 预算|40T；15,131；10,058,752,000 个非 routed 非 router 参数。|景、推、景。40T 为题设，预算沿用仓库假设，无实测，专家数取最接近目标的整数；全精度身份见下。|
|hidden、层数、首层 dense、MoE 层数、专家宽、矩阵数、shared experts|7168，61，1，60，2048，3，1|K 观→迁；60=61−1，3 是 gated MLP 的 gate/up/down 权重。shared expert 属于 non-routed 预算，不另加。|
|Top-K、attention 形式/heads、QK 无 RoPE/有 RoPE、V 维度、KV rank|4/8/16，MLA、64、128/64、128、512|K 支持 Top-8 及 MLA 维度，4/16 为激活量压力档；未证明三档的任务质量相同。|
|权重格式/每参数字节、scale metadata|2026–27 FP8/1，2028/30 FP4/0.5，额外 3%|K 的 FP8 是原 checkpoint 格式；字节按位宽/8 推得。FP4、固定 3% 是景，含量化尺度和布局的不确定性，未验证 40T 精度/吞吐。|
|KV 格式/每元素字节与组成|2026–27 BF16/2，2028/30 FP8/1；每层 latent rank+RoPE dim|K 模板、格式算术→迁。是否转换 KV 为 FP8 属情景，无法由模型权重格式推出。|
|硬件 SKU、单卡 HBM GB / 带宽 TB/s / NVLink TB/s|H100 80/3.35/.9；H200 141/4.8/.9；B200 180/8/1.8；GB300 279/8/1.8|N 规格。GB300 每卡带宽 576/72=8，NVLink 130/72≈1.8，容量约 20 TB/72；279 GB 沿用近似口径，整机舍入值不能验证精确单卡可用字节。各年 SKU 属景。|
|单卡 FP8 稠密 TFLOP/s、跨节点 GB/s|1979/1979/4500/5000；50/50/100/100|N 峰值折算，按稀疏加速 2 倍近似：H100 3958/2，B200 72,000/8/2，GB300 720,000/72/2；H200 沿用 Hopper 档。跨节点带宽是按 NIC 配比的部署假设；交换与拥塞会降低实效。使用独立配置值覆盖共享表。|
|compute/HBM/communication efficiency|2026→27→28→30：.30/.34/.38/.45、.70/.73/.76/.80、.50/.53/.57/.62|景，(0,1] 为物理域；M 未测未来 40T。点值仅供情景，逐项扫动，瓶颈切换会改变斜率。|
|TP、硬件 EP、batch、专家权重复用|TP=4；上述四款 EP=48/32/24/18；prefill 64 Token、decode 1 序列；routed reuse=1|景。正整数与容量取整约束；decode 1 对应顺序流，真实多租户 batch 未知。M 的离线大批量不能验证这些数。|
|跨节点流量比例、all-to-all 延迟、传输元素大小|.5，10 µs/MoE 层/轮，2 字节/元素，dispatch+combine 两次|景，比例只能物理约束在 [0,1]。互联峰值无法识别实际 EP 路径、拥塞或逐层时延。扫描延迟、流量比及 batch。|
|HBM 可用比例、运行时预留、目标利用率|.85，权重的 .10，池目标 .70|景。应以目标引擎显存和队列遥测替换。前两项影响容量取整；利用率用于副本数，对本指标的设备工作量无直接乘数。|
|单价，USD/GPU·h|原按 H100 $4.09 统一，另列 B200 $6.79|历史配置引用 Lambda 按设备的租赁价。本轮未核实相同日期、地区、期限的这两档报价；不用于校准 GPU·h 或报告实际成本。[报价入口](https://lambda.ai/pricing)|

## 结构、设备与不确定性传播

设 E=3×7168×2048×60，R=7168×60，B=10,058,752,000。专家数 n=round((40×10¹²−B)/(E+R))=15,131；总参数 B+n(E+R)=39,998,895,001,600；激活 B+nR+K·E，Top-4/8/16 为 27.14/37.71/58.84B。权重容量为 P_total×字节×1.03；KV 峰值为 61×(512+64)×KV字节×上下文×同时序列。容量卡数先除以单卡可用容量，再向上取整到 TP×EP。这里估计容量下界，未验证该专家数在特定引擎的切分可部署性。

预填充使用未缓存输入，解码使用全部输出。两阶段分别取计算、HBM、通信时间的最大值，按副本卡数乘秒数/3600 得 GPU·h，再按日任务当量放大。预算为设备工作量而非端到端时延；聚合日 Token 后再对 batch 取整与逐任务取整有差异，本分析逐任务计再乘当量。峰值上下文替代逐请求上下文、Token 化差异、共享 batch 的分摊、路由热点、重试和目标服务的 KV 命中均可能改变结果。

可识别的是代码修复样本的条件范围，以及模板与硬件规格。无法从这些材料识别每位研究员每天完成的任务量、40T 质量相当时的重试次数或各参数联合概率。分别报告固定硬件/结构下整条轨迹的经验分位、三条业务与硬件联合路径、单因素压力；区间不附概率或置信水平。下一次校准应按主 Agent ID 关联模型调用、缓存读写、实际 batch、token 时间戳和设备占用，单列工具等待、子 Agent 与重试。

## 默认值的量级复核与适用边界

原配置按 h·d·r 推得 2026 保守/基准/激进的每日输入 180,000 / 316,800 / 548,800、输出 12,000 / 23,040 / 47,040。如果强行假设一日一题，原基准、激进输出均超过 23 条完整轨迹每题的样本 P90（15,558）；若每天多题则完全可能。缺少真实任务率，无法凭这项比较否定原值，也无法验证该值代表研究员平均日。新三档的起点均为实际观测的输入/输出配对；2030 相对起点的 2.16/3.46/5.92 倍只来自旧配置的情景变化。

K2 的窗口限制与本次三条轨迹的峰值相容。预测按目标 40T 复用 T 中 provider 报告的 prompt 缓存比；K2.5、其服务商与未来目标服务的前缀共享、缓存容量、驱逐及计费差异均未知。冷缓存给出同输入、同模型服务条件下 prefill 工作量的上端。目标吞吐需在同引擎用相同输入/输出长度分布、batch 和 TP×EP 构型压测；设备峰值和跨模型 MLPerf 结果只能做可行性检查。

对历史配置中未显式声明的独立输入，复算以仓库 40T JSON 为唯一结构与 serving 默认来源。硬件规格来自共享 GPU 表，独立预测只覆盖其 FP8 稠密算力项。配置的 historical_context 字段留作审计，活跃预测使用日志的 peak_request。原 3% scale metadata、10% runtime reserve、85% usable HBM 没有目标引擎实测；应分别以 checkpoint 存储量、空载/峰值显存和可分配设备容量校准。逐项压力端点与相对影响见 sensitivity.csv；不同扰动幅度的百分比不能解读为全局方差贡献。
