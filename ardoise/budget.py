"""Soft budget caps stored at ~/.ardoise/budgets.json.

Caps warn and flag. They never block capture, backfill, status, or statement.
Identity is (period, metric). Re-running `budget set` upserts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ardoise import paths

PERIODS = ("day", "month")
METRICS = ("usd", "tokens")
PERIOD_ALIASES = {
    "day": "day",
    "daily": "day",
    "month": "month",
    "monthly": "month",
}
WARN_RATIO = 0.80


def _path() -> Path:
    return paths.budgets_path()


def _normalize_period(raw: Any) -> str:
    key = str(raw or "").strip().lower()
    period = PERIOD_ALIASES.get(key)
    if period is None:
        raise ValueError("budget period must be day or month")
    return period


def _normalize_metric(raw: Any) -> str:
    metric = str(raw or "").strip().lower()
    if metric not in METRICS:
        raise ValueError("budget metric must be usd or tokens")
    return metric


def _normalize_limit(raw: Any, *, metric: str) -> float:
    try:
        limit = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("budget limit must be a number") from exc
    if limit <= 0:
        raise ValueError("budget limit must be > 0")
    if metric == "tokens":
        if abs(limit - round(limit)) > 1e-9:
            raise ValueError("token budget must be a whole number")
        return float(int(round(limit)))
    return round(limit, 6)


def budget_id(period: str, metric: str) -> str:
    return f"{period}:{metric}"


def normalize(row: dict[str, Any]) -> dict[str, Any]:
    period = _normalize_period(row.get("period"))
    metric = _normalize_metric(row.get("metric"))
    limit = _normalize_limit(row.get("limit"), metric=metric)
    return {
        "id": budget_id(period, metric),
        "period": period,
        "metric": metric,
        "limit": limit,
    }


def load(path: Path | None = None) -> list[dict[str, Any]]:
    dest = path or _path()
    if not dest.is_file():
        return []
    try:
        raw = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(raw, dict):
        items = raw.get("budgets")
        if items is None and {"period", "metric", "limit"} <= set(raw):
            items = [raw]
    elif isinstance(raw, list):
        items = raw
    else:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not isinstance(items, list):
        return []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            row = normalize(item)
        except ValueError:
            continue
        if row["id"] in seen:
            out = [old for old in out if old["id"] != row["id"]]
        seen.add(row["id"])
        out.append(row)
    out.sort(key=lambda row: (PERIODS.index(row["period"]), METRICS.index(row["metric"])))
    return out


def save(rows: list[dict[str, Any]], path: Path | None = None) -> list[dict[str, Any]]:
    dest = path or _path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    normalized = [normalize(row) for row in rows]
    by_id: dict[str, dict[str, Any]] = {}
    for row in normalized:
        by_id[row["id"]] = row
    ordered = sorted(
        by_id.values(),
        key=lambda row: (PERIODS.index(row["period"]), METRICS.index(row["metric"])),
    )
    payload = {"version": 1, "budgets": ordered}
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    tmp.replace(dest)
    return ordered


def upsert(
    *,
    period: str,
    metric: str,
    limit: float,
    path: Path | None = None,
) -> dict[str, Any]:
    row = normalize({"period": period, "metric": metric, "limit": limit})
    existing = load(path)
    kind = "updated" if any(item["id"] == row["id"] for item in existing) else "inserted"
    merged = [item for item in existing if item["id"] != row["id"]]
    merged.append(row)
    save(merged, path)
    return {"result": kind, **row}


def evaluate(
    budgets: list[dict[str, Any]],
    *,
    used_usd_month: float,
    used_usd_day: float,
    used_tokens_month: int,
    used_tokens_day: int,
    usd_basis: str,
) -> list[dict[str, Any]]:
    """Headroom for each configured cap. Soft — never raises on overage."""
    out: list[dict[str, Any]] = []
    for raw in budgets:
        try:
            row = normalize(raw)
        except ValueError:
            continue
        if row["metric"] == "usd":
            used = used_usd_month if row["period"] == "month" else used_usd_day
            basis = usd_basis if row["period"] == "month" else "estimated"
        else:
            used = float(
                used_tokens_month if row["period"] == "month" else used_tokens_day
            )
            basis = "tokens"
        limit = float(row["limit"])
        ratio = (used / limit) if limit else 0.0
        if used + 1e-12 >= limit:
            state = "over"
        elif ratio >= WARN_RATIO:
            state = "warn"
        else:
            state = "ok"
        out.append(
            {
                "id": row["id"],
                "period": row["period"],
                "metric": row["metric"],
                "limit": limit,
                "used": round(float(used), 6),
                "remaining": round(limit - float(used), 6),
                "ratio": round(ratio, 6),
                "state": state,
                "basis": basis,
            }
        )
    return out
