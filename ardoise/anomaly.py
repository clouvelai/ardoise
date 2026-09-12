"""Soft anomaly notes — local heuristics, not an alerts pipeline.

Two v1 checks:
- a day's T0 spend is > N× the trailing median of recent spending days
- one project takes more than `project_share` of the month (when 2+ projects)
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any

from ardoise import config as config_mod


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _month_start(month: str) -> date:
    year, mon = month.split("-", 1)
    return date(int(year), int(mon), 1)


def _next_month(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _daily_spend(conn: sqlite3.Connection, start: date, end: date) -> dict[str, float]:
    rows = conn.execute(
        """
        SELECT substr(occurred_at, 1, 10) AS day, COALESCE(SUM(cost_usd), 0)
        FROM events
        WHERE occurred_at >= ? AND occurred_at < ?
        GROUP BY 1
        """,
        (f"{start.isoformat()}T00:00:00Z", f"{end.isoformat()}T00:00:00Z"),
    )
    return {str(row[0]): float(row[1] or 0) for row in rows}


def _day_flags(
    conn: sqlite3.Connection,
    month: str,
    knobs: dict[str, float | int],
) -> list[dict[str, Any]]:
    trailing = int(knobs.get("trailing_days") or 14)
    multiple = float(knobs.get("day_multiple") or 3.0)
    min_days = int(knobs.get("min_days") or 3)
    min_day_usd = float(knobs.get("min_day_usd") or 1.0)
    start = _month_start(month)
    end = _next_month(start)
    window_start = start - timedelta(days=trailing)
    daily = _daily_spend(conn, window_start, end)

    flags: list[dict[str, Any]] = []
    cursor = start
    while cursor < end:
        key = cursor.isoformat()
        spend = float(daily.get(key) or 0)
        if spend >= min_day_usd:
            prior: list[float] = []
            look = cursor - timedelta(days=1)
            oldest = cursor - timedelta(days=trailing)
            while look >= oldest:
                value = float(daily.get(look.isoformat()) or 0)
                if value > 0:
                    prior.append(value)
                look -= timedelta(days=1)
            if len(prior) >= min_days:
                median = _median(prior)
                if median > 0:
                    ratio = spend / median
                    if ratio > multiple:
                        flags.append(
                            {
                                "kind": "day_spend_spike",
                                "day": key,
                                "spend_usd": round(spend, 6),
                                "median_usd": round(median, 6),
                                "multiple": round(ratio, 2),
                                "threshold": multiple,
                                "trailing_days": trailing,
                                "note": (
                                    f"{key} spend ${spend:.2f} is {ratio:.1f}× trailing "
                                    f"{trailing}-day median ${median:.2f}"
                                ),
                            }
                        )
        cursor += timedelta(days=1)
    return flags


def _project_flags(
    lines: list[dict[str, Any]],
    knobs: dict[str, float | int],
) -> list[dict[str, Any]]:
    threshold = float(knobs.get("project_share") or 0.75)
    min_month = float(knobs.get("min_month_usd") or 1.0)
    buckets: dict[str, float] = {}
    for row in lines:
        project = str(row.get("project") or "(none)")
        usd = float(row.get("estimated_usd") or row.get("cost_usd") or 0)
        if row.get("allocated_billed_usd") is not None:
            usd = float(row["allocated_billed_usd"] or 0)
        buckets[project] = buckets.get(project, 0.0) + usd
    total = sum(buckets.values())
    if total < min_month or len(buckets) < 2:
        return []
    flags: list[dict[str, Any]] = []
    for project, usd in sorted(buckets.items(), key=lambda item: -item[1]):
        share = usd / total if total else 0.0
        if share < threshold:
            continue
        flags.append(
            {
                "kind": "project_share_spike",
                "project": project,
                "spent_usd": round(usd, 6),
                "month_usd": round(total, 6),
                "share": round(share, 4),
                "threshold": threshold,
                "note": (
                    f"{project} is {share:.0%} of month spend "
                    f"(soft note; threshold {threshold:.0%})"
                ),
            }
        )
    return flags


def scan(
    conn: sqlite3.Connection | None,
    *,
    month: str,
    lines: list[dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return soft notes. Failures are swallowed so status never breaks."""
    cfg = config if config is not None else config_mod.load()
    knobs = cfg.get("anomalies") or dict(config_mod.DEFAULT_ANOMALIES)
    flags: list[dict[str, Any]] = []
    try:
        if conn is not None:
            flags.extend(_day_flags(conn, month, knobs))
        flags.extend(_project_flags(list(lines or []), knobs))
    except (sqlite3.Error, TypeError, ValueError, KeyError):
        return []
    return flags
