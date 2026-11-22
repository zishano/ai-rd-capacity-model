"""Recompute the 2026 baseline and 2027–2030 A/B/C resource forecasts.

Run: python3 -B output_team100_resource_dashboard/build_data.py
Writes dashboard data, baseline/history/category/monthly CSVs, and validation metadata.
The previous 2030 table is read only after calculation, for endpoint assertions.
"""
import csv
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from math import ceil, fsum, isclose, isfinite
from pathlib import Path
from statistics import linear_regression


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
YEARS = range(2026, 2031)
SCENARIOS = ("A", "B", "C")
RESEARCHERS = 100
V1_FUTURE_SHA256 = "db04c55b75fd401946d029e3295754d1d567bcc35b85c0a11e46e9ed6d5c8619"
CORE_FIELDS = (
    "year", "date", "researchers", "scenario", "input_tokens_per_team_day",
    "cached_input_tokens_per_team_day", "uncached_input_tokens_per_team_day",
    "output_tokens_per_team_day", "total_tokens_per_team_day", "agent_hours_per_team_day",
    "mean_online_agent_equivalents", "task_starts_per_team_day", "eflop_per_team_day",
    "prefill_eflop_per_team_day", "decode_eflop_per_team_day", "prefix_cache_hit_rate",
    "tail_share", "compute_pflops_24h",
)
INPUTS = {
    "output": ROOT / "output_openai_researcher_forecast/official_data/output_tokens_14d.csv",
    "workdays": ROOT / "output_openai_official_100/official_data/workdays.csv",
    "task_starts": ROOT / "output_openai_official_100/official_data/task_starts.csv",
    "proxy_tasks": ROOT / "analysis/agentic_30t_forecast/workload/calibration/public_tasks.csv",
    "model": ROOT / "config/models/moe_30t.json",
    "scenario_settings": ROOT / "analysis/agentic_30t_forecast/workload/settings.json",
}
SOURCES = [
    {"label": "OpenAI 9月报告：18类研究员输出Token", "url": "https://openai.com/zh-Hans-CN/index/research-acceleration-view-inside-openai/#chart-4QLdZ4iw0n4L9rYGTvteZK"},
    {"label": "OpenAI 11月报告：Agent时长与任务发起率", "url": "https://openai.com/index/research-acceleration-jagged-frontier/"},
    {"label": "编码代理：SWE-bench的Kimi-K2.5公开提交", "url": "https://github.com/SWE-bench/experiments/tree/main/evaluation/verified/20260217_mini-v2.0.0_kimi-k2-5-high"},
    {"label": "合成30T模型的架构参考：Kimi K2", "url": "https://github.com/MoonshotAI/Kimi-K2"},
]
NOTES = [
    "2026是各指标最新公开观测组成的基线：输出截至8月15日，任务和时长截至10月18日，不是同一天的联合观测。2027–2030各行是当年11月18日的百人团队参考日强度，不是全年累计量。",
    "所有百人基线值均由官方人均统计乘100换算，不代表官方曾观测到这一支100人团队；history同时保留人均值和百人换算值。",
    "输出Token统一使用OpenAI公开的14日滑动平均：2026基线直接取8月15日的已平滑观测，历史不重复平滑；28日拼接值仅保留为旧口径参考，不用于页面计算。",
    "2026输入、缓存与Prefill/Decode FLOPs全部为30T假设下的proxy_estimate；A/B/C在2026都使用252题均匀池，tail_share=0。公开研究员观测不提供这些资源量。",
    "18类输出各用208日全历史OLS斜率，从2026-08-15公开末值锚定；直接预测目标日的14日平滑输出，逐类截零、合计并乘100，不再拼接为28日。",
    "任务发起率使用232日、Agent时长使用169日官方历史，全历史OLS保留拟合截距。任务数、输出及总时长分别外推，A/B/C共用这些量。",
    "A/B在资源汇总中均使用252个完整编码题等权分布；C以全池与输出最高26题混合，高输出子池成分权重在2027–2030依次为12.5%、25%、37.5%、50%。",
    "输入与缓存量由每年代理样本的加权输入/输出、缓存/输出比例迁移到全部研发类别；它们不是OpenAI研究员输入账单。缓存输入已包含在累计输入内。",
    "C年度权重沿用既有情景的渐进规则；252题的原18类资源汇总仅有2030，前述规则在此明确扩展到各年度。A/B的会话组织机制差异不产生这里的任务数变化。",
    "累计Agent小时除24仅是平均在线活动当量，不是团队同时峰值、LLM请求并发或GPU执行并发。",
    "30T Top-8是Kimi-K2风格MLA合成架构；每题使用其自身缓存率和峰值请求长度代理计算Prefill及Decode，再按输出规模加权迁移。FLOPs不是实测服务性能。",
    "compute_pflops_24h等于EFLOP/日×1000÷86400，仅表示24小时摊平的理论计算速率。",
    "输出使用14日窗口，任务/时长保留官方28日窗口。抽样、截尾、假期和名册也存在差异；各总量不能解释为同一批任务的联合账单。",
    "模型参数只用于单份权重载荷计算，总参数不乘研究员人数；KV、HBM、网络、卡数及部署副本均未估算。",
    "月度趋势的历史点取各月最后一条可用官方观测：Token为14日、Agent为28日；未来点取每月18日，沿用全历史OLS直接推算到2030-11-18。每一点仍为代表日强度，不是月累计；输入历史点仍为252题代理估算。",
    "Token月度历史显示范围保留2026-02起，完整14日观测仍保存在history中；Agent月度历史从2026-05开始。两者观测截止日与预测起点不同，不用缺失历史的预测值冒充观测。",
]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def fit_groups(rows, key=None):
    groups = defaultdict(dict)
    for row in rows:
        day = date.fromisoformat(row["date"])
        group = row[key] if key else "overall"
        assert day not in groups[group]
        groups[group][day] = float(row["value"])
    result = {}
    for group, values in groups.items():
        days = sorted(values)
        slope, intercept = linear_regression(
            [(day - days[0]).days for day in days], [values[day] for day in days]
        )
        result[group] = dict(first=days[0], last=days[-1], count=len(days),
                             last_value=values[days[-1]], slope=slope, intercept=intercept)
    return result


def project(fitted, day, anchor_observed=False):
    if anchor_observed:
        value = fitted["last_value"] + fitted["slope"] * (day - fitted["last"]).days
    else:
        value = fitted["intercept"] + fitted["slope"] * (day - fitted["first"]).days
    return max(0.0, value)


