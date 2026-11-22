"""Bundle the updated dashboard, plots, editable charts, data and validation."""
import hashlib
import json
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = [
    'resource-dashboard-preview.html', 'team-resource-dashboard.html',
    'raw-data-dashboard.html', 'raw-dashboard.template.html', 'raw-dashboard.css', 'raw-dashboard.js',
    'raw_research_data.json', 'build_raw_data.py', 'build_raw_dashboard.py',
    'validate_raw_dashboard.py', 'raw_qa_validation.json',
    'raw_dashboard_workdays.png', 'raw_dashboard_concurrency.png', 'raw_dashboard_tasks.png',
    'raw_dashboard_output.png', 'raw_dashboard_mobile.png',
    'dashboard.template.html', 'dashboard.css', 'dashboard.js',
    'team-resource-analysis-2026-2030.png', 'team-resource-analysis-2026-2030.svg',
    'team-resource-analysis-2026-2030.pdf', 'team-resource-analysis-2026-2030.pptx',
    'dashboard_data.json', 'dashboard_data.csv', 'baseline_2026.csv', 'algorithm_forecasts.json',
    'official_history.csv', 'category_mix.csv', 'monthly_tokens.csv', 'monthly_agents.csv',
    'monthly_resources.csv', 'monthly_tasks.csv',
    'dashboard_default.png', 'dashboard_tablet.png', 'dashboard_mobile.png', 'dashboard_dark.png', 'dashboard_compare.png',
    'dashboard_compute.png', 'dashboard_scenarios.png', 'dashboard_algorithms.png', 'dashboard_algorithms_mobile.png',
    'data_validation.json', 'qa_validation.json', 'algorithm_qa_validation.json', 'analysis_figure_validation.json',
    'artifact_validation.json', 'build_data.py', 'build_fragment.py',
    'build_analysis_figures.py', 'build_preview.py', 'validate_explorer.py', 'build_algorithm_data.py', 'validate_algorithms.py',
    'cdp_helper.py', 'qa_reference_forecasts_v1.json',
]
INFO = '''百人团队：2026公开基线与2027–2030资源预测

打开 resource-dashboard-preview.html 查看交互页面。
顶部“原始数据推演”按钮打开同目录 raw-data-dashboard.html；新页“返回资源探索”返回原入口并恢复参数选择。解压时保留两个HTML在同一目录。两页均内嵌数据、脚本和样式，可离线打开。
原始数据页沿用同一布局，通过“分析内容”切换四图：5团队Agent工作日、9档平均日峰值并发占比、18类研发任务、18类输出Token。历史保留全部原始观测日，预测每月18日一个点，直至2030-11-18；支持时间筛选、指针取值、原始数据CSV下载。
原始页保持研究员人均口径：工作日/任务为28日统计窗口，输出为官方14日窗口。资源页采用相同14日输出乘团队人数；同算法、日期与版本下两页可对应，已平滑的数据不重复处理。5团队独立统计不能加总；并发为研究员占比分布，不按百人规模放大，也不等于GPU或团队峰值并发。
原始页的总量算法为完整四图对应的6种：原OLS、历史拟合Holt、365天半衰期Holt、4倍上限Logistic/Gompertz，以及多模型融合与不确定性外推。并发独立提供原双门槛、保持末值、条件Logistic、九档对数比及原双门槛中心配条件趋势范围5种选择。没有重新拟合或改动原观测，单次按一种总量/并发模型展示，保留团队和类别颜色；原资源页仍可比较最多3种算法。
raw_research_data.json包含四图真实点与来源指纹。原始页浏览器检查见raw_qa_validation.json，四图及手机预览以raw_dashboard_*.png保存。
顶部：2026公开观测基线与口径说明；推演参数为情景、人数、服务窗口和模型，取值固定2030年11月18日。模型当前提供已接入的30T MoE模型；单份纯权重按该模型配置的FP8计算，已移除FP8/BF16切换，其他预测口径不变。
方案2：一张大图，先选择指标类别，再勾选同类曲线；默认只画输出Token。月度趋势统一使用实际单位、同一纵轴和共同刻度，从0开始，不做基线倍数归一化。
时间范围右侧外推算法下拉复选：至少1种、最多3种，默认原OLS，没有“全部”选项。16种候选包括原OLS、保持末值、统一水平OLS、单变化点线性、阻尼Holt、AutoARIMA、固定半衰期/饱和上限方案和多模型融合。选择满3种时需先取消一种再添加；算法选择随页面状态保存。
外推算法菜单中每行有“折线”复选框与“顶部”单选按钮：折线选择1–3种方法，影响月度趋势、图下读数及对应CSV；顶部从全部16种方法独立单选，显示其2030-11-18终点，顶部区域只读显示算法名称。顶部算法无需加入折线，选满3条曲线仍可切换顶部，取消曲线不改变顶部选择。各方法共享历史数据，预测用颜色与虚线区分；同一指标与情景下完全相同的算法曲线合并绘制、保留全部算法名称，CSV仍逐算法列出。多指标时保留指标颜色，以不同虚线区分算法。融合方案可显示名义80%/95%条件分位带，不代表已校准长期覆盖率。
新增算法数据来自归档CSV，可通过data_predict的预测更新入口刷新，不重新拟合。输出使用value的14日目标，output_tokens_28d仅保留为旧版参考；人均工作日×8得到Agent小时，小时÷24得到活动当量。输入、缓存和计算量沿用当前各月各情景的资源/输出比率，C仍逐月调整混合权重。条件半衰期和饱和上限属于假设，各算法曲线不是置信区间。
7类指标：Token用量（亿Token/日，5项）、理论计算量（EFLOP/日，3项）、平均计算速率（PFLOP/s）、Agent累计活动时长（万小时/日）、Agent平均活动规模（个活动当量）、研发任务量（项/日）、缓存命中率（%）。Token及计算量可以多选同类指标；其余类别可以勾选同一指标的A/B/C情景，顶部取值仍按全局增长情景计算。切换类别会重置为该类别默认指标，至少保留一条曲线。
同类曲线使用相同尺度，量级差大时可取消大值曲线查看小值变化。输入=缓存+未缓存，总Token=输入+输出；总计算=Prefill+Decode，避免重复加总。同值情景曲线会重合，页面显示说明。
分析内容保留月度趋势、2026–2030年度ABC情景比较、输入缓存分解、Prefill/Decode计算分解、2030年18类任务构成与资源增长倍数六种视图。年度情景比较每次选择当前类别中的一个指标，共15根柱；增长倍数仅保留为独立分析视图。
时间支持完整周期、观测期、预测期和自定义区间；顶部2030预测不会随图表时间改变。每月1点：历史取月内最后有效观测，月度趋势预测取所选算法的每月18日值，终点2030-11-18。不同指标真实观测日期保留；图下读数按月份并列展示各自日期。
月度折线从各指标首个数据月起每隔3个月标注实际数值，另保留当前区间终点；单位与纵轴一致。标签按曲线着色，密集时避让并以细引导线连接数据点。窄窗口或多线标注需要更多空间时，在图表内横向滑动，必要时增加图高；日期筛选仍可缩小查看范围。模块与卡片间距保持紧凑。
Agent平均活动当量=小时/24，活动时长与活动当量分别归类。资源及输入历史为条件估算。独立增长倍数视图使用原年度2026行作为各指标基线。窗口平均计算速率按EFLOP×1000/(窗口小时×3600)计算。
当前图全部数据可展开查看或下载CSV；月度数据同时保留原始值/单位和图表值/单位，缓存比例的0–1原始值会换算为图表百分数。页面数据、样式、脚本全部内嵌，离线打开即可使用，无需宿主或第三方图表服务。
team-resource-analysis-2026-2030.* 为默认100人、C情景的静态总览；PPTX含原生可编辑图表与嵌入的数据表。

2026最新公开基线：按官方人均统计乘100，非同一支真实百人团队的实测。
输出截至2026-08-15：官方14日均值72,283,322.89 Token/日；年度图、月度图和顶部基线均使用此口径。
时长/任务截至2026-10-18：4,560 Agent小时/日、2,630次任务/日、190平均在线活动当量。
2026输入、缓存、计算量是将此负载代入合成30T MoE的条件估算，非OpenAI实际资源消耗。
2027–2030各年11/18的年度参考延续原OLS方法，输出统一到14日目标，输入、缓存和计算量随之重新换算；任务及Agent保持28日窗口。
平均活动当量=Agent小时/24，不能解释为团队峰值、LLM请求或GPU执行并发。

数据：dashboard_data含全部15行情景及原月度序列；algorithm_forecasts包含16算法的2400个月度人均预测值；monthly_tokens/monthly_agents/monthly_resources/monthly_tasks为原月度CSV；baseline_2026保留原始/对齐口径；official_history为历史长表；category_mix为18类任务的输出构成。HTML内嵌绘图所需数据，完整原始档案保存在JSON与CSV。
来源链接、日期、单位与证据类型均保存在数据文件中。输入/缓存与FLOPs另依赖252条编码代理轨迹和合成模型。
复算脚本使用项目内原始档案；单独解压后的文件包可浏览页面、数据与图表，完整复算仍需原项目原始数据。
浏览器检查见qa_validation.json和algorithm_qa_validation.json。PPTX已检查OOXML、图表/数据表及页面边界，未进行Office应用渲染检查。
'''

