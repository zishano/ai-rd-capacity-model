"""Adapt the committed monthly forecasts for the dashboard without refitting them.

Run: python3 -B output_team100_resource_dashboard/build_algorithm_data.py
Only algorithm_forecasts.json is written. The original dashboard data is read-only.
"""
import csv
from datetime import date
import hashlib
import json
from math import isclose, isfinite
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / "analysis/agentic_30t_forecast/workload/trend_models/results/forecast.csv"
# Keep the original research-chart predictions independent of resource updates.
# The update command archives the reviewed CSV here for reproducible rebuilds.
ORIGINAL_SOURCE = SOURCE
RESOURCE_SOURCE = ROOT / "resource_predictions/forecast.csv"
ENSEMBLE_SOURCE = ROOT / "analysis/agentic_30t_forecast/workload/trend_models/results/original_style/ensemble_uncertainty"
if RESOURCE_SOURCE.is_file():
    SOURCE = RESOURCE_SOURCE
DASHBOARD = HERE / "dashboard_data.json"
DESTINATION = HERE / "algorithm_forecasts.json"
METHODS = [
    {"id": "legacy_ols", "name": "原脚本 OLS（默认）", "group": "默认参照"},
    {"id": "naive", "name": "保持末值", "group": "主要统计模型"},
    {"id": "ols", "name": "统一水平 OLS", "group": "主要统计模型"},
    {"id": "piecewise", "name": "单变化点线性", "group": "主要统计模型"},
    {"id": "damped_holt", "name": "阻尼 Holt（历史拟合）", "group": "主要统计模型"},
    {"id": "auto_arima", "name": "低阶 AutoARIMA", "group": "主要统计模型"},
    {"id": "damped_holt_hl90", "name": "阻尼 Holt（半衰期 90 天）", "group": "阻尼条件情景"},
    {"id": "damped_holt_hl365", "name": "阻尼 Holt（半衰期 365 天）", "group": "阻尼条件情景"},
    {"id": "damped_holt_hl730", "name": "阻尼 Holt（半衰期 730 天）", "group": "阻尼条件情景"},
    {"id": "logistic_cap2x", "name": "Logistic（历史最大值 2 倍上限）", "group": "饱和条件情景"},
    {"id": "logistic_cap4x", "name": "Logistic（历史最大值 4 倍上限）", "group": "饱和条件情景"},
    {"id": "logistic_cap8x", "name": "Logistic（历史最大值 8 倍上限）", "group": "饱和条件情景"},
    {"id": "gompertz_cap2x", "name": "Gompertz（历史最大值 2 倍上限）", "group": "饱和条件情景"},
    {"id": "gompertz_cap4x", "name": "Gompertz（历史最大值 4 倍上限）", "group": "饱和条件情景"},
    {"id": "gompertz_cap8x", "name": "Gompertz（历史最大值 8 倍上限）", "group": "饱和条件情景"},
    {"id": "ensemble_uncertainty", "name": "多模型融合与不确定性外推", "group": "融合与不确定性"},
]
METRICS = ("output", "workdays", "tasks")
WINDOW_DAYS = {"output": 14, "workdays": 28, "tasks": 28}
CSV_FIELDS = ("metric", "date", "method", "value", "output_tokens_28d", "lower95", "upper95", "interval_basis")


def expected_dates(metric):
    start = date(2026, 8 if metric == "output" else 11, 18)
    endpoint = date(2030, 11, 18)
    return {
        str(date(year, month, 18))
        for year in range(2026, 2031)
        for month in range(1, 13)
        if start <= date(year, month, 18) <= endpoint
    }


