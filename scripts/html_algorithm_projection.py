"""Materialize the resource page's monthly algorithm values without refitting.

``project_monthly(dashboard, algorithms)`` is a pure function: it reads no files,
changes neither argument, and returns forecast rows for resources, agents and
tasks. It mirrors ``algorithmRows()`` and ``value()`` in
``html/02_frontend/dashboard.js`` at the page's 100-person / 24-hour defaults.

Inputs use the schemas of dashboard_data.json and algorithm_forecasts.json.
Algorithm output is Token / researcher calendar day (official 14-day target); workdays
are eight-hour Agent workdays / researcher calendar day; tasks are starts /
researcher calendar day. Returned Token, EFLOP, hours and task values are daily
team intensities, not monthly totals. Workdays and tasks retain their original
28-day target; they are not smoothed again. Cache hit rate remains a 0--1 ratio.

The browser never displays the stored ``compute_pflops_24h`` column when an
algorithm changes. It calculates ``compute_pflops_window`` from the selected
algorithm's EFLOP value. We rename the unused stored column to
``legacy_reference_compute_pflops_24h`` and export the actual displayed rate
separately, preserving JavaScript's floating-point operation order.
"""

from copy import deepcopy
from math import isclose, isfinite


DEFAULT_TEAM = 100
DEFAULT_WINDOW_HOURS = 24

# Precisely the non-ratio resource metrics registered in dashboard.js. The
# synthetic compute_pflops_window is calculated by value(), not stored in the
# source rows. In particular, compute_pflops_24h is not in this registry.
RESOURCE_SCALED_FIELDS = (
    "output_tokens_per_team_day",
    "input_tokens_per_team_day",
    "cached_input_tokens_per_team_day",
    "uncached_input_tokens_per_team_day",
    "total_tokens_per_team_day",
    "eflop_per_team_day",
    "prefill_eflop_per_team_day",
    "decode_eflop_per_team_day",
)


