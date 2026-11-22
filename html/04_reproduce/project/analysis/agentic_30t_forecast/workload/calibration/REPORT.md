# AI 研发 Agent 任务发起率与单任务 Token 负载的公开证据及代理建模

截至 2026-11-21。预测单位为**一名研究员的一个自然日**，覆盖源报告纳入的交互式研发活动。OpenAI 公布了任务发起率的绝对估计。2026-10-18 的 28 日窗口约为 **26.3 项/研究员日**。公开数据还允许估计同期的**输出 Token 总量与任务发起数之比**。要估计单项任务的输入、缓存、请求和上下文，需要可逐项连接的轨迹。下文只将编码轨迹用于研发与基础设施代码这一类任务。

## 1. OpenAI 原始公开数据

| 核对的原图 | 原文统计单位及取数方法 | 可进入第一层的量 |
|---|---|---|
| 11 月 *Estimated AI R&D tasks per researcher* | 对研究部门交互式 coding-agent 上下文窗口抽样，由 GPT-6 Astra Codex 提取在窗口内开始的用户发起任务。去除评分、无对应研发标签及已知自动化。按账号日发起数在非零账号 P95 截尾，用当日窗口抽样率和活跃研发名单人数还原。图为 28 日 trailing average。| 3/1–10/18 共 232 个图值、18 个任务类别。类别保留到 0.1，10/18 合计约 26.3，其中研究与基础设施代码 5.7、技术协助与评审 10.5。七月名单口径有变。[原图及方法](https://openai.com/index/research-acceleration-jagged-frontier/#figure-research-task-starts) |
| 9 月 *Researchers are using coding agents in new ways* | 从活跃研究员工内部 coding sessions 随机抽取 2%，外推分类的输出 Token；在当日非零样本用户 P95 截尾单人输出，按原份额缩减各类别。图为每研究员工每天的绝对输出，14 日 trailing average。| 1/20–8/15 共 208 日、18 类。8/15 各类合计约 722,833 输出 Token/研究员日。已核对日分类和与原图总量。[原图](https://openai.com/index/research-acceleration-view-inside-openai/#chart-4QLdZ4iw0n4L9rYGTvteZK) · [冻结图值](observed_output_tokens.csv) |
| 11 月 *Agent workdays across research* 与 *Agent concurrency across research* | 工作日为八小时累计合格 Agent 时间，父子分别计、含 auto-review；排除包括 codex exec 在内的部分程序化流量、已知评测等，同一 turn 中相邻服务事件间隔超过 30 分钟时跳过该间隔。并发图按有活动记录的研究者对日峰值作窗口统计、再分箱。| 10/18 时长 5.70 × 8 = 45.60 Agent 小时/研究员日。约 68.2% 落在 ≥4 的并发组、约 11.7% 在 ≥16 组。用于解释时间与并发组织，不能折算真实 session starts 或 GPU 活跃序列。[原文](https://openai.com/index/research-acceleration-jagged-frontier/) |
| 11 月已记录实验、成功率、牌价消费图 | 截至 10/18 的实验数为 2025 基准的 1.68 倍，分母为活跃实验者。任务成功按估计的人类独立完成时长分组。费用取个人过去 28 天日均 API 牌价等值的跨人中位数。| 三者均缺逐任务双向账单及任务—实验映射；可比较使用和难度变化。10/18 的 2,414.70 美元不能反推硬件成本。[原文](https://openai.com/index/research-acceleration-jagged-frontier/) |

检索围绕 task starts / researcher、experiments / active experimenter、sessions / user、tokens / task、calls / task、cached input、context、task duration 及 task outcomes。核对了两期研究报告的原图、图表方法、嵌入数据，另查 Codex 产品发布、升级报告、内部工程案例及企业研究。升级报告有员工简单轮次生成 Token 的相对变化，企业报告有节时问卷，两者均缺同任务级配对的输入和输出。[Codex 发布](https://openai.com/index/introducing-codex/) · [Codex 升级](https://openai.com/index/introducing-upgrades-to-codex/) · [内部工程案例](https://openai.com/business/learn/how-openai-uses-codex/) · [企业报告](https://openai.com/index/the-state-of-enterprise-ai-2025-report/)

## 2. 可识别范围与计数单位

| 单位 | 本模型如何计数 | 目前证据的边界 |
|---|---|---|
| Research task、initiated task | 一项符合分类的用户研发目标，在发起时记一次。若有完整日志，应按窗口起始的唯一 task ID 去重再除以研究员日数。 | 公开的是抽样、分类和截尾后的率。缺可连接的原始 ID 和逐人计数。 |
| Completed / resolved task | 完成事件或通过评测的结果；需另行定义成功标准。 | 一题可能提交补丁但测试未通过。按发起估算消耗要纳入未成功尝试。 |
| Agent session、turn、LLM call | 一个会话可有多个交互轮，一个目标可跨会话；一轮可有多次模型请求和工具动作。 | 所查 OpenAI 资料未给同口径的会话启动数/研究员日、调用/任务、任务/实验；后两者无法由实验增幅或工具链长度求出。 |
| Agent workday | 合格工作时间累计八小时，可同时来自多名 Agent。 | 一位研究员可有超过 24 个 Agent 小时；不能归给一个主 Agent。 |
| Token / task、context、duration | 同一任务所有逐调用账单的和、逐请求长度或题内最大值、任务的首末时间。 | 所查 OpenAI 图文未提供带 task ID 的平均输入/输出、缓存、上下文、实际起止时刻、调用数及其联合分布。人类估计时长、单轮时长、条件成功率均不能填入这些字段。 |

## 3. Anthropic、真实用户与公开运行数据

Anthropic 内部 Claude Code 资料给出约 20 万份记录中的最长连续工具链均值从 9.8 升至 21.2、人工交互轮数从 6.2 降至 4.1。另一项实测给出自主交互时长 P99.9 从不足 25 分钟升至超过 45 分钟。Automation Index 报告 8 月 AL4 加权任务份额 26%、最常用平台约三万个并发 Agent。前者的分母是任务篮，后者缺请求在途与研究员日分母。[内部研究](https://www.anthropic.com/research/how-ai-is-transforming-work-at-anthropic) · [自主交互](https://www.anthropic.com/research/measuring-agent-autonomy) · [自动化指标](https://www.anthropic.com/institute/measuring-pace-of-ai-development)

Mooncake FAST25 的真实生产工具/Agent 一小时轨迹有 23,608 次请求，平均每请求 8,596 输入、182 输出 Token，可核对请求量级；块哈希只说明前缀可复用，缺任务边界与实际命中。METR 时间跨度以人类完成时长衡量难度，其开发者研究记录 16 人、246 项任务。Epoch 的研发分类可对齐类别，无法提供账单。[Mooncake 数据定义](https://raw.githubusercontent.com/kvcache-ai/Mooncake/main/FAST25-release/README.md) · [METR 时间跨度](https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/) · [METR 开发者研究](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/) · [Epoch 分类](https://epoch.ai/gradient-updates/toward-an-onet-for-ai-rnd)

## 4. 候选源选择

逐来源表记录机构、日期或版本、链接、Agent 与模型、样本量、失败、重试、子 Agent、Token、缓存、时间戳、起止边界、两参数识别能力与偏差。六项评价分别为任务相似性、工作流相似性、Token 计量、时钟与边界、样本代表性、可复现性。“未验证”表示公开资料不足以支持此项；未作数值打分或跨维度平均。[候选来源评价表（18 项）](source_comparison.csv)

| 用途 | 采用或保留的候选 | 选择依据 |
|---|---|---|
| 研发任务发起率 | OpenAI 11 月 | 同机构、同研究员日分母且提取发起事件，可直接拟合公开估计。 |
| 全研发输出强度 | 两期 OpenAI 同期分类汇总 | 用共同日期和人日单位约束输出；分类器及截尾差异限制精度。 |
| 编码任务输入、缓存及联合分布 | mini-SWE-agent × Kimi K2.5 high | 该次公开提交有供应商逐调用 usage、缓存字段、时间戳和独立评测结果。选 Kimi 的依据是该提交的可审计性；目标 30T 模型的任务效率仍未知。 |
| 可替换或扩展的编码源 | Nebius SWE-agent 的 80,036 条轨迹；OpenHands 的 275 条反馈；Terminal-Bench 2.0 与 Harbor | 大样本可比较流程，但离线分词长度不等价于供应商实际账单。自愿反馈可中途提交，正负反馈也不等价于测试成败。ATIF 支持可选的逐步 usage、缓存、子 Agent、时钟；替换前须对具体提交核验这些字段，分任务类别与结果重加权。[Nebius](https://huggingface.co/datasets/nebius/SWE-agent-trajectories) · [OpenHands](https://huggingface.co/datasets/OpenHands/openhands-feedback) · [Terminal-Bench](https://www.tbench.ai/leaderboard/terminal-bench/2.0) · [ATIF](https://docs.harborframework.com/agents/atif) |

## 5. mini-SWE-agent 原始样本与选择偏差

固定提交共有 500 个不同 issue 的 500 条运行。仓库旧方法先按对象 key 的 SHA256 排序取前 40，再保留 reported API calls 与逐条 usage 一致且缓存可计量的 23 条。重取原件与 SHA256 后，23 条合计 1,172 次调用，即 **1,172 ÷ 23 = 50.95652 次/题**；平均 820,209 输入、771,171 缓存、8,614 输出、可见跨度 6.57 分钟。23 条中 15 条解决、8 条未解决；原 40 条总计报告 2,114 次、可计量 2,058 次。[原抽样表](../../../agentic_40t_forecast/trace_sample.csv) · [验证程序](../../../agentic_40t_forecast/verify_traces.py)

已对同一提交的全部 500 条原始日志逐题核对，条件为每次报告调用都有 usage、缓存及双时钟。评测 resolved 从独立结果连接，保留逐题标识、URL、原件 SHA256、调用数、输入、缓存、输出、峰值、首末时钟和状态。原始文件可按行下载；供应商未暴露的重试/内部子调用无法验证。运行内的多轮修改自然计入；公开提交不能恢复榜单之外曾经重跑或放弃的试次。[原始提交](https://github.com/SWE-bench/experiments/tree/main/evaluation/verified/20260217_mini-v2.0.0_kimi-k2-5-high) · [500 条联合记录](public_tasks.csv) · [重建脚本](verify_public_traces.py)

| 运行 | 总题数 | 通过测试 | 报告调用 | 可计量调用 | 平均可见分钟 | 平均已记录输入 / 输出 |
|---|---:|---:|---:|---:|---:|---:|
| 完整 | 252 | 180 | 12,378 | 12,378 | 6.20 | 825,124 / 8,327 |
| 不完整 | 248 | 174 | 13,211 | 12,309 | 9.61 | ≥968,208 / ≥10,448（约数） |
| 全提交 | 500 | 354 | 25,589 | 24,687 | 7.89 | ≥896,093.528 / ≥9,378.724 |

少记 902 次调用。500 题的已记录总量除以 500 给出原提交均值下限，缺失请求的非负消耗只能提高它。完整子集的均值甚至低于该下限，说明完整筛选**确实低估这次榜单提交的总体均值**。252 条用于需要完整联合向量的接口，500 条下限用于检验代表性。缺失请求没有可验证上限。500 次中 499 次以提交退出，只有 354 次通过测试。[覆盖审计](../results/calibrated/coverage.csv)

## 6. 任务发起率的识别与外推

对每个日历日，发布方的任务率可概括为 截尾后被抽到的发起数 ÷ 当日窗口抽样率 ÷ 当日活跃研发名单人数，之后做 28 日平滑。这里直接使用发布后的图值。任务类别各自随实际日期作 OLS，以 2026-03-01 为第零日。令 t₀ 为 10/18，fₖ(t) = aₖ + bₖt。定义三条可复算路径。

| 路径 | 每类 k 的预测 | 2030-11-18 总发起率 / 其中代码类 |
|---|---|---:|
| 维持末值 | 取 t₀ 的实际图值 | 26.30 / 5.70 |
| 半速线性 | max(0, fₖ(t₀) + 0.5 bₖ(t−t₀)) | 97.09 / 17.86 |
| 全速线性 | max(0, fₖ(t)) | 168.96 / 29.86 |

半速使用**拟合终点**，维持末值使用**实际终点**。两条线性路径沿用历史绝对增量的 50% 或 100%；合计为各类之和。后 28 个已发布日值的短期留出中，整体任务数趋势的 MAE 约为 1.57 项，保持训练末值约为 3.66 项。滚动窗共享底层日期，短期回测无法为四年外推赋予概率。[逐年逐类率](../results/calibrated/rates_by_category.csv) · [短期留出](../results/monthly_research_validation.csv)

旧的“工作日 × 8 ÷ 编码题跨度”只用于时长压力对照。要赋予这个商以真实发起数含义，还需同时核对时钟口径、任务历时定义、父子或共享时间去重、跨日归属、长任务/失败/重试覆盖以及样本时长的可迁移性。现有资料缺这些映射。真实会话启动率和单主 Agent 每天新接任务数继续留空。[旧时长方案](../evidence.md)

## 7. 单任务和逐请求的实测分布

对同一 issue 的每次可计量请求，分别累加 prompt、completion、cached_tokens 得 I、O、C，未缓存输入为 I−C。每次重传的历史上下文会再次计入 prompt；C 是 I 中命中供应商前缀缓存的部分。最长请求取 max(prompt + completion)，用于已有内核的上下文容量代理。可见跨度为最晚客户端接收减最早服务端创建，包含期间工具等待、网络、排队，遗漏首呼前和末呼后的工作。缺硬件执行时钟。下表按完整的 252 个 issue 等权。

| 指标/题 | 均值 | P10 | 中位数 | P90 | P95 |
|---|---:|---:|---:|---:|---:|
| 累计输入 Token | 825,124 | 158,903 | 554,900 | 1,925,863 | 2,405,273 |
| 其中缓存输入 | 774,476 | 138,752 | 498,857 | 1,804,224 | 2,295,202 |
| 未缓存输入 | 50,648 | 20,571 | 45,122 | 87,990 | 110,071 |
| 输出 Token | 8,327 | 3,196 | 7,114.5 | 14,963 | 17,277 |
| 调用次数 | 49.12 | 22 | 44 | 82 | 96 |
| 峰值请求上下文 Token | 25,302 | 12,243 | 22,721 | 42,122 | 50,223 |
| 可见跨度，分钟 | 6.20 | 2.42 | 5.11 | 11.02 | 12.72 |
| 逐题缓存输入占比 | 88.78% | 74.20% | 92.74% | 96.70% | 97.17% |

全部 12,378 次请求按调用等权的上下文 P50/P90/P95 为 **14,168 / 33,785 / 40,207**。按总输入加权的缓存率为 93.86%。完整样本中，解决/未解决组分别为 180/72 题，平均输入 648,093/1,267,701、输出 7,108/11,373。常用分位采用最近秩，中位数按中间两数平均。任务分位不能逐列拼成一项新工作负载。[全分布及成败分层](../results/calibrated/distributions.csv) · [逐请求上下文直方计数](request_context_histogram.csv)

## 8. 跨报告输出强度与编码代理公式

将 9 月发布的 14 日绝对输出均值 Y₁₄ 和 11 月发布的 28 日发起率 N₂₈ 对齐。在相同日历分母、连续日均的条件下，Y₂₈(d) = [Y₁₄(d) + Y₁₄(d−14)] ÷ 2。取共同期内从 3/1 开始的完整、不重复 28 天窗口，跳过与七月名单变化相交的窗口。分别合计各类，再取 **α = Σ窗口 Y₂₈ ÷ Σ窗口 N₂₈**。同长窗口的天数约去。这里合并的是日均率，不具备按真实逐人暴露加权所需的名单底表。

| 窗口结束日 | 发起/研究员日 | 输出 Token/研究员日 | 输出/发起比值 |
|---|---:|---:|---:|
| 03-28 | 5.8 | 133,988 | 23,101 |
| 04-25 | 8.8 | 137,881 | 15,668 |
| 05-23 | 11.8 | 225,204 | 19,085 |
| 06-20 | 11.1 | 241,786 | 21,782 |
| **合并** | | | **19,702.90** |

同窗的输出可能来自更早发起的任务；两期采样单位、分类器、人员名单和 P95 截尾变量也有差异。这是**汇总强度**，不能识别单个研发任务的平均账单、分位数或完成成本。按类计算时，18 类中只有 11 类在四窗合计有非零发起分母，舍入为零的 7 类强度留空。代码类约 22,812、技术协助与评审约 9,897。全研发总量采用合并强度，保留 18 类输出；在可用类别间选择、或给空缺类别填零，都会改变答案。[四窗原数](../results/calibrated/matched_windows.csv) · [分类强度](../results/calibrated/output_intensity.csv)

对编码子集，假设一个 3.1 类发起对应一次公开 issue 尝试，完整样本的每题权重 wᵢ = N₃.₁/252。日量为 Σwᵢ(Iᵢ,Cᵢ,Oᵢ,callsᵢ)。敏感性按输出排序取最低、最高各 63 个**整题**，在组内重新等权。单主 Agent 的串行重放使用峰值序列数 1；改变并行组织（例如将相同任务分配给 1 或 4 个执行流）时，固定任务集合的 Token 和保持相同。若并行探索带来重复执行，新增独立尝试才增加用量；真实倍数需按任务树、重试和请求 ID 计量。生产服务缓存策略不同也会改变需要预填充的输入量。

## 9. 第一层输出与 30T 接口

按 18 类发起率逐项计算的新版明细见[每研究员日的 18 类任务汇总表](../README.md)。新版按各类输出趋势独立外推后对齐到 28 日，原 11 类和 7 类分别给出 461.18 万及 10.02 万，合计 471.20 万输出 Token/研究员日。下表保留总体强度法，用于对照类别构成和任务发起率对结果的影响。

| 2030-11-18，每研究员自然日 | 维持末值 | 半速线性 | 全速线性 |
|---|---:|---:|---:|
| 公开覆盖的研发任务发起数（预测） | 26.30 | 97.09 | 168.96 |
| 全研发条件输出，万 Token（N × 19,702.90） | 51.82 | 191.29 | 332.90 |
| 低/高历史强度下的条件输出，万 Token | 41.21–60.76 | 152.12–224.28 | 264.73–390.32 |
| 其中研发与基础设施代码类发起数 | 5.70 | 17.86 | 29.86 |
| 该类按 252 题估的累计输入，万 Token | 470.32 | 1,473.29 | 2,463.73 |
| 该类其中缓存输入，万 Token | 441.45 | 1,382.86 | 2,312.50 |
| 该类输出，万 Token | 4.75 | 14.87 | 24.86 |

每人全部覆盖类别的日输入、缓存、调用数和真实会话启动数，及单主 Agent 的任务率、研究员整体的平均/峰值请求在途并发，均缺同口径计量。日表对应的输入、缓存、调用、会话及请求并发字段留空。并发有**研究者日峰分组**；无法从开放尾箱求精确均值。完整单任务分布仅提供给编码子集，1/4 并行对照也不能替代目标高峰测量。[逐年日量](../results/calibrated/researcher_day.csv) · [代码类情景](../results/calibrated/coding_sensitivity.csv)

30T 内核每次接收一题的 input_tokens、output_tokens、prefix_cache_hit_rate=C/I、context_tokens 和 peak_sequences。研究员日权重放在这五个字段之外，先逐题计算，再对可加资源按权重求和。上下文和峰值并发用于容量，不能把各题的显存峰值累加成某一时刻的集群峰值。2030 年三条路径各 252 条，输入只覆盖编码子集，不能再乘会话或并发倍率。[逐题接口 JSON](../results/calibrated/coding_inference_inputs.json) · [现有适配器](../adapter.py)

## 10. 2030 年预测的不确定性与复算

- **发起率与强度。** 全速相对末值的任务数约 6.42 倍。强度固定时，发起数改变 10%，输出同向改变 10%；固定发起率时，强度的弹性也为 1。用之前窗口的合并强度、给定下一窗的真实发起率预测输出，三个留出误差为 +47.4%、−2.4%、−13.6%。低高窗口只是敏感性端点。2025 年 11 月至 2026 年 11 月没有连续整年同指标数据，四年情景不能当作统计置信区间。[有序留出结果](../results/calibrated/intensity_backtest.csv)
- **任务构成与缺失。** 全速下，按低输出四分位/全部完整/高输出四分位迁移，编码日输入分别为 689.07 / 2,463.73 / 5,421.55 万。若目标改为忠实重放全部 500 题的构成，同一发起率下，仅已记录请求就对应至少 2,675.64 万输入和 28.00 万输出。两种样本定义分别报告。源码类按 OpenAI 分类汇总比得到约 68.1 万输出，按完整 SWE 题则约 24.9 万；口径差异和任务差异都可能造成差距，两项不能相加。
- **全研发输入。** 仅作压力测试，可假设所有类别沿用代码样本的总输入/输出比 99.09 和缓存/输出比。全速下据此得到约 3.30 亿输入，含 3.10 亿缓存；这是跨任务、跨模型、跨服务缓存的三重迁移。无公开依据将它当作全研发基准或上限。要替换此假设，需真实交互流量的研究员日分母，以及含 task ID、会话/父子关系、调用账单、缓存、起止与成败的分层样本。
- **更新顺序。** 有新月份时先更新发起率和输出的原图，再对齐不重叠窗口、检查分类器和名单变化，最后按类别替换完整轨迹。预测不以 API 价格、AL4 份额或 GPU 型号推算 Token。

从仓库根目录执行。第一条使用仓库内冻结数据完成预测。第二条需要 matplotlib、python-pptx 与中文字体。两条 verify 命令分别核查 OpenAI 原图和 SWE 原始提交，后者可使用已有本地下载缓存。

```bash
python -B -m analysis.agentic_30t_forecast.workload.forecast
python -B -m analysis.agentic_30t_forecast.workload.calibration.figures
python -B -m analysis.agentic_30t_forecast.workload.calibration.verify_openai
python -B -m analysis.agentic_30t_forecast.workload.calibration.verify_public_traces /tmp/agent-traces
```

[图 1 · 使用时长与任务发起率](../figures/calibration/calibration_1.png) · [图 2 · 编码任务分布](../figures/calibration/calibration_2.png) · [图 3 · 2030 需求](../figures/calibration/calibration_3.png) · [可编辑 PowerPoint，3 页、7 张原生图表](../figures/calibration/task_calibration.pptx)
