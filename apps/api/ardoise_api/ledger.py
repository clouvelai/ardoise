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


def _md_money(value: Any, *, places: int = 2) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    return f"${number:,.{places}f}"


def render_markdown(summary: dict[str, Any]) -> str:
    from ardoise_api.document import build_document

    doc = build_document(summary)
    invoice_grade = bool(doc.get("invoice_grade"))
    period = (doc.get("period") or {}).get("label") or ""
    places = 2 if invoice_grade else 4
    lines = [
        f"# {doc.get('title') or 'Statement'} {doc.get('number') or summary.get('month') or ''}",
        "",
        "## From",
        "",
        f"- {(doc.get('from') or {}).get('name') or 'Ardoise'}",
        "",
        "## Prepared for",
        "",
        f"- {(doc.get('prepared_for') or {}).get('name') or (doc.get('prepared_for') or {}).get('email') or '—'}",
        "",
        "| | |",
        "|---|---|",
        f"| Statement number | {doc.get('number')} |",
        f"| Statement date | {doc.get('statement_date')} |",
        f"| Usage period | {period} |",
        f"| Total | {_md_money(doc.get('total_usd'), places=places)} |",
        "",
        "| Description | Quantity | Rate | Amount |",
        "|---|---:|---:|---:|",
    ]
    groups = doc.get("groups") or []
    if not groups:
        lines.append("| (no usage this period) | — | — | — |")
    for group in groups:
        vendor = group.get("label") or group.get("vendor") or "vendor"
        group_places = 2 if group.get("invoice_grade") else 4
        lines.append(
            f"| **{vendor}** |  |  | **{_md_money(group.get('subtotal_usd'), places=group_places)}** |"
        )
        period_bits = [group.get("period_label") or period]
        if group.get("tier"):
            period_bits.append(str(group.get("tier")))
        lines.append(f"| {' · '.join(bit for bit in period_bits if bit)} |  |  |  |")
        for model in group.get("models") or []:
            lines.append(
                f"| {model.get('model') or '(none)'} |  |  | "
                f"{_md_money(model.get('subtotal_usd'), places=4)} |"
            )
            for meter in model.get("lines") or []:
                lines.append(
                    "| {desc} | {qty} | {rate} | {amt} |".format(
                        desc=meter.get("description") or "",
                        qty=meter.get("quantity_label") or "—",
                        rate=meter.get("rate_label") or "—",
                        amt=_md_money(meter.get("amount_usd"), places=4),
                    )
                )
        adj = group.get("adjustment")
        if adj:
            lines.append(
                "| {desc} | — | — | {amt} |".format(
                    desc=adj.get("description") or "Reconciling adjustment",
                    amt=_md_money(adj.get("amount_usd"), places=4),
                )
            )
    totals = doc.get("totals") or {}
    if totals.get("show_reconciliation"):
        lines += [
            f"| List price |  |  | {_md_money(totals.get('list_usd'), places=4)} |",
            f"| Reconciling adjustment |  |  | {_md_money(totals.get('adjustment_usd'), places=4)} |",
        ]
    lines.append(f"| **Total** |  |  | **{_md_money(doc.get('total_usd'), places=places)}** |")
    if not invoice_grade:
        lines += ["", "Estimated (Free). Upgrade to Pro for invoice-grade statements."]
    lines += ["", "## Memo", ""]
    for item in doc.get("memo") or []:
        lines.append(f"- {item}")
    for note in doc.get("notes") or summary.get("notes") or []:
        if note:
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