def validate_payload(payload, dashboard):
    """Check forecast coverage and compare monthly OLS with the frozen baseline.

    Dedicated resource updates may replace OLS monthly values. Annual analysis
    views still use the unchanged dashboard baseline; these
    comparisons record that boundary instead of rejecting a valid new forecast.
    """
    assert payload["methods"] == METHODS, "Unexpected algorithm names or ordering"
    forecasts = payload["forecasts"]
    assert set(forecasts) == {method["id"] for method in METHODS}
    for method, metric_rows in forecasts.items():
        assert set(metric_rows) == set(METRICS), method
        for metric, values in metric_rows.items():
            assert set(values) == expected_dates(metric), (method, metric, "date coverage")
            assert all(isfinite(value) and value >= 0 for value in values.values()), (method, metric)

    legacy = forecasts["legacy_ols"]
    updated_source = payload.get("meta", {}).get("input_mode") == "resource_prediction_update"
    checked = {}
    series = (
        ("output", dashboard["monthly_resources"], "output_tokens_per_team_day", 1),
        ("workdays", dashboard["monthly_trends"]["agents"], "agent_hours_per_team_day", 8),
        ("tasks", dashboard["monthly_tasks"], "task_starts_per_team_day", 1),
    )
    for metric, rows, field, conversion in series:
        matched = checked_rows = 0
        maximum_relative_error = 0.0
        for row in rows:
            if row["phase"] != "forecast":
                continue
            day = row["date"]
            assert day in legacy[metric], (metric, day, "missing UI forecast date")
            expected = legacy[metric][day] * conversion * row["researchers"]
            actual = row[field]
            agrees = isclose(expected, actual, rel_tol=1e-12, abs_tol=1e-9)
            if not updated_source:
                assert agrees, (metric, day, row["scenario"])
            maximum_relative_error = max(maximum_relative_error, abs(expected - actual) / max(abs(actual), 1))
            checked_rows += 1
            matched += agrees
        assert checked_rows == len({row["date"] for row in rows if row["phase"] == "forecast"}) * 3
        assert checked_rows > 0
        checked[metric] = {"checked_monthly_rows": checked_rows, "matched_monthly_rows": matched,
                           "changed_monthly_rows": checked_rows - matched, "max_relative_error": maximum_relative_error}

    # Annual values remain another independent boundary of the existing page.
    annual_checks = annual_matches = 0
    for row in dashboard["rows"]:
        if row["row_type"] != "forecast":
            continue
        for metric, field, conversion in (
            ("output", "output_tokens_per_team_day", 1),
            ("workdays", "agent_hours_per_team_day", 8),
            ("tasks", "task_starts_per_team_day", 1),
        ):
            expected = legacy[metric][row["date"]] * conversion * row["researchers"]
            agrees = isclose(expected, row[field], rel_tol=1e-12, abs_tol=1e-9)
            if not updated_source:
                assert agrees, (metric, row["date"])
            annual_checks += 1
            annual_matches += agrees
    assert annual_checks == 36
    return {
        "status": "passed", "method_count": len(METHODS),
        "forecast_points": sum(len(values) for metrics in forecasts.values() for values in metrics.values()),
        "points_per_method": {metric: len(expected_dates(metric)) for metric in METRICS},
        "legacy_matches": checked, "checked_annual_values": annual_checks,
        "matched_annual_values": annual_matches, "changed_annual_comparisons": annual_checks - annual_matches,
        "annual_dashboard_preserved": True,
    }


