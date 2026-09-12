"""Optional ~/.ardoise/config.json (soft caps, anomaly knobs, roster aliases).

Never stores prompts or credentials. Unknown keys are ignored.
A missing or invalid file is a no-op: status still prints, estimate still prices.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ardoise import paths

# Heuristic defaults when the file omits `anomalies`.
DEFAULT_ANOMALIES: dict[str, float | int] = {
    "day_multiple": 3.0,
    "trailing_days": 14,
    "min_days": 3,
    "min_day_usd": 1.0,
    "project_share": 0.75,
    "min_month_usd": 1.0,
}


def empty() -> dict[str, Any]:
    return {
        "budgets": {"monthly_usd": None, "person": {}, "project": {}},
        "anomalies": dict(DEFAULT_ANOMALIES),
        "roster": {},
        "path": None,
        "loaded": False,
        "load_error": None,
    }


def _as_float(value: Any) -> float | None:
    if value is None or value is False:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _usd_map(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        usd = _as_float(value)
        if usd is None:
            continue
        name = "" if key in (None, "*", "default") else str(key).strip()
        out[name] = usd
    return out


def _roster(raw: Any) -> dict[str, list[str]]:
    """Optional known seats. List of names, or `{canonical: [aliases]}`."""
    out: dict[str, list[str]] = {}
    if raw is None or raw is False:
        return out
    if isinstance(raw, list):
        items = [(item, []) for item in raw]
    elif isinstance(raw, dict):
        items = list(raw.items())
    else:
        return out
    for key, aliases in items:
        name = "" if key in (None, "*", "default") else str(key).strip()
        extra: list[str] = []
        if isinstance(aliases, str):
            alias_list = [aliases]
        elif isinstance(aliases, list):
            alias_list = aliases
        else:
            alias_list = []
        seen = {name.casefold()}
        for alias in alias_list:
            text = str(alias or "").strip()
            if not text or text.casefold() in seen:
                continue
            seen.add(text.casefold())
            extra.append(text)
        out[name] = extra
    return out


def _anomalies(raw: Any) -> dict[str, float | int]:
    merged: dict[str, float | int] = dict(DEFAULT_ANOMALIES)
    if not isinstance(raw, dict):
        return merged
    for key, default in DEFAULT_ANOMALIES.items():
        if key not in raw:
            continue
        try:
            number = float(raw[key])
        except (TypeError, ValueError):
            continue
        if number <= 0:
            continue
        merged[key] = int(number) if isinstance(default, int) else number
    return merged


def _parse(raw: dict[str, Any], path: Path) -> dict[str, Any]:
    budgets_raw = raw.get("budgets")
    if not isinstance(budgets_raw, dict):
        budgets_raw = {}
    cfg = empty()
    cfg["path"] = str(path)
    cfg["loaded"] = True
    cfg["budgets"] = {
        "monthly_usd": _as_float(budgets_raw.get("monthly_usd")),
        "person": _usd_map(budgets_raw.get("person")),
        "project": _usd_map(budgets_raw.get("project")),
    }
    cfg["anomalies"] = _anomalies(raw.get("anomalies"))
    cfg["roster"] = _roster(raw.get("roster"))
    return cfg


def load(path: Path | None = None) -> dict[str, Any]:
    """Read config.json. Invalid JSON never raises — status/estimate stay usable."""
    dest = path or paths.config_path()
    if not dest.is_file():
        cfg = empty()
        cfg["path"] = str(dest)
        return cfg
    try:
        with dest.open(encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeError):
        cfg = empty()
        cfg["path"] = str(dest)
        cfg["load_error"] = "config.json ignored (invalid JSON); using defaults"
        return cfg
    if not isinstance(raw, dict):
        cfg = empty()
        cfg["path"] = str(dest)
        cfg["load_error"] = "config.json ignored (not an object); using defaults"
        return cfg
    return _parse(raw, dest)


def has_soft_caps(cfg: dict[str, Any] | None) -> bool:
    budgets = (cfg or {}).get("budgets") or {}
    if budgets.get("monthly_usd"):
        return True
    return bool(budgets.get("person") or budgets.get("project"))
