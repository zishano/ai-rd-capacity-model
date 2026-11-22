"""Plot monthly OpenAI researcher-day usage from the bundled historical chart data.

CLI: python monthly_research_usage.py --chart all --output-dir output
Python: run(chart="workdays", output_dir="output")
Requires Matplotlib and a Chinese font for the chart labels.
Sources: https://openai.com/index/research-acceleration-jagged-frontier/
         https://openai.com/index/research-acceleration-view-inside-openai/
"""
import argparse
import csv
from datetime import date, timedelta
from io import StringIO
import json
from math import expm1, log1p
from pathlib import Path
from statistics import fmean, mean

import matplotlib.pyplot as plt
from matplotlib import dates as mdates, font_manager
from matplotlib.ticker import FuncFormatter, PercentFormatter, StrMethodFormatter
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
CHARTS = ('all', 'workdays', 'concurrency', 'tasks', 'output-tokens')


def source_rows(filename, data_dir):
    if data_dir is not None:
        with (Path(data_dir) / filename).open(encoding='utf-8', newline='') as stream:
            return list(csv.DictReader(stream))
    return list(csv.DictReader(StringIO(SNAPSHOTS[filename])))


def write_rows(path, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, rows[0].keys(), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


CUTOFF = date(2026, 10, 18)
END = date(2030, 11, 18)
BINS = ['0', '(0, 1)', '[1, 2)', '[2, 4)', '[4, 8)', '[8, 16)', '[16, 32)', '[32, 64)', '[64, ∞)']
COLORS = ['#93928E', '#E6F3FE', '#A6CEFB', '#5599F3', '#316BC2', '#774FCB', '#A581EE', '#CEB9F6', '#EFE7FA']
PANELS = [
    ('每名研究员的累计 Agent 工作日', '工作日 / 研究员日', [('workdays', '全部研究团队', '#007C78')]),
    ('研究员平均日峰值并发的分布', '研究员占比', [
        ('peak_ge4', '至少 4 个 Agent', '#007C78'), ('peak_ge16', '至少 16 个 Agent', '#CD621E')]),
    ('每名研究员每天发起的研发任务', '项 / 研究员日', [('task_starts', '18 类任务合计', '#007C78')]),
]


def history(source):
    series = {key: {} for _, _, panel in PANELS for key, _, _ in panel}
    for row in source:
        day = date.fromisoformat(row['date'])
        if day > CUTOFF:
            continue
        if row['workdays']:
            series['workdays'][day] = float(row['workdays'])
        if row['bin_0']:
            for threshold, start in [('peak_ge4', 4), ('peak_ge16', 6)]:
                series[threshold][day] = sum(float(row[f'bin_{i}']) for i in range(start, 9))
        if row['task1_1']:
            series['task_starts'][day] = sum(float(v) for k, v in row.items() if k.startswith('task'))
    return series


def trend(points, share):
    first = min(points)
    last = max(points)
    x = [(day - first).days for day in points]
    y = [log1p(-value) if share else value for value in points.values()]
    xm, ym = mean(x), mean(y)
    slope = sum((t - xm) * (v - ym) for t, v in zip(x, y)) / sum((t - xm) ** 2 for t in x)
    intercept = ym - slope * xm
    fitted_last = intercept + slope * (last - first).days

    def predict(day, slope_fraction=1.0):
        fitted = fitted_last + slope * (day - last).days * slope_fraction
        return -expm1(fitted) if share else fitted

    return predict


def concurrency_distribution(projections, usage_rows, results):
    rows = []
    for source in usage_rows:
        day = date.fromisoformat(source['date'])
        if day.day == 18 and day <= CUTOFF and source['bin_0']:
            values = [float(source[f'bin_{i}']) for i in range(9)]
            rows.append((day, 'observed', [v / sum(values) for v in values]))
    if rows[-1][0] != CUTOFF:
        raise ValueError('Missing concurrency bins at the forecast boundary')
    last = rows[-1][2]
    groups = [last[:4], last[4:6], last[6:]]
    for mode in ('full_slope', 'half_slope'):
        for a, b in zip(projections['peak_ge4'], projections['peak_ge16']):
            masses = [1 - a[mode], a[mode] - b[mode], b[mode]]
            values = [mass * v / sum(group) for group, mass in zip(groups, masses) for v in group]
            rows.append((a['date'], mode, values))
    write_rows(results / 'monthly_concurrency_bins.csv',
               [dict(date=day, scenario=mode, **dict(zip(BINS, values))) for day, mode, values in rows])
    return [(day, values) for day, mode, values in rows if mode != 'half_slope']


def edge_labels(ax, day, values, right):
    # Reserve a minimum gap for rounded-zero and narrow bands.
    centers = []
    top = 0.
    for value in values:
        centers.append(top + value / 2)
        top += value
    positions = []
    for center in centers:
        positions.append(max(center, positions[-1] + .078 if positions else .022))
    positions[-1] = min(positions[-1], .978)
    for i in range(7, -1, -1):
        positions[i] = min(positions[i], positions[i + 1] - .078)
    for i, (center, pos) in enumerate(zip(centers, positions)):
        share = '<0.1%' if 0 < values[i] < .0005 else f'{values[i]:.1%}'
        ax.annotate(f'{BINS[i]}  {share}', xy=(day, center), xytext=(1.015 if right else -.015, pos),
                    textcoords='axes fraction', va='center', ha='left' if right else 'right', fontsize=9,
                    arrowprops=dict(arrowstyle='-', color='#9AA8B5', lw=.65, shrinkB=1),
                    annotation_clip=False)


def draw_concurrency(ax, distribution, standalone=False):
    days, values = zip(*distribution)
    ax.stackplot(days, *zip(*values), colors=COLORS, linewidth=0)
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.set_yticks([0, .25, .5, .75, 1])
    ax.axvline(CUTOFF, lw=1.3, color='#24364A', ls='--')
    ax.text(CUTOFF, .97, '  预测 →', transform=ax.get_xaxis_transform(),
            size=9, color='#24364A', va='top', bbox=dict(facecolor='white', alpha=.85, edgecolor='none', pad=2))
    handles = [Line2D([], [], ls='', marker='o', markersize=8, markerfacecolor=c,
                      markeredgecolor='#55555D', markeredgewidth=.55) for c in COLORS]
    ax.legend(handles, BINS, ncol=9, frameon=False, loc='lower left', bbox_to_anchor=(0, 1.01),
              borderaxespad=0, handletextpad=.25, columnspacing=1.25, fontsize=9)
    if standalone:
        ax.set_xlim(days[0], days[-1])
        ax.tick_params(axis='y', left=False, labelleft=False)
        edge_labels(ax, days[0], values[0], False)
        edge_labels(ax, days[-1], values[-1], True)


def monthly_ticks(ax):
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonthday=18))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.tick_params(axis='x', labelrotation=90, labelsize=8)


TEAMS = (
    ('Pretraining', '预训练', '#54B65B'), ('Posttraining', '后训练', '#A581EF'),
    ('Overall Research', '全部研究团队', '#5499FF'),
    ('Scaling / Infrastructure', '扩展与基础设施', '#EF79AB'), ('Other', '其他', '#91918D'),
)
# Source columns task1_1 through task6_4, in the stack's bottom-to-top order.
TASK_GROUPS = (
    ('决策', [('工作方向', '#FFB1A7'), ('继续或停止的工作', '#FC7161'), ('算力与人员配置', '#CD343B')]),
    ('设计', [('研究与实验规划', '#FFCA51'), ('技术规格', '#BC842B')]),
    ('构建', [('研究与基础设施代码', '#A4CDF9'), ('训练与评估数据集', '#356CC9')]),
    ('运行', [('启动、监控与调试运行', '#F6C5DD'), ('计算集群运维', '#EC80B4'), ('生产推理服务可靠性', '#AA517B')]),
    ('分析', [('分析实验结果', '#EEE7F9'), ('分析模型行为与能力', '#CAB3EF'), ('分析生产使用情况', '#A887EB'), ('评阅外部研究', '#7951C9')]),
    ('沟通', [('研究文档与撰写', '#DDF3DF'), ('技术协助与评审', '#A1DCB0'), ('状态更新与工作日志', '#58B75D'), ('传达决策', '#398845')]),
)


def monthly_components(source, keys, dates, output):
    data = {}
    table = []
    for key in keys:
        observed = {date.fromisoformat(r['date']): float(r[key]) for r in source
                    if r[key] and r['date'] <= CUTOFF.isoformat()}
        predict = trend(observed, False)
        data[key] = {}
        for day, value in observed.items():
            if day.day == 18:
                data[key][day] = value
                table.append(dict(date=day, series=key, observed=value, full_slope='', half_slope=''))
        for day in dates:
            data[key][day] = predict(day)
            table.append(dict(date=day, series=key, observed='', full_slope=predict(day),
                              half_slope=predict(day, .5)))
    write_rows(output, table)
    return data


def forecast_boundary(ax):
    ax.axvline(CUTOFF, lw=1, color='#536777', ls=':')
    ax.annotate('预测 →', (CUTOFF, .98), xycoords=('data', 'axes fraction'),
                xytext=(4, -2), textcoords='offset points', va='top', fontsize=9, color='#455969')


def draw_workdays(ax, teams):
    for key, label, color in TEAMS:
        days, values = zip(*teams[key].items())
        overall = key == 'Overall Research'
        ax.plot(days, values, color=color, lw=2.1 if overall else 1.6,
                ls='-' if overall else (0, (4, 3)), label=label)
        ax.scatter(days[-1], values[-1], s=27, color=color, zorder=3, clip_on=False)
        ax.annotate(f'{values[-1]:.2f}×', (days[-1], values[-1]), xytext=(6, 0),
                    textcoords='offset points', va='center', color=color, fontsize=10)
    handles = [Line2D([], [], color=c, ls='', marker='o', label=label) for _, label, c in TEAMS]
    ax.legend(handles=handles, frameon=False, ncol=5, bbox_to_anchor=(0, 1.01), loc='lower left',
              borderaxespad=0, handlelength=1, handletextpad=.35)
    ax.yaxis.set_major_formatter(StrMethodFormatter('{x:.2f}×'))
    ax.set_ylabel('Agent 工作日 / 研究员日')
    forecast_boundary(ax)


def draw_tasks(ax, tasks):
    keys = list(tasks)
    days = list(tasks[keys[0]])
    parts = [list(tasks[k].values()) for k in keys]
    colors = [color for _, items in TASK_GROUPS for _, color in items]
    ax.stackplot(days, *parts, colors=colors, linewidth=0)
    total = sum(v[-1] for v in parts)
    ax.set_ylim(0, total * 1.10)
    ax.annotate(f'合计 {total:.1f}', (days[-1], total), xytext=(-3, 5),
                textcoords='offset points', ha='right', fontsize=9, color='#24364A')
    ax.set_ylabel('研发任务数 / 研究员日')
    forecast_boundary(ax)
    # Label groups outside the data area in the same vertical order as the bands.
    y = .99
    step = .96 / (len(keys) + 1.55 * len(TASK_GROUPS))
    offset = len(keys)
    upper = total
    for group, items in reversed(TASK_GROUPS):
        offset -= len(items)
        mass = sum(v[-1] for v in parts[offset:offset + len(items)])
        center = upper - mass / 2
        upper -= mass
        accent = items[-1][1]
        ax.annotate('', xy=(days[-1], center), xytext=(1.055, y - step * len(items) / 2),
                    textcoords='axes fraction', annotation_clip=False,
                    arrowprops=dict(arrowstyle='-', lw=.8, color=accent,
                                    connectionstyle='angle3,angleA=180,angleB=90'))
        ax.text(1.068, y, group, weight='bold', fontsize=10, transform=ax.transAxes, va='center')
        for label, color in reversed(items):
            y -= step
            ax.plot(1.075, y, 'o', ms=6, mec='#555', mew=.45, color=color,
                    transform=ax.transAxes, clip_on=False)
            ax.text(1.089, y, label, fontsize=9, va='center', transform=ax.transAxes)
        y -= step * 1.55


TITLES = ['累计 Agent 工作日 / 研究员日', '研究员平均日峰值并发的分布', '发起的研发任务 / 研究员日']


def configure_fonts():
    font = Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    if font.exists():
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=font).get_name()
    else:
        families = ('Noto Sans CJK SC', 'Microsoft YaHei', 'PingFang SC', 'WenQuanYi Zen Hei', 'SimHei')
        available = {font.name for font in font_manager.fontManager.ttflist}
        for family in families:
            if family in available:
                plt.rcParams['font.family'] = family
                break
    plt.rcParams.update({'pdf.fonttype': 42, 'axes.unicode_minus': False})


def render_overview(teams, distribution, tasks, tokens, figures):
    fig = plt.figure(figsize=(15.2, 21))
    grid = fig.add_gridspec(4, 1, height_ratios=[1, .95, 1.9, 2],
                            left=.085, right=.79, top=.925, bottom=.055, hspace=.48)
    first = fig.add_subplot(grid[0])
    concurrency = fig.add_subplot(grid[1], sharex=first)
    starts = fig.add_subplot(grid[2], sharex=first)
    bottom = grid[3].subgridspec(2, 1, height_ratios=[.48, 1], hspace=.12)
    legend = fig.add_subplot(bottom[0])
    output = fig.add_subplot(bottom[1], sharex=first)
    fig.suptitle('OpenAI 研究员的 Agent 使用量', x=.085, y=.982, ha='left', fontsize=22)
    fig.text(.085, .96, '预测至 2030 年 11 月 18 日  ·  前三图为 28 天窗口，输出 Token 为 14 天窗口', fontsize=11)
    draw_workdays(first, teams)
    draw_concurrency(concurrency, distribution)
    concurrency.set_ylabel('研究员占比')
    draw_tasks(starts, tasks)
    for ax, title, pad in zip((first, concurrency, starts), TITLES, [30, 30, 12]):
        ax.set_title(title, loc='left', fontsize=15, pad=pad)
        ax.spines[['top', 'right']].set_visible(False)
        ax.set_ylim(bottom=0)
        ax.tick_params(labelbottom=False)
    legend.set_title('编码智能体输出 Token / 研究员日', loc='left', fontsize=15, pad=12)
    draw_token_legend(legend)
    draw_token_stack(output, *tokens)
    monthly_ticks(output)
    fig.savefig(figures / 'monthly_research_usage.pdf')
    fig.savefig(figures / 'monthly_research_usage.png', dpi=175)
    plt.close(fig)


def render_series(name, title, data, draw, right, figures):
    fig, ax = plt.subplots(figsize=(14, 7.4))
    fig.subplots_adjust(left=.085, right=right, top=.81, bottom=.16)
    fig.suptitle(title, x=.055, y=.97, ha='left', fontsize=20, weight='bold')
    fig.text(.055, .90, '每月 18 日 · 28 天窗口    |    竖线右侧为延续历史趋势的预测', fontsize=11)
    draw(ax, data)
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_xlim(min(next(iter(data.values()))), END)
    ax.set_ylim(bottom=0)
    monthly_ticks(ax)
    for ext in ('png', 'pdf'):
        fig.savefig(figures / f'{name}.{ext}', dpi=175)
    plt.close(fig)


def render_concurrency(distribution, figures):
    fig, ax = plt.subplots(figsize=(14, 5.8))
    fig.subplots_adjust(left=.105, right=.875, bottom=.17, top=.78)
    fig.suptitle('研究员的 Agent 平均日峰值并发分布', x=.04, y=.97, ha='left', fontsize=20)
    fig.text(.04, .895, '每月 18 日 · 28 天窗口    |    纵向色带为有记录活动研究员的占比', fontsize=11)
    draw_concurrency(ax, distribution, standalone=True)
    monthly_ticks(ax)
    ax.spines[['top','right','left']].set_visible(False)
    ax.grid(axis='y', color='white', alpha=.25)
    base = figures / 'monthly_concurrency'
    fig.savefig(base.with_suffix('.png'), dpi=175)
    fig.savefig(base.with_suffix('.pdf'))
    ax.patch.set_gid('plot-area')
    svg = StringIO()
    fig.savefig(svg, format='svg')
    payload = json.dumps([[day.isoformat(), values] for day, values in distribution])
    html = HTML_TEMPLATE
    base.with_suffix('.html').write_text(html.replace('{{svg}}', svg.getvalue()[svg.getvalue().index('<svg'):])
                                        .replace('{{series}}', payload).replace('{{bins}}', json.dumps(BINS))
                                        .replace('{{cutoff}}', CUTOFF.isoformat()))
    plt.close(fig)



# September chart uses the same taxonomy as the task starts chart, with its own palette.
TOKEN_COLORS = ('#FFB684', '#F88C49', '#BD5A27', '#FFD274', '#B78932',
                '#599CF4', '#346CC6', '#EF79AB', '#AB507B', '#693249',
                '#A581EB', '#7951C9', '#6342A5', '#493777',
                '#58B75D', '#398443', '#306735', '#214928')


def monthly_output_tokens(output_rows, usage_rows, results):
    groups = [(f'task{g}_{i}', group, name) for g, (group, items) in enumerate(TASK_GROUPS, 1)
              for i, (name, _) in enumerate(items, 1)]
    observed = {date.fromisoformat(r['date']): {k: float(r[k]) for k, _, _ in groups}
                for r in output_rows}
    start, cutoff = min(observed), max(observed)
    months = [date(y, m, 18) for y in range(start.year, END.year+1) for m in range(1, 13)
              if start <= date(y, m, 18) <= END]
    plotted_days = sorted(observed) + [d for d in months if d > cutoff]
    bands, joined = [], []
    for key, group, label in groups:
        tokens = {d: row[key] for d, row in observed.items()}
        starts = {date.fromisoformat(r['date']): float(r[key]) for r in usage_rows
                  if r[key] and r['date'] <= CUTOFF.isoformat()}
        fitted_output = trend(tokens, False)
        fitted_starts = trend(starts, False)
        last_starts = max(starts)
        fitted_end = fitted_output(cutoff)

        def output_at(day, fraction):
            if day <= cutoff:
                return tokens.get(day)
            return max(0., tokens[cutoff] + fitted_output(day, fraction) - fitted_end)

        bands.append([output_at(d, 1) for d in plotted_days])
        for day in months:
            lag = day - timedelta(days=14)
            for mode, fraction in [('full_slope', 1.), ('half_slope', .5)]:
                value = output_at(day, fraction)
                previous = output_at(lag, fraction)
                aligned = (value + previous)/2 if previous is not None else None
                count = starts.get(day) if day <= last_starts else fitted_starts(day, fraction)
                joined.append(dict(date=day, series=key, group=group, category=label, scenario=mode,
                                   output_source='observed' if day <= cutoff else 'forecast',
                                   output_tokens_14d=value, output_tokens_28d=aligned,
                                   output_28d_source=('observed' if day <= cutoff else
                                                      'mixed' if lag <= cutoff else 'forecast'),
                                   starts_source=('forecast' if day > last_starts else
                                                  'observed' if count is not None else 'unavailable'),
                                   task_starts_28d=count,
                                   output_per_start_28d=aligned/count if count and aligned is not None else None))
    write_rows(results/'monthly_output_and_task_starts.csv', joined)

    return plotted_days, bands, cutoff


def draw_token_legend(ax):
    ax.set_axis_off()
    offset = 0
    for g, (group, items) in enumerate(TASK_GROUPS, 1):
        x = .006 + (g-1)/6
        ax.text(x, .96, group, transform=ax.transAxes, va='top', weight='bold', fontsize=11)
        for i, (label, _) in enumerate(items, 1):
            y = .74 - (i-1)*.21
            ax.plot(x, y, 'o', ms=5, mfc=TOKEN_COLORS[offset], mec='#444',
                    mew=.5, transform=ax.transAxes, clip_on=False)
            ax.text(x+.009, y, f'{g}.{i} {label}', transform=ax.transAxes, va='center', fontsize=9)
            offset += 1