def _finite_number(value):
    """Match Number.isFinite for JSON numbers, excluding Python booleans."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _forecast_rows(rows, name):
    selected = [row for row in rows if row["phase"] == "forecast"]
    identities = [(row["date"], row["scenario"]) for row in selected]
    if len(set(identities)) != len(identities):
        raise ValueError(f"Duplicate forecast date/scenario in {name}")
    for row in selected:
        if row.get("researchers", DEFAULT_TEAM) != DEFAULT_TEAM:
            raise ValueError(f"{name} must use the page's 100-person source basis")
    return selected


def project_monthly(dashboard, algorithms):
    """Return ``resources``, ``agents``, ``tasks`` lists for all saved methods.

    Only forecast rows actually used by the resource page are materialized.
    Thus the saved August 2026 output forecast remains in the algorithm source
    but is not inserted into the page's September-onward resource forecasts.
    Original history and annual analysis views are unaffected. The headline
    cards use the selected single algorithm's endpoint rows from these series.

    Every result retains source date/scenario/evidence fields, plus method and
    classification. Resource rows also contain service_window_hours and the
    displayed compute_pflops_window; see the module docstring for the renamed
    legacy reference rate. All methods, including legacy OLS, consume the saved
    predictions; values equal to the original baseline retain exact source rows.
    """
    methods = [method["id"] for method in algorithms["methods"]]
    if len(set(methods)) != len(methods) or set(methods) != set(algorithms["forecasts"]):
        raise ValueError("Algorithm identifiers are duplicated or inconsistent")
    sources = {
        "resources": _forecast_rows(dashboard["monthly_resources"], "resources"),
        "agents": _forecast_rows(dashboard["monthly_trends"]["agents"], "agents"),
        "tasks": _forecast_rows(dashboard["monthly_tasks"], "tasks"),
    }
    metric_for_source = {"resources": "output", "agents": "workdays", "tasks": "tasks"}
    result = {name: [] for name in sources}
    for method in methods:
        prediction = algorithms["forecasts"][method]
        for name, source_rows in sources.items():
            for source in source_rows:
                row = deepcopy(source)
                per_person = prediction[metric_for_source[name]][source["date"]]
                if not _finite_number(per_person) or per_person < 0:
                    raise ValueError(f"Invalid {method}/{name} forecast at {source['date']}")
                team = source.get("researchers") or DEFAULT_TEAM
                base_field = {
                    "agents": "agent_hours_per_team_day",
                    "tasks": "task_starts_per_team_day",
                    "resources": "output_tokens_per_team_day",
                }[name]
                projected = per_person * (8 if name == "agents" else 1) * team
                if not isclose(projected, source[base_field], rel_tol=1e-12, abs_tol=1e-9):
                    if name == "agents":
                        row["agent_hours_per_team_day"] = per_person * 8 * team
                        row["mean_online_agent_equivalents"] = row["agent_hours_per_team_day"] / 24
                    elif name == "tasks":
                        row["task_starts_per_team_day"] = per_person * team
                    else:
                        output = per_person * team
                        source_output = source["output_tokens_per_team_day"]
                        if not _finite_number(source_output) or source_output <= 0:
                            raise ValueError("Resource projection requires a positive original output")
                        factor = output / source_output
                        for field in RESOURCE_SCALED_FIELDS:
                            if _finite_number(source.get(field)):
                                row[field] = source[field] * factor
                        row["output_tokens_per_team_day"] = output

                row["method"] = method
                row["classification"] = (
                    "conditional_resource_estimate" if name == "resources"
                    else "conditional_team_projection"
                )
                if name == "resources":
                    if "compute_pflops_24h" in row:
                        row["legacy_reference_compute_pflops_24h"] = row.pop("compute_pflops_24h")
                    row["service_window_hours"] = DEFAULT_WINDOW_HOURS
                    # Keep JS value()'s exact multiplication/division order.
                    row["compute_pflops_window"] = (
                        row["eflop_per_team_day"] * DEFAULT_TEAM
                        / (source.get("researchers") or DEFAULT_TEAM)
                        * 1000 / (DEFAULT_WINDOW_HOURS * 3600)
                    )
                _check_row(row, source, name, method)
                result[name].append(row)

    for name, rows in result.items():
        expected = len(methods) * len(sources[name])
        assert len(rows) == expected
        assert len({(row["method"], row["date"], row["scenario"]) for row in rows}) == expected
    return result


def _check_row(row, source, name, method):
    """Check semantic identities and fields that algorithm selection must retain."""
    assert row["phase"] == "forecast"
    assert row["date"] == source["date"] and row["scenario"] == source["scenario"]
    changed = set(RESOURCE_SCALED_FIELDS) if name == "resources" else (
        {"agent_hours_per_team_day", "mean_online_agent_equivalents"} if name == "agents"
        else {"task_starts_per_team_day"}
    )
    for key, value in source.items():
        if name == "resources" and key == "compute_pflops_24h":
            assert row["legacy_reference_compute_pflops_24h"] == value
        elif key not in changed:
            assert row[key] == value, (method, name, key)
    for field in changed:
        assert _finite_number(row[field]) and row[field] >= 0, (method, name, field)
    if name == "agents":
        assert row["mean_online_agent_equivalents"] == row["agent_hours_per_team_day"] / 24
    elif name == "resources":
        assert row["prefix_cache_hit_rate"] == source["prefix_cache_hit_rate"]
        assert row["tail_share"] == source["tail_share"]
        for actual, expected in (
            (row["input_tokens_per_team_day"], row["cached_input_tokens_per_team_day"] + row["uncached_input_tokens_per_team_day"]),
            (row["total_tokens_per_team_day"], row["input_tokens_per_team_day"] + row["output_tokens_per_team_day"]),
            (row["eflop_per_team_day"], row["prefill_eflop_per_team_day"] + row["decode_eflop_per_team_day"]),
        ):
            assert isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), (method, name)


__all__ = ["project_monthly"]
