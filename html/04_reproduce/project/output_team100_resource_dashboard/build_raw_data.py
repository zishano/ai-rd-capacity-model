"""Package the saved original four-chart forecasts without fitting any model.

Run: python3 -B output_team100_resource_dashboard/build_raw_data.py
Only raw_research_data.json is written; all CSVs and source scripts are read-only.
"""
import ast
import csv
from datetime import date
import hashlib
import json
from math import fsum, isclose, isfinite
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WORKLOAD = ROOT / "analysis/agentic_30t_forecast/workload"
RESULTS = WORKLOAD / "trend_models/results"
STYLE = WORKLOAD / "monthly_research_usage.py"
ORIGINAL_STYLE = WORKLOAD / "trend_models/original_style.py"
DESTINATION = HERE / "raw_research_data.json"
METHOD_IDS = ("legacy_ols", "damped_holt", "damped_holt_hl365", "logistic_cap4x", "gompertz_cap4x")
ENSEMBLE = "ensemble_uncertainty"
CONCURRENCY_METHODS = [
    {"id": "legacy_log_complement", "name": "原双门槛模型", "note": "分别外推至少4个与至少16个Agent的占比，保留末期组内分布；这是原四图的默认并发模型。"},
    {"id": "naive", "name": "保持末值", "note": "未来九档占比保持最后观测值；用作朴素参照。"},
    {"id": "conditional_logistic", "name": "条件 Logistic（嵌套门槛）", "note": "拟合至少4个Agent的占比及其中至少16个的条件占比，保证门槛嵌套。"},
    {"id": "joint_logratio", "name": "九档对数比模型", "note": "共同外推九档对数份额并归一化，允许组内构成变化。"},
    {"id": ENSEMBLE, "name": "原双门槛 + 28日Bootstrap", "note": "中心保留原双门槛结果；成对28日分块Bootstrap只估计两条门槛趋势拟合的不确定性。80%/95%为名义区间，未经四年覆盖率校准。"},
]
HISTORY_COVERAGE = {
    "workdays": (169, "2026-05-03", "2026-10-18"),
    "concurrency": (161, "2026-05-04", "2026-10-18"),
    "tasks": (232, "2026-03-01", "2026-10-18"),
    "output": (208, "2026-01-20", "2026-08-15"),
}
FORECAST_COVERAGE = {
    "workdays": (49, "2026-11-18", "2030-11-18"),
    "concurrency": (49, "2026-11-18", "2030-11-18"),
    "tasks": (49, "2026-11-18", "2030-11-18"),
    "output": (52, "2026-08-18", "2030-11-18"),
}


