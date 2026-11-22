# HTML 数据来源与更新指南

适用版本：2026-11-22 归档。预测目标：2030-11-18。本文依据本地保存的来源记录和实际代码整理，未重新下载或替换数据。

本目录中的 HTML 是静态成品：数据已经嵌入页面，打开页面不会向 OpenAI 获取最新数据。更新数据后，需要重新生成 HTML。当前重建入口可以复现这一版快照；接入新的观测期，还需要同步更新脚本中的日期、样本数和版本校验。

**仅更新资源页现有算法的月度预测及顶部最终预测**，使用项目根目录的 `data_predict/forecasts/upstream/forecast.csv` 和 `scripts/update_html_predictions.py`，具体步骤见第 6.1 节。这个入口导入已算好的预测，不重新拟合算法，也不更新原始四图或年度基准。

以下路径均以本 `html/` 目录为起点。长路径使用三个简写，方便定位；它们不是需要设置的环境变量：

```text
P = 04_reproduce/project
W = 04_reproduce/project/analysis/agentic_30t_forecast/workload
D = 04_reproduce/project/output_team100_resource_dashboard
```

## 1. 页面实际读取什么

资源探索页的成品是 [01_pages/resource-dashboard-preview.html](01_pages/resource-dashboard-preview.html)，另保留 `team-resource-dashboard.html` 片段入口。构建时使用：

- [03_data/dashboard_data.json](03_data/dashboard_data.json)：2026 基线、2027–2030 年度 A/B/C 情景、月度资源与任务、Agent 活动、18 类活动构成及模型参数。
- [03_data/algorithm_forecasts.json](03_data/algorithm_forecasts.json)：16 种算法的月度人均输出、工作日和任务预测，用于主页面月度趋势的算法比较及顶部单一算法的最终预测。
- [30T 模型配置](04_reproduce/project/config/models/moe_30t.json)：构建时补入模型 ID、名称及权重格式。

原始数据页的成品是 [01_pages/raw-data-dashboard.html](01_pages/raw-data-dashboard.html)，构建时使用 [03_data/raw_research_data.json](03_data/raw_research_data.json)。它保存四张图的全部有效逐日历史、月度预测、团队或任务分类、算法信息和来源文件校验值。该页保留人均量及研究员占比，不套用资源页的团队人数或 30T 资源估算。

这些 JSON 由 `D/build_fragment.py` 和 `D/build_raw_dashboard.py` 嵌入 HTML；`D/build_preview.py` 生成主页面的完整文档外壳。浏览器不单独读取旁边的 JSON、CSV 或截图。

`03_data` 下的八份 CSV 是数据导出：`dashboard_data.csv`、`baseline_2026.csv`、`official_history.csv`、`category_mix.csv`、`monthly_tokens.csv`、`monthly_agents.csv`、`monthly_resources.csv`、`monthly_tasks.csv`。仅修改其中一份 CSV 不会自动修改 JSON 或网页。

## 2. 官方观测来自哪里

### 2.1 研究员输出 Token：用户指定的 OpenAI 中文图表

