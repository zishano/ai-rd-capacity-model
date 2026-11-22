"""Chinese documentation for classified HTML data and the forecast update input."""

READMES = {
    "data_row": """# 原始统计、观测换算与代理样本

本目录从项目的 `html/` 归档导出公开统计、来源材料和校准样本，便于查看、追溯和后续更新。导出仅读取当前归档，不联网下载、不重新拟合，也不改变 HTML 页面、页面读取方式或归档中的任何来源。

`data_row` 沿用本次约定的目录名称。这里的“原始”指已公开并归档的图表统计，不是 OpenAI 研究员的个人逐日使用日志。官方统计、对统计值的确定性换算、第三方代理样本分别保存，不能混用。

## 目录

| 目录或文件 | 内容和用途 |
|---|---|
| `official_sources/` | 官方文章、嵌入图表、下载及归一化记录、图表身份和来源说明等归档证据。用于核对来源 URL、单位、窗口与文件指纹。 |
| `observations/` | 官方发布的研究员使用统计及其历史序列：输出 Token、任务发起数、Agent 工作日、团队分组和并发分布等。 |
| `observed_transforms/` | 从观测值确定性换算的人均历史数据，例如工作日乘 8 小时、累计小时除 24、旧版 28 日输出参考，以及并发占比归一化。28 日输出保留用于追溯，当前页面不再使用。百人团队字段另存于 `../data_predict/team_projections/`。 |
| `proxy_samples/` | 第三方公开编码轨迹的计量摘要和校准说明，用于资源估算；不是 OpenAI 研究员的输入、缓存或计算量实测。 |
| `manifest.json` | 导出文件清单、来源相对路径及哈希、数据分类、行数等追溯信息。具体文件范围以清单为准。 |

## 常用 CSV 入口

- 原始数据页四图的历史：[五团队工作日](observations/raw_page_workdays.csv)、[18 类任务](observations/raw_page_tasks.csv)、[18 类输出 Token](observations/raw_page_output.csv)、[九档并发归一化占比](observed_transforms/raw_page_concurrency.csv)。每行保留实际日期、系列、数值、单位和统计窗口，历史只保存一份，不按算法重复。
- 资源页的人均历史：[官方统计](observations/resource_page_history.csv)、[观测换算](observed_transforms/resource_page_history.csv)；对应最新人均基线分别见 [官方基线](observations/resource_page_baseline.csv)和[换算基线](observed_transforms/resource_page_baseline.csv)。这些文件不含百人团队换算字段。
- 官方归一化长表：[输出 Token](observations/output_tokens_14d.csv)、[任务发起](observations/task_starts.csv)、[工作日](observations/workdays.csv)。与上述页面表部分重合，使用其中一种表达即可，不要拼接成额外样本。
- 代理样本：[500 题计量摘要](proxy_samples/public_tasks.csv)，计算时需使用 `complete` 字段筛出完整样本。

## 数据从哪里来

研究员输出 Token 来自 OpenAI 的[研究加速内部观察文章](https://openai.com/zh-Hans-CN/index/research-acceleration-view-inside-openai/#chart-4QLdZ4iw0n4L9rYGTvteZK)，当前归档为 18 类研发活动、14 日滚动统计。Agent 工作日、任务发起和九档并发分布来自 OpenAI 的[研究加速与不均衡前沿文章](https://openai.com/index/research-acceleration-jagged-frontier/)，当前归档使用相应的 28 日统计口径。导出不会访问这些网站；网页链接供人工追溯。

当前观测范围分别是：输出 2026-01-20 至 2026-08-15，任务 2026-03-01 至 2026-10-18，工作日 2026-05-03 至 2026-10-18，并发 2026-05-04 至 2026-10-18。并发有 161 个有效日期，中间存在缺日；其他序列也应按真实日期读取，不能自行补成零。

代理样本来自 [SWE-bench 的 Kimi-K2.5 公开提交](https://github.com/SWE-bench/experiments/tree/main/evaluation/verified/20260217_mini-v2.0.0_kimi-k2-5-high)。归档包含 500 题计量摘要，当前资源计算使用其中 252 题完整样本。摘要保留任务标识、URL、SHA-256 和计量字段，但不包含逐题原始轨迹文件。此来源属于第三方代理证据，不属于 OpenAI 官方观测。

## 阅读和使用口径

- 本目录的页面历史保留人均强度或研究员占比；代理样本另按单题记录。百人团队换算在 `../data_predict/team_projections/`。14 日、28 日是统计窗口，不是把每日数值累加后的总量。
- 百人值由人均统计乘 100 得到，不代表 OpenAI 曾直接观测同一支固定的百人团队。各指标观测截止日期也不同。
- 一个 Agent 工作日按 8 小时换算；累计 Agent 小时除 24 是平均在线活动当量，不能当作瞬时峰值、LLM 请求并发或 GPU 执行并发。
- 五条团队工作日序列存在包含关系，不能直接相加作为总体。九档并发表示研究员占比，不是设备数；最高档为开口区间，不能据此恢复精确平均并发。
- 两个页面的输出均采用官方 14 日滑动平均口径；已公开平滑值不再二次平滑。资源页按人数放大，原始页保留人均值。同一算法、日期和未独立改写的预测版本下，统一人数和单位后输出相同。旧 28 日换算序列及基线只为追溯保留，不再驱动当前输出和资源估算。任务、Agent 工作日与并发继续使用各自官方 28 日统计窗口，不能仅更改标签当作 14 日数据。
- 目录按证据性质分类，而非仅按年份分类。2026 年的预测放在 `../data_predict/`；2026 年输入、缓存和 FLOPs 的代理估算也放在那里，不能仅因日期早就视为官方观测。

## 文件格式与追溯

CSV 便于筛选、绘图和查看数值；JSON 保留原有字段、嵌套结构及元数据。二者可能表示同一份数据，不应当作两份独立观测合并。

部分 JSON 是分类后拆出的原始 JSON 片段，使用 `records` 中的 `{source, pointer, value}` 记录。`source` 标识所属核心 JSON，`pointer` 保留该 JSON 内的指针路径，`value` 保留原值。重组时须结合 `../data_predict/` 中对应片段和[重组结构说明](../data_predict/assumptions/reconstruction.json)：先按 `structures` 创建字典及指定长度的列表，再按 `source` 分组、依 `pointer` 写入各值。这样可无损恢复三个核心 JSON 的数据结构和值，包括空容器和空日期；不是恢复原文件的空白或排版。单个片段不能直接替换页面完整 JSON。

清单同时记录来源和导出文件的校验信息；分类与行数用于理解数据范围。哈希相同只能证明内容一致，不能证明推演假设有效。来源记录中的历史路径用于追溯，实际导出输入始终来自本项目的 `html/` 归档。

复制的下载及归一化清单属于原始来源记录，其中也可能列出当前页面未使用、未导出的文件；不能把其中所有相对路径理解为本目录下均有副本。当前导出文件及可定位的来源以根目录 `manifest.json` 为准。

## 重新导出与更新

在项目根目录运行：

```bash
python3 -B scripts/export_html_datasets.py
```

这会根据当前 `html/` 归档重新生成 `data_row/` 和 `data_predict/`。只读核对现有导出是否与当前归档及导出规则一致：

```bash
python3 -B scripts/export_html_datasets.py --check
```

导出器遇到未登记文件，或发现已生成文件被手工修改时，会拒绝覆盖。请先备份手工内容、核对差异并处理这些文件，再重新导出；不要通过改写清单中的哈希跳过保护。预测更新入口 `../data_predict/forecasts/upstream/forecast.csv` 可以按预测目录的更新流程编辑；存在待应用的修改时，应先运行预测更新命令，普通导出不会覆盖它。需要修改说明时，应修改 `scripts/html_dataset_docs.py` 后重导出，直接改生成的 README 也会被视为手工修改。

修改本目录的 CSV 或 JSON 不会反向更新 HTML，也不会修改 `html/03_data/`。需要新观测、新算法或新模型时，应先按[数据来源与更新说明](../html/DATA_SOURCES_AND_UPDATES.md)更新并验证 `html/`，再重新导出。当前构建流程包含日期、行数、旧结果哈希和参考值等固定校验，需要按新数据版本审查适配，不能把删除校验当成更新完成。

本导出保留的是当前归档已有的资料；未归档的原始轨迹、拟合过程附件、采集脚本或运行环境不会在导出时联网补齐。预测与资源估算的说明见 [data_predict/README.md](../data_predict/README.md)。
""",
    "data_predict": """# 外推结果、资源估算与计算假设

本目录保存当前页面所用的预测、团队投影、资源估算、模型配置和算法诊断。其中 `forecasts/upstream/forecast.csv` 是资源页月度预测的可编辑入口，其余表格和 JSON 是根据 `html/` 归档生成的分类数据。更新命令可将这份预测表应用到页面；普通导出命令只整理当前已应用版本。两者都不联网下载、不重新拟合算法。

这里保存的是基于公开统计和明确假设的条件推演，不是 OpenAI 公布的未来资源需求。作为起点的统计、观测换算和第三方校准样本分别见 [data_row/README.md](../data_row/README.md)。

## 目录

| 目录或文件 | 内容和用途 |
|---|---|
| `forecasts/` | 研究员人均总量预测、原始四图的分类或分组预测、独立并发分布预测，以及对应来源数据片段。 |
| `team_projections/` | 按团队人数换算的任务、输出和 Agent 活动等年度、月度投影；保存相应口径和原始字段。 |
| `resource_estimates/` | 输入、缓存、未缓存输入、输出关联资源、Prefill/Decode 及理论计算量等估算，包含历史代理估算和未来条件估算。 |
| `assumptions/` | 完整模型配置、情景设置、算法拟合参数、回测、来源记录和数据口径等支撑材料。 |
| `manifest.json` | 每个导出文件的来源相对路径及哈希、分类、行数等信息。具体文件范围以清单为准。 |
| `validation.json` | 本次分类导出的核对结果，包括数据覆盖、数值一致性和核心 JSON 重组等检查；不代替预测模型的实证验证。 |

## 预测覆盖范围

资源页包含 16 种总量外推方法：原脚本 OLS、保持末值、统一水平 OLS、单变化点线性、历史拟合阻尼 Holt、低阶 AutoARIMA，3 种固定半衰期 Holt，各 3 种上限假设下的 Logistic 和 Gompertz，以及新增的“多模型融合与不确定性外推”（`ensemble_uncertainty`）。原始四图采用其中 6 套总量及构成方案；并发分布提供 5 种选择，其中融合方案沿用原双门槛中心并增加条件趋势范围。方法 ID、显示名称、说明和预测值应一起读取，不能只根据某份旧算法运行清单筛选。

导出覆盖归档中全部上述方法和 A/B/C 情景，不以浏览器当前下拉菜单或最多三条算法对比的显示限制裁剪数据。团队资源统一以 100 人、24 小时计算窗口为导出基准；页面中的人数及窗口选择属于交互换算，不表示这里保存了每一种任意人数和窗口组合。

原始数据页保留人均统计口径；资源页保留团队口径。两页输出 Token 均使用官方 14 日滑动平均目标，已有官方平滑数据不再二次平滑。工作日和任务仍使用原有 28 日目标。预测点统一延伸至 2030-11-18；月度点是每月代表日强度，不是整月累计量，年度点也不是全年累计量。

2026 年并非全部属于观测：某指标观测截止之后的 2026 年日期也可能是预测。输入、缓存和理论计算量即使标在历史日期上，也可能来自代理估算。应按 `phase`、`evidence`、统计窗口和来源判断，不要只按年份筛选“真实数据”。

## 常用 CSV 入口

- 原始数据页各算法的预测：[五团队工作日](forecasts/raw_page_workdays.csv)、[18 类任务](forecasts/raw_page_tasks.csv)、[18 类输出 Token](forecasts/raw_page_output.csv)、[九档并发占比](forecasts/raw_page_concurrency.csv)。保留人均或占比单位，按 `method` 区分算法；对应历史在 `../data_row/`。
- 资源页的 [16 种人均总量预测](forecasts/resource_page_algorithms.csv)：按 `method`、`metric`、`date` 筛选，输出采用 14 日窗口，工作日和任务采用 28 日窗口；保留已保存但未显示在资源页时间轴中的 2026-08-18 输出预测点。
- [资源页融合分位带](forecasts/resource_page_uncertainty.csv)：`lower95/lower80/median/upper80/upper95` 使用各指标原始目标，输出 14 日、工作日和任务 28 日，默认 150 条记录。与当前点预测不匹配的日期不导出旧分位，遗漏记录在页面算法 JSON 元数据中说明。[原始页分位带](forecasts/raw_page_uncertainty.csv)同样保留这些原始统计窗口，并发为两条累计分界；九档边际区间不能相加。
- [融合原始分位](forecasts/upstream/ensemble_uncertainty/forecast.csv)、[旧版逐路径对齐后的输出分位](forecasts/upstream/ensemble_uncertainty/output_aligned28.csv)和[独立停滞/回落情景](forecasts/upstream/ensemble_uncertainty/scenarios.csv)完整保留上游原值。当前输出中心和分位采用第一份文件的 14 日目标；28 日文件仅为来源追溯保留，不再用于页面输出。它们都不是其他算法的新增观测。
- `forecasts/upstream/ensemble_uncertainty/chart_data.csv` 是完整绘图来源副本，明确标记为混合历史/预测归档，须按 `status` 区分。实际页面分类表已经分别拆入 `data_row` 历史表和本目录预测表，不要把来源副本中的历史重复计数或当作预测。
- 页面实际月度曲线和顶部最终预测的完整算法换算：[输入、输出、缓存和计算资源](resource_estimates/all_algorithms_monthly_resources.csv)、[Agent 小时与活动当量](team_projections/all_algorithms_monthly_agents.csv)、[任务发起](team_projections/all_algorithms_monthly_tasks.csv)。三表均按 100 人基准保留全部算法、A/B/C 情景及实际使用的预测日期，不含重复的历史段。核对顶部取值时按 `date=2030-11-18`、顶部所选 `method` 和当前 `scenario` 筛选；计算速率的导出基准为 24 小时。
- OLS 基准的年度或月度值位于 `team_projections/`、`resource_estimates/` 中的 `annual_*_basis.csv`、`monthly_*_basis.csv`；本次也统一为 14 日输出及对应资源量，任务和 Agent 不变。`observed` 表示观测依据，`forecast` 表示预测依据。团队换算或资源估算不会因此变成官方实测。
- [18 类输出构成](team_projections/output_category_mix.csv)保留 2026 观测依据与后续预测；[人均强度对应的百人历史](team_projections/observed_intensity_history.csv)保存团队换算及原观测证据。
- [月度预测更新入口](forecasts/upstream/forecast.csv)保存 16 种方法的人均总量预测，可按下述流程编辑并应用到资源页。`forecasts/upstream/concurrency.csv` 仍是原始四图并发预测的归档导出，不通过这个入口更新。不要与页面整理表重复计数。

## 资源如何换算

公开统计主要提供输出、任务、工作日及并发分布；输入、缓存和 FLOPs 还需要第三方编码代理样本与模型架构假设。当前使用 500 题摘要中的 252 题完整样本，不能将这些资源估算说成 OpenAI 研究员的实际账单。

当前模型为合成 30T MoE，参考 Kimi K2 风格架构，并非 OpenAI 官方公布的模型规格。`assumptions/` 保留完整模型配置及情景设置，而非仅保留页面显示的模型名称与参数总量。配置还含权重、KV 和服务假设；保留这些字段不代表当前页面已经计算 GPU 数量、HBM、网络或部署副本。

A/B 在当前团队聚合计算中使用相同代理分布，因此部分甚至整组资源数值相同；C 逐步增加高输出子池混合比例。算法比较沿用当前月份、当前情景的资源与输出比率换算，Agent 总时长和任务发起则使用各自的预测序列。全部 16 种方法（含 `legacy_ols`）的未来月度曲线及顶部最终预测均可通过入口表更新。年度情景、缓存、计算、类别构成和增长倍数分析仍使用既有 OLS 基准。

顶部始终展示单一算法在 2030-11-18 的最终预测，统一在“外推算法”菜单的“顶部”列用圆形按钮从全部 16 种方法中单选。菜单的“折线”列用方框选择 1–3 种算法参与月度对比；两种选择独立，顶部算法无需参与折线，选满 3 条曲线后仍能切换顶部，取消曲线不会改变顶部选择。顶部只读显示当前算法名称，原有保存状态继续有效。未保存有效的顶部选择时，默认使用原脚本 OLS（`legacy_ols`）。图表日期筛选不会改变顶部终点。人数和情景作用于相应团队取值，服务窗口作用于计算速率；模型单份权重和 2026 公开基线不随算法变化。顶部的输入、输出、缓存、Prefill/Decode、计算量、Agent 小时、平均活动当量及任务数均对应上述三份全算法月度表的终点记录，不读取 `annual_forecast_basis.csv` 作为算法终值。

累计输入包含缓存输入，未缓存输入为二者之差；缓存率是按 Token 加权的比例。理论每日 EFLOP 换算为 24 小时平均 PFLOP/s 时使用 `EFLOP/日 × 1000 ÷ 86400`。累计 Agent 小时除 24 是平均在线活动当量，不是峰值并发。

全算法资源表中的 `compute_pflops_window` 才是当前 `method` 在 `service_window_hours=24` 下的实际展示速率，单位为 PFLOP/s。`legacy_reference_compute_pflops_24h` 仅保留原 OLS 行内的辅助参考值，不随算法选择缩放，也未被页面用于显示当前算法速率，不能用它比较算法。其他基准表中的 `compute_pflops_24h` 则属于该表注明的既有 OLS 或历史代理估算口径。完整默认值与公式见 [page_defaults_and_formulas.json](assumptions/page_defaults_and_formulas.json)。

## 参数与诊断资料

保留原 15 种方法的参数、回测和来源资料，以及新增融合方案的独立参数、团队参数、回测、敏感性资料和[导入指纹](assumptions/algorithm_diagnostics/ensemble_uncertainty/import_provenance.json)。融合源来自提交 `fc61b42c84844b22580c85e306878f068300dd69`，未重算原 15 种算法；后续导入的实际版本以指纹中的 `source_commit` 与逐文件 SHA-256 为准。参数 CSV 中的 JSON 字符串应完整保留。

融合中心是三个等权成分预测分布的中位数，名义 80%/95% 条件分位带未经四年覆盖校准。当前页面直接使用上游原始 14 日输出目标的中位数和分位数，不进行 28 日对齐，也不对月度预测点做“14 个点”的移动平均。归档中的 `output_aligned28.csv` 是旧口径参考：它先在同一模拟路径上对齐再取分位，不能直接平均两组分位来重建。停滞/回落情景没有被赋予概率。方法解释见[上游说明](assumptions/algorithm_diagnostics/ensemble_uncertainty/README.upstream.md)。

这些参数和回测是原上游算法运行的记录。通过入口表导入新预测值后，更新命令不会重新拟合或重跑回测，不能把保留的旧诊断解释为对新数值的验证。新预测的算法实现、训练范围和诊断应在生成预测时另行保存。

原始四图的非线性任务和输出构成通常按历史末 84 日份额分配；旧 OLS 保留逐类规则。工作日五团队不是可相加的独立总体；并发模型与其他总量方法独立。阻尼半衰期和饱和上限是条件假设，算法间差距不是置信区间。边界截零等警告也属于结果的一部分，应与预测一起查看。

当前并发预测表保存日期、方法及九档份额，并未保存完整并发拟合系数。归档也未包含全部拟合过程附件或逐题轨迹原件。本目录仅导出现有归档材料，不从原工程其他输出目录补入可能不同版本的文件；具体覆盖以清单为准。

## 文件格式与一致性

CSV 便于查看、筛选和作图，JSON 保留全部原始字段及嵌套结构。不要把同一数据的 CSV、JSON 表达当成额外样本重复统计。

部分 JSON 是分类片段，`records` 中的每条 `{source, pointer, value}` 分别标识所属核心 JSON、该 JSON 内的指针和原值。结合 `../data_row/` 的对应片段及 [reconstruction.json](assumptions/reconstruction.json)，先按 `structures` 创建字典与指定长度的列表，再按 `source` 分组并依 `pointer` 赋值，可无损重组三个核心 JSON 的数据结构和值；原文件空白与排版不在此保证范围。`partitions` 列出所有必要片段，单个片段不等于页面可直接读取的完整 JSON。

`manifest.json` 记录来源、哈希、分类和行数，`validation.json` 记录导出核对结果。检查通过表示导出忠实反映当前归档，不表示长期增长机制已经验证、算法已经选优，或资源估算可以直接转化为硬件采购数量。

## 更新预测并应用到页面

只编辑 [forecasts/upstream/forecast.csv](forecasts/upstream/forecast.csv)。保留现有表头、16 种 `method` ID，以及每个 `method + metric + date` 的唯一记录和日期覆盖；当前共 2,400 行，终点为 2030-11-18。

- `metric=output`：资源页使用 `value`，单位是 Token/研究员自然日，官方 14 日滑动平均目标。`output_tokens_28d` 仅保留旧版 28 日参考，修改这一参考列不会改变当前资源页；两列不能互换。两页原始归档版本相同时，人均输出应一致；单独通过此入口自定义资源预测后，原始四图仍保留自身归档，可能不再相同。
- `metric=workdays`：使用 `value`，单位是 8 小时 Agent 工作日/研究员自然日。团队 Agent 小时按此值乘 8 再乘人数。
- `metric=tasks`：使用 `value`，单位是任务发起项/研究员自然日。团队任务数按此值乘人数。

数值须为有限、非负数。输出覆盖 2026-08-18 至 2030-11-18 的每月 18 日，其余两项覆盖 2026-11-18 至 2030-11-18。输出的 2026-08-18 点保留在算法表中；资源页未来输出曲线仍从 2026-09-18 开始。此入口支持更新现有方法的已算好结果，不支持仅靠添加行注册新算法、增加日期或更改单位。

在项目根目录先检查待应用数据：

```bash
python3 -B scripts/update_html_predictions.py --check
```

该命令在临时目录检查输入、重建和核对结果，不发布页面。确认检查通过后应用：

```bash
python3 -B scripts/update_html_predictions.py
```

应用命令将输入保存为 `html/04_reproduce/project/resource_predictions/forecast.csv` 的已应用快照，生成资源页算法 JSON 和内嵌数据，重算全算法月度团队导出，并同步分类片段、说明和清单。完成后重新打开或刷新 `html/01_pages/resource-dashboard-preview.html`；页面支持离线浏览，不会实时读取或监听 CSV。

融合点预测也可在该入口编辑；若某日期的新中心与归档模拟中位数不同，更新程序会删除该日期的旧分位带并记录原因，不会平移旧区间或插值补齐。若需更新整套融合结果，应在主项目生成或拉取成套来源后运行 `python3 -B scripts/import_ensemble_predictions.py --check`，核对后去掉 `--check` 导入。已有融合记录与新来源不同会停止，审阅差异后才使用 `--replace-ensemble`。它只替换融合 150 点，其他算法逐行保持原值，同时保存来源提交与哈希。资源页再运行上述应用命令；原始四图需按 HTML 更新指南执行完整数据重建，单独应用资源点预测不会改写原始四图。

更新影响月度趋势及顶部所选单一算法终值中的输出、输入、缓存、未缓存输入、总 Token、理论计算量及计算速率，以及 Agent 小时、活动当量和任务数。资源比率仍沿用原月份和 A/B/C 情景，因此只修改输出不会改变该月缓存命中率；只修改任务或工作日也不会自动改变 Token。历史观测、年度分析、18 类构成及原始四图保持既有版本。原工程的 `analysis/` 和其他输出目录不会被这个命令改写。

编辑入口表后、成功应用前，该表是“待应用输入”，页面和其他导出仍对应上一次成功版本。此时运行普通导出会拒绝覆盖该表；应先运行预测更新命令。不要把待应用输入与旧派生表混合分析，也不要通过改写清单哈希跳过保护。

## 重新导出与核对

在项目根目录运行：

```bash
python3 -B scripts/export_html_datasets.py
```

只读核对当前导出与归档是否一致：

```bash
python3 -B scripts/export_html_datasets.py --check
```

导出器遇到未登记文件，或发现已生成文件被手工修改时，会拒绝覆盖。除上述指定入口外，其他派生 CSV、JSON 和清单应由工具生成。先备份手工内容、核对差异并处理这些文件后再重导出；不要用修改清单哈希的方式跳过保护。两份生成的 README 来自 `scripts/html_dataset_docs.py`，说明修改也应从该模块开始。

若需更新官方观测、新增算法、修改预测日期、模型或代理样本，应按[数据来源与更新说明](../html/DATA_SOURCES_AND_UPDATES.md)完成数据版本适配和验证，再重新导出。它们超出当前月度预测入口的范围；单纯导出或导入现有预测表不会完成这些适配。

HTML 继续使用内嵌数据。`data_predict` 是更新入口和分类导出所在位置，不是页面离线浏览时的运行依赖。
""",
}
