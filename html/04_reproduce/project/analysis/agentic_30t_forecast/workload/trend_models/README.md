# 短历史 Agent 使用量的多模型外推实验

本目录为独立实验。观测表和原有预测表继续作为来源，结果写入本目录的 results。预测终点为 2030-11-18，月度截面统一取每月 18 日。各指标从自己的最后一个真实图值起预测，输出序列的外推长度比工作日序列多约两个月。

## 原四图样式与非线性外推（修订）

此前 figures 下的总量折线图是算法诊断图，替换了原有团队和任务分类的视觉编码，不能视为原四图的更新。本轮把两个用途分开：**主展示为 results/original_style/index.html**，原 figures 与 PPT 仍是首轮算法诊断材料。

新增 original_style.py 直接复用 monthly_research_usage.py 的 draw_workdays、draw_concurrency、draw_tasks、draw_token_legend、draw_token_stack 和 monthly_ticks，恢复以下格式：

- 工作日：五条团队曲线，蓝色总体实线、其余团队虚线，顶部圆点图例，终值两位小数。
- 并发：九档百分比堆叠、原紫蓝色阶、顶部图例和首尾占比标签。
- 任务：18 类堆叠、右侧六组分类与引导线。
- 输出：18 类堆叠、顶部六列分类图例、原 9 月图配色与深蓝总量轮廓。

所有图保留真实历史和观测截止线，预测按每月 18 日展示。每个总量模型单独生成一套四图，避免将算法颜色与任务类别颜色混用。五套为：固定 365 天半衰期 Holt、历史拟合 Holt、上限为历史最大值 4 倍的 Logistic/Gompertz、旧 OLS。并发模型独立设置，默认保留原双门槛模型作参照，不宣称其已经通过长期验证。

**为什么上次看起来仍是直线？** OLS 的绝对日增量固定；分段线性只在历史内识别折点，未来延长最后一段直线；本次低阶非季节 ARIMA 带漂移时长期也趋于线性。它们并不是三个不同的非线性长期增长机制。新的同风格图将以下机制分别展示：

| 模型 | 预测形式 | 曲率的来源 | 哪些是条件假设 |
|---|---|---|---|
| 阻尼 Holt | L+b·φ(1−φ^h)/(1−φ)，φ=2^(−1/H) | 每日增量按 φ 衰减，逐渐趋平 | 固定半衰期 H=365 天是情景；另输出 H=90/730 天月度数据用于敏感性 |
| Logistic | K/[1+exp(a−bt)] | 可先加速再减速，最终接近 K | K=历史最大值×4 是未验证的容量上限 |
| Gompertz | K·exp[−exp(a−bt)] | 非对称的加速—减速过程 | 同样需要给定 K，历史估计 a、b |

L、b 为 Holt 终点水平和趋势；后两式 t 为从历史起点起算的实际天数。历史拟合 Holt 可能迅速变平，饱和曲线也可能在 2030 前已接近上限，这些是模型自身的结果。没有人为弯曲已有 OLS 数据，也没有为了曲线外观改变历史观测或选择模型。**固定 365 天图只是一个清楚标注的减速情景，并非新的唯一基准预测。**

工作日各团队独立拟合，总体直接使用 forecast.csv，不能把五条曲线相加当作总体。任务/输出的非线性方案先预测总量，再按末 84 日类别份额分配，份额固定是额外假设；旧 OLS 保留逐类算法。chart_data.csv 包含实际绘图点、观测/预测标记，team_parameters.csv 保留团队参数。原有 workload.csv/第二层接口仍沿用首轮五个主要模型；没有把新条件情景悄悄设为资源计算默认值。

团队检查发现：365 天条件 Holt 对“其他”组的负趋势会产生负数，非负截断后触及零。图中已标注边界问题，参数表记录截断点数。不能据此断言未来该组停止使用 Agent，也不宜直接用于团队分组预算；需要更多分组历史或另外验证具有正值支持的模型。

完整 run 会生成全部同风格图。只重画一套可运行：

```bash
python -B -m analysis.agentic_30t_forecast.workload.trend_models.original_style --method damped_holt_hl365
```

独立改变并发方案可追加 --concurrency-method conditional_logistic、joint_logratio 或 naive；图中会明确标明，且不改变其他三图的总量预测。

## 本次实验结论

**这些数据可以比较增长机制，但尚不能识别唯一的四年预测。** 推荐保留 OLS 作为持续增长参照，阻尼 Holt 作为减速参照，单变化点线性作为近期斜率延续参照，低阶 ARIMA 用于短期校验。并发趋势模型目前未超过保持末值基线，不应自动成为默认预测。

