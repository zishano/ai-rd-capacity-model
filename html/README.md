# 页面资源归档

本目录保存“百人团队 · 资源探索”和“原始数据推演”两个页面的成品、源码、数据、生成依赖及检查材料。可以整体复制到其他目录使用；浏览与本归档支持的重建流程不需要原工程。

各项指标的官方来源、代理数据、模型假设及后续更新步骤，见 [数据来源与更新指南](DATA_SOURCES_AND_UPDATES.md)。接入新一批数据前请先阅读其中的版本校验与同步要求。

## 打开页面

双击 [01_pages/resource-dashboard-preview.html](01_pages/resource-dashboard-preview.html) 打开资源探索页面，点击顶部“原始数据推演”进入另一页。也可以直接打开 [01_pages/raw-data-dashboard.html](01_pages/raw-data-dashboard.html)。两个页面都内嵌了样式、脚本和数据，离线浏览无需启动服务器，也无需安装图表库。

请保留 `01_pages` 中三个 HTML 文件在同一目录。第三个文件 `team-resource-dashboard.html` 是资源页的独立片段入口，用于原有集成和导航检查。外部来源链接用于查阅资料，点击这些链接才需要联网。

## 目录说明

```text
html/
├── README.md
├── DATA_SOURCES_AND_UPDATES.md    指标来源、处理过程和数据更新指南
├── manifest.json                 相对路径、文件来源、大小及 SHA-256
├── 01_pages/                     可直接打开的三个 HTML
├── 02_frontend/                  两套模板、CSS、JavaScript
├── 03_data/                      页面 JSON 及年度、月度、基线、构成 CSV
├── 04_reproduce/
│   ├── rebuild.py                统一重建与检查入口
│   ├── bundle_manifest.py        清单校验和显式更新
│   ├── environment.md            运行环境和可选依赖
│   └── project/                  上游输入和原始构建脚本，保留相对目录
├── 05_figures/
│   ├── screenshots/              页面预览截图
│   └── exports/                  PNG、SVG、PDF、PPTX 等导出
└── 06_validation/
    ├── scripts/                  三套浏览器检查及 CDP 工具
    ├── references/               预期值参考数据
    ├── historical_reports/       原工程的历史检查报告
    ├── latest_reports/           最近一次重建或浏览器检查报告
    └── rebuild_validation.json   最近一次统一入口执行结果
```

`02_frontend` 是页面修改入口，`03_data` 是页面当前使用的数据。`04_reproduce/project` 保存原始构建脚本需要的路径关系，包括模型配置、OpenAI 公开统计的本地档案、来源记录、校准数据和已有算法结果。

其中 `04_reproduce/project/resource_predictions/forecast.csv` 保存资源页最近成功应用的月度预测。原始四图继续读取 `analysis/agentic_30t_forecast/workload/trend_models/results/` 中的原结果，两份预测输入用途不同。

页面图表由 JavaScript 绘制 SVG，不读取 `05_figures` 中的图片。这里的截图和静态导出用于查看、汇报和归档。`team-resource-overview-2030.pptx` 同时是原预览构建脚本的检查输入，因此也作为重建依赖保存。

## 从预测表更新资源页

