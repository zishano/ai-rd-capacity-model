# 运行环境

## 仅浏览页面

使用支持 JavaScript 和 SVG 的现代浏览器，打开 `../01_pages/resource-dashboard-preview.html` 或 `../01_pages/raw-data-dashboard.html`。页面已包含所需数据、脚本和样式，不依赖 Python、Node.js、外部 CDN 或服务器。字体由本机浏览器选择；不同机器上的字形和排版可能略有差异。

三个 HTML 文件需放在同一目录，以便相互导航。来源文章链接不影响离线图表运行。

## 重建 HTML 和页面数据

使用 Python 3.10 或更新版本。页面构建与三个数据生成脚本使用 Python 标准库，无需为这些步骤安装第三方 Python 包；数据复算使用了 Python 3.10 起提供的 `statistics.linear_regression`。

统一入口为 `rebuild.py`，从归档中读取前端源码、数据和 `project` 内的上游文件，在临时工作目录保留原路径关系后调用构建脚本。需要对临时目录及归档的报告目录有写入权限；使用 `--publish` 时还需要对页面、数据和相关导出目录有写入权限。

原始 `build_preview.py` 中的 `RENDERER` 绝对路径是未使用的旧常量，重建不依赖该路径对应的插件。它实际需要的 PPT 输入为 `team-resource-overview-2030.pptx`，统一入口会从本归档中组装这项依赖。

重建不联网获取最新观测，不重新拟合已保存的 16 种算法。缺少依赖文件时应修复归档或文件清单，不需要访问原工程路径。

输出 Token 直接读取官方已平滑的 14 日滑动日均值，预测使用同一目标的 `value` 列；不对这些值或月度点再次做移动平均。输入、缓存与计算量按该输出重新换算。Agent 时长、任务数和并发分布保留各自官方 28 日统计窗口。归档中的 28 日输出只用于历史追溯。

## 可选浏览器检查

运行 `rebuild.py --browser-check` 需要：

- Python 3.10 或更新版本。
- 系统已安装 Chrome 或 Chromium，且 `google-chrome` 或 `chromium` 命令可在 `PATH` 中找到。
- 可写的 `/tmp` 目录。
- 允许启动本地浏览器子进程并使用 `127.0.0.1` 回环连接。

检查使用 `cdp_helper.py` 与浏览器 DevTools 协议通信，不依赖 Selenium、Playwright 或额外的 Python WebSocket 包，也不需要公网访问。脚本使用临时浏览器配置文件，不读取日常浏览器配置。

现有工具按 Linux 环境编写，包含 `/tmp`、进程组与信号处理。跨平台浏览不受此限制；在 Windows 等其他系统自动运行这套浏览器检查前，需要适配这些系统调用。浏览器自身缺失或系统禁止子进程、回环网络时，浏览器检查无法完成，不代表页面数据已检查失败。

三套检查会分别核对资源探索、外推算法比较和原始数据四图；相关脚本必须与组装后的 HTML、JSON、CSV、参考值放在原有相对位置。请使用统一入口，不要单独将检查脚本指向另一个目录的页面。

## 可选静态图表导出

运行 `rebuild.py --export-figures` 除 Python 外，还需要：

- `numpy`
- `matplotlib`
- `python-pptx`
- Noto Sans CJK 中文字体，现有导出脚本读取 `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`

这些依赖不会随归档自动安装。可在自己的 Python 环境中预先安装对应软件；离线环境需提前准备安装包和系统字体。

静态导出调用 `build_presentation.py` 和 `build_analysis_figures.py`：前者生成 2030 总览 PPT，后者使用 Matplotlib 的非交互绘图后端生成年度 PNG、SVG、PDF，并通过 python-pptx 生成含原生图表的年度 PPTX。已有导出文件可直接查看，不要求本机安装上述生成依赖。

PPTX 的结构、标签、图表和形状边界检查通过 Python 的 ZIP/XML 读取完成，不要求安装 Office。此类检查不等价于在 PowerPoint 或其他办公软件中实际渲染；本归档不对未执行的应用渲染作通过承诺。

## 报告与完整性

原工程的历史报告保存在 `../06_validation/historical_reports`，其中的绝对路径仅用于追溯当时的运行环境。不要将这些路径作为迁移后的输入。

使用统一入口生成当前检查结果；最新报告和根目录 `manifest.json` 以归档内相对路径标识文件。校验值反映文件内容，不能用修改校验值来代替实际数据或浏览器检查。

`rebuild.py` 默认及 `--check` 都会重建并比较页面、数据，写入最新报告并刷新清单；仅想读取并验证现有清单时，运行 `python3 -B 04_reproduce/bundle_manifest.py`（从 `html` 目录执行）。`bundle_manifest.py --write` 才会显式更新清单。