| 图表 | 数据特点及原基线 | 优先候选 | 长期对照 | 主要风险 |
|---|---|---|---|---|
| Agent 工作日 | 169 日、28 日均值；原 OLS | 阻尼 Holt | OLS、单变化点线性 | 半衰期影响远大于短期残差 |
| 九档并发 | 161 点、有缺日；原双门槛模型 | 近期保留末值；条件 Logistic 作为受约束实验 | 原门槛模型、九档对数比 | 长期份额集中到高档；上端开口档无法识别平均并发 |
| 18 类任务 | 232 日、28 日均值、存在全零小类；原逐类 OLS | 总量阻尼 Holt / 低阶 ARIMA，再分配份额 | 总量与逐类 OLS、单变化点 | 未来类别迁移、舍入零值与真实零需求不同 |
| 18 类输出 | 208 日、14 日均值；原斜率加末值锚点 | 短期保留 OLS / ARIMA；长期比较阻尼 | 单变化点、条件饱和 | 后期加速不足以证明持续四年；锚点策略改变端点 |

2030-11-18 的点预测如下，单位均以每研究员日为分母。输出列仍按源图的 **14 日窗口**；forecast.csv 同时给出对齐任务图的 28 日窗口值。

| 算法 | Agent 工作日 | 任务发起数 | 输出 Token（万，14 日窗口） | 输出 Token（万，28 日窗口） |
|---|---:|---:|---:|---:|
| 保持末值 | 5.70 | 26.30 | 72.28 | 72.28 |
| 原脚本 OLS | 56.96 | 168.96 | 473.00 | 471.20 |
| 统一拟合水平的 OLS | 56.96 | 168.96 | 450.19 | 448.38 |
| 单变化点线性 | 73.60 | 204.67 | 1,651.69 | 1,644.58 |
| 阻尼 Holt | 12.06 | 28.27 | 84.34 | 84.34 |
| 小范围 AutoARIMA | 51.90 | 179.93 | 636.75 | 634.21 |

28 天回测中，工作日的平均 MAE：Holt 0.105、OLS 0.768；任务：Holt 0.888、OLS 2.015；输出：OLS 58,574 Token、ARIMA 62,365、Holt 81,694。这是三个滚动起点上的滚动目标误差，存在窗口相关性。56 天排除共享底层日期后的评分中，任务和输出以 ARIMA 较低，工作日仍以 Holt 较低，但分别只有 2、2、1 个有效起点，不能据此宣布模型胜出。

任务和输出的全历史 Holt 拟合均触及半衰期 14 天下界。把半衰期固定为 30–730 天再拟合，任务端点从 30.79 变到 102.06，输出从 100.38 万变到 640.28 万。工作日的对应端点为 6.52–26.08。84 日拟合窗口下任务 Holt 为 107.53，也说明它的 28.27 不是稳健的唯一预测。模型拟合前已归一化 Token 数值尺度，完整参数与警告留在 CSV。

并发 28 天九档平均百分点误差：保持末值 0.93、原门槛 1.10、条件 Logistic 2.49、九档对数比 3.18。到 2030 年，三个趋势模型的 ≥4 档总占比都接近 100%；≥16 分别为 78.11%、约 100%、91.42%。这些结果是持续迁移假设的后果，不能当作已经验证的并发需求。本轮不推荐用其唯一端点驱动资源预测。

**最难支持四年外推的是并发分布**：同时受群体构成、工具组织方式和开口尾档影响。若只能补充一类数据，优先获取可追踪同一研究员群体的未平滑逐日使用日志，包含任务类别、请求输入/缓存/输出、开始结束时间及并发。它同时改善平滑相关性、类别 Token 强度和尾档识别；仅补更多相邻滚动图值的价值较小。

## 运行

在仓库根目录、已安装下列依赖的 Python 环境运行。

```bash
python -m pip install -r analysis/agentic_30t_forecast/workload/trend_models/requirements.txt
python -B -m analysis.agentic_30t_forecast.workload.trend_models.run
python -B -m analysis.agentic_30t_forecast.workload.trend_models.check
```

默认运行包含多个滚动起点和低阶 ARIMA 搜索，运行时间取决于 CPU。manifest.json 记录实际依赖版本和三个输入文件 SHA256。模型随机性为零，优化器和数值库版本仍可能影响末位精度及局部最优解。

## 算法与工具

| 模型 | 实现及机制 | 适用边界 |
|---|---|---|
| 保持末值 | 所有未来点等于训练末值 | 朴素参考 |
| OLS | 最小二乘拟合截距和日增量 | 绝对增量长期持续 |
| 单变化点线性 | 连续折线，候选点每 7 日，左右各至少 42 日；BIC 与单直线比较 | 数据只支持一个阶段变化；拐点完全在每次训练集内选择 |
| 阻尼 Holt | statsmodels 加法趋势指数平滑；阻尼半衰期允许 14–730 天 | 适配日频数据；此半衰期范围是实验约束。另固定 30/90/365/730 天复拟合 |
| 小范围 AutoARIMA | statsmodels ARIMA，p/q∈{0,1}，d∈{0,1}，非季节；d=0 带线性趋势，d=1 带漂移，AICc 选择收敛模型 | 精简自定义搜索；长期趋势取决于阶数和漂移。参数文件保留未收敛候选 |
| Logistic | K / (1+exp(a−bt))，b≥0 | K 固定后拟合 a、b |
| Gompertz | K exp(−exp(a−bt))，b≥0 | 非对称饱和曲线 |

