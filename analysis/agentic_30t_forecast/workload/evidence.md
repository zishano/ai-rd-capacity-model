# 历史数据、变量口径与可识别范围

[sources.csv](sources.csv)记录每个快照的来源、原文字段、逐行定位键及 SHA256。研究员口径、平台口径与逐请求口径分别建账。

|来源与时间|观察及分母|在第一层的用途|
|---|---|---|
|OpenAI 2026-11-18，Agent workdays across research|Overall Research，2026-05-03 至 10-18，169 个图值。8 小时计一个 Agent 工作日，按研究员日历日计，累加同时工作的 Agent，通常覆盖交互式使用。时长包含合格子 Agent 与自动评审，排除部分程序化使用，同一 turn 内相邻服务事件超过 30 分钟的间隔不计；未分别公布父子用时。|以 28 天滑动均值拟合总体会话小时代理。相邻点共享最多 27 天，末 28 日留出与训练期也可能共享底层日期。[原图](https://openai.com/index/research-acceleration-jagged-frontier/#agent-workdays-research)|
|OpenAI 同报告，Median spend|291 个日度图值，2026-01-01 至 10-18；先算每位研究员过去 28 天平均 API 牌价等值，再跨研究员取中位数，$0.40→2,414.70。|独立 OLS 给出 2030/2026 约 6.88 倍。V=(未缓存输入×单价+缓存输入×单价+输出×单价)按模型加总。免费/折扣缓存、模型与价格组合未识别，无法唯一推断 Token、调用频次、单 Agent 金额或真实硬件成本。[原图](https://openai.com/index/research-acceleration-jagged-frontier/#median-spend)|
|OpenAI 9 月报告，4+ concurrent workflows|2026-04-12→08-15，126 个图值，达到日峰阈值的研究员比例约 29.6%→74.0%，含多会话与子 Agent。11 月报告另给 10 月中旬日峰平均 ≥4 的研究员超 2/3、≥16 的超 10%。|支持让“更多并行 Agent”进入敏感性分析。阈值份额与请求均值、P95、创建会话数的分母不同。[9 月原文](https://openai.com/index/research-acceleration-view-inside-openai/) · [11 月原文](https://openai.com/index/research-acceleration-jagged-frontier/)|
|Anthropic，R&D Automation Index，2026-09-17|7 月固定工作篮约 15,000 项、378 个叶类；加权 AL4 占比 2 月 <1%、3 月 1%、4 月 3%、5 月 12%、6 月 14%、7 月 22%、8 月 26%。8 月最常用研发工程平台约 30,000 个并发 Agent。7 月 13–20 日近万训练/评测作业约 14% 被抽样。|任务自动化占比可作跨月背景。平台并发缺少同日研究员分母、活跃请求及驻留分布，组织级算力分配亦无法确定主 Agent 占用。[原文与方法](https://www.anthropic.com/institute/measuring-pace-of-ai-development)|
|Anthropic 内部 Claude Code，2025-02→08|约 20 万份记录，两期每会话最长连续工具调用链均值 9.8→21.2，平均人工交互轮数 6.2→4.1。|支持任务形态在变化；工具动作数不等同于模型调用数。[原文 Figure 3](https://www.anthropic.com/research/how-ai-is-transforming-work-at-anthropic)|
|Anthropic Measuring agent autonomy，交互式 Claude Code|2025 年秋至 2026 年 1 月，按 7 日滚动的 P99.9 自主 turn 时长从不足 25 到超过 45 分钟；中位约 45 秒，约 40–55 秒间波动。Turn 以停止/监督事件分段。|尾部与中位变化不同。该 turn 时钟不能校准整次研究会话时长。使用公开 API 的供应商也未必能可靠拼接 session。[原文 Figure 1](https://www.anthropic.com/research/measuring-agent-autonomy)|
|Anthropic 内部员工时长，2026 年 8 月|交互式 Agent 小时/员工工时约 6，人员工时按每周 40 小时估计；统计包含子 Agent 和工具时间，并排除很长的工具等待。|仅作边界对照。该等待处理规则不能移用到 OpenAI 图值。[原文 Figure 2](https://www.anthropic.com/research/employment-at-anthropic)|
|SWE-bench Verified，mini v2.0.0 / Kimi K2.5 high|沿用 500 取 40 的固定抽样。仅 23 个 issue 的 reported_calls=metered_calls 且缓存字段完整。1,172 次调用逐条回溯到 SHA 校验原件。|每题保存 (calls,prompt,completion,cache_read,peak_request)，每次调用另保存上下文长度的两个加数与请求时钟。缺失的 17 条可能系统性偏长；真实生产任务分布未知。[抽样与来源](../../agentic_40t_forecast/trace_sample.csv)|

最新的任务发起率和逐题 Token 校准扩展至全部 500 条提交轨迹，独立保留 252 条完整联合记录。[证据及复算方法](calibration/REPORT.md)

## 字段分类及自由参数

|类别|字段、数值依据与使用限制|
|---|---|
|Public Observation|两个 OpenAI 时间序列和 4+ 阈值图；每题调用数、每次 prompt、completion、cached_tokens、provider created、client received。原请求 usage 不重复加 reasoning 或缓存。日期图值经原作者平滑与舍入。|
|Formula Derived|累计 I/O/C、命中率 C/I、未缓存 I−C；上下文代理为每次 prompt+completion。每题 max 进第二层，跨请求的 P50/P90 用于服务分析；随任务抽样权重给该任务的每次请求同权。OLS 等趋势及模型时长/次数/日 Token 恒等式均可复算。|
|Cross-context Assumption|把历时趋势映射为会话时长总预算；将 SWE 任务的可见跨度（最早 provider created 到最晚 client received）用作一个参考会话。请求在途区间取并集，包含排队、网络与模型服务，不可分解 GPU 忙时。供应商起点为整秒，时钟可能有偏差；首呼前和末呼后的工具工作未计入。归一时每个主 Agent 日一场会话、平均一题；这不确定研究员有多少持久主 Agent。源服务缓存命中迁移到新服务亦有误差。|
|Future Scenario|A/B/C 的会话数增长指数 1/0/½，是固定总量的两个端点及对数均分对照。C 到 2030 在均匀任务样本与输出量上十分位子样本间各给一半权重，按年线性过渡；两者均整题抽取。此设置用于压力分析。工作时长、在途占比、尾部任务权重、任务/日、真实峰值均未在目标生产环境测得。|
|Future Scenario|以自然日 24 小时和工作日单位 8 小时换算。bounded 的上限 48 工作日/研究员日对应同时工作 16 个会话当量的全天预算；16 借自公开并发阈值，作为可修改压力容量，未证明是物理上限。顺序调用条件下单主 Agent 的峰值=1，推理活跃并发的实际均值/P95、集群峰值、生产 context 增长率未知。Context 原长度及 2× 是固定与翻倍压力端点。|

总体会话数是按基准短任务时长换算的“等效会话”，可包括主、子及其他会话。若真实会话时长是基准的 k 倍，相同累计小时对应的会话数缩为 1/k。单主 Agent 的 Token 只计一个焦点会话；不再乘研究员等效会话数。报告中的请求在途并发是特定代理量，真实 GPU 执行并发需要调度日志；单主 Agent 串行条件下其推理时间并发均值可在 0 与请求在途均值之间。
