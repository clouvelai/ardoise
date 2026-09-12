"""Soft budget headroom + lightweight anomaly flags.

`daily_ready()` is the JSON shape status already prints. A later HTTP
`/daily-ready` can return the same object; this module has no server.

Anomaly rules (deterministic; see docs/budgets.md):

* day_spike — a UTC day's USD is >= 3× the mean of prior days with spend
  in the previous 7 days, with at least 3 such prior days, and the day
  itself is at least $0.05.
* session_outlier — a session's USD is >= 3× the median of the other
  sessions in the month, with at least 4 sessions, and the session is
  at least $0.05.

USD for heuristics is event `billed_cents` when present, else T0 `cost_usd`.
Token totals are input + output (cache tokens are ignored).
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from ardoise import budget as budget_mod

DAILY_READY_SCHEMA = "ardoise.daily_ready.v1"

DAY_SPIKE_RATIO = 3.0
DAY_SPIKE_MIN_USD = 0.05
DAY_SPIKE_MIN_PRIOR_DAYS = 3
DAY_SPIKE_LOOKBACK_DAYS = 7

SESSION_OUTLIER_RATIO = 3.0
SESSION_OUTLIER_MIN_USD = 0.05
SESSION_OUTLIER_MIN_SESSIONS = 4

LOOKBACK_DAYS = 14


def month_bounds(month: str) -> tuple[str, str]:
    year, mon = month.split("-", 1)
    y, m = int(year), int(mon)
    start = f"{y:04d}-{m:02d}-01T00:00:00Z"
    if m == 12:
        end = f"{y + 1:04d}-01-01T00:00:00Z"
    else:
        end = f"{y:04d}-{m + 1:02d}-01T00:00:00Z"
    return start, end


def lookback_start(month: str, *, days: int = LOOKBACK_DAYS) -> str:
    start, _ = month_bounds(month)
    stamp = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (stamp - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def event_usd(row: dict[str, Any]) -> float:
    billed = row.get("billed_cents")
    if billed not in (None, ""):
        try:
            return int(billed) / 100.0
        except (TypeError, ValueError):
            pass
    return float(row.get("estimated_usd") or row.get("cost_usd") or 0)


def event_tokens(row: dict[str, Any]) -> int:
    return int(row.get("input_tokens") or 0) + int(row.get("output_tokens") or 0)


def event_day(row: dict[str, Any]) -> str:
    text = str(row.get("occurred_at") or "")
    return text[:10] if len(text) >= 10 else ""


def event_session(row: dict[str, Any]) -> str:
    sid = str(row.get("session_id") or "").strip()
    if sid:
        return sid
    mid = str(row.get("message_id") or "").strip()
    if mid:
        return f"msg:{mid}"
    return ""


def reference_day(month: str, as_of: datetime) -> str:
    if as_of.strftime("%Y-%m") == month:
        return as_of.strftime("%Y-%m-%d")
    start, end = month_bounds(month)
    last = datetime.strptime(end, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    last -= timedelta(seconds=1)
    if last.strftime("%Y-%m") != month:
        return start[:10]
    return last.strftime("%Y-%m-%d")


def _day_totals(lines: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in lines:
        day = event_day(row)
        if not day:
            continue
        totals[day] = totals.get(day, 0.0) + event_usd(row)
    return totals


def _session_totals(lines: list[dict[str, Any]], *, month: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in lines:
        if event_day(row)[:7] != month:
            continue
        sid = event_session(row)
        if not sid:
            continue
        totals[sid] = totals.get(sid, 0.0) + event_usd(row)
    return totals


def detect_anomalies(
    lines: list[dict[str, Any]],
    *,
    month: str,
) -> list[dict[str, Any]]:
    """Return day_spike / session_outlier flags for `month`. Pure."""
    flags: list[dict[str, Any]] = []
    daily = _day_totals(lines)
    days = sorted(daily)
    for day in days:
        if day[:7] != month:
            continue
        usd = daily[day]
        if usd < DAY_SPIKE_MIN_USD:
            continue
        stamp = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        prior: list[float] = []
        for back in range(1, DAY_SPIKE_LOOKBACK_DAYS + 1):
            prev = (stamp - timedelta(days=back)).strftime("%Y-%m-%d")
            if prev in daily:
                prior.append(daily[prev])
        if len(prior) < DAY_SPIKE_MIN_PRIOR_DAYS:
            continue
        baseline = statistics.fmean(prior)
        if baseline <= 0:
            continue
        ratio = usd / baseline
        if ratio + 1e-12 < DAY_SPIKE_RATIO:
            continue
        flags.append(
            {
                "kind": "day_spike",
                "severity": "warn",
                "message": (
                    f"{day} ${usd:.2f} is {ratio:.1f}× the "
                    f"{DAY_SPIKE_LOOKBACK_DAYS}-day baseline (${baseline:.2f})"
                ),
                "detail": {
                    "day": day,
                    "usd": round(usd, 6),
                    "baseline_usd": round(baseline, 6),
                    "ratio": round(ratio, 6),
                    "window_days": DAY_SPIKE_LOOKBACK_DAYS,
                    "prior_days": len(prior),
                },
            }
        )

    sessions = _session_totals(lines, month=month)
    if len(sessions) >= SESSION_OUTLIER_MIN_SESSIONS:
        for sid, usd in sessions.items():
            if usd < SESSION_OUTLIER_MIN_USD:
                continue
            others = [value for key, value in sessions.items() if key != sid]
            if len(others) < SESSION_OUTLIER_MIN_SESSIONS - 1:
                continue
            median = statistics.median(others)
            if median <= 0:
                continue
            ratio = usd / median
            if ratio + 1e-12 < SESSION_OUTLIER_RATIO:
                continue
            flags.append(
                {
                    "kind": "session_outlier",
                    "severity": "warn",
                    "message": (
                        f"session {sid} ${usd:.2f} is {ratio:.1f}× "
                        f"the session median (${median:.2f})"
                    ),
                    "detail": {
                        "session_id": sid,
                        "usd": round(usd, 6),
                        "median_usd": round(float(median), 6),
                        "ratio": round(ratio, 6),
                        "sessions": len(sessions),
                    },
                }
            )
    return flags


def _fmt_limit(metric: str, value: float) -> str:
    if metric == "tokens":
        return str(int(round(value)))
    return f"${value:.2f}"


def budget_flags(headroom: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for row in headroom:
        state = row.get("state")
        if state not in {"warn", "over"}:
            continue
        kind = "budget_over" if state == "over" else "budget_warn"
        metric = str(row.get("metric") or "usd")
        period = str(row.get("period") or "month")
        limit = float(row.get("limit") or 0)
        used = float(row.get("used") or 0)
        pct = 100.0 * float(row.get("ratio") or 0)
        if state == "over":
            message = (
                f"{period} {metric} over {_fmt_limit(metric, limit)} "
                f"(used {_fmt_limit(metric, used)})"
            )
        else:
            message = (
                f"{period} {metric} at {pct:.0f}% of {_fmt_limit(metric, limit)} "
                f"(used {_fmt_limit(metric, used)})"
            )
        flags.append(
            {
                "kind": kind,
                "severity": "warn",
                "message": message,
                "detail": {
                    "id": row.get("id"),
                    "period": period,
                    "metric": metric,
                    "limit": limit,
                    "used": used,
                    "remaining": row.get("remaining"),
                    "ratio": row.get("ratio"),
                    "state": state,
                    "basis": row.get("basis"),
                },
            }
        )
    return flags


def usage_for_day(lines: list[dict[str, Any]], day: str) -> tuple[float, int]:
    usd = 0.0
    tokens = 0
    for row in lines:
        if event_day(row) != day:
            continue
        usd += event_usd(row)
        tokens += event_tokens(row)
    return usd, tokens


def usage_for_month(lines: list[dict[str, Any]], month: str) -> tuple[float, int]:
    usd = 0.0
    tokens = 0
    for row in lines:
        if event_day(row)[:7] != month:
            continue
        usd += event_usd(row)
        tokens += event_tokens(row)
    return usd, tokens


def daily_ready(
    *,
    month: str,
    lines: list[dict[str, Any]],
    budgets: list[dict[str, Any]] | None = None,
    billed_usd: float = 0.0,
    estimated_usd: float = 0.0,
    invoice_grade: bool = False,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Pure JSON payload for `status` and a future `/daily-ready` route."""
    stamp = as_of or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    else:
        stamp = stamp.astimezone(timezone.utc)
    day = reference_day(month, stamp)
    day_usd, day_tokens = usage_for_day(lines, day)
    _month_usd, month_tokens = usage_for_month(lines, month)
    usd_basis = "billed" if invoice_grade else "estimated"
    month_usd = float(billed_usd) if invoice_grade else float(estimated_usd)
    headroom = budget_mod.evaluate(
        budgets or [],
        used_usd_month=month_usd,
        used_usd_day=day_usd,
        used_tokens_month=month_tokens,
        used_tokens_day=day_tokens,
        usd_basis=usd_basis,
    )
    flags = budget_flags(headroom) + detect_anomalies(lines, month=month)
    return {
        "schema": DAILY_READY_SCHEMA,
        "month": month,
        "as_of": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "day": day,
        "budgets": headroom,
        "flags": flags,
    }