def parse_forecast_csv(source_bytes):
    """Validate the complete saved-prediction input before building any output.

    Output ``value`` is the original 14-day statistic consumed by both pages.
    ``output_tokens_28d`` remains a validated legacy reference only. Other
    metrics use ``value`` with their native 28-day windows and leave the output
    column empty. Ensemble bands use the saved native-window quantiles.
    """
    reader = csv.DictReader(source_bytes.decode("utf-8-sig").splitlines(), strict=True)
    if reader.fieldnames is None or len(reader.fieldnames) != len(CSV_FIELDS) or set(reader.fieldnames) != set(CSV_FIELDS):
        raise ValueError("Forecast CSV must have exactly these columns: " + ",".join(CSV_FIELDS))
    rows = list(reader)
    forecasts = {method["id"]: {metric: {} for metric in METRICS} for method in METHODS}

    def number(row, field, line, nonnegative=True):
        try:
            value = float(row[field])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Forecast CSV row {line}: {field} must be a number") from exc
        if not isfinite(value) or (nonnegative and value < 0):
            raise ValueError(f"Forecast CSV row {line}: {field} must be finite" + (" and nonnegative" if nonnegative else ""))
        return value

    for line, row in enumerate(rows, 2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Forecast CSV row {line}: incorrect column count")
        method, metric, day = row["method"], row["metric"], row["date"]
        if method not in forecasts or metric not in METRICS:
            raise ValueError(f"Forecast CSV row {line}: unknown method/metric {method}/{metric}")
        if day not in expected_dates(metric):
            raise ValueError(f"Forecast CSV row {line}: unsupported {metric} date {day}")
        if day in forecasts[method][metric]:
            raise ValueError(f"Forecast CSV row {line}: duplicate {method}/{metric}/{day}")
        value = number(row, "value", line)
        if metric == "output":
            number(row, "output_tokens_28d", line)
        elif row["output_tokens_28d"].strip():
            raise ValueError(f"Forecast CSV row {line}: output_tokens_28d must be empty for {metric}")
        if bool(row["lower95"].strip()) != bool(row["upper95"].strip()):
            raise ValueError(f"Forecast CSV row {line}: interval bounds must be both present or both empty")
        if row["lower95"].strip():
            lower = number(row, "lower95", line, nonnegative=False)
            upper = number(row, "upper95", line, nonnegative=False)
            if lower > upper:
                raise ValueError(f"Forecast CSV row {line}: lower95 exceeds upper95")
        forecasts[method][metric][day] = value
    for method, metrics in forecasts.items():
        for metric, values in metrics.items():
            missing = expected_dates(metric) - set(values)
            if missing:
                raise ValueError(f"Forecast CSV missing {method}/{metric} dates: {', '.join(sorted(missing))}")
    return forecasts, len(rows)


def load_uncertainty(forecasts):
    """Use archived quantiles only when their median still matches the input.

    Users may replace point forecasts independently. A replacement must not be
    displayed inside an unrelated old simulation band; omit that point's bands
    and record the reason instead of silently recentering or interpolating them.
    """
    method = "ensemble_uncertainty"
    bounds = {metric: {} for metric in METRICS}
    omitted, hashes = [], {}
    provenance = json.loads((ENSEMBLE_SOURCE / "import_provenance.json").read_bytes())
    archived = {item["source"]: item for item in provenance["files"]}
    quantiles = ("lower95", "lower80", "median", "upper80", "upper95")
    for filename in ("forecast.csv",):
        path = ENSEMBLE_SOURCE / filename
        content = path.read_bytes()
        relative = path.relative_to(ROOT).as_posix()
        hashes[relative] = hashlib.sha256(content).hexdigest()
        if hashes[relative] != archived[relative]["sha256"]:
            raise ValueError("Ensemble archive differs from imported provenance: " + relative)
        seen = {metric: set() for metric in METRICS}
        for row in csv.DictReader(content.decode("utf-8-sig").splitlines(), strict=True):
            if row["method"] != "ensemble":
                continue
            metric = row["metric"]
            day = row["date"]
            if metric not in METRICS or day not in expected_dates(metric) or day in seen[metric]:
                raise ValueError("Invalid ensemble quantile record: " + metric + "/" + day)
            seen[metric].add(day)
            values = {key: float(row[key]) for key in quantiles}
            ordered = list(values.values())
            if not all(isfinite(value) and value >= 0 for value in ordered) or ordered != sorted(ordered):
                raise ValueError("Invalid ensemble quantile order: " + metric + "/" + day)
            if int(row["window_days"]) != WINDOW_DAYS[metric]:
                raise ValueError("Resource ensemble uncertainty must use its native metric window: " + metric)
            center = forecasts[method][metric][day]
            if center != values["median"]:
                omitted.append({"metric": metric, "date": day,
                                "reason": "point_forecast_differs_from_archived_median",
                                "point_forecast": center, "archived_median": values["median"]})
            else:
                bounds[metric][day] = values
        for metric in METRICS:
            if seen[metric] != expected_dates(metric):
                raise ValueError("Incomplete ensemble uncertainty: " + metric)
    meta = {"source_method": "ensemble", "source_commit": provenance["source_commit"],
            "source_sha256": hashes, "rolling_window_days": WINDOW_DAYS,
            "rolling_window_days_by_metric": WINDOW_DAYS,
            "interval_basis": "nominal conditional model quantiles; not calibrated four-year coverage",
            "point_estimate": "median", "quantiles": {"lower95": 0.025, "lower80": 0.1, "median": 0.5, "upper80": 0.9, "upper95": 0.975},
            "matched_points": sum(len(rows) for rows in bounds.values()), "omitted_points": omitted,
            "mismatch_policy": "omit old bands at edited point forecasts; do not recenter or interpolate missing intervals"}
    return {method: bounds}, {method: meta}


def build_payload(source_bytes, dashboard_bytes):
    forecasts, source_row_count = parse_forecast_csv(source_bytes)
    uncertainty, uncertainty_meta = load_uncertainty(forecasts)
    payload = {
        "methods": METHODS,
        "forecasts": forecasts,
        "uncertainty": uncertainty,
        "meta": {
            "source": str(SOURCE.relative_to(ROOT)),
            "input_mode": "resource_prediction_update" if SOURCE == RESOURCE_SOURCE else "original_archive",
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "dashboard_sha256": hashlib.sha256(dashboard_bytes).hexdigest(),
            "scope": "researcher_calendar_day", "rolling_window_days": WINDOW_DAYS,
            "rolling_window_days_by_metric": WINDOW_DAYS,
            "default_method": "legacy_ols", "endpoint": "2030-11-18",
            "units": {"output": "Token/研究员自然日", "workdays": "8小时工作日/研究员自然日", "tasks": "项/研究员自然日"},
            "uncertainty": uncertainty_meta,
            "uncertainty_omitted_points": [{"method": "ensemble_uncertainty", **row}
                                           for row in uncertainty_meta["ensemble_uncertainty"]["omitted_points"]],
            "notes": [
                "使用归档CSV中的月度点预测，未重新拟合；历史观测仍取原网页数据，不因算法选择改变。",
                "输出直接使用官方14日平滑口径的 value；不对已平滑的公开历史或预测再平滑。output_tokens_28d仅为旧对齐口径参考，不参与页面数值计算。",
                "任务数与Agent时长保留官方28日口径；没有逐日原始记录，不能反推出同等可靠的14日统计。",
                "Agent小时=workdays×8，平均活动当量=Agent小时÷24；各总量再按团队人数缩放。",
                "输入、缓存与计算量沿用原网页各月各情景的资源/输出比率；C保留逐月增加的混合权重。",
                "全部算法（含默认OLS）可更新月度预测；顶部卡片使用所选单一算法的2030-11-18终点值，年度分析和活动构成保留原OLS基线。",
                "固定半衰期与饱和上限均为条件假设；算法差异不是置信区间，不表示已识别长期最优模型。",
                "融合方案使用等权混合预测分布中位数；80%/95%为名义条件分位带，未经四年覆盖校准。输出中位数和分位带均直接使用原生14日模拟分布，任务/时长保留28日。",
                "手工更新融合点预测后，仅保留中心仍与归档中位数一致的日期分位带；不匹配记录列在meta.uncertainty中。",
            ],
        },
    }
    validation = validate_payload(payload, json.loads(dashboard_bytes))
    assert source_row_count == validation["forecast_points"] == len(METHODS) * sum(len(expected_dates(metric)) for metric in METRICS)
    validation["uncertainty_points"] = uncertainty_meta["ensemble_uncertainty"]["matched_points"]
    validation["omitted_uncertainty_points"] = len(uncertainty_meta["ensemble_uncertainty"]["omitted_points"])
    payload["meta"]["validation"] = validation
    return payload


def main():
    source_bytes = SOURCE.read_bytes()
    dashboard_bytes = DASHBOARD.read_bytes()
    payload = build_payload(source_bytes, dashboard_bytes)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
    assert json.loads(encoded) == payload
    assert SOURCE.read_bytes() == source_bytes and DASHBOARD.read_bytes() == dashboard_bytes
    DESTINATION.write_text(encoded, encoding="utf-8")
    assert SOURCE.read_bytes() == source_bytes and DASHBOARD.read_bytes() == dashboard_bytes
    print(json.dumps({"file": str(DESTINATION), "bytes": len(encoded.encode("utf-8")),
                      "source_and_dashboard_unchanged": True, **payload["meta"]["validation"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