def draw_token_stack(ax, plotted_days, bands, cutoff):
    ax.stackplot(plotted_days, *bands, colors=TOKEN_COLORS, linewidth=0)
    totals = [sum(v) for v in zip(*bands)]
    ax.plot(plotted_days, totals, color='#1C3868', lw=2.1)
    ax.set(xlim=(plotted_days[0], END), ylim=(0, max(totals)*1.10), ylabel='输出 Token / 研究员日')
    ax.axvline(cutoff, color='#536777', lw=1.05, ls=':')
    ax.annotate(f'{cutoff:%Y-%m-%d} 观测截止  ·  预测 →', (cutoff,.96),
                xycoords=('data','axes fraction'), xytext=(5,0), textcoords='offset points',
                fontsize=9, color='#42536A')
    ax.annotate(f'{totals[-1]/1e4:,.2f} 万', (END, totals[-1]), xytext=(-3,7),
                textcoords='offset points', ha='right', color='#1C3868', fontsize=10)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f'{y/1000:,.0f} k' if y else '0'))
    ax.spines[['top','right']].set_visible(False)


def render_output_tokens(tokens, figures):
    fig, ax = plt.subplots(figsize=(15.6, 8.2))
    fig.subplots_adjust(left=.091, right=.975, top=.62, bottom=.145)
    fig.suptitle('研究人员正在以全新方式使用编码智能体', x=.045, y=.977,
                 ha='left', fontsize=20, weight='bold')
    fig.text(.046, .905, '每名研究员每日输出 Token  ·  14 天滚动均值', fontsize=12)
    draw_token_legend(fig.add_axes([.04, .66, .94, .21]))
    draw_token_stack(ax, *tokens)
    monthly_ticks(ax)
    for ext in ('png','pdf'):
        fig.savefig(figures/f'monthly_output_tokens.{ext}', dpi=175)
    plt.close(fig)


def run(chart='all', output_dir=None, data_dir=None):
    """Write figures/ and results/ under output_dir. Use data_dir to supply updated source CSVs."""
    if chart not in CHARTS:
        raise ValueError(f'Unknown chart {chart!r}. Choose from {CHARTS}.')
    root = HERE if output_dir is None else Path(output_dir)
    figures, results = root / 'figures', root / 'results'
    figures.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)
    dates = [date(y, m, 18) for y in range(CUTOFF.year, END.year + 1)
             for m in range(1, 13) if CUTOFF < date(y, m, 18) <= END]
    with plt.rc_context():
        configure_fonts()
        if chart in ('all', 'workdays'):
            teams = monthly_components(source_rows('observed_workdays_by_team.csv', data_dir),
                                       [key for key, _, _ in TEAMS], dates, results / 'monthly_workdays_by_team.csv')
            render_series('monthly_workdays', TITLES[0], teams, draw_workdays, .92, figures)
        if chart in ('all', 'concurrency', 'tasks', 'output-tokens'):
            usage = source_rows('observed_openai_research_usage.csv', data_dir)
        if chart in ('all', 'output-tokens'):
            tokens = monthly_output_tokens(source_rows('calibration/observed_output_tokens.csv', data_dir),
                                           usage, results)
            render_output_tokens(tokens, figures)
        if chart in ('all', 'tasks'):
            keys = [f'task{g}_{i}' for g, (_, items) in enumerate(TASK_GROUPS, 1)
                    for i in range(1, len(items) + 1)]
            tasks = monthly_components(usage, keys, dates, results / 'monthly_tasks_by_type.csv')
            render_series('monthly_tasks', TITLES[2], tasks, draw_tasks, .76, figures)
        if chart in ('all', 'concurrency'):
            projections = forecast(history(usage), dates, results, chart)
            distribution = concurrency_distribution(projections, usage, results)
            render_concurrency(distribution, figures)
        if chart == 'all':
            render_overview(teams, distribution, tasks, tokens, figures)
    return root


def forecast(source, dates, results, chart):
    rows = []
    validation = []
    projections = {}
    for key, observed in source.items():
        share = key.startswith('peak_')
        if chart == 'concurrency' and not share:
            continue
        predict = trend(observed, share)
        projections[key] = [dict(date=d, metric=key, observed='', full_slope=predict(d),
                                 half_slope=predict(d, .5)) for d in dates]
        rows.extend(dict(date=d, metric=key, observed=v, full_slope='', half_slope='')
                    for d, v in observed.items() if d.day == 18)
        rows.extend(projections[key])
        train = {d: v for d, v in observed.items() if (CUTOFF - d).days >= 55}
        held = {d: v for d, v in observed.items() if (CUTOFF - d).days < 28}
        test_predict = trend(train, share)
        validation.append(dict(metric=key, chart_dates=len(observed), holdout_dates=len(held),
                               trend_mae=fmean(abs(test_predict(d) - v) for d, v in held.items()),
                               last_value_mae=fmean(abs(train[max(train)] - v) for v in held.values())))
    for a, b in zip(projections['peak_ge4'], projections['peak_ge16']):
        for k in ('full_slope', 'half_slope'):
            assert 0 <= b[k] <= a[k] <= 1
    if chart == 'all':
        write_rows(results / 'monthly_research_usage.csv', rows)
        write_rows(results / 'monthly_research_validation.csv', validation)
    return projections


