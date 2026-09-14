"""Hosted ledger summary: invoice → T2 → T1 → T0, matching local reconcile."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

BILLED_TIERS = ("invoice", "T2", "T1")


def current_month(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    return stamp.strftime("%Y-%m")


def month_bounds(month: str) -> tuple[str, str]:
    year, mon = month.split("-", 1)
    y, m = int(year), int(mon)
    start = f"{y:04d}-{m:02d}-01T00:00:00Z"
    if m == 12:
        end = f"{y + 1:04d}-01-01T00:00:00Z"
    else:
        end = f"{y:04d}-{m + 1:02d}-01T00:00:00Z"
    return start, end


def in_month(stamp: Any, month: str) -> bool:
    text = str(stamp or "")
    if len(text) >= 7 and text[:7] == month:
        return True
    start, end = month_bounds(month)
    if not text:
        return False
    return start <= text < end


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _group(rows: list[dict[str, Any]], column: str, *, missing: str = "(none)") -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        key = str(row.get(column) or missing)
        if key not in buckets:
            buckets[key] = {
                column: key,
                "entries": 0,
                "cost_usd": 0.0,
                "allocated_billed_usd": 0.0,
                "has_allocated": False,
                "input_tokens": 0,
                "output_tokens": 0,
            }
            order.append(key)
        bucket = buckets[key]
        bucket["entries"] += 1
        bucket["cost_usd"] += _float(row.get("cost_usd"))
        bucket["input_tokens"] += _int(row.get("input_tokens"))
        bucket["output_tokens"] += _int(row.get("output_tokens"))
        if row.get("allocated_billed_usd") is not None:
            bucket["allocated_billed_usd"] += _float(row["allocated_billed_usd"])
            bucket["has_allocated"] = True
    out = []
    for key in order:
        bucket = buckets[key]
        has_allocated = bucket.pop("has_allocated")
        bucket["cost_usd"] = round(float(bucket["cost_usd"]), 6)
        bucket["allocated_billed_usd"] = (
            round(float(bucket["allocated_billed_usd"]), 6) if has_allocated else None
        )
        out.append(bucket)
    out.sort(key=lambda item: (-float(item["cost_usd"]), -int(item["entries"])))
    return out


def _scope_key(row: dict[str, Any]) -> tuple[str, str, str]:
    cycle = str(row.get("cycle") or "")[:7]
    if not cycle and row.get("occurred_at"):
        cycle = str(row.get("occurred_at"))[:7]
    return (
        str(row.get("vendor") or "unknown"),
        str(row.get("person") or ""),
        cycle,
    )


def _billed_for(
    vendor: str,
    person: str,
    cycle: str,
    *,
    invoices: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> dict[str, Any] | None:
    matched_inv = [
        row
        for row in invoices
        if str(row.get("vendor") or "") == vendor
        and str(row.get("person") or "") == person
        and str(row.get("cycle") or "")[:7] == cycle
    ]
    if matched_inv:
        cents = sum(_int(row.get("usd_cents") or row.get("billed_cents")) for row in matched_inv)
        note = next((str(row.get("notes") or "") for row in matched_inv if row.get("notes")), "paste")
        return {
            "vendor": vendor,
            "person": person,
            "cycle": cycle,
            "billed_cents": cents,
            "billed_usd": round(cents / 100.0, 6),
            "tier": "invoice",
            "tier_of_truth": "invoice",
            "source": note,
            "invoice_grade": True,
            "usd_cents": cents,
        }
    t2_cents = []
    for row in rows:
        if _scope_key(row) != (vendor, person, cycle):
            continue
        if str(row.get("tier") or "") != "T2":
            continue
        raw = row.get("billed_cents")
        if raw in (None, ""):
            continue
        t2_cents.append(_int(raw))
    if t2_cents:
        cents = sum(t2_cents)
        return {
            "vendor": vendor,
            "person": person,
            "cycle": cycle,
            "billed_cents": cents,
            "billed_usd": round(cents / 100.0, 6),
            "tier": "T2",
            "tier_of_truth": "T2",
            "source": "T2 events",
            "invoice_grade": True,
            "usd_cents": cents,
        }
    snaps = [
        row
        for row in snapshots
        if str(row.get("vendor") or "") == vendor
        and str(row.get("person") or "") == person
        and str(row.get("cycle") or "")[:7] == cycle
        and row.get("billed_cents") not in (None, "")
    ]
    snaps.sort(key=lambda row: str(row.get("as_of") or ""), reverse=True)
    if snaps:
        cents = _int(snaps[0].get("billed_cents"))
        return {
            "vendor": vendor,
            "person": person,
            "cycle": cycle,
            "billed_cents": cents,
            "billed_usd": round(cents / 100.0, 6),
            "tier": "T1",
            "tier_of_truth": "T1",
            "source": "T1 snapshot",
            "invoice_grade": True,
            "usd_cents": cents,
        }
    return None


def _allocate(events: list[dict[str, Any]], billed_cents: int) -> None:
    weights = [max(_int(row.get("input_tokens")) + _int(row.get("output_tokens")), 0) for row in events]
    if not events:
        return
    if sum(weights) <= 0:
        weights = [1] * len(events)
    total_w = sum(weights)
    remaining = int(billed_cents)
    for i, row in enumerate(events):
        if i == len(events) - 1:
            cents = remaining
        else:
            cents = int(round(billed_cents * (weights[i] / total_w)))
            remaining -= cents
        row["allocated_billed_usd"] = round(cents / 100.0, 8)


def summarize(
    *,
    rows: list[dict[str, Any]],
    invoices: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    month: str,
    invoice_grade: bool,
) -> dict[str, Any]:
    month_rows = [row for row in rows if in_month(row.get("occurred_at") or row.get("cycle"), month)]
    month_invoices = [row for row in invoices if str(row.get("cycle") or "")[:7] == month]
    month_snaps = [row for row in snapshots if str(row.get("cycle") or "")[:7] == month]

    scopes: set[tuple[str, str, str]] = set()
    for row in month_rows:
        scopes.add(_scope_key(row))
    for row in month_invoices:
        scopes.add((str(row.get("vendor") or "unknown"), str(row.get("person") or ""), str(row.get("cycle") or "")[:7]))
    for row in month_snaps:
        scopes.add((str(row.get("vendor") or "unknown"), str(row.get("person") or ""), str(row.get("cycle") or "")[:7]))

    section_a: list[dict[str, Any]] = []
    allocated = [dict(row) for row in month_rows]
    by_scope: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in allocated:
        by_scope[_scope_key(row)].append(row)

    for scope in sorted(scopes):
        billed = _billed_for(*scope, invoices=month_invoices, rows=month_rows, snapshots=month_snaps)
        if billed:
            section_a.append(billed)
            _allocate(by_scope.get(scope) or [], billed["billed_cents"])

    estimated = round(sum(_float(row.get("cost_usd")) for row in allocated), 6)
    billed_usd = round(sum(_float(row.get("billed_usd")) for row in section_a), 6)
    cursor_join = sum(
        1
        for row in allocated
        if str(row.get("vendor") or "") == "cursor"
        and _int(row.get("input_tokens")) == 0
        and _int(row.get("output_tokens")) == 0
        and _float(row.get("cost_usd")) == 0
    )
    notes: list[str] = []
    if cursor_join:
        notes.append(
            f"Cursor: {cursor_join} session(s), $0 — Team Admin or usage-shaped events needed for cents"
        )
    if not invoice_grade:
        notes.append("Estimated (Free). Upgrade to Pro for invoice-grade statements.")

    return {
        "ok": True,
        "month": month,
        "entries": len(allocated),
        "month_entries": len(allocated),
        "cost_usd": estimated,
        "estimated_usd": estimated,
        "billed_usd": billed_usd if invoice_grade else 0.0,
        "invoice_grade": invoice_grade,
        "section_a": section_a if invoice_grade else [],
        "lines": allocated,
        "by_project": _group(allocated, "project", missing="unmapped"),
        "by_model": _group(allocated, "model"),
        "by_person": _group(allocated, "person"),
        "by_source": _group(allocated, "source"),
        "by_vendor": _group(allocated, "vendor"),
        "by_agent": _group(allocated, "agent", missing="(unattributed)"),
        "cursor_join_sessions": cursor_join,
        "notes": notes,
        "connected": bool(rows or invoices or snapshots),
    }


def render_markdown(summary: dict[str, Any]) -> str:
    month = summary.get("month") or ""
    invoice_grade = bool(summary.get("invoice_grade"))
    lines = [
        f"# Ardoise statement · {month}",
        "",
        f"Entries: {summary.get('month_entries') or 0}",
        f"T0 estimate: ${float(summary.get('estimated_usd') or 0):.4f}",
    ]
    if invoice_grade:
        lines.append(f"Billed: ${float(summary.get('billed_usd') or 0):.2f}")
    else:
        lines.append("Billed: (Free estimate — upgrade to Pro)")
    lines += ["", "## Section A — vendor lines"]
    section_a = summary.get("section_a") or []
    if not invoice_grade:
        lines.append("Invoice-grade totals are a Pro feature.")
    elif not section_a:
        lines.append("(empty)")
    else:
        for row in section_a:
            lines.append(
                f"- {row.get('vendor')}  ${float(row.get('billed_usd') or 0):.2f}  "
                f"{row.get('tier_of_truth')}  {row.get('source')}"
            )
    lines += ["", "## By project"]
    projects = summary.get("by_project") or []
    if not projects:
        lines.append("(empty)")
    for row in projects:
        alloc = row.get("allocated_billed_usd")
        extra = f"  alloc=${float(alloc):.2f}" if alloc is not None and invoice_grade else ""
        lines.append(
            f"- {row.get('project')}  est=${float(row.get('cost_usd') or 0):.4f}  "
            f"n={row.get('entries')}{extra}"
        )
    for note in summary.get("notes") or []:
        lines += ["", f"> {note}"]
    return "\n".join(lines) + "\n"


def render_csv(summary: dict[str, Any]) -> str:
    rows = ["project,entries,cost_usd,allocated_billed_usd"]
    for row in summary.get("by_project") or []:
        alloc = row.get("allocated_billed_usd")
        rows.append(
            f"{row.get('project') or ''},{row.get('entries') or 0},"
            f"{float(row.get('cost_usd') or 0):.6f},"
            f"{'' if alloc is None else f'{float(alloc):.6f}'}"
        )
    return "\n".join(rows) + "\n"