前三类数值序列在本实验内统一采用拟合的水平预测。旧输出 Token 脚本是“OLS 斜率 + 实际末值”，因此新 OLS 的输出端点与旧图可能不同。该端点差异是明确的锚点策略差异。旧脚本及其归档继续支持精确复算。

Logistic/Gompertz 的 K 为各指标历史最大值的 2/4/8 倍，仅用于测量上限假设的影响，缺少业务容量证据。它们作为条件曲线展示，排除在短期统计模型排名之外。参数文件记录雅可比条件数，较大的数值表示参数拟合病态风险。当前数据不足以把 K 当成已经识别的真实上限。

最小工具组合为 statsmodels（BSD-3-Clause）和 SciPy（BSD-3-Clause），绘图使用 Matplotlib 与 python-pptx。StatsForecast（Apache-2.0）适合扩大批量自动模型搜索，首轮的八种低阶 ARIMA 组合可直接用 statsmodels 完成。scikit-learn（BSD-3-Clause）的 Huber 回归适合作异常点敏感性扩展。Prophet、预训练时间序列模型留待后续有实证收益时评估。下列均为官方项目或接口。

| Python 工具 | 许可证 | 适用模型 | 区间能力 | 本项目实现难度 |
|---|---|---|---|---|
| statsmodels | BSD-3-Clause | OLS、Holt/ETS、ARIMA | ARIMA 原生条件区间；ETSModel 支持预测区间，当前 Holt 接口需另实现 | 低至中 |
| SciPy | BSD-3-Clause | 固定上限 Logistic/Gompertz 非线性拟合 | 无即用时序预测区间；需自行模拟或区块重采样 | 低（点估计）/ 中（区间） |
| StatsForecast | Apache-2.0 | AutoARIMA、AutoETS、批量基线 | 内建模型区间与保形区间选项；不能消除滚动数据依赖 | 低；分类序列规模扩大后更有价值 |
| scikit-learn | BSD-3-Clause | Huber 等稳健回归 | 无原生时序预测区间 | 低（回归）/ 中（时序验证） |