# Embedded snapshots preserve the exact decimal values and blank cells from the public charts.
SNAPSHOTS = {
    'calibration/observed_output_tokens.csv': '''date,task1_1,task1_2,task1_3,task2_1,task2_2,task3_1,task3_2,task4_1,task4_2,task4_3,task5_1,task5_2,task5_3,task5_4,task6_1,task6_2,task6_3,task6_4
2026-01-20,0,0,0,0,0,7101.38316470767,0,0,350,0,0,37.5214408233276,0,0,540.169150901254,3185.46312178388,0,0
2026-01-21,614.153656532457,0,0,0,0,18730.0876382289,177.362366474938,349.835661462613,175,0,0,18.7607204116638,0,0,628.630179394752,5603.88603911708,145.994248151191,0
2026-01-22,409.435771021638,0,0,0,0,22526.8044281403,1636.29256449206,1297.10809448385,478.344298245614,0,0,12.5071469411092,0,0,626.241391526326,6014.58098395004,97.329498767461,0
2026-01-23,307.076828266228,0,0,0,0,21712.5155708354,1818.79791394917,2861.84608713154,369.346217105263,5.42763157894737,0,9.3803602058319,0,0,1146.0893495658,8006.51550769937,80.9329793387536,0
2026-01-24,245.661462612983,0,0,0,151.134868421053,19441.5585092999,1507.21760747513,2289.47686970523,611.381578947368,4.34210526315789,513.700657894737,7.50428816466552,0,0,1445.95024096924,6916.51193431658,64.7463834710029,0
2026-01-25,204.717885510819,0,0,0,126.014254385965,20808.0783590146,1256.01467289594,2069.3146063333,572.155975877193,3.61842105263158,448.183936403509,361.407082242484,0,0,1801.24910831495,5807.88001105329,69.2993436819761,0
2026-01-26,175.472473294988,0,0,0,250.159690927642,21946.7669564544,1076.58400533938,3307.12667036519,509.422728525456,3.18804887825379,384.157659774436,309.777499064987,0,0,1645.00096660091,5803.71367667942,72.0638731675189,0
2026-01-27,153.538414133114,0,0,0,374.831773180427,24515.3682859126,942.011004671954,2963.79338907358,755.51882730393,2.78954276847207,535.28981013785,271.055311681863,0,0,1641.6046261412,6153.34033946929,63.055889021579,0
2026-01-28,136.478590340546,0,0,0,333.183798382602,25683.212632182,1085.78951839786,3321.26631023065,1105.77367982572,91.3729340278156,1139.98695374077,240.938054828323,0,0,1647.03352807992,6842.70767727424,56.0496791302924,0
2026-01-29,122.830731306491,0,0,13.356,790.793418544342,26963.6233689638,977.210566558076,3785.60367920758,995.196311843144,379.479640625034,1029.28825836669,513.268249345491,0,0,1650.21817527193,6560.11690954682,50.4447112172632,0
2026-01-30,111.664301187719,0,0,12.1418181818182,883.568562313038,26601.9967333519,888.798696870978,3787.06516291599,1087.56028349377,344.981491477304,973.720234878809,593.760226677719,0,0,1616.04195986295,6451.20717386017,45.8588283793302,0
2026-01-31,102.358942755409,0,0,11.13,860.314214361159,25807.0343591327,891.44410256072,3670.4105853242,1020.99767260576,316.352937930934,897.952581412689,779.450554734107,0,0,1481.37179654104,6694.26538232679,42.0372593477193,0
2026-02-01,94.4851779280703,0,0,10.2738461538462,921.599948179039,24427.9965772497,822.871479286818,3501.56049606235,1029.03237610723,292.018096551631,828.879305919406,839.81415177717,0,0,1683.21638432247,6355.60291865801,38.8036240132794,0
2026-02-02,87.7362366474938,0,0,9.54,855.771380451965,27063.0996841075,824.380204740647,4167.7616728303,972.929768040016,327.285357185487,852.018225822764,779.827426650229,0,0,1759.17655052924,6453.06576141561,36.0319365837594,0
2026-02-03,87.7362366474938,0,0,9.54,1097.80417846451,28850.757826658,1118.61534509751,4189.96590058346,1072.67689839574,327.285357185487,939.50628217151,777.147323734277,0,0,1825.62202031655,6909.99656208762,90.7597465621661,0
2026-02-04,0,0,0,9.54,1132.74120331416,28094.931439644,1752.50287268267,4338.19821361928,1294.93379162165,336.640854745909,1113.44376153514,777.147323734277,0.187223419947804,0,1960.65731869784,7284.64133096591,69.9034253977102,0
2026-02-05,0,0,0,9.54,1404.33133936858,29883.9053687805,1505.79466801923,4553.05180033906,1343.84584109056,336.827929575841,1233.20283182993,1099.48575910843,0.187223419947804,0,2245.1360937605,7809.8412572269,119.157960545102,0
2026-02-06,0,0,0,9.54,1404.33133936858,30534.4932452334,1384.37633933219,4285.99464391941,1486.04650290445,335.277177696142,1248.42466321538,1099.48575910843,0.187223419947804,0,2220.99606036561,7203.05073638299,139.870829766408,0
2026-02-07,0,0,0,9.54,1579.09623232725,33502.5574167413,1365.74088350512,4416.47870368794,1892.98684727461,335.277177696142,1528.91705107317,1099.829002045,0.187223419947804,0,2058.3016996208,7512.85565381336,165.401296122927,0
2026-02-08,0,0,0,9.54,1579.0668620265,33888.0723884902,1365.74088350512,4347.29989729696,2282.87285644841,416.353428688994,2504.77454488091,947.620355428457,9.04913196414388,0,2068.7987495862,7900.14812079545,177.85399337564,0
2026-02-09,0,0,0,9.54,1548.35794618935,32790.6497026825,1544.32919826365,4158.88909603284,2506.83961896317,479.579884824826,2519.88509613243,1053.97800487121,9.04913196414388,0,2157.56075124901,8122.07238304471,186.840361575994,0
2026-02-10,0,0,0,9.54,1459.24820697864,34599.6372543314,1563.00186418041,4819.41964315355,2901.22920114447,529.900469751711,2558.63586446415,1053.97800487121,9.04913196414388,0,2205.51357590266,8380.27314219638,187.017526930325,0
2026-02-11,0,0,0,9.54,1879.7691691007,36733.1938835205,1403.61789174877,4801.86355271251,2873.97115419044,478.262225316825,2133.00452949962,1327.13062007791,109.026652476676,0,2111.61222212596,8952.89714573206,194.778569978543,0
2026-02-12,0,0,0,0,1598.5048968635,37259.1704905718,1453.26692589072,4700.01505421001,3202.93847224974,340.980657648585,2258.70500119773,1467.93176113811,109.026652476676,0,2016.32440990674,9462.98701545354,206.761948235507,0
2026-02-13,0,0,0,0,1469.1248968635,37350.8222789687,1831.79045688803,4881.96491045439,3071.98629345369,388.397548933401,2305.18428691202,1368.02604685239,109.223193357179,0,2066.69312548718,9740.61292657049,214.017114452937,0
2026-02-14,0,0,0,0,1491.04230229226,37180.632804309,1766.03734509175,4993.77525328525,3137.33810230311,388.294774010482,2300.57654453449,1166.45146375565,252.341454812705,0,2066.69312548718,9714.33956520568,214.017114452937,0
2026-02-15,0,0,0,0,1372.68310557843,37243.389489866,2066.07946099472,5240.32696102905,3056.94890100848,388.294774010482,2300.57654453449,1054.7245125918,252.341454812705,0,2075.43879997314,9915.91565083614,228.979490912955,0
2026-02-16,0,0,0,0,1372.68310557843,35052.4752435618,2033.52857630612,4918.81621757807,3039.5491964966,332.169077908652,2243.59189295832,1054.7245125918,252.341454812705,0,2720.7779098862,9574.7685594244,228.979490912955,0
2026-02-17,50.9920634920635,0,0,0,1174.51907573043,37198.6048559309,2070.00512598583,5445.8434899367,3123.52064246945,332.169077908652,2185.08885784811,1054.7245125918,255.619456154087,0,2800.78134604278,9540.78341094533,244.917341564998,0
2026-02-18,50.9920634920635,0,0,0,1146.53796605935,41004.2051390377,1423.7070147971,6248.6739982964,3275.08610008907,465.581437491087,2197.99847669876,1054.7245125918,348.54049166271,0,2707.73028431304,9885.29804875921,244.917341564998,0
2026-02-19,50.9920634920635,0,0,0,1076.51591036207,39826.8385970938,1526.49678339497,6112.68392778903,3148.6717009961,494.71913944687,2083.11663854684,732.386077217649,365.80611666271,0,2732.76469651542,9521.15006657801,257.85867695332,0
2026-02-20,50.9920634920635,0,0,0,1141.0803555609,41220.4993543,1478.89268620197,6504.07325353156,3070.16811404203,494.71913944687,2133.16029388705,732.386077217649,365.80611666271,0,2967.76255676703,9854.28970875739,234.878420513969,0
2026-02-21,50.9920634920635,0,0,0,1220.6536022066,39326.5382331826,1478.89268620197,6807.31141127396,2758.47391014608,494.71913944687,1669.20338535257,732.042834281078,365.80611666271,0,2943.00579111357,9596.57497823104,209.34795415745,0
2026-02-22,50.9920634920635,0,0,0,1236.32044086033,37720.3154746571,1478.89268620197,6807.31141127396,2378.33733694936,413.642888454018,763.254283549617,732.042834281078,356.944208118514,0,2787.18838271408,9423.90406525938,190.319246566391,0
2026-02-23,50.9920634920635,0,0,0,1301.90135050362,40638.0503299609,1730.57743038769,7523.60296709747,2177.26829845398,350.373159758757,1355.32835115837,625.685184838323,361.56739817666,0,2822.08923437909,9446.36010542395,284.694538054145,0
2026-02-24,156.293625457632,0,0,0,1307.12880461376,40125.049924959,1996.37631845566,6928.71720501874,2087.01028775839,538.831900010323,1447.23553386186,625.685184838323,367.752553803157,0,2907.96999230537,10654.8341380931,400.213986540881,0
2026-02-25,156.293625457632,0,0,0,1057.73979453751,38759.3459150072,2153.59860089079,7704.37785032138,2110.60372303441,533.32442558074,1553.79482975436,429.46000727335,372.638978868856,0,2943.48214104108,12760.7714641078,419.232988844137,0
2026-02-26,164.035030200625,0,0,0,1335.62930676109,40421.8297959066,2192.10343035941,8130.4348475013,1888.67430353406,458.288850391837,1429.16397112785,92.0131065399419,418.44063551245,0,3040.81466448237,14009.672721227,407.368752763504,0
2026-02-27,164.035030200625,0,0,0,1573.32794955601,43039.7529859396,2049.89885318033,8178.50722217449,2244.43070336721,410.871959107021,1407.67179749635,380.793884935494,418.244094631947,0,3376.36111200453,15532.5201590105,503.28503781125,0
2026-02-28,164.035030200625,0,0,0,2172.72626705911,46561.5242200856,2169.02300284019,8745.93792830174,2158.44968360081,917.555632576408,1871.04645433478,380.793884935494,275.125833176422,26.5127883768977,3512.35034102947,17157.9199544144,504.206239625309,0
2026-03-01,164.035030200625,0,0,0,2520.19709520005,49147.2402851559,2114.15279537415,8970.68819096668,2158.44968360081,917.555632576408,2156.55682025751,658.713903061698,275.284437458737,26.5127883768977,3501.72134475019,17785.604949548,489.243863165291,0
2026-03-02,371.60872634575,0,0,0,2870.67328567624,51697.4405579734,2447.3578689914,8991.00215904935,2615.27143330403,962.26084799591,2199.03517105966,887.081250000473,275.284437458737,26.5127883768977,2879.75530198256,19648.2733654873,554.144656816085,0
2026-03-03,341.820955381508,0,0,0,2920.82280050056,51668.0708357277,2198.03103019262,9559.76627854576,2535.87093555825,962.547584312058,3065.29770830397,930.77872899207,272.006436117356,26.5127883768977,3026.05724449262,20853.4243174731,502.942998002578,0
2026-03-04,363.589005723747,0,0,89.6086332523736,3836.61197253771,56498.6252657478,2734.25753835971,9092.63464434504,2616.39744903151,819.779727169201,3586.27909460929,1064.48926111837,304.775854380217,26.5127883768977,3285.50249756372,22258.4126995174,598.306943566718,0
2026-03-05,363.589005723747,0,0,89.6086332523736,3678.03361707285,60370.5431910596,2837.29343479792,10570.6982691711,2975.03090294559,1027.54477471229,3620.50803857957,1141.54428266295,289.250368591354,26.5127883768977,3343.05633527848,24397.5871114064,791.765144404333,0
2026-03-06,373.95222996081,0,0,89.6086332523736,3624.00101619069,62447.7724347143,2956.38343922074,10383.1623402244,3034.93407410523,1090.06688882109,3803.21358237138,1141.54428266295,289.250368591354,26.5127883768977,3298.48952318293,26384.9507522669,1220.40728040294,36.5269792127377
2026-03-07,394.136882769302,0,0,89.6086332523736,3322.04117988133,64024.8850068872,2956.38343922074,10527.9507374857,2843.2293008358,1090.06688882109,3980.65166286673,1359.64744498051,289.250368591354,26.5127883768977,3401.25197210966,27838.028597604,1220.71411366256,36.5269792127377
2026-03-08,394.136882769302,0,0,89.6086332523736,3306.91337262963,66571.5129910873,3147.51844585498,10851.5188489408,2806.78658063714,1090.06688882109,4152.85043445106,1359.64744498051,482.267838737307,26.5127883768977,3441.10768376156,28530.85016887,1220.71411366256,36.5269792127377
2026-03-09,399.85944206329,0,0,135.127110913708,3218.01397442856,67496.1814745459,2965.0746735563,11179.6075514947,2797.82624759859,1133.34598424304,4448.9386185908,1359.64744498051,496.108520714462,26.6644706714371,3693.92148842435,29590.2152850778,1142.58670053515,36.5269792127377
2026-03-10,294.886573059825,0,0,135.127110913708,3351.34579553663,67630.9560001854,2680.73846373245,11716.9969437204,2991.29429859947,938.512079460131,4432.93778735187,1515.05844928942,489.923365087965,26.6644706714371,3617.97248129588,30575.247459114,1431.49453995619,36.5269792127377
2026-03-11,294.886573059825,0,0,135.127110913708,3868.42149497246,70073.7496746621,2846.16946069263,11762.3855948947,2850.8222589064,1575.04735146367,4620.57667624076,1599.72156892324,385.230803852945,26.6644706714371,4305.14216629049,29488.4396548896,1443.86752423762,36.5269792127377
2026-03-12,292.334943684764,0,0,135.127110913708,3521.13339784322,71633.870615145,2877.51321797395,12555.690059169,3092.53394538673,1622.18965532557,5258.47822742947,1637.18375882772,395.700586846398,26.6644706714371,4773.1603033588,28920.6664647127,1949.04328081087,36.5269792127377
2026-03-13,292.334943684764,0,0,135.127110913708,3283.4347550483,74321.1706973385,3143.4169222716,12775.6963621993,2810.12134310239,1744.88425948302,5356.66074825247,1348.40298043217,545.49857711502,26.6644706714371,4384.78939561561,28827.5616276694,2077.34849916091,36.5269792127377
2026-03-14,292.334943684764,0,0,166.473860139715,2618.93929019569,72767.4089757792,3100.92368813584,13323.1511547105,2956.78211267338,1238.20058601363,5203.92839705213,1388.31341829152,571.164764642662,0.151682294539437,4333.27882647567,27344.9774242421,2077.74308682054,36.5269792127377
2026-03-15,298.52689414916,0,0,166.473860139715,2271.46846205476,70917.1941834002,3300.12650327256,13123.235411118,2988.71488578262,1238.20058601363,5153.4628116691,1110.65324094374,571.006160360347,0.151682294539437,4352.24175588133,27163.6312965671,2208.68072503372,36.5269792127377
2026-03-16,95.662622377033,0,0,166.473860139715,1933.2395370741,69895.2742522159,3115.69793743069,12741.9597346471,2624.40777534578,1537.33767222087,5236.87577078782,1381.62850808075,571.006160360347,0.151682294539437,4264.01509722094,26804.9476435727,2283.0021167768,36.5269792127377
2026-03-17,87.9373278802765,0,0,166.845770006265,1883.39922389489,68454.5757857416,3358.80663280841,13334.8030677448,3035.36453629076,1700.0267617634,4564.85291450248,1547.74015181941,857.283780137201,0.151682294539437,4232.36251307107,26736.0581525345,2778.04592127546,36.5269792127377
2026-03-18,79.9004733215008,0,0,81.2175913492572,1080.30660181588,67658.8763832818,4324.13384662372,14328.0457025661,3194.17885764977,1700.0267617634,4255.14165181428,1626.41020605526,769.267089000451,0.151682294539437,4394.29166716842,25741.0731358095,3007.27063486008,36.5269792127377
2026-03-19,104.432980388254,0,0,81.2175913492572,1265.99158881749,66687.5419346461,4408.26453855965,12703.4445024859,3168.70750419232,1463.23319749113,4930.78009265221,1671.97966809406,767.526949789314,0.151682294539437,4337.35980994535,24601.1091425525,3325.26572634824,36.5269792127377
2026-03-20,101.011482613466,0,0,81.2175913492572,1255.45974450082,64598.7991019496,4694.61890810533,13682.9171450716,3102.43762926325,1598.61288698125,4998.73773942484,1763.70884835064,924.626319217451,0.151682294539437,4870.98442597777,23116.0973332954,3417.85167298738,0
2026-03-21,105.682667037049,0,0,81.2175913492572,1249.10470248401,63168.4136482728,5197.15943688348,14698.6895854318,3153.34763552184,1604.96148887441,4998.66066426079,1574.54976175934,924.626319217451,0.151682294539437,5087.96545096082,22184.0643569594,3761.55800478053,7.79022957240779
2026-03-22,123.338526029541,0,0,90.8764968002419,1248.56567108198,61801.7982455743,5241.56735267336,15107.6043376477,3153.33954273488,1728.18801482371,5319.65334468729,1673.89150912089,791.656721990658,0.151682294539437,5468.95656538151,21821.1043677918,4265.01129834406,21.7196170166467
2026-03-23,161.734253319593,0,0,54.9198804130971,1331.88354864643,64800.6749621022,5212.79927498625,14878.019705622,3967.50253253464,1747.32466195449,4512.87434468794,1745.55654499825,803.848970851204,0,5526.1409793174,21295.1141513993,4931.96532255063,21.7196170166467
2026-03-24,227.524158740239,0,2.20485175202156,54.9198804130971,1271.39704970855,68276.8819920054,5606.92078395616,16541.0714100894,3374.11834064925,1737.91562969911,4777.43528609348,1785.16710403165,846.477003196218,0,5571.81300376495,19830.0318758468,4704.76607122118,21.7196170166467
2026-03-25,384.653518420619,0,2.20485175202156,54.9198804130971,940.164886835043,67732.8128429179,5489.56707346611,16710.3399652581,3455.06080761443,1101.38035769557,4595.15407996023,1848.77360970827,866.063204426919,0,5106.26625365858,19438.8323820858,4758.31091438819,21.7196170166467
2026-03-26,386.784229649738,0,4.28257809500789,95.4220929178987,1074.82190217287,65206.5146451447,5620.50814349897,16246.3727787993,3483.51544262037,1265.03038885359,4391.77382590095,1929.91344602884,809.791764789871,0,4734.60346134841,20111.340202798,4278.10752172107,21.7196170166467
2026-03-27,386.784229649738,0,4.28257809500789,95.4220929178987,1198.34703943199,66095.6529587566,5272.68260240323,16877.1746203713,3851.70018300206,1175.05997459817,4300.00751520422,2036.39568068118,671.507392779404,0,5055.73771854999,20324.7466858442,4233.80116107345,26.6017356515913
2026-03-28,401.710486512694,0,4.28257809500789,64.0753436918925,1478.68130576852,65231.5932393252,5200.76694148134,16669.7564726647,3852.7679095017,1287.57746840805,4027.6979969869,1998.17379090963,645.841205251761,0,5116.32042156734,20134.3340606877,4399.75849034236,42.7821641153656
2026-03-29,404.798329352205,0,4.28257809500789,64.0753436918925,1681.77905579543,66134.6861358887,5091.95847907682,16734.8864501294,3820.83513639245,1287.88159156447,3899.44888874776,2025.7156510678,851.231990050986,0,5121.075706956,19885.3197426725,4298.70297076413,42.7821641153656
2026-03-30,413.672175514249,0,4.28257809500789,76.3559982295177,2023.09348858,64968.4356483976,5192.71574688072,17429.3539369417,4099.34861254557,1059.21584284978,4051.41650680959,1631.40856288285,851.231990050986,0,5205.650683454,20222.253318539,4245.04704653938,42.7821641153656
2026-03-31,400.193177483184,0,4.28257809500789,75.9840883629677,2080.29326087841,65143.2234912464,5190.37308309026,17240.1334968094,3758.4183423062,896.240016991107,3952.83064891384,1423.08419135645,625.093482098637,0,5745.77361677146,19607.7335640083,3768.77091491613,42.7821641153656
2026-04-01,386.461981699721,0,4.28257809500789,142.40873504292,2117.29335173785,58337.9499483154,4188.48489760916,16283.4445170685,3150.72080875571,935.209580810633,3727.1815441117,1266.42646428056,587.232496043954,0,5279.02666622576,19015.9790098218,3564.02471638251,42.7821641153656
2026-04-02,361.929474632967,480.755872101153,4.28257809500789,142.40873504292,2021.76889169263,57698.266162546,3976.36492575384,17407.8269386896,3237.75144839191,935.751923261869,3261.68406037251,1144.18779143557,668.949353829829,0,5201.48118518819,19207.8267430143,3096.84592111292,42.7821641153656
2026-04-03,359.984533081206,480.755872101153,4.28257809500789,187.211007039491,2022.92364466659,55312.929997172,3607.64759068792,16845.6674827842,3542.01923500588,799.058527139795,3402.25790156917,1092.06047593089,511.965754693988,0,4540.39798997647,19163.836360634,2648.93527497716,42.7821641153656
2026-04-04,355.441028144935,480.755872101153,6.69215199218509,187.211007039491,2093.87996107745,55487.4320330601,3112.12112222961,15494.9060992229,3498.98810689906,840.128622252112,3547.13542671419,1063.11640020464,524.824781795707,0,4523.80441049319,19082.431563402,2326.58949212896,34.9919345429578
2026-04-05,340.927274980498,480.755872101153,6.69215199218509,180.94911779544,2365.96861622396,54929.9541205128,2895.86820731865,15521.5851479656,3551.09914949855,736.428231324817,3018.47429484685,1124.91021149931,613.657986476633,0,4324.06894083944,19041.6222039704,1888.29129140648,21.0625470987189
2026-04-06,315.482305370746,480.755872101153,6.69215199218509,171.38725652125,2280.13550658117,51223.6483978316,2683.46441860983,15413.8136412365,3141.1563423725,869.328822923374,3257.75879121673,1053.40787699824,605.726713548353,0,4071.10461895305,19744.4741392546,1295.22796697133,21.0625470987189
2026-04-07,252.396353952682,480.755872101153,4.48730024016353,171.696655859775,2220.56534419181,48950.9180592429,2698.50554904889,14029.0521497375,3498.89554510053,1067.97017936872,3076.80357536159,1095.71694419044,684.612604173573,0,4224.35592519665,21194.9590504436,1120.59669014269,21.0625470987189
2026-04-08,100.858437669528,480.755872101153,4.48730024016353,310.218921875015,2079.31579013836,49245.0352678203,2651.73811627066,13371.929697141,4472.33747424162,1381.15743280679,3150.93125507315,1141.60428238197,685.706442935147,10.470719051149,4802.27289554852,21093.6059315322,1161.36275888678,25.5817676853969
2026-04-09,109.285065337012,480.755872101153,2.4095738971772,269.925859004863,2157.97301111438,49846.7469259312,2761.65365599295,12596.457582611,4675.23226933989,1308.05703890728,3314.3731204731,1094.47541390279,697.204377913438,10.470719051149,4886.39711626073,20694.3676693484,1162.75912742043,25.5817676853969
2026-04-10,112.070514089004,480.755872101153,2.4095738971772,269.925859004863,2162.82546280905,47820.6597127013,3366.15287652656,12084.7265379461,5083.2310179004,1398.21654523467,3399.74017532192,1049.32350320159,779.551619984545,10.470719051149,4854.32280311297,20627.9865140244,995.044474321131,20.6996490504523
2026-04-11,99.2047989148419,480.755872101153,2.4095738971772,269.925859004863,1917.11148324895,48915.072873884,3437.70421778201,11596.0309561699,4995.3139928866,1492.46219534407,3378.57148774183,1537.38213398006,779.551619984545,10.6725246804639,5096.73082513369,21199.5213021464,902.343846284852,4.51922058667796
2026-04-12,89.9250056109341,480.755872101153,2.75476773679484,269.925859004863,1947.47645526549,49810.1152839596,4100.4540614383,13433.947805601,5599.83868752282,1492.34129045636,3702.70687919931,1509.58043304346,574.16083518532,47.969545458585,5319.75792894091,22656.1062438173,1018.90888643907,4.51922058667796
2026-04-13,235.030355290125,480.755872101153,28.6933614370812,257.645204467238,1685.59477215913,52287.1023042972,3941.21539436734,13897.7654877937,5607.5513850762,1601.06440877138,3667.64231047525,1472.67249226239,582.889226319057,80.0699802873049,5936.62041563327,23000.1888452718,1028.55155516707,4.51922058667796
2026-04-14,235.030355290125,480.755872101153,46.537286571902,259.625219271087,1667.21110851145,58567.02243235,3793.9534826748,13806.0338526722,5764.099276399,1713.9305396797,3741.51515064002,2333.03875089253,752.558721875327,80.0699802873049,5708.70967506748,23881.5953495397,1051.72148774976,4.51922058667796
2026-04-15,258.70427752174,480.755872101153,46.537286571902,215.90016871428,1567.07535302249,59957.4616433864,3410.17814521723,14587.8992536087,5934.87517118631,1771.00915844682,3571.02030072826,2528.30120437044,754.685201165268,106.158315029486,5981.7774348223,24682.758998308,967.812564750837,4.51922058667796
2026-04-16,274.043985890294,0.253592561284869,46.7644632413863,216.071872010984,1764.26111131752,62408.713639217,3703.44425879233,15269.2892719184,6561.62111178502,2070.03319330169,4154.03496789616,2617.70565145114,673.182312102977,432.090796010044,6849.34495292792,25449.88767708,861.542957936623,4.51922058667796
2026-04-17,269.321926254506,0.253592561284869,46.7644632413863,171.269600014413,1914.93169646697,65346.8464603578,3740.01339486861,15562.8212645587,6653.42215798909,2009.88670467522,4478.0927786488,3039.71092955638,673.066541810682,432.090796010044,6957.1316225648,26280.6360667884,1080.71651256271,4.51922058667796
2026-04-18,249.009593958703,0.533601014370245,44.3548893442091,171.467719202917,1958.08410786676,69003.2095268388,4003.10182820895,16369.1560666114,6784.16615969622,2072.60642694278,4703.07953816388,3344.1705933855,710.157324514542,441.719388571329,6946.03969841166,27022.5004231569,1212.44885563286,4.51922058667796
2026-04-19,300.321207488212,1.06456043956044,44.3548893442091,218.43788389201,1705.55906218771,68262.5805458942,4272.96075261627,18155.8510323555,7021.78986466766,2067.07014821832,5159.56553354437,3244.86142948837,561.535122654101,446.513872933121,6963.89783727714,27395.0707347971,1168.15703413586,4.51922058667796
2026-04-20,345.156977580704,37.291314454776,44.3548893442091,219.045449403422,1746.68096306503,69071.9906232379,4673.83714470812,18506.7896749783,7808.2358620848,2012.84447376434,4930.31385746217,3342.19981272518,540.107294973939,446.513872933121,7176.12695134034,27395.2579978317,1121.75787923923,4.51922058667796
2026-04-21,551.419973976175,37.291314454776,148.695020367032,218.736050064897,1742.72822237778,71769.5762455509,4323.39024721164,19538.799198035,7695.85781967039,2051.98023298272,5636.12231081562,3218.11475768687,434.508946813511,446.513872933121,7407.3925968471,26507.1055028306,1208.69760586809,4.51922058667796
2026-04-22,593.583179775906,37.8434065934066,148.695020367032,80.3432219194796,1569.91490405301,71544.6738894123,4394.07007203414,21014.3052977189,7189.99673927722,2379.64251462495,5508.33965803189,3109.60960421856,414.162066011414,436.243914659655,6845.76121547018,26921.5331039519,1113.85369813643,0
2026-04-23,603.34741098916,38.0910895592104,148.836173024964,101.123206193427,1536.43980697428,72909.9254404538,4639.8741258255,21873.9463037434,7221.88687764142,2530.65569761235,5623.42267284672,3053.71020018022,540.951123682532,436.243914659655,6872.95367042793,28139.9694477336,1134.46819914617,0
2026-04-24,845.410146717579,38.0910895592104,148.836173024964,111.637449231941,1427.26364765881,75793.5766572289,5049.28232944195,23203.1953952163,6695.31556809007,2838.79461954147,6528.87266263211,3059.50352927506,447.09026335327,436.243914659655,6948.65791992648,28574.0227700006,1155.65854775884,0
2026-04-25,863.841378343523,38.0910895592104,148.836173024964,111.637449231941,1820.06226368744,77513.7107457317,6051.65720236458,23531.2191457925,7268.572484956,3548.24826853802,7556.17067274354,2840.49144056136,483.892781223749,436.042109030341,7179.80080221234,29166.5212723947,1087.32205406521,0
2026-04-26,863.841378343523,38.0910895592104,148.490979185346,111.637449231941,1614.57283289265,77263.6415853124,6405.59484955047,23881.2095479582,6944.45694427262,3698.53448374844,7566.67884631672,3987.36590230647,483.892781223749,398.745088252219,6880.67807399249,28549.8609983503,1060.27370035446,0
2026-04-27,705.15275812929,38.0910895592104,157.713981442529,111.905898542395,1623.47978500888,78386.2055913008,7278.88038006411,24695.3180137771,7665.15817783096,3518.5291149584,8053.51364951866,3967.12748999957,530.009636958104,366.6446534235,6735.40170363671,27926.9987145384,1095.5232397699,0
2026-04-28,755.747996224528,38.0910895592104,158.351409025786,160.581699162061,1715.99041242344,77239.0024762738,8475.85041491084,24621.274642423,7463.12686344817,3522.85377629618,8292.48353645075,3970.67892432909,469.667422329119,368.765056456757,6561.12153119749,28467.7960235349,1064.32601513287,0
2026-04-29,829.256055593845,38.0910895592104,158.351409025786,190.518440237986,2146.92610885157,78646.6733119909,8813.63664815037,25653.2999811776,8308.65688600235,3574.68811459353,9108.85649904712,4082.61473846295,485.487966408112,362.68835331022,6717.43102736867,30269.6217613035,1452.32977264195,0
2026-04-30,1814.78886591632,37.8374969979255,158.124232356302,196.897440124111,1983.16934807127,81285.2761383417,9339.32540055919,31398.0260837679,8558.44064839171,3636.93291087793,10758.7546052842,4742.53878230058,485.385026552033,36.7558723296621,6149.33097152843,30426.0790669472,1452.12901186426,0
2026-05-01,1853.8077973185,37.8374969979255,158.124232356302,196.897440124111,1969.78253584005,83948.8631235297,9439.68805723153,34002.5914405545,9432.7041472432,3739.079718068,11774.7240113159,4543.33235955357,1131.66004508428,36.7558723296621,6474.91883344141,32492.7674892425,1349.47440747769,0
2026-05-02,1853.8077973185,37.5574885448401,158.124232356302,196.699320935607,1855.6738080294,80164.2920594362,10325.364238825,35693.823832571,9825.78204883729,3629.09749915502,11870.6742978976,4238.87269572445,1095.50352131068,27.1272797683773,6619.87059143646,33267.3077191963,1232.41376935747,0
2026-05-03,1855.64563982181,37.0265291196499,158.124232356302,941.875303927121,1917.46847500655,82224.0613711701,10780.3347211166,36265.7649750103,9717.16277802273,3615.10764285748,12404.4688444589,4328.79627449072,1104.58225014585,22.3327954065852,7166.41438049428,34784.3841862317,1214.56331173789,0
2026-05-04,1796.65986194289,45.7439797575557,158.124232356302,959.618576506511,2292.50087127325,82865.8203458692,11071.4298202988,36573.968372813,8894.95315441262,3764.03698526566,12740.7089425943,5227.14437905764,1253.9352982867,22.3327954065852,7047.11623958112,35783.7224899915,1329.7394323479,0
2026-05-05,1599.22241573614,45.7439797575557,56.9153612175062,959.66865557873,2645.32924680179,82225.9314773936,11955.0066788535,38042.7669791235,9812.05292048725,3856.51007178112,12250.236921057,5420.99948885401,1289.39030861132,29.4957005929174,7026.18937660356,37314.2513009764,1304.77802099457,0
2026-05-06,1898.25112164145,45.1918876189252,70.971766067269,992.844436475381,4151.46215250653,85969.4000198968,12890.9214891187,40628.7878692013,9861.96325469555,3337.21298793961,13266.9079598222,5675.77399554313,1702.35176402364,29.2949398152336,7503.43051545571,40852.6083539708,1323.64876208998,0.158144438587243
2026-05-07,1874.87873305057,44.9442046531214,76.1692924555501,1206.24961420092,4320.66289510302,88308.5519088455,13372.3977267313,45246.8526640175,10775.2438580738,3317.86057537432,13496.5403106651,6186.51226955404,1564.3944822837,1298.05944709525,8268.62127905771,40766.3995440491,1617.21161119507,0.158144438587243
2026-05-08,1655.05958457481,44.9442046531214,76.1692924555501,1255.1113610262,4374.58075655537,86597.5803329495,13398.9934828054,46257.0505661941,11841.3944970101,3130.67440532052,12905.2465150919,6291.56156551027,1570.86159240935,1298.05944709525,8170.51414410917,40232.8832485547,1711.40881228902,0.158144438587243
2026-05-09,1647.98244540641,164.319138662202,76.1692924555501,1255.1113610262,3977.99545104733,84393.8466024322,12527.2177093055,47081.6784448305,11709.2727673805,2425.91099641906,11949.1224898193,6402.41236913872,1534.05907453887,1298.05944709525,7621.90768410116,40162.3367048613,1836.46306973731,0.158144438587243
2026-05-10,1702.58520970268,164.319138662202,76.1692924555501,1347.44360411546,4469.8579301043,83684.3498093399,11889.341627536,47409.6809403435,11779.9793551453,2288.95179716655,12423.806186605,5256.17359002707,1534.05907453887,1298.05944709525,7513.99307015273,39377.0961269861,1726.36211230608,0.158144438587243
2026-05-11,1702.58520970268,164.319138662202,41.0076964980809,1347.17515480501,4854.55618354697,81527.1612604215,11189.9845545058,46501.897609856,11565.2761380666,2522.59208825612,12872.1968904596,5852.41332429364,1597.21256901754,1298.05944709525,7057.18796308507,39613.6938107249,1608.60895865321,0.158144438587243
2026-05-12,1721.43616418139,164.319138662202,22.5263437800025,1478.09842476014,5511.48340358878,78242.0501873065,10262.8444493028,48168.4482531357,12073.5553489879,2434.51027440314,12536.9418758557,5513.59992984694,1429.9461972433,1403.99601361874,7105.86854064051,39246.7705527581,1809.5119034601,0.158144438587243
2026-05-13,1624.25418258045,164.319138662202,234.014176798672,1447.97366149518,5642.982194864,80675.4665491733,10145.0779737022,49618.6200858806,11704.2853528357,2947.0550501346,12506.8542838727,5366.11143588232,1425.21241071095,1383.98438202309,7356.20756368985,38273.4013102459,1555.47968490287,21.1173430960238
2026-05-14,646.065344845302,164.319138662202,311.092051235314,1442.0937475378,5541.80489498178,75928.8753314874,9813.40915485228,45743.4173198459,11319.8086167646,2676.45794035299,10931.8384504044,5285.12158658907,1665.88327053436,1383.98438202309,7713.4527619892,38870.713804875,1855.91369452923,22.1156661229602
2026-05-15,606.960624874602,164.319138662202,311.984252347942,1442.0937475378,5554.84374916726,75626.7544960603,10259.6637144451,46097.3980801639,11851.945174881,2869.25005403123,9214.96915388627,5519.36172355517,1079.70062105848,1383.98438202309,7665.59931793461,37305.2584391079,1879.21628123163,22.1156661229602
2026-05-16,822.454074150189,166.047194079548,313.107376101484,1442.0937475378,5620.14499824882,77212.7312052608,9470.67154071343,47725.5051163244,12016.7328971786,3036.02730596465,9942.12011929105,5570.59243626641,1085.9136329167,1383.98438202309,7300.72475504717,36888.8812890137,1881.80077967595,22.1156661229602
2026-05-17,766.162512289307,166.047194079548,313.107376101484,646.550583650255,5538.78672180421,77867.6268312475,9620.02901725765,47673.7601419458,12134.0888590739,3053.22531016634,9546.82489632657,5526.52103416962,1076.57602834189,1383.98438202309,6611.83534356879,34777.9467768937,1982.43554998511,22.1156661229602
2026-05-18,994.142574820505,121.102989426426,313.107376101484,628.199745559453,5361.44970107981,77171.3019571215,8960.25268380222,47268.6795478959,12249.8810143482,2824.31901280201,9266.88108184339,4646.10913101512,1090.62823929446,1479.92535100328,7070.50498669638,33360.1887825711,1995.06987116083,22.1156661229602
2026-05-19,982.284377667105,121.102989426426,321.225987470933,628.322186829185,5307.77830755249,75458.8012800038,8786.96750495947,49224.9040488012,12064.9045421816,2679.32818499645,9528.21725606878,4930.08949600873,1223.23901166338,1526.59394236654,6829.9403071432,32057.3032806854,1944.08320911067,22.1156661229602
2026-05-20,656.794679592244,121.102989426426,307.16958262117,595.016968062711,3950.36881247258,73727.1256521852,8424.04214419477,52801.6921917835,12203.9914786447,2596.15184177662,9152.16570922795,4744.10298551145,809.986886145838,1526.59394236654,6522.62858894823,29433.2594668122,2162.04337215386,21.9575216843729
2026-05-21,654.65572270533,121.102989426426,301.830903574958,360.622656428571,3752.24848088938,73624.6649699036,7429.41293897453,49429.0165883586,12843.0654992962,2419.23136243143,8527.34518062507,4252.22590250938,923.056024709039,257.829435086522,6544.98055852654,30441.7481404411,2016.22472135618,21.9575216843729
2026-05-22,689.781776259443,121.102989426426,426.492327777667,326.685722921264,3679.25369831771,75314.0610984128,8086.11217244359,50908.8745870194,12193.2026421241,2483.25861026378,9715.01270247246,4906.11893890391,1308.01967037195,257.829435086522,7449.90188133497,32983.0193928743,2965.99131403482,21.9575216843729
2026-05-23,688.020702619873,1.72805541734589,426.492327777667,326.685722921264,3778.25627402201,76813.6683349335,7879.24647716326,50638.8064758328,11924.3005447746,2304.09661987109,10062.2731324281,4524.5330451229,1468.31674332957,257.829435086522,7917.39935067401,32465.570648971,2845.1685126101,21.9575216843729
2026-05-24,668.387357283853,1.72805541734589,569.550431753202,234.353479832005,3428.87703495272,78362.631625425,7269.0125378083,49873.1056157596,11799.9410284829,2478.3190199826,10889.5451642707,4981.33729258991,1529.82176735753,257.829435086522,7871.04915646924,33225.8319702079,2909.41369685457,21.9575216843729
2026-05-25,1620.89445283731,371.535888448684,569.550431753202,234.353479832005,3218.25638805685,78061.859584907,8089.32511589659,50258.4197262093,12233.590161283,2207.65206213159,10552.6141479249,4439.10053310799,1450.16696683815,257.829435086522,8005.30912054997,32557.3878367503,2958.0698673908,21.9575216843729
2026-05-26,2031.95323112612,371.535888448684,717.073751843027,52.9190653809812,2496.99651258057,80651.1165960114,8006.79959912456,49158.5465956987,13598.3081560214,2196.20357671377,10721.8984776002,4856.16331899505,1560.38902822343,167.653360330261,8842.19762820644,34565.1815771598,2961.95462028931,21.9575216843729
2026-05-27,2062.11843126414,371.535888448684,505.585918824357,206.286919423478,1946.85656153615,81671.0516740379,7968.87161672962,49007.3811258817,13872.3356544784,1642.82855753102,10163.2098019122,4717.01174196227,1687.40612264979,167.653360330261,9468.12190481534,35634.034928612,2975.59422971158,0.99832302693638
2026-05-28,2047.03176523364,371.535888448684,428.508044387715,221.671567298243,2105.74672292916,84098.4078544233,8072.72484467881,48207.7629974476,14172.0740690274,1949.48845038971,9868.97675832291,4333.74756539953,1446.62423395887,167.653360330261,9384.33552062223,37341.4577696429,2746.56746955216,0
2026-05-29,2046.84282852744,371.535888448684,427.750171633297,221.671567298243,1987.40793560202,84281.1189918529,7567.92170994124,47170.1721643236,13439.3588420474,1713.9568888556,10108.8259144526,3891.95148904712,1578.16939155496,167.653360330261,9243.43164414479,38320.7570208172,2797.85489086822,0
2026-05-30,1847.35151144801,369.807833031338,426.627047879754,260.447686701229,2074.11521530511,83292.0747847085,7311.12881183076,44523.0086186847,13303.7169852038,1736.45414018686,9285.34336108521,3936.61629872394,1789.23985272659,167.653360330261,9247.68661033362,37865.9623897762,2907.24047371289,0
2026-05-31,1849.34314784237,369.807833031338,426.627047879754,268.350871629842,2193.32193998197,81914.5340969094,6843.76905437938,43423.337915087,13393.2942547574,1797.82122849172,9017.13719353888,3908.61374317777,1894.25575730093,167.653360330261,9538.56590550231,38457.9198201871,2811.9100308468,0
2026-06-01,1674.07957436523,369.807833031338,439.50282059548,297.009356187713,2048.77828880396,81523.9904005446,7006.1507044422,43579.2773650058,13493.9872153351,1813.63613751973,9701.78693101704,4365.82675483133,1808.4403438698,71.7123913500768,9413.64541528642,39630.342684539,2694.14776995658,14.7535777796596
2026-06-02,1674.8394973262,369.807833031338,428.252949342003,296.836835845762,2018.48902253744,82214.269803666,6693.28407491173,39723.863764515,13487.8910979472,1816.30520501766,9544.15116897608,3967.38941305142,1626.5021952092,17.8808948004837,9554.99465101996,42627.6912903344,2866.53540952815,14.7535777796596
2026-06-03,1728.78016953137,369.807833031338,428.252949342003,319.114850742406,1878.22131102289,80869.5119499722,6537.73803920416,32932.9021401218,13946.8773377494,1954.42503808163,9264.05098036785,3867.44111637641,1640.28112452604,17.8808948004837,10559.2812625384,44065.0036559244,2839.05292081983,14.7535777796596
2026-06-04,1825.30668997451,369.807833031338,428.252949342003,375.171620674721,2368.43005281334,77748.0260594797,6866.66671531327,32001.8979223176,12716.2358051166,2114.23070573357,9602.07001078972,3937.66145848523,1589.57487260821,108.142157570539,10000.8852421826,44565.9875282884,2880.02639719619,25.4301813636489
2026-06-05,1834.11112974885,370.208857638712,307.299428053547,405.134848688772,2593.9438242977,78169.9181815315,5743.44898279144,29876.6140440292,13508.1703978886,2122.84681159374,8328.42065438176,3369.66005694672,1225.11354656686,108.142157570539,9891.69689365256,47162.051030176,2066.93755300328,25.4301813636489
2026-06-06,2118.00010724494,370.208857638712,307.299428053547,405.134848688772,2765.66555840985,76964.5505550587,6157.94885681512,30031.8604711901,13468.7430851559,2105.10568252233,8234.88943907289,3456.90705451118,1064.81647360924,108.142157570539,9817.98030177342,48531.4468418049,2329.07235074387,25.4301813636489
2026-06-07,2206.48148981156,370.208857638712,164.241324078012,544.412266973159,2735.81539553388,77630.0470047556,6882.8523303291,29466.897540871,13865.4738002048,2278.60375998111,6809.58330289051,2999.4671244107,1038.19820916316,108.142157570539,10035.7057645374,49631.931488757,2384.74990952751,25.4301813636489
2026-06-08,1290.84524143419,0.401024607373814,164.241324078012,544.412266973159,2859.79187370645,79457.8732831885,5962.49626307621,30628.4817072208,13186.4536556372,2705.88764707072,6792.38824187037,3572.62142020944,1406.41201616975,363.085012942596,10492.4361683641,53130.3416318003,2782.76965256747,25.4301813636489
2026-06-09,828.590776950691,81.2461242751479,21.7969076426714,614.061882550872,3471.32905110063,78689.6863709024,5949.43909169665,31015.7862704069,12283.2130051608,3469.11522150292,7743.63010490729,3282.15687269845,1537.37448530193,345.204118142112,10020.463843501,54239.7441553855,2716.9072036701,25.4301813636489
2026-06-10,970.155819887285,81.2461242751479,25.029487053947,956.400190373238,3718.93225402439,78494.1937484907,5930.08072073475,32019.88689543,11944.4366101155,3618.8627943945,8365.22251884935,3499.91633205102,1469.85343816574,370.798663294283,9517.50677217268,56162.8671132722,2903.27146496065,25.4301813636489
2026-06-11,1054.69961371221,81.2461242751479,45.7105274098273,1381.83962009729,4254.44460556279,83294.9383727447,5401.71801115049,31794.4764920163,11671.2898129951,3387.18251672023,8787.58833047912,3335.76773697166,1585.03879342999,421.819369648128,11153.829063126,60303.6842105698,2985.02565710921,50.0481992312284
2026-06-12,1845.75404397126,81.2461242751479,67.3476945350576,1474.52739192733,5071.39554764348,84967.8960265332,6075.6341848883,32913.9809111744,12083.4088498501,3787.45679825462,9408.12577828701,4248.65291032256,1643.64382281635,421.819369648128,11641.9717991842,62648.5531221223,3055.5211803269,98.866784042202
2026-06-13,1829.7519117751,81.2461242751479,67.3476945350576,1816.31333341428,4938.42766790534,87825.877585086,7783.59870844029,33357.8166877484,12078.0278059229,3790.74732246528,9277.65894237166,4497.87072015263,1734.03745518978,421.819369648128,12019.7970407827,64122.6406148057,2967.7136631661,98.866784042202
2026-06-14,1838.32395632819,81.2461242751479,67.3476945350576,1808.41014848567,4861.63553500613,89916.334925215,7489.55205242878,33395.3800809205,12341.0042304695,4011.12047627558,9859.96177359864,4856.73107097295,1697.26747666391,421.819369648128,11884.07411498,67388.9840076057,3103.04363921257,98.866784042202
2026-06-15,1813.26494857613,81.2461242751479,54.4719218193323,1826.22145777848,5104.92473835437,92038.273479204,7834.67815186821,34322.6416896544,12797.2591717627,4319.79240845728,9830.17939431363,4730.31372513324,2051.30723822682,421.819369648128,11735.9898426965,70750.5455049303,3409.97765085503,84.1132062625424
2026-06-16,1812.50502561515,97.4251509263646,195.297116323553,2097.93402793714,5357.64062001038,95864.3649407288,7761.26444208887,35600.8490610021,12662.3146314215,4733.35579120983,10296.3390776203,5181.46450429457,2197.19069715432,421.819369648128,11787.4417711896,70627.9879325059,3371.39102568546,85.3112694971062
2026-06-17,1878.57504420867,97.4251509263646,195.297116323553,2075.6560130405,5413.08389887309,97339.0853177316,7260.77231892286,36143.1332923479,12295.886252818,5103.8764132739,10885.6690496716,5181.12423205058,2552.13702573852,421.819369648128,10916.3488788856,71495.8554479962,3199.82630315092,85.3112694971062
2026-06-18,1802.65928981107,97.4251509263646,195.297116323553,2028.93878762164,5094.57051366652,102578.279299325,7024.01016863304,37240.297336641,12633.2448487274,5211.6819916855,10994.493628126,5543.59031566466,2612.0075751816,331.558106878072,11905.8074597194,72730.7574053264,3259.11805408351,74.6346659131169
2026-06-19,1811.401623832,97.0241263189908,246.587143015927,2042.54781697846,5215.2272999082,99082.8402450443,6902.62595246919,37924.784267413,11552.7869553065,5221.56036794206,11357.0967589113,5571.46362000518,2782.20791769112,331.558106878072,12140.4974330437,68508.9597690092,3242.51317898702,74.6346659131169
2026-06-20,1595.6334129513,97.0241263189908,295.274513616341,2174.24346915237,5058.09382343655,99624.6443651809,6608.46355256559,37969.4689207016,11818.9005559568,5464.85068310194,11516.7106190053,5500.7921917989,3193.15061894034,331.558106878072,12132.7128187762,67999.3703973341,3852.28204695844,74.6346659131169
2026-06-21,1701.17169136902,97.0241263189908,295.274513616341,2062.98943934488,5104.27948506558,97152.4688304581,5779.41634816476,37943.4715990478,11646.295580033,5225.3871009507,12013.9142409568,5616.79537002398,3209.57793319107,331.558106878072,12330.0362948545,67250.0968344743,3769.99935865459,74.6346659131169
2026-06-22,1976.25978767374,97.0241263189908,348.961937303764,2143.16241451786,4949.22330473914,98728.4436585063,5829.96424879987,36688.261209117,12560.9509613712,5602.40163435157,12495.5276568322,5779.41302842586,2859.5395372663,76.6152515060151,12885.3902661924,67522.8595225494,3452.91157671216,74.6346659131169
2026-06-23,2252.28562923388,16.1790266512167,343.883033649279,2161.59300177046,4479.46094155786,101809.768659544,5692.69071739373,37463.2133302348,13233.8880595352,5397.77430651891,12314.1172672585,5824.99997066366,2715.49429493534,100.075912851511,13419.7970346192,68192.3640322675,4011.97672070264,93.0273194397499
2026-06-24,2085.58748432276,16.1790266512167,352.894481541758,1771.34264170279,4499.17913161192,103405.029137787,6330.51495010558,38094.9091292827,14788.9283398046,5585.17647147171,13199.0225038405,6880.62099138751,2722.25437534622,74.4813676993409,13826.8864837595,72620.9751113028,4020.49266937086,93.0273194397499
2026-06-25,2127.88479350311,16.1790266512167,370.284300929092,1477.10573344512,4001.72766298637,102118.276809699,6730.62803240513,39371.2010095456,16347.8608208888,6019.99686884313,13299.8527084048,6940.38311388645,2797.54927361682,27.4222634670288,12651.2639165946,68411.5849252988,4094.53746861347,68.4093015721704
2026-06-26,1402.18803260427,16.1790266512167,531.151637871054,1484.89344170588,3639.840736248,105911.068056068,6368.02502446942,39229.2750336188,16043.1770325533,6010.7778233123,12840.9963463319,5976.36890905963,2882.10426209383,27.4222634670288,14205.6746506668,71798.1733483143,3885.34411424713,28.4776181352923
2026-06-27,1502.40552996178,16.1790266512167,554.574273857719,1104.33138081595,4257.32777930778,103839.176866801,5016.86094580253,40847.5123737815,16658.4982199224,6021.1950620189,13103.3085179721,6036.96335796192,2573.75485610454,27.4222634670288,14512.6099489244,71797.2812570914,4457.35148440934,28.4776181352923
2026-06-28,1491.84184901433,16.1790266512167,554.574273857719,1321.74133284457,4461.66495596659,101787.675111162,5583.96113279077,41618.9372393071,16671.0809524411,6026.49293245951,12365.0059393557,5724.3098452747,2705.84635586304,27.4222634670288,15015.8515772781,69512.4438711142,4521.04439483986,28.4776181352923
2026-06-29,1459.66105852448,17.4372590278327,577.391169540295,1306.78426360564,5143.24246411093,100231.534385931,5137.15294896695,42684.6474471109,16175.143962208,5856.18631284412,12595.1259882211,5370.32219793163,2301.56026823171,27.4222634670288,14922.1945840204,66375.8166223101,4318.54065938286,28.4776181352923
2026-06-30,1459.66105852448,1.25823237661598,436.565975036074,1035.07169344698,5715.39940841723,92069.8790483846,4992.73721516164,40619.8240806433,15792.1919230726,5626.32582314177,12006.4223555074,5234.59897631311,2226.25061655119,27.4222634670288,15251.0461917957,62969.0499041411,4272.49365059427,27.2795549007285
2026-07-01,1454.07709100069,1.25823237661598,436.565975036074,1035.07169344698,6479.53638200357,90730.9805375942,5736.49005024531,42515.3047957653,15509.027417712,5170.69557561317,11685.4214408464,6143.62660178367,2116.62475015505,27.4222634670288,15466.1917509434,61906.2161948748,4467.3753770214,27.2795549007285
2026-07-02,1448.56465097496,11.1181759476761,491.522906614166,1025.73214893352,6259.52386424977,82297.8720047034,5747.94586889864,42099.4695608684,15129.042068528,4879.67127498923,11058.1222887687,6249.37714402326,1994.06160315712,27.4222634670288,14070.3164573105,58007.0254801707,4569.74041634474,27.2795549007285
2026-07-03,1583.22245244358,11.1181759476761,476.982184947664,960.361506124425,7011.23563171772,81155.8383876932,5297.47008641539,43060.6890612363,15514.8559890738,4741.838153883,11341.299305109,6231.45576358678,1942.76923083531,27.4222634670288,13113.3781353774,59296.7224014803,4859.6726126816,27.2795549007285
2026-07-04,1503.44812532142,11.1181759476761,485.527160588708,843.832222320183,7756.87529943431,80804.4073609521,6594.08737510814,45690.0539628687,15246.6352280746,4631.99830635639,12189.241884706,6602.03286328044,1785.02576486106,27.4222634670288,12678.8676855503,60169.897078148,3977.53741973873,27.2795549007285
2026-07-05,1274.79976087939,11.1181759476761,485.527160588708,850.161754584208,8032.76141995756,83029.6744794671,6726.82040017506,45732.83716492,15160.1324019514,4566.48188200687,12605.4997087052,6937.80621890725,1733.71169102845,27.4222634670288,12596.114950233,60359.4936937742,4370.70051517697,27.2795549007285
2026-07-06,1133.59344048172,11.1181759476761,477.578235690631,789.647221147927,8507.72371618221,86872.0882165854,8162.0053133905,48150.7215155056,16301.5753046231,4245.92649926394,13630.1545337062,7175.75955053316,1745.27950618947,47.8237969617826,12526.4733395271,64568.409082075,4697.60924328859,27.2795549007285
2026-07-07,973.428865774725,11.1181759476761,477.751371461286,841.493212263556,8590.40961784584,88923.6597914758,9013.59608664752,50732.4967944214,17487.1773193035,3890.66863208746,14119.4020142384,7613.46261123164,2030.89953025138,64.8366418169631,13758.8513458606,67996.4948874356,4293.2634815691,33.0655130667996
2026-07-08,1334.98365505894,199.038462305462,465.507344157532,854.662262878805,8541.7236271749,92995.9037111255,8979.03450252754,50996.4427993953,18049.2592959541,5049.39671418214,14245.8591404596,6676.09138041773,2123.1302139763,64.8366418169631,13940.8915235319,71286.4831296286,4262.61209438085,33.0655130667996
2026-07-09,1419.34619749515,214.185116502756,446.739492779825,777.878078358164,8615.53849310191,93389.7812331237,8905.95599827803,53554.9403916159,17392.8531038552,4816.68756823707,14976.4734471246,7759.54536196137,2528.5255235045,115.832005589896,14578.6904510016,79858.500541459,4913.93223466645,33.0655130667996
2026-07-10,1508.21795670097,214.185116502756,296.849492694576,713.472175370874,8953.05229638117,95278.6565828757,9131.93634469233,56012.6535738879,17999.7046576178,4856.89653543988,16788.8117491424,9611.45153014097,2358.16867131136,115.832005589896,12925.913404843,85236.090253773,5211.01284769126,34.5365598325012
2026-07-11,1598.02492391914,219.801963015882,273.426856707911,743.99013592679,8546.94633046648,100152.280945355,8809.45256483572,56828.7964540035,17976.9545841353,4903.81846509696,17386.9153411493,9206.50373918587,2345.04768586539,115.832005589896,12639.2884115828,88123.6462068037,4862.59144099914,34.5365598325012
2026-07-12,1612.74089708185,219.801963015882,282.386440541444,574.800736489733,8361.48234562295,102539.251200599,8897.93496177856,57451.3366869623,17912.982058657,5193.52392497015,18410.2065529494,9208.85383020331,2432.39533408803,138.369020395819,12835.7264732869,89964.281435705,5401.24006952718,34.5365598325012
2026-07-13,1621.60978668854,218.543730639266,266.674577507379,863.142657157528,7971.20532571032,105636.215808955,10204.7102677826,57561.4809302017,18557.7949458138,5963.28260334526,20149.17192823,9846.85742873703,2403.75479420674,182.624365502813,14585.7492871568,96119.2397119365,5728.35495410941,34.5365598325012
2026-07-14,1705.07672455246,218.543730639266,297.896161618411,989.53264133085,7890.18184354994,115602.173683289,10704.3149430633,63287.189662829,20802.1035052995,5598.41027538041,21439.5481003861,9474.14816553307,2471.96337972154,366.743373239911,15334.1633831178,103847.24967234,6144.47330575876,34.6362647060754
2026-07-15,1569.35634425017,218.543730639266,297.896161618411,1081.9228819948,7664.27513946859,121489.141103837,10834.0696603145,64390.038469983,24112.3579109454,6563.0383971425,22654.8375198518,9729.24815221131,2662.75985142057,366.743373239911,15511.4447484846,107473.302141005,5976.80517105931,34.6362647060754
2026-07-16,1554.25801823034,208.683787068206,319.435961545421,1293.57611992049,8529.83555192275,132186.228677673,11045.1266209504,66868.9119071454,27444.6405514219,6878.14111044945,23947.86429641,11254.1585020528,3051.70675830833,369.423937653176,17096.3218264775,116843.459450071,6260.90079297352,34.6362647060754
2026-07-17,1350.29021294481,208.683787068206,299.301977867069,1466.57737543549,8069.98728424843,137727.950481069,11657.5775678301,69189.5782416704,28537.232478885,7474.87472181418,25609.8430957766,11912.8737914149,3340.01730729599,375.124256887015,18135.0735722056,121863.985374202,6175.42746532626,47.7248520963388
2026-07-18,1614.86772556878,208.683787068206,242.069631625611,1489.09381289077,7685.66010573511,141014.184148127,10912.092604611,67628.7111504121,30336.3006958133,7937.58027172247,25758.851853745,12370.7796348922,3220.72669133467,375.124256887015,18625.8421909823,123526.310893959,6573.32611558179,47.7248520963388
2026-07-19,1617.37984982559,208.683787068206,242.069631625611,1521.78255881652,7522.58116157166,142827.66303395,11174.9340914146,71155.203268356,31458.0438025127,8479.19541821553,25794.388114306,12606.0269341113,3726.43899292197,403.876241013999,20092.4449001507,125089.960144029,6304.84019713718,47.7248520963388
2026-07-20,1639.3523625721,299.840343925983,196.331132836265,1504.09963480696,7198.26506746836,142674.575561848,10442.6062586058,73874.1573821993,30841.3627757777,8714.18763880724,26080.4949898824,12303.6011979656,3853.0718923706,394.198891871478,20655.4857523393,126269.16787525,6563.93867984265,47.7248520963388
2026-07-21,1668.21103542162,319.054352324683,227.453060848194,1568.88843233204,7245.50724115473,141374.366246381,10003.2793955937,75353.684025592,30215.1362215435,10012.7973359128,25604.4978072662,12132.410782225,3740.87705159053,399.025197917373,19066.9556047151,127525.478071896,6467.04482288678,23.5462404036347
2026-07-22,1490.79035047528,173.906221868549,271.227272248304,1588.8690421315,7582.37006168133,146631.448176471,11296.1892305353,78479.9757174704,29874.8843477849,8959.76797852511,29235.5065500797,13505.5713277565,3806.41795346053,435.466813855392,20557.9462870699,126770.499925829,6788.1795688284,23.5462404036347
2026-07-23,1816.30593818153,176.602867781997,353.272942889282,1606.75319729227,7611.4114283315,154645.032873977,12672.7512345031,78537.920893591,31745.7610863964,10108.3224198023,30194.7719990931,13774.4686026756,3279.91234768271,499.049240462113,20413.8119374955,129759.844221457,6221.76559078545,23.5462404036347
2026-07-24,1673.71903953462,176.602867781997,320.696633750527,1812.58486223441,7446.57342495709,157640.318415827,12653.6128217948,77097.1841829207,32053.9585799812,10936.5806844188,29908.3612189675,12581.9117762267,3524.49243746521,499.120629373035,22589.4900131015,128922.244886495,6484.9621545151,13.1882922638376
2026-07-25,1577.63243997937,353.366841448137,320.696633750527,1957.71137012184,7791.53636359755,163007.472319637,14766.0397168739,81271.8892735197,33173.878724612,11941.8234128395,30176.359176855,13060.1337008706,4391.38610673311,506.081048187979,23372.0667731963,131483.449808286,6896.11329600885,13.1882922638376
2026-07-26,1977.74595489248,353.366841448137,311.737049916994,2465.54599320439,8015.63582553158,164578.730263654,14586.0674604346,89446.3930379324,34164.9328248995,11704.1516180644,34078.0120493646,12980.5626839042,4155.33818022156,483.544033382057,23014.8414193851,131846.445453963,6335.64486045394,13.1882922638376
2026-07-27,2152.4411460345,353.366841448137,335.195092525657,2216.75523857239,7857.63723540216,170833.879458705,13680.9466005207,92717.7698795884,35807.5193278495,11139.8121388856,33089.9830799439,13628.6229704463,4690.75448393125,462.492338982774,23197.4529686184,138731.800976941,6205.46686396678,13.1882922638376
2026-07-28,2114.62890558584,353.366841448137,307.409509033724,2228.85114723287,7139.83524907688,177804.182681639,13127.5781755326,94733.5047265226,37551.4119184434,11956.3209967073,33020.8374640271,14609.6540854397,4946.54759849841,309.697816619457,23681.3755434371,142625.528755758,5994.6757787074,13.0885873902634
2026-07-29,2307.35608579046,378.604678867891,312.79855691059,2416.01268938275,6884.46013672737,179078.2436582,13697.5452263154,98862.9538301125,36292.4004259087,11954.5199555678,33687.0717620196,14169.7423773239,5288.46547421067,309.697816619457,25004.4486824599,152008.614089949,6429.13834091327,13.0885873902634
2026-07-30,2482.31968430256,378.604678867891,237.380613753799,2234.56939877655,6234.63030928802,179763.400833473,13407.6596437315,98737.4414068094,34074.1166662842,12535.9678662973,34102.1024405442,12390.7376742191,5633.89240726976,307.017252206192,25381.3124030053,151670.625601058,6196.51614183603,13.0885873902634
2026-07-31,2506.81966530758,378.604678867891,217.057389492028,2811.45676073745,5835.11219212868,181571.315072175,14276.7762941097,96327.6231577464,34061.1691583097,12773.3230820012,33197.437529741,12027.5206610648,5347.98631162903,338.464063846949,26375.4811006379,151439.678664621,6124.70490074598,0
2026-08-01,2267.40817584963,378.604678867891,243.244648179286,2907.87048000902,5540.47284756634,181693.360803608,14290.9970304267,100471.344914489,33848.0118869877,13102.0569543495,32545.7660660531,11778.9235384971,5301.88850312619,338.464063846949,26212.425217539,150571.559495611,6188.73441734915,0
2026-08-02,2292.66407070717,378.604678867891,243.244648179286,3139.93101653726,5785.2892980391,183472.35466998,15829.547405016,109161.05809701,33213.3458951389,12507.6669872962,33045.4385943911,11434.7679277959,4946.43608077148,309.712079719965,24697.531495599,153437.728332491,6220.28566069293,0
2026-08-03,2170.32224947575,287.448122010114,392.704159256445,3806.55024955527,5819.72482764717,189527.097665252,15301.2848858216,116074.15337174,32740.6498513559,13077.7862178538,36019.6519536527,11314.3416299115,5423.71952223606,298.987895367732,24900.2952796459,152600.696454225,5663.88155774408,0
2026-08-04,2214.19527446227,268.234113611414,848.678003036885,3633.80785436494,5515.12601364115,194196.856676285,15712.0663904343,113389.021340035,33367.0194157195,12238.190279287,36346.8879817798,11018.5849303295,5319.76328036312,265.301910470282,24936.1328250737,149230.53546686,5892.9159836453,16.4177578721826
2026-08-05,2170.58203026868,254.276718592655,1144.2776420353,3670.93179432047,7579.40654493886,207940.991679607,15832.7562956731,120214.064079292,37734.6432359452,14064.6204347701,36885.6900131725,10845.5800418983,5222.7430537131,228.860294532263,23957.027716904,157163.131148626,5808.02014579519,16.4177578721826
2026-08-06,1938.21121021077,236.433418481913,1111.94720337216,4343.41008366027,9337.08267748074,212585.125589604,15729.1391594883,124784.939979472,37324.9885771367,13653.6461173138,37842.6715868319,11105.0901166021,5199.36368202869,271.255528027398,23043.4147912789,159648.493925965,6067.99692521304,16.5173899997117
2026-08-07,2097.63334225472,241.393762730451,1275.85910621172,4522.56544863511,9655.74675216512,216025.312307704,16172.1293976134,131626.141500251,37668.850884887,13336.7422442573,39189.134227534,11789.0224344188,5060.0480605707,291.194107677169,21575.6143152364,162901.139525574,5986.94340562313,23.3746095380907
2026-08-08,2003.69547723428,59.0129425511852,1278.3416612305,4522.03029055864,9496.07197410541,213840.639059113,14330.1917126618,128104.032299073,38318.3354470975,13146.3727903683,39685.4601456341,11980.9878930847,4639.61827674174,284.233688862224,21900.6374221315,161838.045903397,5986.50182750712,23.3746095380907
2026-08-09,1639.39875304906,94.5206742377692,1278.3416612305,4288.1899061641,9452.59955376404,218978.723231287,13878.9227263354,127011.476676383,37803.4461102464,13022.1918723714,35756.2382271362,12137.0539469135,4751.77948438664,367.417895380653,22222.8871780977,165662.579325687,6167.39520612735,26.3615879115296
2026-08-10,2058.34586749691,197.22331074512,1250.09107646473,4466.37497137314,9501.48114880456,217455.903187142,14851.4397992376,132567.983308082,38111.6573625299,12787.2044428688,38684.7049554278,11165.5941373054,4231.55067485294,635.818106777629,22368.072969761,161426.918211099,6515.88344940671,27.6433466214033
2026-08-11,2279.53512088174,197.22331074512,1270.9571014886,5998.84645130075,10026.3071848574,223321.168960395,15597.4976275882,136737.433514562,36101.9032231503,13941.8627238686,41655.5506349733,10853.6520786497,3908.40893311415,701.331873433284,23076.9430635577,168488.284846271,7635.97023990101,27.9487104026035
2026-08-12,2491.88283684966,172.031017579199,1265.80716094436,6006.77917306339,10555.5648398806,227057.993271577,15057.186297306,135987.016489335,35344.3982748183,13582.615893207,41987.9168195535,10823.6926516879,3428.87942309257,726.783520617131,22134.9008452672,166412.854137037,7715.58459382158,35.1686670808624
2026-08-13,2436.22380624867,172.241547887977,1265.24237001658,6043.52734728248,10870.6987421275,226172.739684719,16441.6554521687,139412.954786483,35695.2026738811,13973.6477178773,43026.5926514476,11798.356210818,3091.1321175495,755.461162677673,21472.0082936005,168476.710511067,7763.2844862853,35.3914005497541
2026-08-14,2565.90642310216,172.440803998498,1378.78039946853,5453.78826208773,10943.0155363047,231171.615495394,15480.9477828358,141966.098871753,38232.2585718221,14036.544751146,42522.2050731122,12090.4376770377,3331.92533637938,718.503799527382,20202.7927912182,170710.568743559,8335.95614673415,35.808978268762
2026-08-15,2541.56442970754,191.983980120621,1554.56397696264,5328.37301711778,10841.2235494156,233303.206370846,14978.0916538454,139563.637478304,39343.8361216949,13255.7881745895,43204.934016766,12285.2475213528,3244.27971126007,765.908295616089,20527.2731526722,173640.014931168,8226.78534354511,36.5171881874983
''',
    'observed_workdays_by_team.csv': '''date,Pretraining,Posttraining,Overall Research,Scaling / Infrastructure,Other
2026-05-03,0.5,0.6,0.5,0.4,0.3
2026-05-04,0.6,0.7,0.5,0.4,0.3
2026-05-05,0.6,0.7,0.5,0.4,0.3
2026-05-06,0.6,0.7,0.5,0.4,0.3
2026-05-07,0.7,0.7,0.5,0.4,0.3
2026-05-08,0.7,0.7,0.6,0.4,0.3
2026-05-09,0.7,0.8,0.6,0.4,0.3
2026-05-10,0.7,0.7,0.6,0.4,0.3
2026-05-11,0.7,0.8,0.6,0.4,0.3
2026-05-12,0.7,0.8,0.6,0.4,0.3
2026-05-13,0.8,0.8,0.6,0.5,0.3
2026-05-14,0.8,0.8,0.6,0.5,0.3
2026-05-15,0.8,0.8,0.6,0.5,0.3
2026-05-16,0.8,0.8,0.6,0.5,0.3
2026-05-17,0.8,0.8,0.6,0.5,0.3
2026-05-18,0.8,0.8,0.6,0.5,0.3
2026-05-19,0.9,0.8,0.7,0.5,0.4
2026-05-20,0.9,0.8,0.7,0.5,0.4
2026-05-21,0.9,0.8,0.7,0.5,0.4
2026-05-22,0.9,0.9,0.7,0.5,0.4
2026-05-23,0.9,0.8,0.7,0.5,0.4
2026-05-24,0.9,0.8,0.7,0.6,0.4
2026-05-25,0.9,0.8,0.7,0.6,0.4
2026-05-26,1,0.8,0.7,0.6,0.4
2026-05-27,1,0.8,0.7,0.6,0.4
2026-05-28,1,0.8,0.7,0.6,0.4
2026-05-29,1,0.9,0.7,0.6,0.4
2026-05-30,1.1,0.9,0.7,0.6,0.4
2026-05-31,1.1,0.8,0.7,0.6,0.4
2026-06-01,1.1,0.8,0.7,0.6,0.4
2026-06-02,1.1,0.9,0.8,0.7,0.4
2026-06-03,1.1,0.9,0.8,0.7,0.4
2026-06-04,1.2,0.9,0.8,0.7,0.4
2026-06-05,1.2,0.9,0.8,0.8,0.4
2026-06-06,1.2,0.9,0.8,0.8,0.4
2026-06-07,1.2,0.9,0.9,0.8,0.4
2026-06-08,1.3,0.9,0.9,0.8,0.4
2026-06-09,1.3,1,0.9,0.9,0.4
2026-06-10,1.4,1,0.9,0.9,0.4
2026-06-11,1.4,1,1,0.9,0.4
2026-06-12,1.5,1.1,1,0.9,0.5
2026-06-13,1.5,1.1,1,1,0.5
2026-06-14,1.5,1.1,1,1,0.5
2026-06-15,1.5,1.2,1.1,1,0.5
2026-06-16,1.5,1.2,1.1,1,0.5
2026-06-17,1.6,1.3,1.2,1.1,0.5
2026-06-18,1.6,1.3,1.2,1.2,0.5
2026-06-19,1.6,1.3,1.2,1.2,0.5
2026-06-20,1.6,1.3,1.2,1.2,0.5
2026-06-21,1.6,1.3,1.2,1.2,0.5
2026-06-22,1.7,1.4,1.2,1.2,0.5
2026-06-23,1.7,1.4,1.3,1.3,0.6
2026-06-24,1.7,1.4,1.3,1.3,0.6
2026-06-25,1.8,1.4,1.3,1.3,0.6
2026-06-26,1.8,1.5,1.3,1.3,0.6
2026-06-27,1.8,1.5,1.4,1.3,0.6
2026-06-28,1.8,1.5,1.4,1.4,0.6
2026-06-29,1.8,1.5,1.4,1.4,0.6
2026-06-30,1.8,1.6,1.4,1.4,0.6
2026-07-01,1.8,1.6,1.4,1.4,0.6
2026-07-02,1.8,1.6,1.4,1.4,0.6
2026-07-03,1.8,1.6,1.4,1.3,0.6
2026-07-04,1.8,1.6,1.4,1.3,0.6
2026-07-05,1.9,1.6,1.4,1.3,0.6
2026-07-06,1.9,1.6,1.4,1.3,0.6
2026-07-07,1.9,1.7,1.4,1.3,0.6
2026-07-08,1.9,1.7,1.5,1.4,0.6
2026-07-09,1.9,1.8,1.5,1.4,0.7
2026-07-10,2,1.9,1.6,1.4,0.7
2026-07-11,2,2,1.6,1.4,0.7
2026-07-12,2,2,1.6,1.4,0.8
2026-07-13,2,2,1.6,1.4,0.8
2026-07-14,2.1,2,1.6,1.4,0.8
2026-07-15,2.1,2,1.6,1.4,0.9
2026-07-16,2.1,2,1.6,1.4,0.9
2026-07-17,2.2,2.1,1.7,1.4,1
2026-07-18,2.3,2.1,1.7,1.4,1
2026-07-19,2.3,2.1,1.7,1.4,1
2026-07-20,2.3,2.2,1.7,1.4,1
2026-07-21,2.4,2.2,1.8,1.5,1.1
2026-07-22,2.5,2.3,1.8,1.5,1.1
2026-07-23,2.6,2.4,1.9,1.6,1.1
2026-07-24,2.7,2.4,2,1.6,1.2
2026-07-25,2.8,2.5,2,1.7,1.2
2026-07-26,3,2.5,2.1,1.7,1.2
2026-07-27,3.1,2.6,2.1,1.8,1.3
2026-07-28,3.3,2.6,2.2,1.8,1.3
2026-07-29,3.4,2.7,2.3,1.9,1.4
2026-07-30,3.5,2.8,2.3,2,1.4
2026-07-31,3.6,2.9,2.4,2.1,1.5
2026-08-01,3.7,2.9,2.5,2.1,1.5
2026-08-02,3.9,3,2.5,2.2,1.5
2026-08-03,4,3,2.6,2.2,1.6
2026-08-04,4.1,3.1,2.7,2.3,1.6
2026-08-05,4.2,3.1,2.7,2.4,1.7
2026-08-06,4.3,3.2,2.8,2.4,1.7
2026-08-07,4.4,3.1,2.8,2.5,1.8
2026-08-08,4.4,3.1,2.8,2.5,1.8
2026-08-09,4.5,3.2,2.9,2.5,1.8
2026-08-10,4.6,3.2,2.9,2.5,1.8
2026-08-11,4.7,3.3,3,2.6,1.9
2026-08-12,4.8,3.4,3,2.6,1.9
2026-08-13,4.9,3.5,3.1,2.7,1.9
2026-08-14,5,3.6,3.1,2.7,2
2026-08-15,5,3.6,3.2,2.7,2
2026-08-16,5.2,3.7,3.2,2.7,2
2026-08-17,5.3,3.8,3.3,2.8,2.1
2026-08-18,5.4,3.8,3.4,2.8,2.1
2026-08-19,5.5,3.9,3.4,2.9,2.2
2026-08-20,5.5,3.9,3.4,2.9,2.2
2026-08-21,5.5,3.9,3.5,2.9,2.3
2026-08-22,5.6,4,3.5,3,2.3
2026-08-23,5.6,4,3.5,3,2.3
2026-08-24,5.6,4.1,3.6,3,2.4
2026-08-25,5.6,4.2,3.6,3,2.4
2026-08-26,5.6,4.2,3.6,3,2.4
2026-08-27,5.7,4.3,3.7,3.1,2.5
2026-08-28,5.8,4.4,3.8,3.1,2.6
2026-08-29,5.8,4.5,3.8,3.2,2.6
2026-08-30,5.8,4.6,3.8,3.1,2.6
2026-08-31,5.8,4.6,3.9,3.1,2.6
2026-09-01,5.8,4.7,3.9,3.2,2.6
2026-09-02,5.9,4.8,3.9,3.2,2.6
2026-09-03,6,4.8,4,3.2,2.6
2026-09-04,6.1,4.9,4,3.2,2.6
2026-09-05,6.2,5,4,3.2,2.7
2026-09-06,6.2,5.1,4.1,3.2,2.7
2026-09-07,6.2,5.2,4.1,3.2,2.7
2026-09-08,6.2,5.2,4.1,3.2,2.7
2026-09-09,6.3,5.3,4.2,3.3,2.7
2026-09-10,6.4,5.4,4.3,3.3,2.7
2026-09-11,6.4,5.6,4.3,3.4,2.7
2026-09-12,6.5,5.7,4.4,3.4,2.7
2026-09-13,6.5,5.8,4.5,3.5,2.8
2026-09-14,6.5,5.9,4.5,3.5,2.8
2026-09-15,6.5,6,4.5,3.5,2.8
2026-09-16,6.5,6.2,4.6,3.6,2.8
2026-09-17,6.6,6.3,4.7,3.6,2.8
2026-09-18,6.7,6.4,4.7,3.6,2.8
2026-09-19,6.8,6.5,4.8,3.6,2.8
2026-09-20,6.8,6.6,4.8,3.6,2.9
2026-09-21,6.8,6.7,4.9,3.6,2.9
2026-09-22,6.9,6.8,4.9,3.7,2.9
2026-09-23,6.9,6.8,4.9,3.7,2.9
2026-09-24,6.9,6.9,5,3.7,2.8
2026-09-25,7,6.9,5,3.8,2.8
2026-09-26,7,6.9,5,3.8,2.7
2026-09-27,7.1,6.9,5.1,3.8,2.8
2026-09-28,7.1,6.9,5.1,3.8,2.8
2026-09-29,7.1,7,5.1,3.9,2.7
2026-09-30,7.1,7,5.1,3.9,2.8
2026-10-01,7.1,7,5.2,3.9,2.9
2026-10-02,7.2,7.1,5.2,4,2.9
2026-10-03,7.3,7.2,5.3,4,2.9
2026-10-04,7.6,7.2,5.3,4,3
2026-10-05,7.8,7.3,5.4,4.1,3
2026-10-06,7.9,7.4,5.5,4.2,3
2026-10-07,8,7.4,5.6,4.2,3
2026-10-08,8.1,7.4,5.6,4.3,3
2026-10-09,8.1,7.4,5.6,4.3,3
2026-10-10,8.1,7.4,5.6,4.2,3
2026-10-11,8.1,7.4,5.6,4.2,3
2026-10-12,8.1,7.4,5.6,4.2,3
2026-10-13,8.1,7.4,5.6,4.2,2.9
2026-10-14,8.1,7.5,5.6,4.2,2.9
2026-10-15,8.2,7.5,5.6,4.2,2.9
2026-10-16,8.2,7.6,5.6,4.2,2.8
2026-10-17,8.2,7.7,5.7,4.2,2.7
2026-10-18,8.2,7.8,5.7,4.2,2.7
''',
    'observed_openai_research_usage.csv': '''date,workdays,bin_0,bin_1,bin_2,bin_3,bin_4,bin_5,bin_6,bin_7,bin_8,task1_1,task1_2,task1_3,task2_1,task2_2,task3_1,task3_2,task4_1,task4_2,task4_3,task5_1,task5_2,task5_3,task5_4,task6_1,task6_2,task6_3,task6_4
2026-03-01,,,,,,,,,,,0,0,0,0,0,0.6,0,0.1,0.1,0,0,0,0,0,0.1,0.8,0,0
2026-03-02,,,,,,,,,,,0,0,0,0,0,1.3,0,0.1,0.1,0,0,0,0,0,0.1,1.4,0,0
2026-03-03,,,,,,,,,,,0,0,0,0,0,1.5,0,0.1,0.1,0,0,0,0,0,0.2,1.6,0.1,0
2026-03-04,,,,,,,,,,,0,0,0,0,0,1.7,0,0.1,0.1,0,0,0,0,0,0.2,1.7,0.1,0
2026-03-05,,,,,,,,,,,0,0,0,0,0.1,1.9,0,0.2,0.1,0,0,0,0,0,0.2,1.9,0.1,0
2026-03-06,,,,,,,,,,,0,0,0,0,0.1,2,0,0.2,0.1,0,0,0,0,0,0.2,2,0.1,0
2026-03-07,,,,,,,,,,,0,0,0,0,0.1,2,0,0.2,0.1,0,0,0,0,0,0.2,1.9,0.1,0
2026-03-08,,,,,,,,,,,0,0,0,0,0.1,1.8,0,0.2,0.1,0,0,0,0,0,0.2,1.7,0.1,0
2026-03-09,,,,,,,,,,,0,0,0,0,0.1,1.9,0,0.2,0.1,0,0,0,0,0,0.2,1.8,0.1,0
2026-03-10,,,,,,,,,,,0,0,0,0,0.1,2,0,0.2,0.1,0,0,0,0,0,0.2,1.9,0.1,0
2026-03-11,,,,,,,,,,,0,0,0,0,0.1,2.1,0,0.2,0.1,0,0,0,0,0,0.2,2,0.1,0
2026-03-12,,,,,,,,,,,0,0,0,0,0.1,2.2,0,0.2,0.1,0,0,0,0,0,0.3,2.1,0.1,0
2026-03-13,,,,,,,,,,,0,0,0,0,0.1,2.2,0,0.2,0.1,0,0,0,0,0,0.3,2.1,0.1,0
2026-03-14,,,,,,,,,,,0,0,0,0,0.1,2.2,0,0.2,0.1,0,0,0,0,0,0.3,2.1,0.1,0
2026-03-15,,,,,,,,,,,0,0,0,0,0.1,2.1,0,0.2,0.1,0,0,0,0,0,0.3,2,0.1,0
2026-03-16,,,,,,,,,,,0,0,0,0,0.1,2.2,0,0.2,0.1,0,0,0,0,0,0.3,2,0.1,0
2026-03-17,,,,,,,,,,,0,0,0,0,0.1,2.3,0,0.2,0.1,0,0,0,0,0,0.3,2.1,0.1,0
2026-03-18,,,,,,,,,,,0,0,0,0,0.1,2.4,0,0.3,0.1,0,0,0,0,0,0.3,2.2,0.1,0
2026-03-19,,,,,,,,,,,0,0,0,0,0.1,2.4,0,0.3,0.1,0,0,0,0,0,0.3,2.2,0.1,0
2026-03-20,,,,,,,,,,,0,0,0,0,0.1,2.5,0,0.3,0.1,0,0,0,0,0,0.3,2.3,0.1,0
2026-03-21,,,,,,,,,,,0,0,0,0,0.1,2.4,0,0.3,0.1,0,0,0,0,0,0.3,2.2,0.1,0
2026-03-22,,,,,,,,,,,0,0,0,0,0.1,2.4,0,0.3,0.1,0,0,0,0,0,0.3,2.2,0.1,0
2026-03-23,,,,,,,,,,,0,0,0,0,0.1,2.4,0,0.3,0.1,0,0,0,0,0,0.3,2.2,0.1,0
2026-03-24,,,,,,,,,,,0,0,0,0,0.1,2.5,0,0.3,0.1,0,0.1,0,0,0,0.3,2.3,0.1,0
2026-03-25,,,,,,,,,,,0,0,0,0,0.1,2.5,0,0.3,0.1,0,0.1,0,0,0,0.3,2.3,0.1,0
2026-03-26,,,,,,,,,,,0,0,0,0,0.1,2.5,0,0.3,0.1,0,0.1,0,0,0,0.3,2.3,0.1,0
2026-03-27,,,,,,,,,,,0,0,0,0,0.1,2.5,0,0.3,0.1,0,0.1,0,0,0,0.3,2.4,0.1,0
2026-03-28,,,,,,,,,,,0,0,0,0,0.1,2.5,0,0.3,0.1,0,0.1,0,0,0,0.3,2.3,0.1,0
2026-03-29,,,,,,,,,,,0,0,0,0,0.1,2.5,0,0.3,0.1,0,0.1,0,0,0,0.3,2.3,0.1,0
2026-03-30,,,,,,,,,,,0,0,0,0,0.1,2.5,0,0.3,0.2,0,0.1,0,0,0,0.3,2.3,0.1,0
2026-03-31,,,,,,,,,,,0,0,0,0,0.1,2.5,0,0.3,0.2,0,0.1,0,0,0,0.3,2.3,0.1,0
2026-04-01,,,,,,,,,,,0,0,0,0,0.1,2.6,0,0.3,0.2,0,0.1,0,0,0,0.3,2.4,0.1,0
2026-04-02,,,,,,,,,,,0,0,0,0,0.1,2.5,0,0.3,0.2,0,0.1,0,0,0,0.3,2.4,0.1,0
2026-04-03,,,,,,,,,,,0,0,0,0,0.1,2.5,0,0.4,0.2,0,0.1,0,0,0,0.3,2.4,0.1,0
2026-04-04,,,,,,,,,,,0,0,0,0,0.1,2.6,0,0.4,0.2,0,0.1,0,0,0,0.3,2.4,0.1,0
2026-04-05,,,,,,,,,,,0,0,0,0,0.1,2.7,0,0.4,0.2,0,0.1,0,0,0,0.3,2.5,0.1,0
2026-04-06,,,,,,,,,,,0,0,0,0,0.1,2.7,0,0.4,0.2,0,0.1,0,0,0,0.3,2.5,0.2,0
2026-04-07,,,,,,,,,,,0,0,0,0,0.1,2.7,0,0.4,0.2,0,0.1,0,0,0,0.3,2.5,0.2,0
2026-04-08,,,,,,,,,,,0,0,0,0,0.1,2.8,0.1,0.4,0.2,0,0.1,0,0,0,0.3,2.5,0.2,0
2026-04-09,,,,,,,,,,,0,0,0,0,0.1,2.8,0,0.4,0.2,0,0.1,0,0,0,0.3,2.6,0.2,0
2026-04-10,,,,,,,,,,,0,0,0,0,0.1,2.8,0.1,0.4,0.2,0,0.1,0,0,0,0.3,2.6,0.2,0
2026-04-11,,,,,,,,,,,0,0,0,0,0.1,2.8,0.1,0.4,0.2,0,0.1,0,0,0,0.3,2.7,0.2,0
2026-04-12,,,,,,,,,,,0,0,0,0,0.1,2.8,0.1,0.5,0.2,0,0.1,0,0,0,0.3,2.7,0.2,0
2026-04-13,,,,,,,,,,,0,0,0,0,0.1,2.8,0.1,0.5,0.2,0,0.1,0,0,0,0.3,2.7,0.2,0
2026-04-14,,,,,,,,,,,0,0,0,0,0.1,2.8,0.1,0.5,0.2,0,0.1,0,0,0,0.4,2.7,0.2,0
2026-04-15,,,,,,,,,,,0,0,0,0,0.1,2.9,0.1,0.5,0.2,0,0.1,0,0,0,0.4,2.8,0.2,0
2026-04-16,,,,,,,,,,,0,0,0,0,0.1,2.9,0.1,0.5,0.2,0,0.1,0,0,0,0.3,2.9,0.2,0
2026-04-17,,,,,,,,,,,0,0,0,0,0.1,3,0.1,0.6,0.3,0.1,0.1,0,0,0,0.4,2.9,0.2,0
2026-04-18,,,,,,,,,,,0,0,0,0,0.1,3,0.1,0.6,0.3,0.1,0.1,0,0,0,0.4,3,0.2,0
2026-04-19,,,,,,,,,,,0,0,0,0,0.1,3,0.1,0.6,0.3,0.1,0.1,0,0,0,0.4,3,0.2,0
2026-04-20,,,,,,,,,,,0,0,0,0,0.1,3,0.1,0.6,0.3,0.1,0.1,0,0,0,0.4,3,0.2,0
2026-04-21,,,,,,,,,,,0,0,0,0,0.1,3,0.1,0.6,0.3,0.1,0.1,0,0,0,0.4,3.1,0.2,0
2026-04-22,,,,,,,,,,,0,0,0,0,0.1,3.1,0.1,0.6,0.3,0.1,0.1,0,0,0,0.4,3.2,0.2,0
2026-04-23,,,,,,,,,,,0,0,0,0,0.1,3.2,0.1,0.6,0.3,0.1,0.1,0.1,0,0,0.4,3.2,0.2,0
2026-04-24,,,,,,,,,,,0,0,0,0,0.1,3.3,0.1,0.7,0.3,0.1,0.1,0.1,0,0,0.4,3.3,0.2,0
2026-04-25,,,,,,,,,,,0,0,0,0,0.1,3.3,0.1,0.7,0.3,0.1,0.1,0.1,0,0,0.4,3.4,0.2,0
2026-04-26,,,,,,,,,,,0,0,0,0,0.1,3.4,0.1,0.7,0.3,0.1,0.1,0.1,0,0,0.4,3.4,0.3,0
2026-04-27,,,,,,,,,,,0,0,0,0,0.1,3.4,0.1,0.7,0.3,0.1,0.1,0.1,0,0,0.4,3.4,0.3,0
2026-04-28,,,,,,,,,,,0,0,0,0,0.1,3.4,0.1,0.7,0.3,0.1,0.1,0.1,0,0,0.5,3.5,0.3,0
2026-04-29,,,,,,,,,,,0,0,0,0,0.1,3.5,0.1,0.7,0.3,0.1,0.1,0.1,0,0,0.5,3.5,0.3,0
2026-04-30,,,,,,,,,,,0,0,0,0,0.1,3.5,0.1,0.8,0.3,0.1,0.1,0.1,0,0,0.5,3.6,0.3,0
2026-05-01,,,,,,,,,,,0,0,0,0,0.1,3.7,0.1,0.8,0.4,0.1,0.1,0.1,0,0,0.5,3.7,0.3,0
2026-05-02,,,,,,,,,,,0,0,0,0,0.1,3.7,0.1,0.8,0.4,0.1,0.1,0.1,0,0,0.5,3.6,0.3,0
2026-05-03,0.5,,,,,,,,,,0,0,0,0,0.1,3.6,0.1,0.8,0.4,0.1,0.1,0.1,0,0,0.5,3.6,0.3,0
2026-05-04,0.5,0.065,0.119,0.278,0.431,0.089,0.014,0.004,0,0.001,0,0,0,0,0.1,3.7,0.2,0.8,0.4,0.1,0.2,0.1,0,0,0.5,3.6,0.3,0
2026-05-05,0.5,0.066,0.115,0.268,0.44,0.094,0.013,0.004,0,0.001,0,0,0,0,0.1,3.8,0.2,0.8,0.4,0.1,0.2,0.1,0,0,0.6,3.7,0.3,0
2026-05-06,0.5,0.061,0.112,0.268,0.442,0.101,0.011,0.003,0.002,0.001,0,0,0,0,0.1,3.8,0.2,0.8,0.4,0.1,0.2,0.1,0,0,0.6,3.8,0.3,0
2026-05-07,0.5,0.061,0.101,0.267,0.45,0.104,0.012,0.003,0.001,0.001,0,0,0,0,0.1,3.9,0.2,0.8,0.4,0.1,0.2,0.1,0,0,0.6,3.8,0.3,0
2026-05-08,0.6,0.054,0.097,0.266,0.457,0.108,0.012,0.003,0.002,0.001,0,0,0,0,0.1,3.9,0.2,0.8,0.4,0.1,0.2,0.1,0,0,0.6,3.9,0.3,0
2026-05-09,0.6,0.053,0.09,0.266,0.46,0.114,0.013,0.002,0.002,0.001,0,0,0,0,0.1,4,0.2,0.8,0.4,0.1,0.2,0.1,0,0,0.6,3.9,0.3,0
2026-05-10,0.6,0.053,0.089,0.266,0.458,0.116,0.013,0.003,0.002,0.001,0,0,0,0,0.1,3.9,0.2,0.9,0.4,0.1,0.2,0.1,0,0,0.6,3.9,0.3,0
2026-05-11,0.6,0.05,0.089,0.268,0.46,0.116,0.011,0.003,0.002,0.001,0,0,0,0,0.1,4,0.2,0.9,0.5,0.1,0.2,0.1,0,0,0.6,4,0.3,0
2026-05-12,0.6,0.05,0.082,0.269,0.466,0.115,0.014,0.002,0.002,0.001,0,0,0,0,0.1,4,0.2,0.9,0.5,0.1,0.2,0.1,0,0,0.6,4,0.3,0
2026-05-13,0.6,0.051,0.08,0.267,0.471,0.114,0.013,0.003,0.001,0.001,0,0,0,0,0.1,4,0.2,0.9,0.5,0.1,0.2,0.1,0,0,0.6,4,0.3,0
2026-05-14,0.6,0.052,0.079,0.267,0.474,0.112,0.013,0.004,0,0.001,0,0,0,0,0.1,4.1,0.2,0.9,0.5,0.1,0.2,0.1,0,0,0.7,4,0.3,0
2026-05-15,0.6,0.052,0.078,0.265,0.474,0.112,0.014,0.004,0,0.001,0,0,0,0,0.1,4.1,0.2,0.9,0.5,0.1,0.2,0.1,0,0,0.7,4.1,0.3,0
2026-05-16,0.6,0.051,0.077,0.262,0.479,0.112,0.014,0.005,0,0.001,0,0,0,0,0.1,4.1,0.2,0.9,0.5,0.1,0.2,0.1,0,0,0.7,4.1,0.3,0
2026-05-17,0.6,0.05,0.077,0.261,0.479,0.115,0.012,0.005,0,0.001,0,0,0,0,0.1,4.1,0.2,0.9,0.5,0.1,0.2,0.1,0,0,0.7,4,0.3,0
2026-05-18,0.6,0.049,0.077,0.265,0.473,0.118,0.012,0.005,0,0.001,0,0,0,0,0.1,4.1,0.2,1,0.5,0.1,0.2,0.1,0,0,0.7,4.1,0.3,0
2026-05-19,0.7,0.053,0.074,0.256,0.482,0.117,0.013,0.005,0,0.001,0,0,0,0,0.1,4.1,0.2,1,0.5,0.1,0.2,0.1,0,0,0.7,4.1,0.3,0
2026-05-20,0.7,0.053,0.074,0.251,0.481,0.124,0.013,0.005,0,0.001,0,0,0,0,0.1,4.1,0.2,1,0.5,0.1,0.2,0.1,0,0,0.7,4.1,0.3,0
2026-05-21,0.7,0.049,0.072,0.257,0.482,0.121,0.013,0.004,0.001,0.001,0,0,0,0,0.1,4.2,0.2,1,0.5,0.1,0.2,0.1,0,0,0.7,4.2,0.3,0
2026-05-22,0.7,0.048,0.06,0.222,0.482,0.159,0.022,0.005,0.001,0.001,0,0,0,0,0.1,4.1,0.2,1,0.5,0.1,0.2,0.1,0,0,0.7,4.3,0.3,0
2026-05-23,0.7,0.051,0.057,0.228,0.492,0.146,0.02,0.004,0.002,0.001,0,0,0,0,0.1,4.1,0.2,1,0.6,0.1,0.2,0.1,0,0,0.8,4.3,0.3,0
2026-05-24,0.7,0.051,0.058,0.227,0.493,0.146,0.018,0.005,0.001,0.001,0,0,0,0,0.1,4.1,0.2,1,0.5,0.1,0.2,0.1,0,0,0.8,4.3,0.3,0
2026-05-25,0.7,0.051,0.059,0.229,0.489,0.146,0.018,0.005,0.001,0.001,0,0,0,0,0.1,4,0.2,1,0.5,0.1,0.2,0.1,0,0,0.8,4.2,0.3,0
2026-05-26,0.7,0.051,0.056,0.231,0.488,0.148,0.02,0.005,0.001,0.001,0,0,0,0,0.1,4,0.2,1,0.5,0.1,0.2,0.1,0,0,0.8,4.2,0.3,0
2026-05-27,0.7,0.047,0.054,0.233,0.491,0.152,0.016,0.007,0.001,0.001,0,0,0,0,0.1,4,0.2,1,0.5,0.1,0.2,0.1,0,0,0.8,4.2,0.3,0
2026-05-28,0.7,0.045,0.049,0.235,0.493,0.152,0.017,0.007,0.001,0.001,0,0,0,0,0.1,4,0.2,1,0.6,0.1,0.2,0.1,0,0,0.8,4.2,0.3,0
2026-05-29,0.7,0.044,0.046,0.232,0.492,0.157,0.021,0.005,0.001,0.001,0,0,0,0,0.1,3.9,0.2,1,0.6,0.1,0.2,0.1,0,0,0.8,4.3,0.3,0
2026-05-30,0.7,0.044,0.047,0.227,0.498,0.153,0.023,0.006,0.001,0.001,0,0,0,0,0.1,3.8,0.2,1,0.6,0.1,0.2,0.1,0,0,0.7,4.2,0.3,0
2026-05-31,0.7,0.044,0.045,0.226,0.501,0.153,0.023,0.005,0.002,0.001,0,0,0,0,0.1,3.8,0.2,1,0.6,0.1,0.2,0.1,0,0,0.8,4.2,0.3,0
2026-06-01,0.7,0.044,0.045,0.225,0.501,0.155,0.023,0.005,0.002,0.001,0,0,0,0,0.1,3.8,0.2,1,0.6,0.1,0.2,0.1,0,0,0.8,4.3,0.3,0
2026-06-02,0.8,0.041,0.044,0.224,0.501,0.157,0.025,0.006,0.002,0.001,0,0,0,0,0.1,3.7,0.2,1,0.6,0.1,0.2,0.1,0,0,0.8,4.4,0.3,0
2026-06-03,0.8,0.04,0.046,0.212,0.507,0.16,0.027,0.005,0.002,0,0,0,0,0,0.1,3.7,0.2,1,0.6,0.1,0.2,0.1,0,0,0.7,4.4,0.3,0
2026-06-04,0.8,0.038,0.043,0.213,0.505,0.161,0.033,0.004,0.003,0,0,0,0,0,0.1,3.6,0.2,1,0.6,0.1,0.2,0.1,0,0,0.8,4.3,0.3,0
2026-06-05,0.8,0.037,0.041,0.211,0.498,0.17,0.033,0.006,0.003,0,0,0,0,0,0.1,3.7,0.2,1,0.7,0.1,0.2,0.1,0,0,0.8,4.5,0.3,0
2026-06-06,0.8,0.034,0.044,0.204,0.496,0.174,0.034,0.009,0.004,0.001,0,0,0,0,0.1,3.6,0.2,1,0.7,0.1,0.2,0.1,0,0,0.8,4.5,0.3,0
2026-06-07,0.9,0.034,0.043,0.204,0.494,0.177,0.035,0.009,0.003,0.002,0,0,0,0,0.1,3.6,0.2,1.1,0.6,0.1,0.2,0.1,0,0,0.8,4.6,0.3,0
2026-06-08,0.9,0.033,0.045,0.199,0.497,0.176,0.036,0.009,0.003,0.002,0,0,0,0,0.1,3.6,0.2,1,0.7,0.1,0.2,0.1,0,0,0.8,4.6,0.3,0
2026-06-09,0.9,0.031,0.046,0.196,0.489,0.185,0.036,0.011,0.004,0.001,0,0,0,0,0.1,3.5,0.2,1,0.6,0.1,0.2,0.1,0,0,0.8,4.5,0.3,0
2026-06-10,0.9,0.031,0.041,0.191,0.488,0.195,0.037,0.011,0.004,0.001,0,0,0,0,0.1,3.4,0.2,1,0.6,0.1,0.2,0.1,0,0,0.8,4.4,0.3,0
2026-06-11,1,0.027,0.045,0.181,0.483,0.207,0.041,0.011,0.005,0.001,0,0,0,0,0.1,3.4,0.2,1,0.6,0.1,0.2,0.1,0,0,0.8,4.4,0.3,0
2026-06-12,1,0.027,0.043,0.175,0.472,0.225,0.041,0.011,0.005,0.001,0,0,0,0,0.1,3.4,0.1,1,0.6,0.1,0.2,0.1,0,0,0.8,4.4,0.3,0
2026-06-13,1,0.026,0.041,0.169,0.473,0.232,0.04,0.011,0.005,0.001,0,0,0,0,0.1,3.4,0.2,1,0.6,0.1,0.2,0.1,0,0,0.8,4.5,0.3,0
2026-06-14,1,0.026,0.041,0.169,0.472,0.233,0.041,0.012,0.005,0.001,0,0,0,0,0.1,3.4,0.1,1,0.6,0.1,0.1,0.1,0,0,0.8,4.5,0.3,0
2026-06-15,1.1,0.027,0.042,0.166,0.469,0.238,0.042,0.01,0.006,0.001,0,0,0,0,0.1,3.4,0.2,1,0.6,0.1,0.2,0.1,0,0,0.8,4.5,0.3,0
2026-06-16,1.1,0.027,0.038,0.166,0.465,0.243,0.042,0.012,0.005,0.001,0,0,0,0,0.1,3.4,0.2,1,0.6,0.1,0.1,0.1,0,0,0.8,4.6,0.3,0
2026-06-17,1.2,0.024,0.041,0.158,0.465,0.249,0.045,0.011,0.006,0.001,0,0,0,0,0.1,3.3,0.2,1,0.6,0.1,0.2,0.1,0,0,0.8,4.6,0.3,0
2026-06-18,1.2,0.025,0.04,0.158,0.463,0.25,0.045,0.013,0.005,0.002,0,0,0,0,0.1,3.3,0.2,1,0.6,0.1,0.1,0.1,0,0,0.8,4.6,0.3,0
2026-06-19,1.2,0.024,0.04,0.154,0.466,0.251,0.044,0.013,0.005,0.002,0,0,0,0,0.1,3.3,0.2,1,0.6,0.1,0.1,0.1,0,0,0.8,4.5,0.3,0
2026-06-20,1.2,0.023,0.037,0.159,0.462,0.254,0.044,0.014,0.005,0.002,0,0,0,0,0.1,3.3,0.2,1,0.6,0.1,0.1,0.1,0,0,0.8,4.5,0.3,0
2026-06-21,1.2,0.023,0.036,0.161,0.454,0.261,0.044,0.015,0.004,0.002,0,0,0,0.1,0.1,3.4,0.2,1.1,0.6,0.1,0.2,0.1,0.1,0,0.8,4.5,0.3,0
2026-06-22,1.2,0.024,0.035,0.163,0.453,0.26,0.043,0.016,0.004,0.002,0,0,0,0.1,0.1,3.5,0.2,1,0.6,0.1,0.2,0.1,0.1,0,0.8,4.7,0.3,0
2026-06-23,1.3,0.023,0.035,0.161,0.453,0.265,0.042,0.014,0.005,0.002,0,0,0,0.1,0.1,3.5,0.2,1.1,0.6,0.1,0.1,0.1,0.1,0,0.8,4.7,0.3,0
2026-06-24,1.3,0.023,0.033,0.158,0.448,0.273,0.044,0.013,0.005,0.002,0,0,0,0.1,0.1,3.5,0.2,1.1,0.6,0.1,0.1,0.1,0.1,0,0.8,4.8,0.3,0
2026-06-25,1.3,0.022,0.033,0.15,0.442,0.285,0.047,0.014,0.005,0.002,0,0,0,0.1,0.1,3.6,0.2,1.1,0.6,0.1,0.1,0.1,0.1,0,0.8,4.8,0.3,0
2026-06-26,1.3,0.025,0.034,0.142,0.447,0.285,0.048,0.013,0.005,0.002,0,0,0,0.1,0.1,3.6,0.2,1.1,0.6,0.1,0.1,0.1,0.1,0,0.8,4.9,0.3,0
2026-06-27,1.4,0.025,0.032,0.136,0.44,0.298,0.049,0.012,0.005,0.002,0,0,0,0.1,0.2,3.6,0.2,1.1,0.6,0.1,0.2,0.1,0,0,0.8,4.8,0.3,0
2026-06-28,1.4,0.025,0.032,0.135,0.441,0.294,0.052,0.013,0.005,0.002,0,0,0,0.1,0.2,3.6,0.2,1.1,0.6,0.1,0.1,0.1,0,0,0.8,4.8,0.3,0
2026-06-29,1.4,,,,,,,,,,0,0,0,0.1,0.2,3.6,0.2,1.1,0.6,0.1,0.2,0.1,0,0,0.8,4.8,0.3,0
2026-06-30,1.4,,,,,,,,,,0,0,0,0.1,0.2,3.5,0.2,1.1,0.6,0.1,0.2,0.1,0,0,0.8,4.7,0.3,0
2026-07-01,1.4,,,,,,,,,,0,0,0,0.1,0.2,3.5,0.2,1.1,0.6,0.1,0.2,0.1,0.1,0,0.8,4.7,0.3,0
2026-07-02,1.4,,,,,,,,,,0,0,0,0.1,0.2,3.5,0.2,1.1,0.6,0.1,0.2,0.1,0.1,0,0.8,4.7,0.3,0
2026-07-03,1.4,,,,,,,,,,0,0,0,0.1,0.2,3.4,0.2,1,0.5,0.1,0.2,0.1,0.1,0,0.8,4.5,0.3,0
2026-07-04,1.4,,,,,,,,,,0,0,0,0.1,0.2,3.5,0.2,1,0.6,0.1,0.2,0.1,0.1,0,0.8,4.6,0.3,0
2026-07-05,1.4,,,,,,,,,,0,0,0.1,0.1,0.2,3.6,0.2,1,0.6,0.1,0.2,0.1,0.1,0,0.8,4.7,0.3,0
2026-07-06,1.4,0.025,0.034,0.132,0.437,0.298,0.055,0.012,0.005,0.003,0,0,0.1,0.1,0.2,3.6,0.2,1,0.5,0.1,0.2,0.1,0.1,0,0.8,4.6,0.3,0
2026-07-07,1.4,0.023,0.034,0.129,0.427,0.304,0.06,0.015,0.005,0.003,0,0,0.1,0.1,0.2,3.8,0.2,1.1,0.5,0.1,0.2,0.1,0.1,0,0.8,5,0.3,0
2026-07-08,1.5,0.022,0.032,0.13,0.414,0.316,0.062,0.017,0.004,0.004,0,0,0.1,0.1,0.2,4,0.2,1.2,0.6,0.1,0.2,0.1,0.1,0,0.8,5.1,0.3,0
2026-07-09,1.5,0.022,0.032,0.13,0.406,0.322,0.066,0.016,0.003,0.003,0,0,0.1,0.1,0.2,3.9,0.2,1.3,0.6,0.1,0.2,0.1,0.1,0,0.8,5.3,0.3,0
2026-07-10,1.6,0.019,0.033,0.125,0.4,0.327,0.075,0.013,0.004,0.003,0,0,0.1,0.1,0.2,3.9,0.2,1.4,0.6,0.1,0.3,0.1,0.1,0,0.8,5.3,0.3,0
2026-07-11,1.6,0.019,0.032,0.127,0.383,0.343,0.075,0.013,0.003,0.003,0,0,0.1,0.1,0.2,3.9,0.2,1.3,0.6,0.1,0.3,0.2,0.1,0,0.7,5.3,0.3,0
2026-07-12,1.6,0.018,0.033,0.127,0.381,0.344,0.076,0.015,0.003,0.003,0,0,0.1,0,0.2,3.9,0.2,1.4,0.6,0.1,0.3,0.2,0.1,0,0.7,5.3,0.3,0
2026-07-13,1.6,0.019,0.031,0.126,0.378,0.347,0.079,0.014,0.003,0.003,0,0,0.1,0.1,0.2,3.8,0.2,1.5,0.6,0.1,0.3,0.2,0.1,0,0.7,5.3,0.4,0
2026-07-14,1.6,0.018,0.03,0.126,0.376,0.348,0.084,0.012,0.003,0.003,0,0,0,0.1,0.2,4,0.2,1.5,0.6,0.1,0.3,0.2,0.1,0,0.8,5.4,0.3,0
2026-07-15,1.6,0.018,0.032,0.13,0.368,0.347,0.087,0.013,0.002,0.003,0,0,0,0.1,0.2,4,0.2,1.6,0.7,0.2,0.3,0.2,0.1,0,0.7,5.5,0.3,0
2026-07-16,1.6,0.018,0.034,0.133,0.359,0.35,0.089,0.013,0.002,0.003,0,0,0,0.1,0.2,3.9,0.2,1.7,0.7,0.1,0.3,0.2,0.1,0,0.8,5.5,0.4,0
2026-07-17,1.7,0.016,0.035,0.132,0.357,0.356,0.088,0.012,0.002,0.003,0,0,0.1,0,0.2,4,0.2,1.8,0.7,0.1,0.4,0.2,0.1,0,0.8,5.9,0.4,0
2026-07-18,1.7,0.016,0.037,0.127,0.348,0.356,0.098,0.012,0.002,0.003,0,0,0.1,0,0.2,4,0.2,1.9,0.7,0.2,0.5,0.2,0.1,0,0.9,6,0.4,0
2026-07-19,1.7,0.016,0.037,0.128,0.346,0.358,0.097,0.013,0.002,0.003,0,0,0.1,0,0.3,4,0.2,2,0.6,0.2,0.5,0.3,0.1,0,0.8,5.9,0.5,0
2026-07-20,1.7,0.016,0.038,0.124,0.346,0.355,0.1,0.015,0.002,0.004,0,0,0.1,0,0.3,4,0.2,2.1,0.6,0.2,0.5,0.3,0.1,0,0.9,6,0.4,0
2026-07-21,1.8,0.013,0.037,0.121,0.342,0.357,0.108,0.016,0.002,0.003,0,0,0.1,0,0.3,4,0.2,2.1,0.6,0.1,0.5,0.3,0.1,0,0.8,6,0.4,0
2026-07-22,1.8,0.012,0.039,0.119,0.339,0.352,0.116,0.017,0.003,0.003,0,0,0.1,0,0.2,4,0.2,2.2,0.6,0.2,0.6,0.3,0.1,0,0.8,6.3,0.4,0
2026-07-23,1.9,0.014,0.036,0.121,0.328,0.352,0.122,0.018,0.004,0.003,0,0,0.1,0,0.3,4,0.2,2.3,0.6,0.2,0.6,0.3,0.1,0,0.8,6.4,0.4,0
2026-07-24,2,0.016,0.033,0.121,0.327,0.344,0.129,0.023,0.004,0.003,0,0,0.1,0,0.2,4,0.2,2.5,0.6,0.2,0.6,0.3,0.1,0,0.9,6.7,0.4,0
2026-07-25,2,0.015,0.033,0.121,0.321,0.34,0.135,0.026,0.005,0.003,0.1,0,0.1,0,0.2,4,0.2,2.5,0.5,0.2,0.6,0.3,0.1,0,0.9,6.9,0.3,0
2026-07-26,2.1,0.015,0.034,0.119,0.317,0.344,0.134,0.027,0.006,0.003,0.1,0,0.1,0,0.2,4.1,0.3,2.5,0.7,0.2,0.6,0.3,0.1,0,0.9,7,0.3,0
2026-07-27,2.1,0.015,0.034,0.12,0.316,0.344,0.133,0.029,0.006,0.003,0.1,0,0.1,0.1,0.2,4.1,0.2,2.5,0.6,0.2,0.6,0.3,0.1,0,0.9,7.2,0.3,0
2026-07-28,2.2,0.014,0.034,0.117,0.311,0.338,0.144,0.032,0.006,0.004,0.1,0,0.1,0,0.2,4.2,0.2,2.6,0.6,0.2,0.6,0.3,0.1,0,1,7.2,0.3,0
2026-07-29,2.3,0.016,0.034,0.117,0.303,0.337,0.151,0.03,0.007,0.004,0.1,0,0.1,0,0.2,4.4,0.2,2.7,0.7,0.2,0.6,0.3,0.1,0,1,7.3,0.3,0
2026-07-30,2.3,0.015,0.034,0.12,0.297,0.332,0.159,0.031,0.008,0.004,0.1,0,0.1,0,0.3,4.5,0.2,2.7,0.6,0.2,0.6,0.3,0.1,0,1,7.3,0.3,0
2026-07-31,2.4,0.015,0.037,0.118,0.288,0.33,0.167,0.034,0.008,0.004,0.1,0,0.1,0,0.2,4.6,0.2,2.6,0.7,0.2,0.6,0.3,0.1,0,1,7.5,0.3,0
2026-08-01,2.5,0.018,0.036,0.115,0.282,0.324,0.176,0.036,0.008,0.004,0.1,0,0.1,0,0.2,4.6,0.4,2.6,0.6,0.2,0.6,0.3,0.1,0,1.1,7.3,0.3,0
2026-08-02,2.5,0.017,0.034,0.118,0.28,0.326,0.175,0.04,0.007,0.004,0.1,0,0.1,0,0.2,4.5,0.4,2.5,0.6,0.2,0.6,0.3,0.1,0,1.1,7.1,0.3,0
2026-08-03,2.6,0.018,0.034,0.117,0.281,0.322,0.175,0.041,0.007,0.004,0.1,0,0.1,0,0.2,4.5,0.4,2.6,0.7,0.2,0.6,0.2,0.1,0,1.1,7.3,0.3,0
2026-08-04,2.7,0.016,0.036,0.116,0.273,0.324,0.178,0.046,0.008,0.003,0.1,0,0.1,0,0.2,4.6,0.4,2.5,0.7,0.2,0.6,0.2,0.1,0,1.2,7.5,0.3,0
2026-08-05,2.7,0.017,0.035,0.119,0.266,0.323,0.18,0.048,0.009,0.003,0.1,0,0.1,0,0.2,4.6,0.4,2.5,0.8,0.2,0.6,0.2,0.1,0,1.1,7.6,0.3,0
2026-08-06,2.8,0.016,0.035,0.119,0.262,0.32,0.185,0.05,0.008,0.003,0.1,0,0.1,0,0.2,4.7,0.4,2.4,0.8,0.2,0.5,0.2,0.1,0,1.1,7.6,0.4,0
2026-08-07,2.8,0.016,0.036,0.119,0.259,0.315,0.187,0.056,0.009,0.003,0.1,0,0.1,0,0.2,4.7,0.5,2.3,0.8,0.2,0.5,0.2,0.1,0,1.1,7.6,0.4,0
2026-08-08,2.8,0.016,0.037,0.118,0.254,0.316,0.187,0.059,0.011,0.003,0.1,0,0.1,0.1,0.2,4.7,0.5,2.3,0.8,0.2,0.5,0.2,0.1,0,1.1,7.6,0.5,0
2026-08-09,2.9,0.017,0.036,0.119,0.254,0.313,0.186,0.061,0.011,0.003,0.1,0,0.1,0.1,0.2,4.7,0.5,2.3,0.8,0.2,0.5,0.2,0.1,0,1.1,7.6,0.4,0
2026-08-10,2.9,0.017,0.037,0.117,0.254,0.315,0.185,0.061,0.012,0.003,0.1,0,0.1,0.1,0.2,4.9,0.5,2.3,0.8,0.2,0.5,0.2,0.1,0,1.2,7.7,0.5,0
2026-08-11,3,0.019,0.037,0.111,0.252,0.315,0.188,0.061,0.014,0.003,0.1,0,0.1,0.1,0.2,5,0.5,2.3,0.8,0.2,0.5,0.2,0.1,0,1.2,7.6,0.5,0
2026-08-12,3,0.017,0.038,0.115,0.251,0.307,0.193,0.062,0.015,0.003,0,0,0.1,0.1,0.3,5.1,0.5,2.3,0.8,0.2,0.5,0.2,0.1,0,1.2,7.7,0.5,0
2026-08-13,3.1,0.015,0.039,0.115,0.244,0.302,0.201,0.067,0.013,0.004,0,0,0.1,0.1,0.3,5.3,0.5,2.2,0.8,0.2,0.6,0.2,0.1,0,1.2,7.9,0.5,0
2026-08-14,3.1,0.015,0.037,0.116,0.246,0.292,0.208,0.068,0.014,0.005,0,0,0,0.1,0.2,5.3,0.5,2.2,0.9,0.2,0.5,0.2,0.1,0,1.3,7.8,0.4,0
2026-08-15,3.2,0.014,0.039,0.115,0.24,0.294,0.209,0.069,0.014,0.006,0,0,0,0.1,0.2,5.3,0.5,2.1,0.9,0.2,0.5,0.2,0.1,0,1.2,7.9,0.4,0
2026-08-16,3.2,0.014,0.039,0.114,0.241,0.292,0.212,0.069,0.014,0.005,0,0,0,0.1,0.2,5.4,0.5,2,0.9,0.2,0.4,0.2,0.1,0,1.2,8,0.4,0
2026-08-17,3.3,0.014,0.039,0.115,0.239,0.289,0.215,0.068,0.016,0.004,0,0,0,0.1,0.2,5.5,0.5,2,0.9,0.2,0.4,0.2,0.1,0,1.2,8.1,0.4,0
2026-08-18,3.4,0.017,0.037,0.113,0.236,0.285,0.221,0.071,0.015,0.004,0,0,0,0.1,0.2,5.6,0.5,2,0.9,0.2,0.4,0.2,0.1,0,1.4,8.3,0.4,0
2026-08-19,3.4,0.019,0.036,0.115,0.232,0.285,0.223,0.069,0.016,0.004,0,0,0,0.1,0.2,5.7,0.5,2,0.9,0.2,0.4,0.2,0.1,0,1.4,8.3,0.4,0
2026-08-20,3.4,0.02,0.035,0.116,0.229,0.282,0.227,0.069,0.017,0.004,0,0,0,0.1,0.2,5.6,0.6,2,1,0.2,0.3,0.2,0.1,0,1.4,8.4,0.5,0
2026-08-21,3.5,0.017,0.037,0.116,0.226,0.28,0.23,0.071,0.019,0.004,0,0,0,0.1,0.2,5.7,0.5,1.9,1.1,0.2,0.3,0.3,0.1,0,1.4,8.5,0.5,0
2026-08-22,3.5,0.017,0.036,0.114,0.23,0.277,0.228,0.075,0.02,0.003,0,0,0,0.1,0.3,5.7,0.5,1.9,1.1,0.2,0.3,0.3,0,0,1.4,8.4,0.5,0
2026-08-23,3.5,0.017,0.037,0.111,0.233,0.272,0.233,0.075,0.018,0.003,0,0,0,0.1,0.2,5.6,0.5,2,1.1,0.2,0.3,0.3,0,0,1.4,8.4,0.5,0
2026-08-24,3.6,0.016,0.037,0.111,0.233,0.268,0.238,0.072,0.02,0.003,0,0,0,0.1,0.2,5.7,0.6,1.9,1.1,0.2,0.3,0.3,0,0,1.4,8.4,0.5,0
2026-08-25,3.6,0.018,0.035,0.114,0.225,0.273,0.239,0.073,0.02,0.004,0,0,0,0.1,0.3,5.7,0.6,1.8,1.1,0.2,0.3,0.3,0,0,1.4,8.4,0.5,0
2026-08-26,3.6,0.017,0.038,0.113,0.227,0.265,0.242,0.075,0.019,0.004,0,0,0,0.1,0.2,5.7,0.7,1.7,1.1,0.2,0.3,0.3,0,0,1.4,8.6,0.5,0
2026-08-27,3.7,0.017,0.039,0.11,0.22,0.27,0.243,0.078,0.02,0.004,0,0,0,0.1,0.2,5.7,0.8,1.7,1.1,0.2,0.3,0.3,0,0,1.5,8.8,0.5,0
2026-08-28,3.8,0.016,0.04,0.105,0.22,0.268,0.25,0.077,0.021,0.004,0,0,0,0.1,0.2,5.6,0.8,1.7,1.1,0.2,0.3,0.4,0,0,1.4,8.6,0.5,0
2026-08-29,3.8,0.016,0.039,0.105,0.216,0.263,0.256,0.08,0.02,0.004,0,0,0,0.1,0.3,5.5,1.4,1.7,1.1,0.2,0.3,0.4,0,0,1.4,8.6,0.5,0
2026-08-30,3.8,0.016,0.04,0.106,0.214,0.264,0.254,0.08,0.022,0.004,0,0,0,0.1,0.3,5.4,1.3,1.7,1.1,0.2,0.3,0.4,0,0,1.4,8.7,0.5,0
2026-08-31,3.9,0.015,0.041,0.104,0.214,0.266,0.256,0.079,0.021,0.004,0,0,0,0.1,0.3,5.5,1.3,1.7,1.1,0.3,0.3,0.4,0,0,1.4,8.7,0.5,0
2026-09-01,3.9,0.014,0.039,0.105,0.213,0.267,0.256,0.079,0.022,0.004,0,0,0,0.1,0.3,5.6,1.3,1.7,1.1,0.3,0.3,0.4,0,0,1.4,8.6,0.5,0
2026-09-02,3.9,0.016,0.037,0.106,0.208,0.275,0.251,0.082,0.021,0.003,0,0,0,0.1,0.3,5.5,1.3,1.8,1.1,0.2,0.3,0.4,0,0,1.5,8.7,0.5,0
2026-09-03,4,0.016,0.036,0.107,0.206,0.273,0.253,0.086,0.021,0.003,0,0,0,0.1,0.3,5.5,1.3,2,1.2,0.2,0.4,0.4,0.1,0,1.5,8.8,0.4,0
2026-09-04,4,0.016,0.035,0.106,0.203,0.275,0.253,0.087,0.021,0.003,0,0,0,0.1,0.3,5.5,1.3,2.1,1.3,0.2,0.4,0.3,0.1,0,1.5,8.9,0.4,0
2026-09-05,4,0.017,0.036,0.106,0.196,0.281,0.255,0.084,0.021,0.003,0,0,0,0.1,0.3,5.5,1.2,2.2,1.3,0.2,0.4,0.4,0.1,0,1.5,8.9,0.4,0
2026-09-06,4.1,0.017,0.035,0.107,0.195,0.284,0.256,0.083,0.02,0.004,0.1,0,0,0.1,0.3,5.5,1.3,2.2,1.3,0.2,0.4,0.4,0.1,0,1.5,8.8,0.3,0
2026-09-07,4.1,0.017,0.035,0.108,0.191,0.285,0.257,0.084,0.02,0.004,0.1,0,0,0.1,0.3,5.3,1.2,2.2,1.2,0.2,0.4,0.4,0.1,0,1.4,8.7,0.3,0
2026-09-08,4.1,0.018,0.034,0.107,0.189,0.288,0.254,0.088,0.018,0.004,0.1,0,0,0.1,0.3,5.1,1.2,2.1,1.2,0.2,0.3,0.3,0.1,0,1.5,8.7,0.3,0
2026-09-09,4.2,0.017,0.036,0.103,0.192,0.289,0.257,0.084,0.019,0.004,0.1,0,0,0.1,0.4,5.1,1.3,2.1,1.2,0.2,0.3,0.4,0.1,0,1.6,8.7,0.3,0
2026-09-10,4.3,0.019,0.034,0.104,0.192,0.289,0.254,0.084,0.019,0.004,0.1,0,0,0.1,0.4,5.2,1.3,2.2,1.3,0.2,0.3,0.4,0.1,0,1.6,8.8,0.3,0
2026-09-11,4.3,0.019,0.032,0.099,0.199,0.292,0.247,0.089,0.019,0.004,0.1,0,0,0.1,0.4,5.1,1.3,2.1,1.3,0.2,0.3,0.5,0.1,0,1.6,8.9,0.3,0
2026-09-12,4.4,0.019,0.033,0.097,0.197,0.287,0.258,0.085,0.02,0.004,0.1,0,0,0.1,0.4,5.1,1.3,2.1,1.3,0.2,0.3,0.5,0.1,0,1.6,8.9,0.3,0
2026-09-13,4.5,0.019,0.034,0.097,0.197,0.289,0.253,0.085,0.022,0.004,0,0,0,0.1,0.4,5.1,1.4,2.2,1.3,0.2,0.3,0.4,0.1,0,1.6,8.9,0.3,0
2026-09-14,4.5,0.022,0.034,0.097,0.198,0.286,0.252,0.085,0.021,0.005,0,0,0,0.1,0.4,5,1.4,2.1,1.4,0.2,0.3,0.4,0.1,0,1.6,8.9,0.3,0
2026-09-15,4.5,0.018,0.036,0.101,0.197,0.287,0.251,0.085,0.02,0.005,0,0,0,0.1,0.4,5,1.4,2.1,1.4,0.2,0.4,0.4,0.1,0,1.5,9,0.3,0
2026-09-16,4.6,0.018,0.034,0.103,0.192,0.287,0.253,0.088,0.02,0.005,0,0,0,0.1,0.5,4.9,1.5,2,1.5,0.2,0.4,0.5,0.1,0,1.6,8.8,0.3,0
2026-09-17,4.7,0.017,0.034,0.102,0.189,0.289,0.251,0.092,0.02,0.006,0,0,0,0.1,0.4,5.1,1.4,2,1.5,0.3,0.4,0.4,0.1,0,1.5,8.9,0.3,0
2026-09-18,4.7,0.017,0.033,0.104,0.19,0.287,0.249,0.095,0.019,0.006,0,0,0,0.1,0.4,5.1,1.5,1.9,1.5,0.3,0.4,0.4,0.1,0,1.6,8.6,0.3,0
2026-09-19,4.8,0.019,0.031,0.102,0.187,0.291,0.252,0.094,0.018,0.006,0,0,0,0.1,0.4,5.1,1.5,1.8,1.4,0.3,0.4,0.4,0.1,0,1.6,8.7,0.3,0
2026-09-20,4.8,0.019,0.031,0.101,0.184,0.294,0.253,0.094,0.017,0.006,0,0,0,0.1,0.4,5.1,1.4,1.8,1.4,0.3,0.4,0.4,0.1,0,1.7,8.6,0.3,0
2026-09-21,4.9,0.021,0.032,0.1,0.186,0.294,0.251,0.094,0.016,0.006,0,0,0,0.1,0.4,5.1,1.4,1.8,1.4,0.3,0.4,0.4,0.1,0,1.7,8.4,0.3,0
2026-09-22,4.9,0.018,0.034,0.099,0.183,0.299,0.248,0.096,0.016,0.006,0,0,0,0.1,0.4,5.1,1.4,1.9,1.5,0.3,0.4,0.4,0.1,0,1.8,8.6,0.4,0
2026-09-23,4.9,0.017,0.033,0.099,0.184,0.3,0.248,0.096,0.017,0.007,0,0,0,0.1,0.4,5.1,1.2,1.8,1.6,0.3,0.4,0.4,0.1,0,1.8,8.7,0.4,0
2026-09-24,5,0.016,0.03,0.101,0.185,0.303,0.248,0.092,0.018,0.007,0,0,0,0.1,0.4,5.2,1.2,1.8,1.6,0.3,0.4,0.3,0.1,0,1.7,8.9,0.4,0
2026-09-25,5,0.014,0.028,0.095,0.194,0.308,0.245,0.093,0.015,0.008,0,0,0,0.1,0.4,5.3,1.1,1.9,1.8,0.3,0.5,0.3,0.1,0,1.8,9.3,0.4,0
2026-09-26,5,0.014,0.029,0.087,0.196,0.315,0.239,0.095,0.017,0.008,0,0,0,0.1,0.5,5.4,0.5,1.9,1.8,0.3,0.5,0.3,0.1,0,1.8,9.2,0.4,0
2026-09-27,5.1,0.014,0.029,0.086,0.195,0.314,0.241,0.096,0.016,0.009,0,0,0,0.1,0.4,5.3,0.4,1.9,1.9,0.3,0.5,0.3,0.1,0,1.8,9.3,0.4,0
2026-09-28,5.1,0.028,0.029,0.085,0.189,0.318,0.234,0.092,0.016,0.009,0,0,0,0.1,0.4,5.3,0.4,1.9,2,0.4,0.5,0.3,0.1,0,1.8,9.3,0.3,0
2026-09-29,5.1,0.016,0.033,0.091,0.193,0.311,0.24,0.09,0.018,0.009,0,0,0,0.1,0.4,5.2,0.4,2,2.2,0.4,0.5,0.3,0.1,0,1.9,9.5,0.3,0
2026-09-30,5.1,0.016,0.027,0.09,0.205,0.308,0.239,0.087,0.021,0.008,0,0,0,0.1,0.4,5.4,0.4,1.9,2.2,0.3,0.5,0.3,0.1,0,1.9,9.4,0.4,0
2026-10-01,5.2,0.013,0.023,0.091,0.206,0.315,0.241,0.085,0.018,0.008,0,0,0,0.1,0.4,5.5,0.5,1.8,2.2,0.3,0.5,0.4,0.1,0,2,9.6,0.4,0
2026-10-02,5.2,0.012,0.021,0.088,0.209,0.317,0.244,0.085,0.019,0.008,0.1,0,0,0.1,0.4,5.6,0.5,1.9,2.3,0.4,0.5,0.4,0.1,0,2,9.8,0.4,0
2026-10-03,5.3,0.011,0.02,0.087,0.206,0.319,0.245,0.084,0.021,0.008,0.1,0,0,0.1,0.4,5.7,0.5,1.9,2.3,0.4,0.5,0.4,0.1,0,2,9.8,0.4,0
2026-10-04,5.3,0.011,0.02,0.085,0.208,0.317,0.248,0.083,0.02,0.01,0.1,0,0,0.1,0.4,5.7,0.4,1.9,2.3,0.4,0.5,0.4,0.1,0,2.1,9.9,0.4,0
2026-10-05,5.4,0.013,0.021,0.082,0.207,0.316,0.248,0.081,0.021,0.009,0.1,0,0,0.1,0.4,5.8,0.4,1.8,2.4,0.4,0.6,0.4,0.1,0,2.1,10.2,0.5,0
2026-10-06,5.5,0.011,0.02,0.076,0.208,0.319,0.253,0.081,0.022,0.01,0.1,0,0.1,0.1,0.4,6,0.4,1.9,2.5,0.4,0.6,0.4,0.1,0,2.1,10.4,0.6,0
2026-10-07,5.6,0.009,0.021,0.076,0.208,0.323,0.252,0.079,0.022,0.01,0.1,0,0.1,0.1,0.4,6,0.4,1.9,2.6,0.4,0.6,0.3,0.1,0,2,10.4,0.5,0
2026-10-08,5.6,0.009,0.02,0.078,0.204,0.325,0.253,0.08,0.02,0.01,0.1,0,0.1,0.1,0.3,5.7,0.4,1.9,2.6,0.4,0.6,0.3,0.1,0,2,10.3,0.5,0
2026-10-09,5.6,0.007,0.02,0.081,0.201,0.329,0.252,0.079,0.02,0.011,0.1,0,0.1,0.1,0.4,5.7,0.4,1.9,2.5,0.3,0.6,0.3,0.1,0,1.9,10.4,0.5,0
2026-10-10,5.6,0.007,0.02,0.081,0.204,0.322,0.252,0.083,0.02,0.01,0.1,0,0.1,0.1,0.4,5.7,0.4,1.9,2.6,0.3,0.6,0.2,0.1,0,1.9,10.3,0.5,0
2026-10-11,5.6,0.007,0.02,0.08,0.2,0.327,0.25,0.084,0.019,0.01,0.1,0,0.1,0.1,0.4,5.7,0.4,1.9,2.6,0.3,0.7,0.2,0.1,0,1.9,10.4,0.5,0
2026-10-12,5.6,0.007,0.021,0.08,0.198,0.326,0.255,0.081,0.021,0.01,0.1,0,0.1,0.1,0.4,5.5,0.4,1.9,2.6,0.3,0.7,0.2,0.1,0,2,10.2,0.6,0
2026-10-13,5.6,0.013,0.02,0.079,0.201,0.326,0.248,0.082,0.021,0.01,0.1,0,0.1,0.1,0.3,5.5,0.3,1.9,2.6,0.3,0.7,0.2,0.1,0,1.9,10,0.6,0
2026-10-14,5.6,0.01,0.022,0.081,0.201,0.321,0.248,0.084,0.022,0.009,0.1,0,0.1,0.1,0.4,5.6,0.4,2,2.6,0.3,0.6,0.2,0.1,0,1.9,10.3,0.7,0
2026-10-15,5.6,0.008,0.025,0.078,0.206,0.322,0.248,0.083,0.023,0.008,0.1,0,0.1,0.1,0.4,5.5,0.4,2.1,2.6,0.3,0.7,0.2,0.1,0,1.9,10.1,0.7,0.1
2026-10-16,5.6,0.007,0.024,0.08,0.208,0.316,0.25,0.085,0.022,0.008,0.1,0,0.1,0.1,0.4,5.7,0.3,2.1,2.6,0.3,0.7,0.2,0.1,0,2,10.4,0.6,0.1
2026-10-17,5.7,0.007,0.025,0.077,0.21,0.321,0.244,0.085,0.021,0.009,0.1,0,0.1,0.1,0.4,5.7,0.3,2.2,2.8,0.3,0.7,0.3,0.1,0,2,10.3,0.6,0.1
2026-10-18,5.7,0.007,0.026,0.076,0.21,0.321,0.244,0.086,0.021,0.01,0.1,0,0.1,0.1,0.4,5.7,0.3,2.2,2.8,0.3,0.7,0.3,0.1,0,1.9,10.5,0.7,0.1
2026-10-19,,0.018,0.026,0.077,0.204,0.319,0.241,0.086,0.021,0.01,,,,,,,,,,,,,,,,,,
''',
}