def model_parameters(architecture):
    a = architecture
    per_expert = a["expert_mlp_matrices"] * a["hidden_size"] * a["expert_intermediate_size"] * a["num_moe_layers"]
    router = a["hidden_size"] * a["num_routed_experts"] * a["num_moe_layers"]
    return {
        "total_parameters": per_expert * a["num_routed_experts"] + router + a["non_routed_parameters"],
        "active_parameters": per_expert * a["experts_per_token"] + router + a["non_routed_parameters"],
        "experts_per_token": a["experts_per_token"],
        "name": "合成30T Top-8 MoE",
    }


def observed_baseline(output_rows, starts_rows, work_rows):
    """Keep source dates/windows separate; never treat November fits as observations."""
    output_by_day = defaultdict(dict)
    starts_by_day = defaultdict(list)
    for row in output_rows:
        output_by_day[row["date"]][row["category"]] = row
        assert int(row["rolling_window_days"]) == 14
    for row in starts_rows:
        starts_by_day[row["date"]].append(float(row["value"]))
        assert int(row["rolling_window_days"]) == 28
    assert all(len(v) == 18 for v in output_by_day.values())
    assert all(len(v) == 18 for v in starts_by_day.values())
    assert all(int(r["rolling_window_days"]) == 28 for r in work_rows)
    output_day = max(output_by_day)
    lag_day = str(date.fromisoformat(output_day) - timedelta(days=14))
    hours_row = max(work_rows, key=lambda r: r["date"])
    tasks_day = max(starts_by_day)
    dates = dict(output=output_day, agent_hours=hours_row["date"], task_starts=tasks_day)
    output14 = fsum(float(r["value"]) for r in output_by_day[output_day].values())
    category28 = {
        k: (float(r["value"]) + float(output_by_day[lag_day][k]["value"])) / 2
        for k, r in output_by_day[output_day].items()
    }
    output28 = fsum(category28.values())
    hours = float(hours_row["value"]) * 8
    tasks = fsum(starts_by_day[tasks_day])
    selected_manifest = json.loads((INPUTS["output"].parent.parent / "source_downloads/download_manifest.json").read_text())
    november_manifest = next(m for m in json.loads((INPUTS["workdays"].parent.parent / "source_downloads/download_manifest.json").read_text()) if m["id"] == "november_2026")
    source_checks = []
    for role in ("output", "workdays", "task_starts"):
        path = INPUTS[role]
        manifest = json.loads((path.parent / "normalization_manifest.json").read_text())
        table = next(t for t in manifest["tables"] if t["file"] == path.name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == table["sha256"]
        source_checks.append(dict(role=role, sha256=digest, normalization_manifest_verified=True))

    def metric(day, window, value, unit, evidence, label, source_row, download):
        return dict(date=day, rolling_window_days=window,
                    value_per_researcher_day=value, value_per_team_day=value*RESEARCHERS,
                    researchers=RESEARCHERS, evidence=evidence, unit=unit, label=label,
                    source_url=source_row["source_url"], chart_file=source_row["chart_file"],
                    source_unit=source_row["unit"], downloaded_at_utc=download["downloaded_at_utc"])

    out_source = output_rows[0]
    metadata = {
        "output_14d": metric(output_day, 14, output14, "Token/日", "official_observation", "官方公布输出：14日均值", out_source, selected_manifest),
        "output_28d": metric(output_day, 28, output28, "Token/日", "derived_from_observed", "旧口径参考：相邻14日观测拼接为28日；非当前页面输出", out_source, selected_manifest),
        "agent_hours": metric(hours_row["date"], 28, hours, "Agent小时/日", "derived_from_observed", "官方Agent工作日×8小时", hours_row, november_manifest),
        "mean_online_agent_equivalents": metric(hours_row["date"], 28, hours*RESEARCHERS/24/RESEARCHERS, "平均在线活动当量", "derived_from_observed", "累计Agent小时÷24", hours_row, november_manifest),
        "task_starts": metric(tasks_day, 28, tasks, "次/日", "official_observation", "官方18类任务发起率之和", starts_rows[0], november_manifest),
        "resource_estimates": dict(evidence="proxy_estimate", label="30T/252题均匀代理估算；非官方输入、缓存或FLOPs观测"),
    }
    metadata["output_28d"].update(lag_date=lag_day, source_rolling_window_days=14,
                                  formula="(T14(d) + T14(d-14)) / 2", current_page_usage=False)
    metadata["output_14d"]["current_page_usage"] = True
    for key in ("agent_hours", "mean_online_agent_equivalents"):
        metadata[key].update(source_agent_workdays_per_researcher_day=float(hours_row["value"]),
                             hours_per_agent_workday=8, source_group="Overall Research",
                             source_values_rounded=True)
    metadata["task_starts"]["source_values_rounded"] = True
    baseline = dict(year=2026, researchers=RESEARCHERS, observed_dates=dates, metrics=metadata,
                    output_tokens_per_team_day=output14*RESEARCHERS, output_rolling_window_days=14,
                    reported_output_tokens_per_team_day_14d=output14*RESEARCHERS,
                    comparison_output_tokens_per_team_day_28d=output28*RESEARCHERS,
                    agent_hours_per_team_day=hours*RESEARCHERS,
                    mean_online_agent_equivalents=hours*RESEARCHERS/24,
                    task_starts_per_team_day=tasks*RESEARCHERS)
    history = []

    def history_row(day, name, value, window, unit, evidence, source_row):
        history.append(dict(date=day, metric=name, value_per_researcher_day=value,
                            value_per_team_day=value*RESEARCHERS, researchers=RESEARCHERS,
                            unit=unit, rolling_window_days=window, evidence=evidence,
                            source_url=source_row["source_url"], chart_file=source_row["chart_file"]))

    for day, categories in sorted(output_by_day.items()):
        value = fsum(float(r["value"]) for r in categories.values())
        history_row(day, "output_tokens_14d", value, 14, "Token/日", "official_observation", out_source)
        lag = str(date.fromisoformat(day) - timedelta(days=14))
        if lag in output_by_day:
            aligned = fsum((float(r["value"])+float(output_by_day[lag][k]["value"]))/2 for k, r in categories.items())
            history_row(day, "output_tokens_28d", aligned, 28, "Token/日", "derived_from_observed", out_source)
    for row in sorted(work_rows, key=lambda r: r["date"]):
        value = float(row["value"])
        history_row(row["date"], "agent_workdays", value, 28, "8小时Agent工作日/日", "official_observation", row)
        history_row(row["date"], "agent_hours", value*8, 28, "Agent小时/日", "derived_from_observed", row)
        history_row(row["date"], "mean_online_agent_equivalents", value*8/24, 28, "平均在线活动当量", "derived_from_observed", row)
    for day, values in sorted(starts_by_day.items()):
        history_row(day, "task_starts", fsum(values), 28, "次/日", "official_observation", starts_rows[0])
    return baseline, history, output_by_day[output_day], category28, source_checks


def monthly_forecast_dates(last_observed, endpoint=date(2030, 11, 18)):
    """One forecast point per month, beginning after the last observed month."""
    month_index = last_observed.year * 12 + last_observed.month
    while True:
        year, month0 = divmod(month_index, 12)
        day = date(year, month0 + 1, 18)
        if day > endpoint:
            return
        yield day
        month_index += 1


def calculate_monthly(history, output_fits, work_fit, tasks, cutoff, tail_size, settings):
    """Sample actual observations monthly, then evaluate the existing forecast models."""
    samples = {}
    for metric in ("output_tokens_14d", "agent_hours"):
        last_in_month = {}
        for row in sorted((r for r in history if r["metric"] == metric), key=lambda r: r["date"]):
            if metric == "output_tokens_14d" and row["date"] < "2026-02-01":
                continue  # Retain the existing chart's display range; full history stays archived.
            last_in_month[row["date"][:7]] = row
        samples[metric] = list(last_in_month.values())

    monthly = dict(tokens=[], agents=[])
    reference = date.fromisoformat(settings["reference_date"])
    source_tokens = samples["output_tokens_14d"][0]["source_url"]
    source_agents = samples["agent_hours"][0]["source_url"]

    def token_row(day, output, phase, scenario):
        progress = max(0.0, min(1.0, ((day.year - reference.year) * 12 + day.month - reference.month) / 48))
        tail_share = settings["scenarios"][scenario]["upper_decile_mix_2030"] * progress if phase == "forecast" else 0.0
        weights = [(1 - tail_share) / len(tasks) + (tail_share / tail_size if int(t["completion"]) >= cutoff else 0) for t in tasks]
        sample_input = fsum(w * float(t["prompt"]) for w, t in zip(weights, tasks))
        sample_output = fsum(w * float(t["completion"]) for w, t in zip(weights, tasks))
        return dict(
            date=str(day), month=str(day)[:7], year=day.year, scenario=scenario, researchers=RESEARCHERS,
            input_tokens_per_team_day=output * sample_input / sample_output,
            output_tokens_per_team_day=output,
            input_evidence="estimated" if phase == "observed" else "forecast",
            output_evidence=phase, phase=phase, rolling_window_days=14, tail_share=tail_share,
            source_url=source_tokens, input_proxy_source_url=SOURCES[2]["url"],
        )

    def agent_row(day, hours, phase, scenario):
        return dict(
            date=str(day), month=str(day)[:7], year=day.year, scenario=scenario, researchers=RESEARCHERS,
            agent_hours_per_team_day=hours, mean_online_agent_equivalents=hours / 24,
            agent_hours_evidence=phase, mean_online_agent_equivalents_evidence=phase,
            phase=phase, rolling_window_days=28, source_url=source_agents,
        )

    for sample in samples["output_tokens_14d"]:
        day = date.fromisoformat(sample["date"])
        for scenario in SCENARIOS:
            monthly["tokens"].append(token_row(day, sample["value_per_team_day"], "observed", scenario))
    for day in monthly_forecast_dates(date.fromisoformat(samples["output_tokens_14d"][-1]["date"])):
        output = RESEARCHERS * fsum(project(f, day, True) for f in output_fits.values())
        for scenario in SCENARIOS:
            monthly["tokens"].append(token_row(day, output, "forecast", scenario))

    for sample in samples["agent_hours"]:
        day = date.fromisoformat(sample["date"])
        for scenario in SCENARIOS:
            monthly["agents"].append(agent_row(day, sample["value_per_team_day"], "observed", scenario))
    for day in monthly_forecast_dates(date.fromisoformat(samples["agent_hours"][-1]["date"])):
        hours = RESEARCHERS * 8 * project(work_fit, day)
        for scenario in SCENARIOS:
            monthly["agents"].append(agent_row(day, hours, "forecast", scenario))

    metadata = dict(
        endpoint="2030-11-18", researchers=RESEARCHERS, rolling_window_days={"tokens": 14, "agents": 28},
        value_semantics="每月代表日的百人自然日日强度；不是整月累计量",
        historical_sampling="每月最后一条可用官方观测，输出14日/Agent28日，保留其实际日期；不填补缺失观测月份",
        future_sampling="从各指标最后观测的次月起，每月18日直接计算，直至2030-11-18",
        evidence=dict(observed="官方观测换算值：Token直接使用14日平滑值；Agent的28日工作日乘8、小时除24",
                      estimated="历史输出乘252题输入/输出比的代理估算，非官方输入观测",
                      forecast="沿用全历史OLS的条件外推；输入另外包含252题代理比率假设"),
        sources=SOURCES[:3],
    )
    for name, metric in (("tokens", "output_tokens_14d"), ("agents", "agent_hours")):
        selected = [r for r in monthly[name] if r["scenario"] == "A"]
        observed = [r for r in selected if r["phase"] == "observed"]
        forecast = [r for r in selected if r["phase"] == "forecast"]
        metadata[name] = dict(
            observed_start=observed[0]["date"], observed_end=observed[-1]["date"],
            forecast_start=forecast[0]["date"], forecast_end=forecast[-1]["date"],
            observed_points_per_scenario=len(observed), forecast_points_per_scenario=len(forecast),
            points_per_scenario=len(selected), row_count=len(monthly[name]),
            history_metric=metric, observed_dates=[r["date"] for r in observed],
            rolling_window_days=14 if name == "tokens" else 28,
            source_url=selected[0]["source_url"],
        )
    metadata["tokens"].update(
        output_forecast_method="18类各用208日全历史OLS斜率，从2026-08-15末值锚定；目标日14日平滑预测逐类截零、求和并乘100；不重复平滑",
        input_forecast_method="每月输出乘当月252题加权输入/输出比；A/B始终均匀池，C按年月进度混合输出最高26题",
        c_tail_share_formula="0.5 × clip(((year−2026)×12 + month−11)/48, 0, 1)；所有历史点为0",
        no_january_point_reason="保持既有月度图显示范围从2026-02开始；2026-01原始14日观测仍完整保留于history",
    )
    metadata["agents"].update(
        hours_forecast_method="169日Overall Research工作日历史全样本OLS，保留拟合截距；预测工作日乘8小时再乘100",
        equivalents_method="agent_hours_per_team_day / 24；为平均活动当量，不是瞬时峰值并发",
    )
    return monthly, metadata


def calculate_monthly_resources(token_rows, token_metadata, tasks, cutoff, tail_size):
    """Extend each existing token point using the identical annual proxy arithmetic."""
    result = []
    evidence_fields = {
        "cached_input_tokens_per_team_day": "cached_input_evidence",
        "uncached_input_tokens_per_team_day": "uncached_input_evidence",
        "total_tokens_per_team_day": "total_tokens_evidence",
        "prefill_eflop_per_team_day": "prefill_eflop_evidence",
        "decode_eflop_per_team_day": "decode_eflop_evidence",
        "eflop_per_team_day": "eflop_evidence",
        "prefix_cache_hit_rate": "prefix_cache_hit_rate_evidence",
        "compute_pflops_24h": "compute_pflops_24h_evidence",
    }
    for token in token_rows:
        tail_share = token["tail_share"]
        weights = [(1 - tail_share) / len(tasks) + (tail_share / tail_size if int(t["completion"]) >= cutoff else 0) for t in tasks]

        def weighted(field):
            return fsum(w * float(t[field]) for w, t in zip(weights, tasks))

        sample_input, sample_output, sample_cached = (weighted(k) for k in ("prompt", "completion", "cache_read"))
        output = token["output_tokens_per_team_day"]
        assert token["input_tokens_per_team_day"] == output * sample_input / sample_output
        inp = token["input_tokens_per_team_day"]
        cached = output * sample_cached / sample_output
        prefill = output * weighted("prefill_eflop") / sample_output
        decode = output * weighted("decode_eflop") / sample_output
        evidence = "estimated" if token["phase"] == "observed" else "forecast"
        row = dict(token, cached_input_tokens_per_team_day=cached,
                   uncached_input_tokens_per_team_day=inp-cached,
                   total_tokens_per_team_day=inp+output,
                   prefill_eflop_per_team_day=prefill, decode_eflop_per_team_day=decode,
                   eflop_per_team_day=prefill+decode,
                   prefix_cache_hit_rate=sample_cached/sample_input,
                   compute_pflops_24h=(prefill+decode)*1000/86400,
                   resource_evidence=evidence)
        row.update({evidence_field: evidence for evidence_field in evidence_fields.values()})
        result.append(row)
    metadata = dict(token_metadata,
                    value_semantics="与Token序列完全相同日期的百人自然日日资源强度；不是月累计量",
                    resource_method="沿用年度252题代理的逐题加权输入、缓存、Prefill和Decode计算，再按当月输出规模迁移；未重新拟合",
                    phase_semantics="phase沿用Token输出的观测/预测阶段；所有输入、缓存和计算量均为条件估算或预测",
                    resource_evidence=dict(estimated="历史输出观测乘合成30T/252题代理比率；不是官方资源实测",
                                           forecast="月度输出OLS预测乘相同代理模型当月比率"),
                    metric_evidence_fields={"input_tokens_per_team_day": "input_evidence",
                                            "output_tokens_per_team_day": "output_evidence", **evidence_fields},
                    units={"input_tokens_per_team_day": "Token/日", "output_tokens_per_team_day": "Token/日",
                           "cached_input_tokens_per_team_day": "Token/日", "uncached_input_tokens_per_team_day": "Token/日",
                           "total_tokens_per_team_day": "Token/日", "prefill_eflop_per_team_day": "EFLOP/日",
                           "decode_eflop_per_team_day": "EFLOP/日", "eflop_per_team_day": "EFLOP/日",
                           "prefix_cache_hit_rate": "比例（0至1）", "compute_pflops_24h": "PFLOP/s"},
                    identities=["input = cached_input + uncached_input", "total_tokens = input + output",
                                "eflop = prefill_eflop + decode_eflop", "compute_pflops_24h = eflop × 1000 / 86400"],
                    cache_rate_method="加权缓存输入 / 加权累计输入；按Token加权，不是逐题缓存率平均",
                    sources=SOURCES[:3],
                    unsupported_metrics=["GPU卡数", "部署副本", "HBM容量", "显存带宽", "网络带宽", "请求瞬时峰值并发", "LLM请求并发"])
    return result, metadata


def calculate_monthly_tasks(history, starts_fits):
    """Keep the task series' own observation dates and original 232-day OLS fits."""
    last_in_month = {}
    for row in sorted((r for r in history if r["metric"] == "task_starts"), key=lambda r: r["date"]):
        last_in_month[row["date"][:7]] = row
    samples = list(last_in_month.values())
    source = samples[0]["source_url"]
    result = []

    def append_point(day, value, phase):
        for scenario in SCENARIOS:
            result.append(dict(date=str(day), month=str(day)[:7], year=day.year,
                               scenario=scenario, researchers=RESEARCHERS,
                               task_starts_per_team_day=value, task_starts_evidence=phase,
                               phase=phase, rolling_window_days=28, source_url=source))

    for sample in samples:
        append_point(date.fromisoformat(sample["date"]), sample["value_per_team_day"], "observed")
    for day in monthly_forecast_dates(date.fromisoformat(samples[-1]["date"])):
        starts = RESEARCHERS * fsum(project(f, day) for f in starts_fits.values())
        append_point(day, starts, "forecast")
    observed = [r for r in result if r["scenario"] == "A" and r["phase"] == "observed"]
    forecast = [r for r in result if r["scenario"] == "A" and r["phase"] == "forecast"]
    metadata = dict(observed_start=observed[0]["date"], observed_end=observed[-1]["date"],
                    forecast_start=forecast[0]["date"], forecast_end=forecast[-1]["date"],
                    observed_points_per_scenario=len(observed), forecast_points_per_scenario=len(forecast),
                    points_per_scenario=len(observed)+len(forecast), row_count=len(result),
                    history_metric="task_starts", observed_dates=[r["date"] for r in observed], source_url=source,
                    researchers=RESEARCHERS, rolling_window_days=28, unit="次/日",
                    value_semantics="每月代表日的百人研发任务发起强度；不是月累计或LLM请求次数",
                    historical_sampling="每月最后一条可用28日官方任务发起率观测，18类求和乘100，保留实际日期",
                    future_sampling="最后观测次月起每月18日，直至2030-11-18",
                    forecast_method="沿用18类各232日全历史OLS拟合，保留截距；目标日各类预测截零、求和后乘100",
                    scenario_semantics="A/B/C共用任务发起率，情景差异不改变这里的任务数",
                    evidence=dict(observed="官方18类任务发起率求和并按百人换算", forecast="全历史OLS的条件外推"))
    return result, metadata


def calculate_rows():
    output_rows = read_csv(INPUTS["output"])
    starts_rows = read_csv(INPUTS["task_starts"])
    work_rows = [r for r in read_csv(INPUTS["workdays"]) if r["group"] == "Overall Research"]
    baseline, history, latest_categories, category28, source_checks = observed_baseline(output_rows, starts_rows, work_rows)
    output_fits = fit_groups(output_rows, "category")
    starts_fits = fit_groups(starts_rows, "category")
    work_fit = fit_groups(work_rows)["overall"]
    assert set(output_fits) == set(starts_fits) and len(output_fits) == 18
    assert all(f["count"] == 208 for f in output_fits.values())
    assert all(f["count"] == 232 for f in starts_fits.values())
    assert work_fit["count"] == 169
    settings = json.loads(INPUTS["scenario_settings"].read_text())
    assert settings["reference_date"] == "2026-11-18"
    assert settings["scenarios"]["C"]["upper_decile_mix_2030"] == 0.5
    assert all(settings["scenarios"][s]["upper_decile_mix_2030"] == 0 for s in ("A", "B"))
    a = json.loads(INPUTS["model"].read_text())["architecture"]
    assert a["target_total_parameters"] == 30_000_000_000_000 and a["experts_per_token"] == 8
    model = model_parameters(a)
    tasks = [r for r in read_csv(INPUTS["proxy_tasks"]) if r["complete"] == "1"]
    assert len(tasks) == 252
    cutoff = sorted(int(t["completion"]) for t in tasks)[ceil(0.9 * len(tasks)) - 1]
    tail_size = sum(int(t["completion"]) >= cutoff for t in tasks)
    assert tail_size == 26
    for task in tasks:
        inp, out, cached = (int(task[k]) for k in ("prompt", "completion", "cache_read"))
        assert inp > 0 and out >= 0 and 0 <= cached <= inp
        context = int(task["peak_request"])
        attention = a["num_hidden_layers"] * a["num_attention_heads"] * (
            a["qk_nope_head_dim"] + a["qk_rope_head_dim"] + a["v_head_dim"]
        ) * context
        # Same first-order core arithmetic: 2P plus QK/AV, uncached input only.
        task["prefill_eflop"] = inp * (1 - cached / inp) * (2 * model["active_parameters"] + 2 * attention) / 1e18
        task["decode_eflop"] = out * (2 * model["active_parameters"] + 4 * attention) / 1e18
    rows, category_mix = [], []
    for year in YEARS:
        day = date(year, 11, 18) if year != 2026 else None
        if year == 2026:
            category_values = {key: float(row["value"]) for key, row in latest_categories.items()}
            output = baseline["output_tokens_per_team_day"]
            starts = baseline["task_starts_per_team_day"]
            hours = baseline["agent_hours_per_team_day"]
        else:
            category_values = {k: project(f, day, True) for k, f in output_fits.items()}
            output = RESEARCHERS * fsum(category_values.values())
            starts = RESEARCHERS * fsum(project(f, day) for f in starts_fits.values())
            hours = RESEARCHERS * 8 * project(work_fit, day)
        for scenario in SCENARIOS:
            tail_share = settings["scenarios"][scenario]["upper_decile_mix_2030"] * (year - 2026) / 4
            weights = [(1 - tail_share) / len(tasks) + (tail_share / tail_size if int(t["completion"]) >= cutoff else 0) for t in tasks]
            assert isclose(fsum(weights), 1.0, rel_tol=1e-14)

            def weighted(field):
                return fsum(w * float(t[field]) for w, t in zip(weights, tasks))

            sample_input, sample_output, sample_cached = (weighted(k) for k in ("prompt", "completion", "cache_read"))
            inp = output * sample_input / sample_output
            cached = output * sample_cached / sample_output
            prefill = output * weighted("prefill_eflop") / sample_output
            decode = output * weighted("decode_eflop") / sample_output
            rows.append(dict(
                year=year, date=str(day) if day else None, researchers=RESEARCHERS, scenario=scenario,
                output_rolling_window_days=14, agent_rolling_window_days=28, task_rolling_window_days=28,
                input_tokens_per_team_day=inp, cached_input_tokens_per_team_day=cached,
                uncached_input_tokens_per_team_day=inp-cached, output_tokens_per_team_day=output,
                total_tokens_per_team_day=inp+output, agent_hours_per_team_day=hours,
                mean_online_agent_equivalents=hours/24, task_starts_per_team_day=starts,
                eflop_per_team_day=prefill+decode, prefill_eflop_per_team_day=prefill,
                decode_eflop_per_team_day=decode, prefix_cache_hit_rate=sample_cached/sample_input,
                tail_share=tail_share, compute_pflops_24h=(prefill+decode)*1000/86400,
                row_type="observed_baseline_with_proxy_resources" if year == 2026 else "forecast",
                evidence="mixed_observed_and_proxy_estimate" if year == 2026 else "conditional_forecast",
                observed_dates=baseline["observed_dates"] if year == 2026 else None,
                resource_evidence="proxy_estimate" if year == 2026 else "conditional_proxy_forecast",
            ))
            for category, value in category_values.items():
                source = latest_categories[category]
                raw14 = float(source["value"])*RESEARCHERS if year == 2026 else None
                category_mix.append(dict(
                    year=year, scenario=scenario, researchers=RESEARCHERS, category=category,
                    category_label=source["category_label"], category_label_en=source["category_label_en"],
                    area=source["area"], stack_index=int(source["stack_index"]),
                    date=baseline["observed_dates"]["output"] if year == 2026 else str(day),
                    rolling_window_days=14, output_tokens_per_team_day=value*RESEARCHERS,
                    share=value*RESEARCHERS/output,
                    output_tokens_14d_per_team_day=raw14,
                    share_14d=raw14/baseline["reported_output_tokens_per_team_day_14d"] if year == 2026 else None,
                    evidence="official_observation_scaled_to_team" if year == 2026 else "conditional_forecast",
                    source_url=source["source_url"],
                ))
    monthly, monthly_metadata = calculate_monthly(history, output_fits, work_fit, tasks, cutoff, tail_size, settings)
    monthly_resources, resources_metadata = calculate_monthly_resources(monthly["tokens"], monthly_metadata["tokens"], tasks, cutoff, tail_size)
    monthly_tasks, tasks_metadata = calculate_monthly_tasks(history, starts_fits)
    extensions = dict(monthly_resources=monthly_resources, monthly_resources_metadata=resources_metadata,
                      monthly_tasks=monthly_tasks, monthly_tasks_metadata=tasks_metadata)
    return rows, model, baseline, history, category_mix, source_checks, monthly, monthly_metadata, extensions


def validate_monthly(monthly, metadata, rows, history):
    annual = {(r["year"], r["scenario"]): r for r in rows}
    fields = dict(tokens=("input_tokens_per_team_day", "output_tokens_per_team_day"),
                  agents=("agent_hours_per_team_day", "mean_online_agent_equivalents"))
    expected = dict(tokens=(58, 7, "2026-02-28", "2026-08-15", "2026-09-18"),
                    agents=(55, 6, "2026-05-31", "2026-10-18", "2026-11-18"))
    for name, collection in monthly.items():
        count, observed_count, first, observed_end, forecast_start = expected[name]
        assert len(collection) == count * 3
        assert metadata[name]["observed_start"] == first
        assert metadata[name]["observed_end"] == observed_end
        assert metadata[name]["forecast_start"] == forecast_start
        assert metadata[name]["forecast_end"] == "2030-11-18"
        history_index = {r["date"]: r for r in history if r["metric"] == metadata[name]["history_metric"]}
        for scenario in SCENARIOS:
            selected = [r for r in collection if r["scenario"] == scenario]
            assert len({r["month"] for r in selected}) == count
            assert [r["date"] for r in selected] == sorted(r["date"] for r in selected)
            assert sum(r["phase"] == "observed" for r in selected) == observed_count
            for r in selected:
                assert all(isfinite(r[k]) and r[k] >= 0 for k in fields[name])
                assert r["month"] == r["date"][:7]
                if r["phase"] == "observed":
                    assert r["date"] in history_index
                    history_value = history_index[r["date"]]["value_per_team_day"]
                    assert r[fields[name][1 if name == "tokens" else 0]] == history_value
                    same_month = [h for h in history_index if h[:7] == r["month"]]
                    assert r["date"] == max(same_month)
                    if name == "tokens":
                        assert r["input_evidence"] == "estimated" and r["output_evidence"] == "observed"
                        assert r["tail_share"] == 0
                else:
                    assert r["phase"] == "forecast" and r["date"][-2:] == "18"
                    assert r["date"] > observed_end
                if name == "agents":
                    assert r["mean_online_agent_equivalents"] == r["agent_hours_per_team_day"] / 24
                if r["month"] in {f"{year}-11" for year in range(2027, 2031)}:
                    assert all(r[k] == annual[(r["year"], scenario)][k] for k in fields[name])
            latest_observed = next(r for r in selected if r["date"] == observed_end)
            assert all(latest_observed[k] == annual[(2026, scenario)][k] for k in fields[name])
        for month in {r["month"] for r in collection}:
            group = [r for r in collection if r["month"] == month]
            assert len(group) == 3
            assert all(group[0][k] == group[1][k] for k in group[0] if k != "scenario")
            if name == "tokens":
                assert len({r["output_tokens_per_team_day"] for r in group}) == 1
            else:
                assert all(group[0][k] == group[2][k] for k in group[0] if k != "scenario")
    return dict(status="passed", tokens_rows=len(monthly["tokens"]), agents_rows=len(monthly["agents"]),
                checks=["历史每月选最后一条实际观测（Token14日，Agent28日），真实日期与原始history严格相同；未补造历史。",
                        "预测每月18日直接计算，两个序列分别从自己的观测截止次月起始。",
                        "各年11月18日月度值与2027–2030既有年度值逐字段精确相同。",
                        "2026各序列最后观测及输入估算与既有基线精确相同。",
                        "A/B相同、ABC输出与Agent共用；Agent小时除24换算通过。"])


def validate_monthly_extensions(extensions, monthly, rows, history):
    annual = {(r["year"], r["scenario"]): r for r in rows}
    resources = extensions["monthly_resources"]
    metadata = extensions["monthly_resources_metadata"]
    assert len(resources) == len(monthly["tokens"]) == 174
    metrics = list(metadata["units"])
    evidence_fields = metadata["metric_evidence_fields"]
    for resource, token in zip(resources, monthly["tokens"]):
        assert all(resource[k] == value for k, value in token.items()), "Monthly token fields changed"
        assert all(isfinite(resource[k]) and resource[k] >= 0 for k in metrics)
        assert 0 <= resource["prefix_cache_hit_rate"] <= 1
        expected_evidence = "estimated" if resource["phase"] == "observed" else "forecast"
        assert resource["resource_evidence"] == expected_evidence
        for metric, field in evidence_fields.items():
            assert resource[field] == (resource["phase"] if metric == "output_tokens_per_team_day" else expected_evidence)
        for actual, expected in (
            (resource["input_tokens_per_team_day"], resource["cached_input_tokens_per_team_day"]+resource["uncached_input_tokens_per_team_day"]),
            (resource["total_tokens_per_team_day"], resource["input_tokens_per_team_day"]+resource["output_tokens_per_team_day"]),
            (resource["eflop_per_team_day"], resource["prefill_eflop_per_team_day"]+resource["decode_eflop_per_team_day"]),
            (resource["compute_pflops_24h"], resource["eflop_per_team_day"]*1000/86400),
            (resource["prefix_cache_hit_rate"], resource["cached_input_tokens_per_team_day"]/resource["input_tokens_per_team_day"]),
        ):
            assert isclose(actual, expected, rel_tol=1e-12)
        if resource["date"] == "2026-08-15" or resource["month"] in {f"{year}-11" for year in range(2027, 2031)}:
            reference = annual[(resource["year"], resource["scenario"])]
            assert all(resource[k] == reference[k] for k in metrics), (resource["date"], resource["scenario"])

    tasks = extensions["monthly_tasks"]
    task_meta = extensions["monthly_tasks_metadata"]
    assert len(tasks) == 171 and task_meta["points_per_scenario"] == 57
    assert task_meta["observed_start"] == "2026-03-31"
    assert task_meta["observed_end"] == "2026-10-18"
    assert task_meta["forecast_start"] == "2026-11-18"
    assert task_meta["forecast_end"] == "2030-11-18"
    history_index = {r["date"]: r for r in history if r["metric"] == "task_starts"}
    field = "task_starts_per_team_day"
    for scenario in SCENARIOS:
        selected = [r for r in tasks if r["scenario"] == scenario]
        assert len({r["month"] for r in selected}) == 57
        assert [r["date"] for r in selected] == sorted(r["date"] for r in selected)
        assert sum(r["phase"] == "observed" for r in selected) == 8
        for row in selected:
            assert isfinite(row[field]) and row[field] >= 0
            assert row["task_starts_evidence"] == row["phase"]
            assert row["month"] == row["date"][:7]
            if row["phase"] == "observed":
                assert row["date"] in history_index
                assert row[field] == history_index[row["date"]]["value_per_team_day"]
                assert row["date"] == max(day for day in history_index if day[:7] == row["month"])
            else:
                assert row["phase"] == "forecast" and row["date"][-2:] == "18"
                assert row["date"] > task_meta["observed_end"]
            if row["date"] == "2026-10-18" or row["month"] in {f"{year}-11" for year in range(2027, 2031)}:
                assert row[field] == annual[(row["year"], scenario)][field]
    for month in {r["month"] for r in tasks}:
        group = [r for r in tasks if r["month"] == month]
        assert len(group) == 3 and len({r[field] for r in group}) == 1
    return dict(status="passed", resource_rows=len(resources), task_rows=len(tasks),
                checks=["月度资源完整保留原Token各行全部字段，日期及旧值精确不变。",
                        "新增缓存、未缓存、总Token、Prefill/Decode/总EFLOP、缓存率和PFLOP/s沿用年度252题代理算式。",
                        "所有新增资源字段在基线及2027–2030年11月18日与既有年度数据精确相同。",
                        "历史输入缓存计算均标记estimated，未把代理估算标记为官方观测。",
                        "任务月度历史点为每月最后真实28日观测，未来沿用原232日OLS，无重新拟合或口径改变。",
                        "任务2026最后观测及2027–2030年11月18日与既有年度值精确相同；ABC任务数相同。",
                        "资源加总、Token加权缓存率及24小时计算速率恒等式通过。"],
                supported_metrics=metrics+[field], unsupported_metrics=metadata["unsupported_metrics"])


def validate(rows, baseline, history, category_mix, source_checks):
    assert len(rows) == 15
    assert {(r["year"], r["scenario"]) for r in rows} == {(y, s) for y in YEARS for s in SCENARIOS}
    for r in rows:
        assert all(isfinite(v) and v >= 0 for v in r.values() if isinstance(v, (int, float)))
        assert 0 <= r["prefix_cache_hit_rate"] <= 1
        for actual, expected in [
            (r["input_tokens_per_team_day"], r["cached_input_tokens_per_team_day"] + r["uncached_input_tokens_per_team_day"]),
            (r["total_tokens_per_team_day"], r["input_tokens_per_team_day"] + r["output_tokens_per_team_day"]),
            (r["eflop_per_team_day"], r["prefill_eflop_per_team_day"] + r["decode_eflop_per_team_day"]),
            (r["agent_hours_per_team_day"], 24 * r["mean_online_agent_equivalents"]),
            (r["eflop_per_team_day"], r["compute_pflops_24h"] * 86400 / 1000),
        ]:
            assert isclose(actual, expected, rel_tol=1e-12)
    for year in YEARS:
        group = [r for r in rows if r["year"] == year]
        assert all(group[0][k] == group[1][k] for k in group[0] if k != "scenario")
        for key in ("output_tokens_per_team_day", "agent_hours_per_team_day", "mean_online_agent_equivalents", "task_starts_per_team_day"):
            assert len({r[key] for r in group}) == 1
    future_rows = [{k: r[k] for k in CORE_FIELDS} for r in rows if r["year"] >= 2027]
    future_hash = hashlib.sha256(json.dumps(future_rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    # The v1 hash described the retired 28-day output convention. Validate the
    # unchanged model/usage dimensions and the native 14-day endpoint below.
    assert isclose(next(r for r in rows if r["year"] == 2030)["output_tokens_per_team_day"],
                   473000175.4735102, rel_tol=1e-14), "Native 14-day OLS endpoint changed"
    assert baseline["observed_dates"] == dict(output="2026-08-15", agent_hours="2026-10-18", task_starts="2026-10-18")
    for key, expected in {
        "reported_output_tokens_per_team_day_14d": 72283322.89131717,
        "output_tokens_per_team_day": 72283322.89131717,
        "comparison_output_tokens_per_team_day_28d": 65525718.13177636,
        "agent_hours_per_team_day": 4560, "mean_online_agent_equivalents": 190,
        "task_starts_per_team_day": 2630,
    }.items():
        assert isclose(baseline[key], expected, rel_tol=1e-14), key
    baseline_rows = [r for r in rows if r["year"] == 2026]
    assert all(r["date"] is None and r["tail_share"] == 0 and r["resource_evidence"] == "proxy_estimate" for r in baseline_rows)
    assert all(baseline_rows[0][k] == r[k] for r in baseline_rows for k in baseline_rows[0] if k != "scenario")
    assert len(category_mix) == 15*18
    for r in rows:
        categories = [c for c in category_mix if (c["year"], c["scenario"]) == (r["year"], r["scenario"])]
        assert len(categories) == 18
        assert isclose(fsum(c["share"] for c in categories), 1.0, rel_tol=1e-14)
        assert isclose(fsum(c["output_tokens_per_team_day"] for c in categories), r["output_tokens_per_team_day"], rel_tol=1e-14)
    expected_history_counts = dict(output_tokens_14d=208, output_tokens_28d=194,
                                   agent_workdays=169, agent_hours=169,
                                   mean_online_agent_equivalents=169, task_starts=232)
    assert all(sum(r["metric"] == key for r in history) == count for key, count in expected_history_counts.items())
    # Validation-only dependency; calculated rows never consume the old result.
    reference_path = ROOT / "output/team_100_2030.csv"
    reference = {r["scenario"]: r for r in read_csv(reference_path)}
    mapping = {
        "input_tokens_per_team_day": "input_tokens_per_team_day",
        "cached_input_tokens_per_team_day": "cached_input_tokens_per_team_day",
        "uncached_input_tokens_per_team_day": "prefill_tokens_per_team_day",
        "output_tokens_per_team_day": "output_decode_tokens_per_team_day",
        "agent_hours_per_team_day": "agent_hours_per_team_day",
        "mean_online_agent_equivalents": "mean_online_session_equivalents_team",
        "task_starts_per_team_day": "task_starts_per_team_day",
        "eflop_per_team_day": "eflop_per_team_day",
        "prefix_cache_hit_rate": "prefix_cache_hit_rate",
    }
    endpoint_checks = []
    for r in rows:
        if r["year"] != 2030:
            continue
        output_scale = r["output_tokens_per_team_day"] / float(reference[r["scenario"]]["output_decode_tokens_per_team_day"])
        for field, source in mapping.items():
            old_value = float(reference[r["scenario"]][source])
            unchanged = field in ("agent_hours_per_team_day", "mean_online_agent_equivalents",
                                  "task_starts_per_team_day", "prefix_cache_hit_rate")
            expected = old_value if unchanged else old_value * output_scale
            assert isclose(r[field], expected, rel_tol=1e-11), (r["scenario"], field)
            endpoint_checks.append(dict(scenario=r["scenario"], metric=field, recomputed=r[field],
                                        reference=expected, old_28d_reference=old_value,
                                        output_window_scale=1 if unchanged else output_scale,
                                        relative_error=abs(r[field]-expected)/abs(expected)))
    return dict(
        status="passed", row_count=len(rows), years=list(YEARS), scenarios=list(SCENARIOS),
        source_observations=dict(output_per_category=208, task_starts_per_category=232, agent_workdays=169),
        complete_proxy_tasks=252, top_output_decile_tasks=26, endpoint_check_count=len(endpoint_checks),
        endpoint_checks=endpoint_checks,
        checks=["原始历史独立复算15行；输出直接使用官方14日统计口径。",
                "2030旧28日表按输出14/28比率换算后核对资源值；任务、时长和缓存率与旧表一致。",
                "2026输出直接使用最新14日观测，不以11月18日拟合值冒充实测。",
                "2026资源标记proxy_estimate，ABC均匀252题且tail_share=0。",
                "18类占比合计为1，分类输出合计与各年总量一致。",
                "A/B资源相同；A/B/C共用输出、任务与累计时长。",
                "输入、缓存、未缓存及Prefill/Decode恒等式通过。", "H/24平均活动当量及24小时PFLOP/s换算通过。"],
        future_rows_window_migration=dict(row_count=12, core_fields=list(CORE_FIELDS),
                                   output_rolling_window_days=14,
                                   canonical_json_sha256=future_hash, retired_28d_v1_sha256=V1_FUTURE_SHA256,
                                   canonicalization="json.dumps(rows, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()"),
        observed_dates=baseline["observed_dates"], history_counts=expected_history_counts,
        category_mix_rows=len(category_mix), official_csv_manifest_checks=source_checks,
        source_files=[dict(role=k, path=str(p.relative_to(ROOT)), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for k, p in INPUTS.items()],
        endpoint_reference=dict(path=str(reference_path.relative_to(ROOT)), usage="assertions_only_after_14d_output_rescaling", sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest()),
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
    )


def write_csv(name, rows):
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (HERE / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False, separators=(",", ":")) if isinstance(v, (dict, list)) else v for k, v in r.items()} for r in rows)


def main():
    rows, model, baseline, history, category_mix, source_checks, monthly, monthly_metadata, extensions = calculate_rows()
    validation = validate(rows, baseline, history, category_mix, source_checks)
    validation["monthly"] = validate_monthly(monthly, monthly_metadata, rows, history)
    validation["monthly_extensions"] = validate_monthly_extensions(extensions, monthly, rows, history)
    previous_path = HERE / "dashboard_data.json"
    preserved = dict(rows=rows, model=model, baseline=baseline, history=history, category_mix=category_mix,
                     monthly_trends=monthly, monthly_metadata=monthly_metadata)
    if previous_path.exists():
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        assert previous["model"] == model, "The output-window change must preserve model assumptions"
        assert previous["history"] == history, "The output-window change must preserve original observation history"
        assert previous["monthly_trends"]["agents"] == monthly["agents"], "Agent observations/forecasts changed"
        assert previous["monthly_tasks"] == extensions["monthly_tasks"], "Task observations/forecasts changed"
        unchanged_fields = ("agent_hours_per_team_day", "mean_online_agent_equivalents",
                            "task_starts_per_team_day", "prefix_cache_hit_rate", "tail_share")
        old_rows = {(r["year"], r["scenario"]): r for r in previous["rows"]}
        for row in rows:
            old = old_rows[row["year"], row["scenario"]]
            assert all(old[k] == row[k] for k in unchanged_fields), "Non-output assumptions changed"
        if previous["baseline"].get("output_rolling_window_days") == 14:
            assert all(previous[k] == value for k, value in preserved.items()), "Rebuilding 14-day data changed an existing section"
    validation["calculated_section_sha256"] = {
        key: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        for key, value in preserved.items()
    }
    HERE.mkdir(parents=True, exist_ok=True)
    write_csv("dashboard_data.csv", rows)
    write_csv("baseline_2026.csv", [dict(metric=k, **v) for k, v in baseline["metrics"].items() if "value_per_team_day" in v])
    write_csv("official_history.csv", history)
    write_csv("category_mix.csv", category_mix)
    write_csv("monthly_tokens.csv", monthly["tokens"])
    write_csv("monthly_agents.csv", monthly["agents"])
    write_csv("monthly_resources.csv", extensions["monthly_resources"])
    write_csv("monthly_tasks.csv", extensions["monthly_tasks"])
    for name, content in (
        ("dashboard_data.json", dict(rows=rows, model=model, sources=SOURCES, notes=NOTES,
                                     baseline=baseline, baseline_metadata=baseline["metrics"],
                                     history=history, category_mix=category_mix,
                                     monthly_trends=monthly, monthly_metadata=monthly_metadata, **extensions)),
        ("data_validation.json", validation),
    ):
        (HERE / name).write_text(json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(dict(status="passed", rows=len(rows), endpoint_checks=validation["endpoint_check_count"],
                          monthly_rows={key: len(value) for key, value in monthly.items()},
                          monthly_resource_rows=len(extensions["monthly_resources"]),
                          monthly_task_rows=len(extensions["monthly_tasks"]), model=model), ensure_ascii=False))


if __name__ == "__main__":
    main()