- [statsmodels ETS 和预测](https://www.statsmodels.org/stable/generated/statsmodels.tsa.exponential_smoothing.ets.ETSModel.html)
- [本次使用的 Holt 接口](https://www.statsmodels.org/stable/generated/statsmodels.tsa.holtwinters.ExponentialSmoothing.html)
- [statsmodels ARIMA](https://www.statsmodels.org/stable/generated/statsmodels.tsa.arima.model.ARIMA.html)
- [SciPy 非线性最小二乘](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)
- [StatsForecast](https://github.com/Nixtla/statsforecast)
- [scikit-learn Huber](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.HuberRegressor.html)
- [Forecasting: Principles and Practice：阻尼趋势](https://otexts.com/fpp3/holt.html)
- [Forecasting: Principles and Practice：时间序列交叉验证](https://otexts.com/fpp3/tscv.html)

## 数据审计与窗口

工作日为 2026-05-03 至 10-18 共 169 个日值，任务为 03-01 至 10-18 共 232 个日值，两者为发布的 28 日滚动统计。输出为 01-20 至 08-15 共 208 个日值，14 日滚动均值。并发使用 05-04 至 10-18 的 161 个图值，中间 7 个日期缺失；按实际日期拟合，计算占比时归一化消除图值舍入。并发原报告是最近 28 个纳入日期内每人的日峰平均，再分箱，原始底层日期与发布图值日期存在差异。

任务与输出来自抽样还原，存在非零用户 P95 截尾；输出报告抽取 2% 内部编码会话。任务报告七月研究员名单口径有变化，因此拟合出的变化点不能直接解释成真实行为转折。工作日包括父子 Agent 的合格累计时间，每个工作日按 8 小时换算；它不是 GPU 工作日。详细原文统计口径沿用上一级 calibration 的证据台账。

任务分类 1.2 和 5.4 在整段历史均显示零，其他小类也大量显示零。现有发布精度不足以识别这些类别的连续增长。所有算法均从既有观测拟合，图中的月份只负责显示。

任务和输出的分类预测支持两种构成假设，先拟合总量，再按训练期最近 28 或 84 日的类别合计份额分配。零份额保留并列为待补数据。另有逐类 OLS 的 bottom_up_ols 路径。分类总量具有完全加总一致性。当前没有用测试期类别份额调参，也没有把训练期内缺失视为零需求。

## 回测

工作日、任务、输出各取前 60%、70%、80% 作为训练集。预测 14/28/56 个实际日，只报告有完整未来观测的组合。模型选择、变化点、初始水平和趋势都在对应训练集估计。三种指标使用自己的完整可用窗口。

backtest.csv 同时报告两种评分。rolling_target 对整段已发布滚动指标评分。new_underlying_days 只纳入起点之后第 28 日及以后的 28 日目标，或第 14 日及以后的 14 日目标。该筛选避免训练最后一个窗口和评分窗口共享底层日期；相邻评分点和不同回测起点之间仍可能相关。只有一个合格点的组合仍写出 n=1，分析时须结合有效样本数。

指标为 MAE、RMSE、WAPE、按训练期一阶朴素误差缩放的 MASE。分母为零时留空。ARIMA 另给条件高斯 95% 覆盖率和平均区间宽度。其区间未计入参数估计误差、选择模型的不确定性及四年增长机制变化。其余模型当前只输出点预测和条件敏感性，不伪造区间。平滑序列下 MASE 的分母可能很小，不能单独用于跨指标排序。

并发另按实际日历提前期评估九档百分点误差、≥4/≥16 门槛误差和总变差距离。其回测针对发布的滚动分布，缺完整底层纳入日期，不能宣称窗口已完全独立。

短期排名不确定长期最优模型。四年曲线间最大值与最小值描述情景差异，不能称为 95% 置信区间。

## 并发的三个趋势模型

原模型分别拟合 log(1−p4) 和 log(1−p16)，保持末期组内构成。新 conditional_logistic 模型拟合 logit(p4) 和 logit(p16/p4)，还原三组质量 1−p4、p4−p16、p16，保证嵌套。joint_logratio 同时拟合九档对数份额并经 softmax 归一化，允许组内构成变化。朴素基线保持末值。

对数变换将零替换为 0.0005，对应发布精度 0.1 个百分点的一半，是模型处理假设。九档对数比对该值和稀疏尾部敏感，不能用此方法恢复未知的 [64,∞) 尾箱均值。三类趋势均没有把占比换算为 GPU 活跃并发。

## 第一层接口与两种业务量

workload.csv 和 inference_inputs.json 按 5 种主要统计模型 × A/B/C × 2026–2030 年生成。日输出由各模型的输出序列提供，按 252 条完整编码轨迹的联合经验分布换算输入、缓存和任务当量。A/B 使用全样本等权，C 使用一半全样本、一半输出最高十分位。此处沿用最新研究员日模型，A/B 的总 Token 相同。人数、会话组织及复杂任务构成的外推仍是业务条件。

图表输出维持原始 14 日窗口。forecast.csv 的 output_tokens_28d 使用 [预测14日均值(t)+预测14日均值(t−14)]/2 对齐至 28 日；若滞后日期仍在历史内，则使用当日观测。两段相邻 14 日窗口权重相同，此式要求研究员日统计分母与抽样口径保持一致；原始个体权重不可得，因此是口径对齐近似。workload.csv 使用该 28 日值、明示 output_window_days=28，并保留 output_tokens_14d 便于追溯。任务与输出仍分别预测，其比值是条件预测强度，并非实测单任务强度。每题五个工作负载字段通过已有 task_input 适配器构造，日权重单列，保留上下文、缓存和任务之间的相关性。上下文峰值是轨迹实测代理，未来上下文增长仍未识别。

工作日另外换算 hours=workdays×8、average_agent_equivalents=hours/24。单个研究员可以有多名并行 Agent，较高当量意味着更大的在线组织规模。任务当量来自编码轨迹的 Token 标度，用户发起任务来自另一条公开序列；两者分开记录。未将小时、任务率和输出倍率同时相乘。

## 结果文件

- audit.json、manifest.json 为数据范围、来源指纹与运行环境。
- forecast.csv、parameters.csv 为月度预测、原始区间和拟合参数。
- backtest.csv、backtest_parameters.csv 为回测误差、有效样本数和每折参数。
- categories.csv 为 18 类份额及逐类 OLS 对照。
- concurrency.csv、concurrency_backtest.csv 为九档分布预测及误差。
- sensitivity.csv 为拟合窗口与阻尼半衰期敏感性。
- workload.csv、inference_inputs.json 为第一层的日负载和第二层可读取的任务输入。
- figures 提供六张核心研究图、两张分类堆叠对照以及原生可编辑图表 PPTX。

原始证据来自 [OpenAI 11 月报告](https://openai.com/index/research-acceleration-jagged-frontier/) 和 [OpenAI 9 月报告](https://openai.com/index/research-acceleration-view-inside-openai/)。