if __name__ == '__main__':
    for name in FILES:
        assert (HERE/name).is_file(), name
    artifact_path = HERE/'artifact_validation.json'
    artifact = json.loads(artifact_path.read_text())
    artifact['annual_analysis_exports'] = json.loads((HERE/'analysis_figure_validation.json').read_text())
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2)+'\n')
    assert json.loads((HERE/'data_validation.json').read_text())['status']=='passed'
    assert json.loads((HERE/'analysis_figure_validation.json').read_text())['status']=='passed'
    browser_validation = json.loads((HERE/'qa_validation.json').read_text())
    assert browser_validation['status']=='passed'
    for file_path, digest in browser_validation['source_sha256'].items():
        assert hashlib.sha256(Path(file_path).read_bytes()).hexdigest()==digest, file_path
    algorithm_validation = json.loads((HERE/'algorithm_qa_validation.json').read_text())
    assert algorithm_validation['status']=='passed'
    for file_path, digest in algorithm_validation['source_sha256'].items():
        assert hashlib.sha256(Path(file_path).read_bytes()).hexdigest()==digest, file_path
    raw_validation = json.loads((HERE/'raw_qa_validation.json').read_text())
    assert raw_validation['status']=='passed'
    for file_path, digest in raw_validation['source_sha256'].items():
        assert hashlib.sha256(Path(file_path).read_bytes()).hexdigest()==digest, file_path
    dest = HERE/'team-resource-dashboard-2026-2030.zip'
    with zipfile.ZipFile(dest, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('阅读说明.txt', INFO)
        for name in FILES: archive.write(HERE/name, name)
    print(json.dumps({'archive':str(dest),'files':len(FILES)+1,'bytes':dest.stat().st_size}, ensure_ascii=False))