class Sources:
    """Read once and retain source fingerprints for the exported evidence record."""

    def __init__(self):
        self.contents = {}

    def read(self, path):
        if path not in self.contents:
            self.contents[path] = path.read_bytes()
        return self.contents[path]

    def rows(self, path):
        return list(csv.DictReader(self.read(path).decode("utf-8-sig").splitlines()))

    def literals(self, path, names):
        result = {}
        for node in ast.parse(self.read(path).decode("utf-8")).body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in names:
                        result[target.id] = ast.literal_eval(node.value)
        assert set(result) == set(names), (path, names)
        return result

    def fingerprints(self):
        return [{"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(content).hexdigest()}
                for path, content in self.contents.items()]

    def assert_unchanged(self):
        assert all(path.read_bytes() == content for path, content in self.contents.items()), "A source changed during packaging"


def matrix(rows, metric, status, series):
    keys = [item["id"] for item in series]
    entries = {}
    for row in rows:
        if row["metric"] != metric or row["status"] != status:
            continue
        key = (row["date"], row["series"])
        assert key not in entries and key[1] in keys, (metric, status, key)
        date.fromisoformat(key[0])
        value = float(row["value"])
        assert isfinite(value) and value >= 0, (metric, status, key, value)
        entries[key] = value
    dates = sorted({day for day, _ in entries})
    assert len(entries) == len(dates) * len(keys), (metric, status, "incomplete series")
    values = [[entries[day, key] for key in keys] for day in dates]
    coverage = HISTORY_COVERAGE[metric] if status == "observed" else FORECAST_COVERAGE[metric]
    assert (len(dates), dates[0], dates[-1]) == coverage, (metric, status, "coverage")
    if status == "forecast":
        assert all(day.endswith("-18") for day in dates)
        ordinal = [date.fromisoformat(day).year * 12 + date.fromisoformat(day).month for day in dates]
        assert all(right - left == 1 for left, right in zip(ordinal, ordinal[1:])), (metric, "missing forecast month")
    if metric == "concurrency":
        assert all(all(value <= 1 for value in row) and isclose(fsum(row), 1, abs_tol=1e-12) for row in values)
    return {"dates": dates, "values": values}


def metric_definitions(constants):
    task_series = [{"id": f"task{group_index}_{index}", "name": name, "color": color, "group": group}
                   for group_index, (group, items) in enumerate(constants["TASK_GROUPS"], 1)
                   for index, (name, color) in enumerate(items, 1)]
    assert len(task_series) == len(constants["TOKEN_COLORS"]) == 18
    output_series = [{**series, "color": color} for series, color in zip(task_series, constants["TOKEN_COLORS"])]
    teams = [{"id": key, "name": name, "color": color, "group": "研究团队"} for key, name, color in constants["TEAMS"]]
    bins = [{"id": label, "name": label, "color": color, "group": "平均日峰值并发档位"}
            for label, color in zip(constants["BINS"], constants["COLORS"])]
    assert len(teams) == 5 and len(bins) == 9
    specifications = {
        "workdays": {"title": "累计 Agent 工作日", "unit": "Agent工作日/研究员日", "display": "Agent工作日/研究员日", "divisor": 1, "windowDays": 28, "series": teams},
        "concurrency": {"title": "平均日峰值并发分布", "unit": "研究员占比（0–1）", "display": "%", "divisor": 0.01, "windowDays": 28, "series": bins},
        "tasks": {"title": "18类研发任务发起", "unit": "项/研究员日", "display": "项/研究员日", "divisor": 1, "windowDays": 28, "series": task_series},
        "output": {"title": "18类输出 Token", "unit": "Token/研究员日", "display": "万Token/研究员日", "divisor": 10000, "windowDays": 14, "series": output_series},
    }
    for metric, definition in specifications.items():
        definition["cutoff"] = HISTORY_COVERAGE[metric][2]
        definition["forecast"] = {}
    return specifications


def ensemble_intervals(sources, metrics, folder):
    """Use saved total quantiles and cumulative boundaries, never sum quantiles."""
    rows = [row for row in sources.rows(folder / "forecast.csv") if row["method"] == "ensemble"]
    assert len(rows) == 150
    for metric in ("workdays", "tasks", "output"):
        points = [{"date": row["date"], "center": float(row["median"]),
                   **{key: float(row[key]) for key in ("lower95", "lower80", "upper80", "upper95")}}
                  for row in rows if row["metric"] == metric]
        assert [point["date"] for point in points] == metrics[metric]["forecast"][ENSEMBLE]["dates"]
        for point in points:
            values = [point[key] for key in ("lower95", "lower80", "center", "upper80", "upper95")]
            assert all(isfinite(value) and value >= 0 for value in values) and values == sorted(values)
        metrics[metric]["uncertainty"] = {ENSEMBLE: {
            "calibrated": False, "scope": "overall" if metric == "workdays" else "total",
            "bands": [{"id": "Overall Research" if metric == "workdays" else "total",
                       "name": "总体研究员" if metric == "workdays" else "18类合计", "points": points}],
        }}
    boundary_rows = sources.rows(folder / "main_concurrency_bands.csv")
    assert len(boundary_rows) == 98
    bands = []
    center = metrics["concurrency"]["forecast"][ENSEMBLE]
    for threshold, count in ((4, 4), (16, 6)):
        points = [{"date": row["date"], "center": float(row["boundary_center"]),
                   **{key: float(row[source]) for key, source in (
                       ("lower95", "boundary_p025"), ("lower80", "boundary_p10"),
                       ("upper80", "boundary_p90"), ("upper95", "boundary_p975"))}}
                  for row in boundary_rows if row["threshold"] == str(threshold)]
        assert [point["date"] for point in points] == center["dates"]
        for point, values in zip(points, center["values"]):
            assert isclose(point["center"], fsum(values[:count]), abs_tol=1e-12)
            quantiles = [point[key] for key in ("lower95", "lower80", "upper80", "upper95")]
            assert all(isfinite(value) and 0 <= value <= 1 for value in quantiles) and quantiles == sorted(quantiles)
        bands.append({"id": f"boundary_lt{threshold}", "name": f"<{threshold}个Agent的累计占比边界",
                      "threshold": threshold, "points": points})
    metadata = json.loads(sources.read(folder / "main_concurrency_metadata.json"))
    assert metadata["center_method"] == "legacy_log_complement" and metadata["center_unchanged"]
    metrics["concurrency"]["uncertainty"] = {ENSEMBLE: {
        "calibrated": False, "scope": "cumulative_boundaries", "bands": bands, "metadata": metadata,
    }}
    return rows


def build_payload(sources):
    constants = sources.literals(STYLE, {"TEAMS", "TASK_GROUPS", "TOKEN_COLORS", "BINS", "COLORS"})
    presets = sources.literals(ORIGINAL_STYLE, {"PRESETS"})["PRESETS"]
    assert set(presets) == set(METHOD_IDS)
    metrics = metric_definitions(constants)
    methods = [{"id": method, "name": presets[method][0], "note": presets[method][1]} for method in METHOD_IDS]
    ensemble_folder = RESULTS / "original_style" / ENSEMBLE
    preset = json.loads(sources.read(ensemble_folder / "preset.json"))
    assert preset["method"] == ENSEMBLE and preset["point"] == "median"
    methods.append({"id": ENSEMBLE, "name": preset["label"], "note": preset["note"]})
    warnings = []
    default_concurrency = None
    chart_rows = 0
    for method in (*METHOD_IDS, ENSEMBLE):
        folder = RESULTS / "original_style" / method
        rows = sources.rows(folder / "chart_data.csv")
        assert len(rows) == 12718 and {row["method"] for row in rows} == {method}
        assert {row["metric"] for row in rows} == set(metrics)
        assert {row["status"] for row in rows} == {"observed", "forecast"}
        chart_rows += len(rows)
        for metric, definition in metrics.items():
            history = matrix(rows, metric, "observed", definition["series"])
            if "history" not in definition:
                definition["history"] = history
            elif method == ENSEMBLE and metric == "concurrency":
                # The upstream preset renormalizes already-normalized shares,
                # adding only roundoff (~1e-16). Keep the original bytes' values.
                assert definition["history"]["dates"] == history["dates"]
                assert all(isclose(old, new, rel_tol=0, abs_tol=1e-15)
                           for old_row, new_row in zip(definition["history"]["values"], history["values"])
                           for old, new in zip(old_row, new_row))
            else:
                assert definition["history"] == history, (method, metric, "historical values changed")
            future = matrix(rows, metric, "forecast", definition["series"])
            if metric == "concurrency":
                if default_concurrency is None:
                    default_concurrency = future
                elif method == ENSEMBLE:
                    assert default_concurrency["dates"] == future["dates"]
                    assert all(isclose(old, new, rel_tol=0, abs_tol=1e-15)
                               for old_row, new_row in zip(default_concurrency["values"], future["values"])
                               for old, new in zip(old_row, new_row))
                else:
                    assert default_concurrency == future, (method, "original concurrency differs")
            else:
                definition["forecast"][method] = future

        if method == ENSEMBLE:
            continue  # New preset stores team diagnostics in a different schema.
        parameters = sources.rows(folder / "team_parameters.csv")
        assert {row["series"] for row in parameters} == {series["id"] for series in metrics["workdays"]["series"]}
        for row in parameters:
            assert row["method"] == method
            parameter = json.loads(row["parameters"])
            count = parameter.get("negative_forecasts_before_floor", 0)
            if count:
                name = next(series["name"] for series in metrics["workdays"]["series"] if series["id"] == row["series"])
                message = f"{name}团队的{count}个预测点在非负截断前为负，原结果已截为零；不应据此推断该团队停止使用Agent。"
                warnings.append({"method": method, "metric": "workdays", "series": row["series"], "count": count, "note": message})

    concurrency_rows = sources.rows(RESULTS / "concurrency.csv")
    assert len(concurrency_rows) == 196
    assert {row["method"] for row in concurrency_rows} == {item["id"] for item in CONCURRENCY_METHODS if item["id"] != ENSEMBLE}
    bins = metrics["concurrency"]["series"]
    for method in CONCURRENCY_METHODS:
        if method["id"] == ENSEMBLE:
            metrics["concurrency"]["forecast"][ENSEMBLE] = default_concurrency
            continue
        flattened = [{"metric": "concurrency", "status": "forecast", "date": row["date"],
                      "series": series["id"], "value": row[f"bin_{index}"]}
                     for row in concurrency_rows if row["method"] == method["id"]
                     for index, series in enumerate(bins)]
        metrics["concurrency"]["forecast"][method["id"]] = matrix(flattened, "concurrency", "forecast", bins)
    assert default_concurrency == metrics["concurrency"]["forecast"]["legacy_log_complement"]

    # Compare the stack totals to the saved point forecasts, preserving the
    # native 14-day output field also used by the resource dashboard.
    total_rows = sources.rows(RESULTS / "forecast.csv")
    totals = {(row["method"], row["metric"], row["date"]): float(row["value"]) for row in total_rows}
    assert len(totals) == len(total_rows) == 2250
    interval_rows = ensemble_intervals(sources, metrics, ensemble_folder)
    totals.update({(ENSEMBLE, row["metric"], row["date"]): float(row["median"]) for row in interval_rows})
    overall = next(index for index, series in enumerate(metrics["workdays"]["series"]) if series["id"] == "Overall Research")
    compared_totals = 0
    for metric in ("workdays", "tasks", "output"):
        for method, pack in metrics[metric]["forecast"].items():
            for day, values in zip(pack["dates"], pack["values"]):
                total = values[overall] if metric == "workdays" else fsum(values)
                assert isclose(total, totals[method, metric, day], rel_tol=1e-10, abs_tol=1e-9), (method, metric, day)
                compared_totals += 1
    assert compared_totals == 900
    assert warnings and any(item["method"] == "damped_holt_hl365" and item["series"] == "Other" and item["count"] == 46 for item in warnings)
    summary = {
        "status": "passed", "source_chart_rows": chart_rows, "total_forecast_checks": compared_totals,
        "method_count": len(methods), "concurrency_method_count": len(CONCURRENCY_METHODS),
        "metrics": {metric: {"series": len(definition["series"]), "history_dates": len(definition["history"]["dates"]),
                              "forecast_dates_per_method": len(next(iter(definition["forecast"].values()))["dates"])}
                    for metric, definition in metrics.items()},
    }
    return {
        "methods": methods, "concurrencyMethods": CONCURRENCY_METHODS, "metrics": metrics,
        "meta": {
            "schemaVersion": 2, "defaultMethod": "legacy_ols", "defaultConcurrencyMethod": "legacy_log_complement",
            "endpoint": "2030-11-18", "scope": "researcher_calendar_day", "historySampling": "all_available_daily_chart_values",
            "forecastSampling": "monthly_18th", "sources": sources.fingerprints(), "boundaryWarnings": warnings,
            "links": [
                {"name": "OpenAI：研究加速的新前沿", "url": "https://openai.com/index/research-acceleration-jagged-frontier/"},
                {"name": "OpenAI：研究加速内部观察", "url": "https://openai.com/zh-Hans-CN/index/research-acceleration-view-inside-openai/"},
            ],
            "notes": [
                "直接读取已提交的原四图绘图数据；保留全部有效逐日历史和每月18日预测点，未重新拟合。",
                "工作日、任务、输出均为每研究员自然日强度；1个Agent工作日为8小时，不是GPU工作日。",
                "五条工作日曲线分别对应各团队的人均强度；总体不等于分团队曲线相加。",
                "并发为研究员平均日峰值所属档位的占比，九档加总为100%；不乘百人人数，也不能换算未知开口尾档的均值。",
            "前三图沿用官方28日统计窗口；输出沿用官方14日窗口，与资源探索页输出口径一致；已平滑的官方数据不再二次平滑。",
                "并发历史缺7个日期，原有有效日期全部保留；所有算法共享相同历史。",
                "工作日团队来自原monthly_research_usage.py内冻结的observed_workdays_by_team.csv；任务和并发来自observed_openai_research_usage.csv；输出来自calibration/observed_output_tokens.csv。",
                "任务与输出的非线性方法按历史末84日类别份额分配总量；旧OLS保留逐类拟合及输出末值锚定规则。",
                "并发算法独立于工作日、任务与输出的总量算法；原四图默认使用原双门槛模型。",
                "固定阻尼半衰期与历史最大值4倍饱和上限均为条件假设；曲线差异不是置信区间，也不代表已验证的四年预测。",
                "融合方案保留已发布预测分布的中位数与名义80%/95%区间；区间未经长期校准。工作日仅总体有区间，任务和输出为总量区间，不代表类别独立区间。",
                "融合方案的并发中心与原双门槛完全相同；阴影对应<4与<16个Agent的累计占比边界，来自成对28日分块Bootstrap，不是九档独立区间。",
            ],
            "validation": summary,
        },
    }


def main():
    sources = Sources()
    payload = build_payload(sources)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
    assert json.loads(encoded) == payload
    sources.assert_unchanged()
    DESTINATION.write_text(encoded, encoding="utf-8")
    sources.assert_unchanged()
    print(json.dumps({"file": str(DESTINATION), "bytes": len(encoded.encode("utf-8")),
                      "source_files_unchanged": True, **payload["meta"]["validation"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