HTML_TEMPLATE = r'''<!DOCTYPE html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>研究员的 Agent 平均日峰值并发分布</title>
<style>body{margin:1rem auto;max-width:1500px;font:16px system-ui}svg{width:100%;height:auto;display:block}output{position:fixed;pointer-events:none;color:white;background:#15181c;padding:.6rem .8rem;border-radius:8px;white-space:pre-line;font:14px/1.55 system-ui}</style>
{{svg}}<output hidden></output><script>
const series={{series}}, bins={{bins}}, cutoff='{{cutoff}}';
const area=document.querySelector('#plot-area path'), svg=document.querySelector('svg'), tip=document.querySelector('output');
const times=series.map(([d])=>Date.parse(d));
svg.addEventListener('pointermove', e=>{
  const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(area.getScreenCTM().inverse()), box=area.getBBox();
  const x=(p.x-box.x)/box.width, y=1-(p.y-box.y)/box.height;
  if(x<0 || x>1 || y<0 || y>1){tip.hidden=true;return}
  const t=times[0]+x*(times.at(-1)-times[0]);
  let i=0;while(i+1<times.length && t>(times[i]+times[i+1])/2)i++;
  const [day,shares]=series[i];let band=0,sum=shares[0];
  while(band<shares.length-1 && sum<y)sum+=shares[++band];
  tip.textContent=day+' · '+(day<=cutoff?'历史观测':'全速外推')+'\n平均日峰值并发 '+bins[band]+'\n研究员占比 '+(shares[band]*100).toFixed(2)+'%';
  tip.hidden=false;tip.style.left=Math.max(0,Math.min(innerWidth-tip.offsetWidth-8,e.clientX+12))+'px';
  tip.style.top=Math.max(0,Math.min(innerHeight-tip.offsetHeight-8,e.clientY+12))+'px';
});
svg.addEventListener('pointerleave',()=>tip.hidden=true);
</script></html>
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chart', choices=CHARTS, default='all', help='Plot to generate (default: all).')
    parser.add_argument('--output-dir', type=Path, default=HERE, help='Parent of figures/ and results/.')
    parser.add_argument('--data-dir', type=Path, help='Use local source CSVs instead of embedded observations.')
    args = parser.parse_args()
    run(chart=args.chart, output_dir=args.output_dir, data_dir=args.data_dir)