在完整项目中，编辑 `data_predict/forecasts/upstream/forecast.csv`，保留现有算法、指标和月份；输出、工作日和任务均修改各自记录的 `value`。输出是官方 14 日平均口径，工作日和任务仍是 28 日口径；`output_tokens_28d` 仅保留为旧口径参考，不驱动页面。详细单位和覆盖范围见[更新指南第 6.1 节](DATA_SOURCES_AND_UPDATES.md#61-从-data_predict-更新资源页月度预测)。从**项目根目录**运行：

```bash
python3 -B scripts/update_html_predictions.py --check
python3 -B scripts/update_html_predictions.py
```

第一条在临时目录验证并重建，不发布；第二条应用预测，更新资源页内嵌数据和分类派生数据。完成后刷新页面。编辑 CSV 本身不会实时改变页面；普通导出也不会覆盖待应用的编辑。

此入口更新 16 种现有算法的月度未来曲线和顶部最终预测，包含 `legacy_ols` 和 `ensemble_uncertainty`。统一在“外推算法”菜单中操作：每行的“折线”方框选择 1–3 种方法参与曲线对比，“顶部”圆形按钮从全部 16 种方法中单选，显示其 2030-11-18 最终预测。两种选择独立，顶部算法无需加入折线；满 3 条曲线时仍可切换顶部，取消某条曲线不会改变顶部算法。顶部只读显示当前算法名称，已保存的选择继续有效。未保存有效的顶部选择时，默认使用原脚本 OLS（`legacy_ols`）。图表日期范围不会改变顶部终点。年度分析、历史观测和原始四图保留各自已应用的归档版本。它导入已算好的预测值，不重新拟合算法。单独复制 `html/` 后仍能浏览并重建已应用版本；从外部分类目录导入新值的命令位于完整项目的 `scripts/` 中。

新增“多模型融合与不确定性外推”读取主分支保存的混合分布中位数及名义 80%/95% 条件分位带，未经四年覆盖校准。两页输出统一采用原始 14 日目标及其分位带，官方观测已平滑，不再对历史或月度预测点重复滑动平均。原始页现在提供 6 种总量方案与 5 种并发选择；融合并发保留原双门槛中心和累计分界区间。

在完整项目里重新导入上游保存的融合结果，可运行 `python3 -B scripts/import_ensemble_predictions.py --check`，核对后去掉 `--check`。已有融合记录不同会停止，审阅后可用 `--replace-ensemble`；原有 15 种方法的行保持原样。导入保存来源提交及哈希，资源页再执行上述应用命令。需要同时更新原始四图时，按[指南](DATA_SOURCES_AND_UPDATES.md#62-导入一套新的融合结果)同步已应用资源快照并完整重建。手改融合点预测造成中心不匹配时，只剥离该日期的旧分位带并显示说明。

## 重建和检查

以下命令在本 `html` 目录中运行。具体环境要求见 [04_reproduce/environment.md](04_reproduce/environment.md)。

```bash
python3 -B 04_reproduce/rebuild.py
```

默认在临时目录中组装原有路径、生成三个 HTML，并将页面和数据与 `01_pages`、`03_data` 逐文件比较。不会修改原工程，也不会自动覆盖页面和数据；会写入 `06_validation` 中的最新报告，并刷新归档清单。临时目录的绝对路径不是下次运行的依赖。`--check` 与默认运行相同，显式表示只比较、不发布：

```bash
python3 -B 04_reproduce/rebuild.py --check
```

仅核对文件是否与现有清单一致、不构建页面、不改写文件：

```bash
python3 -B 04_reproduce/bundle_manifest.py
```

修改 `02_frontend` 中的模板、CSS 或 JavaScript 后，执行下面命令将新页面保存到 `01_pages`：

```bash
python3 -B 04_reproduce/rebuild.py --publish
```

直接修改源码不会改变已经生成的 HTML。未使用 `--publish` 时，新旧页面不一致的结果用于提示修改尚未发布。

按归档中的原始输入复算页面数据：

```bash
python3 -B 04_reproduce/rebuild.py --recompute-data
```

如需同时保存复算结果与重建后的页面：

```bash
python3 -B 04_reproduce/rebuild.py --recompute-data --publish
```

运行现有的三套浏览器检查：

```bash
python3 -B 04_reproduce/rebuild.py --browser-check
```

浏览器检查需要已安装的 Chrome 或 Chromium，会在临时目录打开本地页面，检查取值、图形位置、控制项、下载、响应式布局和双页导航。报告保存到 `06_validation/latest_reports`；如需同时把新截图保存到 `05_figures/screenshots`，加上 `--publish`。普通离线浏览不需要运行这些检查。

重新生成 2030 总览 PPT 和年度静态图表：

```bash
python3 -B 04_reproduce/rebuild.py --export-figures --publish
```

该步骤需要额外的绘图库及中文字体；不会在运行时自动下载安装依赖。

## 数据口径和复现范围

资源探索页使用百人团队的资源推算口径，模型为配置文件中的合成 30T MoE。人数、增长情景、服务窗口及算法选择的作用范围，由页面中的说明给出。输入、缓存和计算量属于条件估算，不能解释为 OpenAI 的实际资源消耗。

原始数据页保留研究员人均统计：Agent 工作日、任务数和并发分布使用 28 日统计窗口，输出 Token 使用官方 14 日平均窗口。资源页输出、年度 OLS 参考和类别构成均统一到 14 日口径，输入、缓存与计算量按该输出重新估算；同算法、同日期、同版本下，资源页团队输出等于原始页人均输出乘人数。两页算法选择与预测更新入口仍独立。五类研究团队存在包含关系，不能加总；九档并发图展示研究员占比，不能直接当作 GPU 数量或团队峰值并发。

`--recompute-data` 调用归档的三个页面数据生成脚本，重新读取已保存的观测、校准数据和算法结果；它不会抓取新的 OpenAI 数据，也不会重新拟合 16 种外推算法。现有算法结果及其来源记录已保存，完整重拟合算法、下载更新数据及训练模型不属于本次资源快照的重建范围。

来源资料另含四张核心官方图表的 JSON、两份原网页、图表身份与下载记录，以及原四图使用的历史 CSV。原始并发图保留实际使用的 161 个有效日期和归一化口径。两份 `source_methods.md` 是此前分析的来源与方法背景，当前页面口径以本说明和页面内说明为准。

编码代理校准使用的 `public_tasks.csv` 已保存各题计量摘要、来源 URL 和 SHA-256；本地没有对应的逐题原始轨迹文件，因此本目录不包含这些轨迹原件。字体和 Python/浏览器运行环境按环境说明准备，不复制系统安装目录。

## 检查记录与迁移

归档建立时已在隔离临时目录中独立复算数据、重建页面：3 个 HTML 与 11 个数据文件均与归档版本逐字节相同；三套浏览器检查共 770 项通过。完整浏览器运行记录保存在 `06_validation/browser_rebuild_validation.json`，各项结果见 `06_validation/latest_reports`。这些是当时版本的检查记录，后续更新需核对相应新版本报告。复算使用本目录中的输入，不读取原工程数据。

`manifest.json` 使用相对路径记录归档文件，可用于发现遗漏或文件变化。首次归档的来源信息用于追溯复制位置；这些来源路径不构成运行依赖。

统一重建入口会刷新清单。其他有意的文件修改，如更新说明文档，可在核对后显式刷新；刷新只记录当前内容，不代替构建或浏览器检查：

```bash
python3 -B 04_reproduce/bundle_manifest.py --write
```

`06_validation/historical_reports` 保留原工程报告，其中可能包含原机器绝对路径。这些报告是历史证据，不应直接用其中的路径在新机器上读取文件。统一入口生成的最新报告使用归档内的相对路径及校验信息，便于目录整体迁移后核对。

请通过 `04_reproduce/rebuild.py` 运行流程，不要直接在分类目录中调用旧 `package_outputs.py`。旧脚本假设文件平铺在原输出目录，并按历史报告的绝对路径校验文件；统一入口负责组装这些依赖关系。
