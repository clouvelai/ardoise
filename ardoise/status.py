"""Ledger status (human + JSON).

`cost_usd` remains the T0 list-price estimate (Phase 1). Billed truth lives
in `section_a` / `billed_usd` (invoice / T1 / T2 only).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ardoise import db, paths, reconcile


def _month_bounds(month: str) -> tuple[str, str]:
    year, mon = month.split("-", 1)
    y, m = int(year), int(mon)
    start = f"{y:04d}-{m:02d}-01T00:00:00Z"
    if m == 12:
        end = f"{y + 1:04d}-01-01T00:00:00Z"
    else:
        end = f"{y:04d}-{m + 1:02d}-01T00:00:00Z"
    return start, end


def current_month(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    return stamp.strftime("%Y-%m")


def _group(rows: list[dict[str, Any]], column: str) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        key = str(row.get(column) or "(none)")
        if key not in buckets:
            buckets[key] = {
                column: key,
                "entries": 0,
                "cost_usd": 0.0,
                "allocated_billed_usd": 0.0,
                "has_allocated": False,
                "input_tokens": 0,
                "output_tokens": 0,
                "tiers": set(),
            }
            order.append(key)
        bucket = buckets[key]
        bucket["entries"] += 1
        bucket["cost_usd"] += float(row.get("estimated_usd") or row.get("cost_usd") or 0)
        if row.get("allocated_billed_usd") is not None:
            bucket["allocated_billed_usd"] += float(row["allocated_billed_usd"])
            bucket["has_allocated"] = True
        bucket["input_tokens"] += int(row.get("input_tokens") or 0)
        bucket["output_tokens"] += int(row.get("output_tokens") or 0)
        bucket["tiers"].add(str(row.get("origin_tier") or row.get("tier") or "T0"))
    out = []
    for key in order:
        bucket = buckets[key]
        tiers = sorted(bucket.pop("tiers"))
        has_allocated = bucket.pop("has_allocated")
        bucket["cost_usd"] = round(float(bucket["cost_usd"]), 6)
        bucket["allocated_billed_usd"] = (
            round(float(bucket["allocated_billed_usd"]), 6) if has_allocated else None
        )
        bucket["tier"] = "T0"
        bucket["tiers"] = tiers
        out.append(bucket)
    out.sort(key=lambda item: (-float(item["cost_usd"]), -int(item["entries"])))
    return out


def summarize(month: str | None = None) -> dict[str, Any]:
    month = month or current_month()
    paths.ensure_home()
    with db.session() as conn:
        total_rows = db.count_entries(conn)
        lines = reconcile.flatten_month(conn, month)
        section_a = reconcile.section_a(conn, month)
        cycles = [item.as_dict() for item in reconcile.reconcile_month(conn, month)]

    estimated = round(sum(float(row.get("estimated_usd") or row.get("cost_usd") or 0) for row in lines), 6)
    billed_usd = round(
        sum(float(row.get("billed_usd") or 0) for row in section_a if row.get("invoice_grade")),
        6,
    )
    return {
        "ok": True,
        "ledger": str(paths.ledger_path()),
        "home": str(paths.ardoise_home()),
        "entries": total_rows,
        "month": month,
        "month_entries": len(lines),
        "cost_usd": estimated,
        "estimated_usd": estimated,
        "billed_usd": billed_usd,
        "input_tokens": sum(int(row.get("input_tokens") or 0) for row in lines),
        "output_tokens": sum(int(row.get("output_tokens") or 0) for row in lines),
        "cache_read_tokens": sum(int(row.get("cache_read_tokens") or 0) for row in lines),
        "cache_creation_tokens": sum(int(row.get("cache_creation_tokens") or 0) for row in lines),
        "by_project": _group(lines, "project"),
        "by_source": _group(lines, "source"),
        "by_model": _group(lines, "model"),
        "by_tier": _group(lines, "origin_tier"),
        "by_vendor": _group(lines, "vendor"),
        "lines": lines,
        "section_a": section_a,
        "reconciled": [
            {k: v for k, v in item.items() if k != "lines"}
            for item in cycles
        ],
    }


def render_text(data: dict[str, Any]) -> str:
    billed = data.get("billed_usd")
    section_a = data.get("section_a") or []
    if any(row.get("invoice_grade") for row in section_a):
        billed_line = f"billed    ${float(billed or 0):.2f}  (invoice / T1 / T2)"
    else:
        billed_line = "billed    (none)  — invoice add or T1/T2; T0 vendor lines are estimated"
    lines = [
        f"Ardoise  {data['month']}",
        f"ledger   {data['ledger']}",
        f"entries  {data['month_entries']} this month / {data['entries']} total",
        billed_line,
        f"estimated ${data['cost_usd']:.4f}  (T0 allocate only — not billed)",
        f"tokens   in={data['input_tokens']} out={data['output_tokens']} "
        f"cache_read={data['cache_read_tokens']} cache_write={data['cache_creation_tokens']}",
        "",
        "section A — vendor lines",
    ]
    if not section_a:
        lines.append("  (empty)")
    for row in section_a:
        usd = float(row.get("billed_usd") or 0)
        tier = row.get("tier_of_truth") or row.get("tier") or "T0"
        fmt = f"${usd:.2f}" if row.get("invoice_grade") else f"${usd:.4f}"
        lines.append(f"  {str(row.get('vendor') or ''):<16} {fmt}  {tier}  {row.get('source')}")
    lines.append("by project (T0 allocation)")
    if not data["by_project"]:
        lines.append("  (empty)")
    for row in data["by_project"]:
        alloc = row.get("allocated_billed_usd")
        extra = f"  alloc=${alloc:.2f}" if alloc is not None else ""
        lines.append(
            f"  {row['project']:<32} est=${row['cost_usd']:.4f}  n={row['entries']}  T0{extra}"
        )
    lines.append("by source (T0 allocation)")
    if not data["by_source"]:
        lines.append("  (empty)")
    for row in data["by_source"]:
        lines.append(
            f"  {row['source']:<32} est=${row['cost_usd']:.4f}  n={row['entries']}  T0"
        )
    return "\n".join(lines) + "\n"