公开来源：[OpenAI 研究加速内部观察中的指定图表](https://openai.com/zh-Hans-CN/index/research-acceleration-view-inside-openai/#chart-4QLdZ4iw0n4L9rYGTvteZK)。

本地档案位于 `P/output_openai_researcher_forecast/`：

- `source_downloads/selected_zh_article.html`：下载时的原网页。
- `source_downloads/chart_08.json`：该图的 Vega 规范及数据。
- [selected_chart_identity.json](04_reproduce/project/output_openai_researcher_forecast/source_downloads/selected_chart_identity.json)：将用户指定锚点 `chart-4QLdZ4iw0n4L9rYGTvteZK`、图表 ID `rsi-output-token-usage` 与本地 `chart_08.json` 对应起来。
- `source_downloads/download_manifest.json`：请求地址、实际下载地址、采集时间、网页 SHA-256。
- `official_data/output_tokens_14d.csv`：主资源页实际使用的规范化输出观测。
- `official_data/normalization_manifest.json`：字段、日期、行数和规范化 CSV 的 SHA-256。

当前观测区间为 **2026-01-20 至 2026-08-15**，208 个日期，每天 18 个研发类别，共 3,744 行。`value` 的单位是 **Token/研究员自然日**，统计窗口是 **14 日滚动均值**。

原图中的 `areaRows` 提供类别序列，`categoryRows` 提供类别解释，`totalRows` 用于核对类别合计。这个指定图表提供输出用量，不提供任务发起数、输入 Token、缓存输入或推理 FLOPs。

下载记录为 **2026-11-21 08:15:04 UTC**。下载日期不代表观测截止日期；本版输出观测仍截止 8 月 15 日。

### 2.2 Agent 工作日、任务发起和并发：OpenAI 另一篇公开报告

公开来源：[OpenAI 研究加速的新前沿](https://openai.com/index/research-acceleration-jagged-frontier/)。这些指标补充自另一篇报告，不能全部归因于上面的指定输出图。

本地档案位于 `P/output_openai_official_100/`：

- `source_downloads/november_2026_page.html`：下载时的原网页。
- `source_downloads/november_2026_chart_02.json`：五类研究团队的 Agent 工作日，对应页面的 `agent-workdays-research` 图。
- `source_downloads/november_2026_chart_03.json`：九档平均日峰值并发分布，对应 `figure-codex-concurrency`。
- `source_downloads/november_2026_chart_08.json`：18 类任务发起率，对应 `figure-research-task-starts`。
- `official_data/workdays.csv`、`official_data/task_starts.csv`：主资源页实际使用的规范化观测。
- `source_downloads/download_manifest.json`、`official_data/normalization_manifest.json`：下载及规范化记录。

Agent 工作日观测为 **2026-05-03 至 2026-10-18**，169 个日期、五个团队，共 845 行。单位为 **8 小时 Agent 工作日/研究员自然日**，28 日统计窗口。主资源页取 `Overall Research`；原始数据页保留五条团队曲线。总体与分组存在包含关系，不能将五条曲线相加当作总体。

任务发起率观测为 **2026-03-01 至 2026-10-18**，232 个日期、18 类任务，共 4,176 行。单位为 **项/研究员自然日**，28 日统计窗口。合计任务数由 18 类相加得到；这里统计发起任务，不是已完成任务数或 LLM 调用次数。

该报告的本地下载记录为 **2026-11-21 07:47:51 UTC**。

### 2.3 原始四图使用的历史快照

原始数据页通过保存好的绘图点读取历史，相关上游快照保存在：

- `W/observed_openai_research_usage.csv`：总体工作日、18 类任务和九档并发。
- `W/observed_workdays_by_team.csv`：五类研究团队工作日。
- `W/calibration/observed_output_tokens.csv`：18 类输出的宽表快照，保留 14 日口径。
- `W/monthly_research_usage.py`：原四图样式、类别颜色以及内嵌的 `SNAPSHOTS` 历史数据。
- [W/sources.csv](04_reproduce/project/analysis/agentic_30t_forecast/workload/sources.csv)：历史采集来源、选择条件和校验值索引。

当前原始页并发历史使用 **2026-05-04 至 2026-10-18 的 161 个有效日期**。该时间段存在缺日，未填造观测；九档占比经过归一化，每天合计为 1，页面换算为百分数。

历史规范化清单还记载过另一份 `official_data/concurrency.csv`：162 个日期、截止 10 月 19 日，原始舍入后的占比合计约 0.997–1.003。这份 CSV **不是当前原始页采用的输入，也未包含在本归档中**。更新时应明确选择日期截断和归一化规则，不能把两个版本直接互换。

两个 `normalization_manifest.json` 和 `sources.csv` 是保留的完整历史记录，其中会列出当前页面未用、归档也未收录的其他文件。判断归档实际包含什么，以根目录 [manifest.json](manifest.json) 为准。

## 3. 输入、缓存和计算量来自哪里

### 3.1 编码代理任务计量

公开来源：[SWE-bench 的 Kimi-K2.5 编码代理提交](https://github.com/SWE-bench/experiments/tree/main/evaluation/verified/20260217_mini-v2.0.0_kimi-k2-5-high)。

实际输入是 [W/calibration/public_tasks.csv](04_reproduce/project/analysis/agentic_30t_forecast/workload/calibration/public_tasks.csv)。表中保存 500 道题的摘要，每行对应一道题，带有来源 URL 和原始轨迹 SHA-256。核心字段包括：

- `instance`：题目标识；`complete`：计量是否完整，当前计算筛选 `complete == 1`，得到 252 道题，包含成功和失败运行。
- `prompt`：该题累计输入 Token，包含缓存输入。
- `completion`：累计输出 Token。
- `cache_read`：累计缓存读取 Token。
- `peak_request`：最大单次请求的输入加输出 Token，作为本地计算量估算的长度代理。
- `reported_calls`、`metered_calls`、`cache_calls` 等：计量完整性相关字段。
- `url`、`sha256`：逐题原始轨迹的追溯信息。

本归档保存的是计量摘要，不含这些逐题轨迹原件。更换提交或扩展样本时，应重新获取并核对原始轨迹、重新计量，不能只调整题目数量或修改摘要中的校验值。背景说明见 `W/calibration/REPORT.md`。

这些题目提供输入/输出、缓存/输出和计算量/输出的代理比率，再迁移到研究员研发用量。它们不是 OpenAI 研究员实际的输入账单或缓存日志。

### 3.2 合成 30T MoE 与情景假设

架构来源参考：[Kimi K2 官方仓库](https://github.com/MoonshotAI/Kimi-K2) 和 [官方模型配置](https://huggingface.co/moonshotai/Kimi-K2-Instruct/blob/main/config.json)。项目配置是 `P/config/models/moe_30t.json`，模型 ID 为 `synthetic-kimi-k2-scaled-30t`。

这是项目构造的 **Kimi-K2 风格 MLA、约 30T 总参数、Top-8 MoE 假设模型**，不是 OpenAI 公布的模型配置，也不是一个已发布的真实 30T 模型。主页面的模型选择与 FLOPs 估算使用它；原始数据四图不使用模型参数。

当前单份纯权重按配置的 `weights.bytes_per_parameter = 1`（FP8）换算。纯权重值不包含量化元数据、KV Cache、运行时预留、部署副本等完整显存成本；配置中存在其他服务参数，不代表页面已经计算了相应硬件需求。

增长情景来源是 `W/settings.json`：A/B 使用完整任务池的等权比率；C 逐步提高高输出任务的混合权重。当前高输出子池为 26 道题，C 在 2030 年的混合权重为 50%。这是本地情景设定，不是官方观测。

### 3.3 页面指标的计算口径

以下 `N` 为团队人数，默认 100；所有日量均为自然日强度，不是月累计或年累计。

- **输出 Token**：官方人均输出或所选算法的人均预测，乘 `N`。两个页面均采用官方 14 日滑动平均口径；公开观测已经平滑，不重复计算滑动平均，预测也不对月度点再做 14 点平均。
- **累计输入**：团队输出 × 代理任务的加权输入/加权输出。
- **缓存输入**：团队输出 × 代理任务的加权缓存读取/加权输出。
- **未缓存输入 / Prefill Token**：累计输入 − 缓存输入。
- **输入与输出总量**：累计输入 + 输出。缓存输入已经包含在累计输入中，不能再加一次。
- **Prefix Cache 命中率**：加权缓存读取 / 加权输入；采用 Token 加权，不采用各题缓存率的简单平均。
- **Prefill、Decode 计算量**：先根据合成模型及每题输入、输出、缓存和长度代理计算，再按团队输出规模迁移。总计算量为两者相加，单位 EFLOP/日。
- **平均计算速率**：`EFLOP/日 × 1000 ÷ (处理窗口小时 × 3600)`，单位 PFLOP/s。
- **Agent 活动小时**：人均 Agent 工作日 × 8 × `N`，保留官方 28 日统计窗口。
- **平均活动当量**：团队 Agent 活动小时 ÷ 24。它不是峰值并发、LLM 请求并发或 GPU 数量。
- **任务数**：人均 18 类任务发起率合计 × `N`，保留官方 28 日统计窗口。
- **九档并发占比**：原始页保留研究员占比分布，不乘 `N`。最高档 `[64,∞)` 为开口区间，不能据此唯一还原平均并发。

计算公式的实现以 `D/build_data.py` 中的 `calculate_rows`、`calculate_monthly_resources` 等函数为准；页面中的人数、窗口及算法换算位于 `02_frontend/dashboard.js`。

## 4. 预测结果来自哪里

预测数值由本地算法产生，不是 OpenAI 发布的 2030 预测。原算法运行结果保存在 `W/trend_models/results/`；资源页通过专用快照接收后续月度预测更新，原始四图继续使用原算法结果。

### 4.1 主资源页的 16 种算法

可编辑入口是项目根目录的 `data_predict/forecasts/upstream/forecast.csv`。成功应用后，资源页构建读取归档内的 [P/resource_predictions/forecast.csv](04_reproduce/project/resource_predictions/forecast.csv)。该快照初始内容来自 `W/trend_models/results/forecast.csv`，后续可独立更新。它按 `method`、`metric`、`date` 保存人均月度预测：

- 工作日和任务读取 `value`。
- 输出读取 **`value`**，即原始 14 日输出目标；`output_tokens_28d` 仅保留为旧口径参考，不再驱动页面。
- 本版包含 16 种算法、共 2,400 条预测记录，终点为 2030-11-18。

`D/build_algorithm_data.py` 将已应用快照转换为 `03_data/algorithm_forecasts.json`，校验方法、指标、月份、数值及输入来源。包含 `legacy_ols` 在内的全部 16 种方法均可更新未来月度值；顶部也使用所选算法的最新终点预测。`dashboard_data.json` 中的原 OLS 年度/月度基准单独保留，因此更新后的月度 OLS 及顶部取值可以与年度图不同。

“外推算法”下拉菜单中，每个算法前有两个控件：“折线”复选框选择 1–3 种方法，影响月度曲线、对应读数和 CSV；“顶部”单选按钮从全部 16 种方法中选择一个，展示其 2030-11-18 最终预测。顶部的独立下拉框已移除，仅保留当前算法名称说明。两种选择保持独立：顶部算法无需参与折线，选满 3 条曲线仍可切换顶部，增减或切换曲线不会改变顶部选择。非月度视图仍可从该菜单切换顶部预测。已保存的 `algorithms` 和 `headlineAlgorithm` 状态继续使用；未保存有效的顶部选择时，默认使用原脚本 OLS（`legacy_ols`）。图表日期范围只筛选图表，不改变顶部终点。顶部输入、输出、缓存、Prefill/Decode、计算量及速率、Agent 小时、平均活动当量和任务数均随该单一算法变化；人数、情景和服务窗口继续按各自口径换算。单份模型权重及 2026 公开基线不受算法选择影响。

核对顶部数值时，在项目根目录下三份导出表中筛选 `date=2030-11-18`、顶部所选 `method` 和当前 `scenario`：`data_predict/resource_estimates/all_algorithms_monthly_resources.csv` 对应 Token、缓存、Prefill/Decode 和计算资源；`data_predict/team_projections/all_algorithms_monthly_agents.csv` 对应 Agent 小时和平均活动当量；`data_predict/team_projections/all_algorithms_monthly_tasks.csv` 对应任务数。三表使用 100 人基准，计算速率使用 24 小时窗口；页面其他人数和窗口需作相应换算。顶部不从 `annual_forecast_basis.csv` 读取算法终值，也没有单独新增顶部数据表。

年度情景比较、缓存分解、计算分解、类别构成和增长倍数等视图，仍采用 `dashboard_data.json` 中的原 OLS 方法基准，输出及相应资源已同步重算为 14 日口径；这些年度参考视图不会随顶部算法变化。

选择算法时，历史观测保持不变；未来输出、工作日和任务替换为已应用版本中的对应预测。输入、缓存和 FLOPs 沿用原月份、原情景相对输出的比率进行缩放，缓存命中率保持原比率。它没有重新预测缓存机制或逐题上下文结构。

新增的 `ensemble_uncertainty` 来自主分支提交 `fc61b42c84844b22580c85e306878f068300dd69`，保存于 `W/trend_models/results/original_style/ensemble_uncertainty/`。其中 `forecast.csv` 的 `method=ensemble` 提供工作日、任务和原始 14 日输出中位数及分位带，两个页面的输出均读取这份原生 14 日分布。`output_aligned28.csv` 继续归档以便追溯旧口径，不参与当前页面输出计算。算法 JSON 的 `uncertainty.ensemble_uncertainty.<metric>.<date>` 保存 `lower95/lower80/median/upper80/upper95`；`meta.rolling_window_days` 和 `meta.rolling_window_days_by_metric` 明确记录 `{output: 14, workdays: 28, tasks: 28}`，`meta.uncertainty` 保存来源提交、SHA-256、名义分位含义和剥离记录。两个页面使用的分位、原始成分结果、停滞/回落情景与诊断，分别导出到 `data_predict/forecasts/` 和 `data_predict/assumptions/algorithm_diagnostics/ensemble_uncertainty/`。

中位数来自三个等权成分的预测分布混合。名义 80%/95% 带未经四年覆盖校准；停滞和回落情景未赋予概率。资源区间按同一月份、同一情景的固定资源/输出比率换算，未额外加入缓存、硬件或资源模型参数不确定性。手动修改中心后，与归档中位数不一致的日期不会继续显示旧分位，`meta.uncertainty_omitted_points` 明确列出，其他日期区间保留。

### 4.2 原始四图的 6 种总量算法和 5 种并发选择

页面参数名称用括号标明适用范围：总量外推算法用于图 1、3、4（Agent 工作日、研发任务、输出 Token），并发占比外推算法仅用于图 2（并发占比）。两项选择各自作用于对应图表和概要取值。

六套保存好的绘图点位于：

```text
W/trend_models/results/original_style/
  legacy_ols/{chart_data.csv,team_parameters.csv}
  damped_holt/{chart_data.csv,team_parameters.csv}
  damped_holt_hl365/{chart_data.csv,team_parameters.csv}
  logistic_cap4x/{chart_data.csv,team_parameters.csv}
  gompertz_cap4x/{chart_data.csv,team_parameters.csv}
  ensemble_uncertainty/{chart_data.csv,team_parameters.csv,forecast.csv,main_concurrency_bands.csv}
```

`chart_data.csv` 的关键字段为 `metric,method,series,date,value,status`；每套同时保存真实历史与预测，当前每套 12,718 行。`team_parameters.csv` 保存团队拟合参数和截零情况。工作日保留五组，任务和输出各保留 18 类。

并发四种方法来自 `W/trend_models/results/concurrency.csv`：`legacy_log_complement`、`naive`、`conditional_logistic`、`joint_logratio`，每期九档占比合计为 1。当前共 196 行，方法独立于其他三图的总量算法。

第五个并发选择为 `ensemble_uncertainty`：中心沿用原双门槛预测，范围来自 `ensemble_uncertainty/main_concurrency_bands.csv`，表示低于 4、低于 16 的两条累计分界的条件趋势拟合范围。不能把它们当作九档独立区间相加。原始页总量区间只对应工作日总体或任务/输出合计，未声称每个类别都具有同样区间。原始页 JSON 在 `metrics.<metric>.uncertainty` 保存这些分位资料。

`D/build_raw_data.py` 读取上述结果、`forecast.csv` 以及两个样式脚本中的名称/颜色常量，生成 `raw_research_data.json`；它不重新拟合。任务与输出的非线性方案按历史末 84 日类别份额拆分总量；原 OLS 保留逐类算法。五团队工作日分别拟合，总体不由分组相加。

当前“365 天半衰期 Holt”的“其他”团队有 46 个未来点触及非负边界。这是本版结果特征，不代表未来实际使用为零；更换数据时应重新计算和说明，不能继续机械保留这个计数。

算法说明、参数、回测和环境记录保存在 `W/trend_models/README.md`、`results/parameters.csv`、`results/backtest.csv`、`results/concurrency_backtest.csv`、`results/audit.json` 和 `results/manifest.json`。

这些记录属于原上游运行。仅通过资源页入口导入新月度值，不会重跑拟合或回测；保留的参数和诊断不能视为对新数值的验证。原始四图的 `forecast.csv` 交叉核对仍使用 `W/trend_models/results/forecast.csv`，不使用资源页的独立快照。

## 5. 两个页面的输出口径与对照方法

两个页面的输出现在都使用官方 14 日滑动平均：每个观测点描述过去 14 天的人均日均输出，并非 14 天累计量。公开序列已经经过这一平滑处理，页面直接使用；外推算法以该平滑序列为目标，预测点不再做第二次平滑。特别是“每月一个预测点”不能当成逐日原始记录做 14 点平均。

本版 2026 最新输出观测为 8 月 15 日，人均约 722,833 Token/日；资源页 100 人基线约为 7,228 万 Token/日。原先拼接的 28 日值约 655,257 Token/人日，仅留作历史参考，不再用于当前页面的输出、资源或增长倍数。任务与工作日继续采用官方 28 日统计窗口，最新观测截止 10 月 18 日；现有平滑后序列不足以无损还原为逐日值或 14 日值，不能把这些基线误认为同一天、同窗口的联合实测。

核对两页时，应使用同一算法、同一日期和同一数据版本：`资源页团队输出 = 原始页人均输出 × 团队人数`。例如融合方案在 2030-11-18 的人均输出为 3,776,020.5612096465 Token/日，100 人为 377,602,056.12096465 Token/日，即约 3.7760 亿。人数与显示单位不同仍会使页面显示的数字不同；两页算法选择独立，资源页专用预测 CSV 也可独立更新，手工更新后需同步原始四图来源才能继续直接对照。

主资源页月度历史取月内最后一条有效观测；原始页保留全部有效逐日观测。未来均按每月 18 日取点。资源页输出预测从 2026-09-18 开始，原始页的 14 日输出预测从 2026-08-18 开始；工作日、任务和并发预测从 2026-11-18 开始。年度图中的 2027–2030 数值代表各年 11 月 18 日的日强度，不是全年累计。

## 6. 更新当前版本：重建与发布

### 6.1 从 `data_predict` 更新资源页月度预测

本小节的命令从**项目根目录**执行，即包含 `html/`、`data_predict/` 和 `scripts/` 的目录。

1. 编辑 `data_predict/forecasts/upstream/forecast.csv`，保留表头和全部 2,400 条记录。每条记录由 `method + metric + date` 唯一确定，支持现有 16 种方法，不新增方法、日期或指标。
2. 填入算法已算好的预测值：输出、工作日和任务均修改各自记录的 `value`。输出是 14 日平均口径，其他两项仍是 28 日口径；它们都是人均自然日强度，不是百人值，也不是整月总量。
3. 先检查，再应用，最后刷新资源页。

```bash
python3 -B scripts/update_html_predictions.py --check
python3 -B scripts/update_html_predictions.py
```

`--check` 在临时目录验证并重建，不发布页面。无参数命令将检查通过的输入保存为归档内 `P/resource_predictions/forecast.csv`，生成 `algorithm_forecasts.json` 和两个资源页 HTML，重算全算法月度团队与资源导出，并同步分类数据片段和清单。完成后打开或刷新 `html/01_pages/resource-dashboard-preview.html`。浏览器使用内嵌数据，不直接读取 CSV，单独刷新页面不能应用尚未导入的编辑。

输入字段的口径如下：

- `output` 的 `value`：官方 14 日平均口径的 Token/研究员自然日，是当前资源页和原始页可对照的输出目标。`output_tokens_28d` 保留为旧口径参考；只修改该列不会改变当前页面曲线。若生成算法同时保存两种窗口，应分别填写对应结果，不将 28 日值复制到 `value`。
- `workdays` 的 `value`：8 小时 Agent 工作日/研究员自然日。页面再乘 8 和人数得到团队 Agent 小时。
- `tasks` 的 `value`：任务发起项/研究员自然日。页面乘人数得到团队任务数。

所用数值必须有限且非负。输出要求 2026-08-18 至 2030-11-18 每月 18 日各一点；工作日和任务要求 2026-11-18 至 2030-11-18 的同类月度点。输出 2026-08-18 点保存在算法输入中，资源页未来输出仍从 2026-09-18 开始。

更新范围是月度趋势、顶部所选单一算法在 2030-11-18 的最终预测、对应读数、下载数据以及 `data_predict` 中的全算法月度派生表。输出变化会按原月份和情景的资源比率传递到输入、缓存、未缓存输入、总 Token 和理论计算量；工作日变化传递到 Agent 小时和平均活动当量；任务变化传递到任务发起数。缓存命中率由原代理比率决定，不随单纯的输出缩放而改变。

年度情景比较、缓存分解、计算分解、18 类构成和增长倍数分析继续使用已转换为 14 日输出口径的原 OLS 基准。日常预测更新不会再修改历史观测、2026 公开基线、原始四图及其数据、原工程 `analysis/` 和其他输出目录。若修改了 `legacy_ols` 的月度预测，顶部及月度终点采用新版本，年度参考图仍保留归档 OLS，应按标签区分。

成功应用前，编辑过的 CSV 是“待应用输入”，页面和其他派生表仍代表上次成功版本。普通 `export_html_datasets.py` 不会把它覆盖回旧值，会提示先处理待应用输入。更新成功后，该入口与归档快照一致，派生数据和清单与页面同步。其他派生 CSV、JSON 或清单不作为编辑入口。

更新器不训练模型、不重新拟合、不下载观测，也不会凭空补齐新算法的实现或诊断。新预测的算法代码、训练数据和回测需由预测生成过程保存；新观测、新模型、新日期区间或新算法注册应按第 7、8 节进行完整适配。

### 6.2 导入一套新的融合结果

本流程用于拉取或重新生成了整套 `ensemble_uncertainty` 来源后，同时更新资源页和原始四图。它不重新拟合，原 15 种资源算法的输入行逐字节保留。先从**项目根目录**检查：

```bash
python3 -B scripts/import_ensemble_predictions.py --check
```

无差异或首次导入时，去掉 `--check` 即可保存。已有融合输入与新来源不同会拒绝覆盖；审阅后使用 `--replace-ensemble`（也可与 `--check` 组合）。来源归档包括统一四图目录、方法代码/说明及表格诊断；`import_provenance.json` 保存来源提交和逐文件哈希。页面未读取的 23 MB 路径样本 NPZ 仍在主项目中，本 HTML 归档不包含它。

导入完成后，将已审阅输入同步为资源页快照，完整重建两个页面，再更新分类导出：

```bash
cp data_predict/forecasts/upstream/forecast.csv html/04_reproduce/project/resource_predictions/forecast.csv
python3 -B html/04_reproduce/rebuild.py --publish --recompute-data --browser-check
python3 -B scripts/export_html_datasets.py
python3 -B scripts/export_html_datasets.py --check
python3 -B scripts/update_html_predictions.py --check
```

完整重建会读取已归档的融合总量、类别及并发分位资料；仅更新单页月度值的命令有保护边界，不用于替代这一步。只有手改资源页中心时继续用第 6.1 节即可：不匹配日期的旧分位带会被剥离，不改原始四图。`data_predict/forecasts/upstream/ensemble_uncertainty/` 是来源归档的生成副本，应通过导入器更新而非手改派生副本。

### 6.3 重建归档内的已应用版本

以下命令从本 `html/` 目录执行。它们使用已归档输入，不联网，不获取新观测，也不重新拟合 16 种算法。`--recompute-data` 会复算基础资源页的 OLS 与资源换算；算法比较和原始四图仍读取已保存的算法结果。

这里读取的是已应用的资源页快照，不会自动导入 `../data_predict` 中的待应用编辑。即使单独复制 `html/` 到其他目录，也可依靠归档内快照重建已应用版本。

仅检查文件是否与清单一致：

```bash
python3 -B 04_reproduce/bundle_manifest.py
```

复算当前快照并比较生成结果，不发布页面：

```bash
python3 -B 04_reproduce/rebuild.py --check --recompute-data
```

修改前端后重新生成页面：

```bash
python3 -B 04_reproduce/rebuild.py --publish
```

经核对的数据版本及代码已全部适配后，复算、运行浏览器检查并发布：

```bash
python3 -B 04_reproduce/rebuild.py --recompute-data --browser-check --publish
```

最后一条是完成下文数据版本更新后的发布入口，不是绕过旧基线校验的命令。若使用 `--check` 比较一个有意改变的新版本，预期会报告与旧成品不一致。

## 7. 接入新一批官方数据的步骤

### 第一步：保存新的来源版本

保留旧归档作为可回溯版本，在工作副本更新。下载对应的官方文章，保存原 HTML、目标 Vega JSON、下载时间和网页 SHA-256。重新核对图表锚点、名称、指标和单位；`chart_08.json` 等本地编号可能因网页结构变化而改变，不能仅凭编号认定还是同一张图。

原工程中可参考的采集与规范化脚本为：

```text
output_openai_researcher_forecast/source_downloads/fetch_selected_article.py
output_openai_researcher_forecast/source_downloads/normalize_selected_article.py
output_openai_official_100/source_downloads/fetch_official_sources.py
output_openai_official_100/source_downloads/normalize_official_data.py
```

这些脚本没有包含在当前 `html/` 快照中，不能在归档内直接运行。它们还依赖原工程中更完整的下载目录和图表；本归档只保存当前页面所需的四张核心官方图表及两个网页原件。采集脚本指向既有的固定文章，不会自动发现新文章。使用原工程脚本前应先检查采集范围、图表匹配和日期截断，不能将“重新下载”当作已适配新版本。

### 第二步：同步规范化观测和原四图快照

至少同步三份主页面观测：`P/output_openai_researcher_forecast/official_data/output_tokens_14d.csv`，以及 `P/output_openai_official_100/official_data/` 下的 `workdays.csv`、`task_starts.csv`。保留类别 ID、团队名、日期、单位、统计窗口和来源字段，同时更新相应的 `normalization_manifest.json` 与下载记录。

然后从同一批官方数据同步 `W/observed_openai_research_usage.csv`、`W/observed_workdays_by_team.csv`、`W/calibration/observed_output_tokens.csv`。上述规范化脚本不会自动同步这三份算法快照，需要按图表字段另行导出。核对宽表快照与规范化长表在共同日期上的总量和类别值一致，并明确并发的缺失、舍入及归一化规则。

特别注意：上游 `trend_models/original_style.py` 的五团队数据通过 `monthly_research_usage.py` 的 `source_rows(..., None)` 读取 **内嵌 `SNAPSHOTS`**。仅替换同名外部 CSV 不会更新这条读取路径。应同步内嵌快照，或明确改为读取经校验的新版本 CSV；同时调整旧观测截止日期。

### 第三步：重新拟合并成套导出算法结果

新增观测会改变拟合参数。不要保留旧 `forecast.csv` 却只更新历史，也不要只更新总量结果而保留旧类别堆叠。

在具有完整代码、依赖和更新后观测的原工程中，使用 `analysis.agentic_30t_forecast.workload.trend_models` 的完整流程重新拟合并导出，随后同步到归档：

- `forecast.csv`：包含主页面全部方法、完整月份和两种输出窗口字段。
- `concurrency.csv`：四种方法的九档分布。
- 原五个 `original_style/<method>/chart_data.csv` 和 `team_parameters.csv`，以及 `ensemble_uncertainty/` 的第六套图表、原生 14 日输出与总量分位、并发范围及来源资料；28 日对齐输出可继续作为历史参考归档，不驱动当前页面。
- 对应的来源 SHA、参数、回测与算法说明。

若这次更新也要替换资源页的月度算法值，还需同步专用的 `P/resource_predictions/forecast.csv`。现有月份和方法范围内可使用第 6.1 节入口；若观测期或覆盖范围已变化，应先适配构建和校验代码。只更新 `W/trend_models/results/forecast.csv` 不会自动替换专用快照。

完整拟合流程不在当前归档范围内。`trend_models/run.py`、`models.py` 等执行模块以及其上游导入依赖未全部保存；归档中的 `requirements.txt` 也不代表完整执行代码已经具备。原工程的旧 `run.py` 仍有 `2026-10-18` 截断，旧 `monthly_research_usage.py` 也有固定截止日期，必须先适配，新增观测才会实际参与拟合。

完成输入、截止日期和验证基准适配，并按该模块的 `requirements.txt` 准备好独立 Python 环境后，在**完整原工程根目录**执行：

```bash
python3 -B -m analysis.agentic_30t_forecast.workload.trend_models.run
python3 -B -m analysis.agentic_30t_forecast.workload.trend_models.check
```

原 `run` 入口生成既有总量、并发和五套原样式图表。融合方案另由完整项目中的 `trend_models.uncertainty.run` 生成，再通过 `trend_models.original_style --method ensemble_uncertainty` 输出统一入口；运行方式和限制见归档 `W/trend_models/uncertainty/README.md`。不要在 `html/` 内直接执行这些拟合命令，本次接入仅读取已保存结果。

### 第四步：更新版本校验、基线参考和页面说明

当前脚本有意锁定 2026 快照。新数据接入时需审核并同步以下位置，而不是删除断言后强行通过：

- `D/build_data.py`：观测日期和样本数、2026 基线预期值、252/26 个代理样本假设、30T/Top-8 假设、月度覆盖、固定未来结果哈希 `V1_FUTURE_SHA256`，以及已有 `dashboard_data.json` 字段必须保持不变的检查。
- `P/output/team_100_2030.csv`：旧版本终点对照。它仅用于断言，不参与预测计算。接受新预测后应保存旧参考、建立经独立核对的新版本参考；不能拿旧表反向覆盖新计算值。
- `D/build_algorithm_data.py`：方法清单、固定月份区间、2,400 行预期、输入字段与来源校验，以及已应用快照的读取路径。
- `D/build_raw_data.py`：各图历史及预测覆盖、每套 12,718 行、并发 196 行、团队/类别完整性和特定截零计数等。
- `D/build_fragment.py`：年度行数、基线日期及数据来源 SHA 校验。
- `02_frontend/dashboard.template.html`、`dashboard.js`、`raw-dashboard.template.html`、`raw-dashboard.js`：顶部基线文字、默认日期、预测终点、模型展示和相关说明。调整预测终点时还需同步年度数组和日期控件。
- `06_validation/references/qa_reference_forecasts_v1.json` 与 `06_validation/scripts/validate_*.py`：旧结果、CSV 固定哈希、日期/行数、算法和预期指标。应通过独立算式或来源核对后更新预期，不能仅复制待测结果来产生“通过”。
- `D/build_preview.py`、`build_presentation.py`、`build_analysis_figures.py`：固定的 2030 标签、PPT 检查值、年度说明。`build_preview.py` 会验证已有 `team-resource-overview-2030.pptx`；基准数值改变时应同步导出和校验逻辑。

三份 SHA 清单职责不同：下载清单记录原网页；规范化清单记录观测 CSV；根 `manifest.json` 记录归档文件。更新其中一份不会自动修复其他层级。算法结果还保存来源快照校验值，更新时也要保持一致。

### 第五步：验证、发布并记录更新

完成上述适配后，执行第 6 节的复算、浏览器检查和发布命令。需要同步年度静态导出时追加 `--export-figures`，并按 [environment.md](04_reproduce/environment.md) 准备依赖和字体。

发布前至少核对：

- 同一指标的日期唯一、序列完整、单位与滚动窗口一致；缺失观测不能用预测填充后标成历史。
- 18 类任务/输出合计等于总量；五团队总体单独核对；并发九档比例合法且合计为 1。
- 规范化观测、原四图快照、总量预测和分类预测来自同一数据版本。
- 输入 = 缓存 + 未缓存；总 Token = 输入 + 输出；总 FLOPs = Prefill + Decode。
- 人均与团队、14 日与 28 日、观测与条件推算的标签正确。
- 两页跳转、取值、算法选择、日期筛选和 CSV 下载正常；新截图及 PDF/PPTX 与发布版本对应。

每次更新建议记录：更新日期、官方来源、采集时间、每项观测截止日、数据 SHA、算法/模型/样本版本、变化原因、旧新关键值差异、验证报告位置。旧版本的检查通过记录不自动证明新版本正确。

## 8. 只更新算法、模型或代理样本时

**只更新资源页既有算法的月度总量及顶部终值**：使用第 6.1 节流程。它支持现有 16 种方法的已保存预测值，不修改历史、年度基准或原始四图。

**重跑算法并同时更新原始四图**：保持历史观测不变，重新导出总量、并发及原四图的成套结果，核对各文件的一致性后运行数据构建；资源页专用快照也应按需同步。增加新算法还需同步方法清单、原四图预设和相应验证；仅添加 CSV 行不会自动注册新方法。

**更换代理任务样本**：更新 `public_tasks.csv` 的计量摘要、来源与完整性定义，并复核 `build_data.py` 的样本数、高输出子池和比率。输入、缓存与 FLOPs 会改变；若官方观测及外推模型未变，输出、任务数和 Agent 工作日不应仅因代理样本更换而改变。

**修改 30T 模型配置**：同步架构与权重信息、资源计算及版本参考，并检查页面模型名称与标签。只修改 `moe_30t.json` 后运行普通 `--publish`，只会更新构建时补入的模型展示信息，不会自动重算已经保存在 JSON 中的 FLOPs；资源量需要 `--recompute-data`，且当前模型固定校验需要先适配。

**只改图形样式**：修改 `02_frontend`，执行 `--publish`；不需要重新采集或拟合数据。

**只改说明文档**：执行 `python3 -B 04_reproduce/bundle_manifest.py --write` 更新归档清单，不需要重算网页。清单更新只记录当前文件，不代表新数据已验证。

## 9. 本版检查记录

本版完整来源复制核对见 `06_validation/source_copy_validation.json`，归档总体核对见 `06_validation/bundle_validation.json`。归档建立时，3 个 HTML 与 11 个数据文件独立重建一致，浏览器检查共 770 项通过，完整运行记录见 `06_validation/browser_rebuild_validation.json`。

这些结果适用于归档建立时的版本，不自动覆盖后续预测更新。分类导出的核对结果见项目根目录的 `data_predict/validation.json`；预测更新命令还会检查待应用输入与生成结果。读取检查报告时，应同时核对报告对应的输入与成品版本。
