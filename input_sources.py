"""Build the per-run input ledger from the same configuration used for forecasting."""

import json


def _cell(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return value


def _row(config, group, key, entry, dimension, default, overrides, pointer):
    original = entry["evidence"]
    evidence = {k: v for k, v in original.items() if k not in ("by_level", "by_year")}
    if group == "scenarios":
        evidence.update(original.get("by_level", {}).get(dimension, {}))
    elif group == "settings" and key == "years":
        evidence.update(original.get("by_year", {}).get(dimension, {}))

    override_key = dimension if key == "years" and group == "settings" else key
    overridden = override_key in overrides
    supplied_in_config = default is not None
    effective_value = overrides[override_key] if overridden else default
    configured_refs = evidence.get("references", []) if supplied_in_config else []
    effective_refs = [] if overridden else configured_refs
    return {
        "group": group,
        "key": key,
        "level_or_year": dimension,
        "label": entry["label"],
        "unit": entry["unit"],
        "config_value": _cell(default),
        "effective_value": _cell(effective_value),
        "value_origin": "override" if overridden else "config",
        "config_pointer": pointer if supplied_in_config else "",
        "config_as_of": config["as_of"],
        "effective_kind": "C" if overridden else evidence["kind"],
        "evidence_as_of": "" if overridden else evidence["as_of"],
        "scope": "本次运行临时覆盖值" if overridden else evidence["scope"],
        "rationale": "取自本次运行的覆盖文件，未附独立依据。" if overridden else evidence["rationale"],
        "calibration": evidence["calibration"],
        "source_urls": "\n".join(ref["url"] for ref in effective_refs),
        "references_with_roles": _cell(effective_refs),
        "config_kind": evidence["kind"] if supplied_in_config else "",
        "config_references_with_roles": _cell(configured_refs),
    }


def source_rows(config, overrides=None):
    """Describe configured inputs and any explicitly supplied run-time overrides.

    The caller supplies the original (unmodified) configuration and the same
    overrides passed to the model. JSON reference lists keep each URL paired
    with its title and evidence role. A newly added year has no configured value.
    """
    overrides = overrides or {}
    rows = []
    for key, entry in config["scenarios"].items():
        for level, value in entry["values"].items():
            rows.append(_row(config, "scenarios", key, entry, level, value,
                             overrides.get(level, {}), f"/scenarios/{key}/values/{level}"))

    for key, entry in config["fixed"].items():
        rows.append(_row(config, "fixed", key, entry, "", entry["value"],
                         overrides.get("fixed", {}), f"/fixed/{key}/value"))

    for key, entry in config["settings"].items():
        if key == "years":
            years = {str(year): value for year, value in entry["value"].items()}
            updates = {str(year): value for year, value in overrides.get("years", {}).items()}
            for year in sorted(years.keys() | updates.keys(), key=int):
                rows.append(_row(config, "settings", key, entry, year, years.get(year),
                                 updates, f"/settings/years/value/{year}"))
        else:
            rows.append(_row(config, "settings", key, entry, "", entry["value"],
                             {}, f"/settings/{key}/value"))
    return rows
