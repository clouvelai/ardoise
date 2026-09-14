"""Orb-shaped spend statement document for the hosted API.

Same shape as local ardoise.document, but rates are derived from already-priced
cost_usd / tokens (no local pricebook on the API).
"""

from __future__ import annotations

import calendar
from datetime import datetime, timezone
from typing import Any


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _strip_day_zero(label: str) -> str:
    parts = label.split(" ", 1)
    if len(parts) != 2:
        return label
    mon, rest = parts
    if rest.startswith("0") and len(rest) > 1 and rest[1].isdigit():
        rest = rest[1:]
    return f"{mon} {rest}"


def month_period(month: str) -> dict[str, str]:
    year_s, mon_s = month.split("-", 1)
    year, mon = int(year_s), int(mon_s)
    last = calendar.monthrange(year, mon)[1]
    start = datetime(year, mon, 1, tzinfo=timezone.utc)
    end = datetime(year, mon, last, tzinfo=timezone.utc)
    start_label = _strip_day_zero(start.strftime("%b %d, %Y"))
    end_label = _strip_day_zero(end.strftime("%b %d, %Y"))
    return {
        "start": start_label,
        "end": end_label,
        "label": f"{start_label} – {end_label}",
    }


def format_date(stamp: datetime | None = None) -> str:
    now = stamp or datetime.now(timezone.utc)
    return _strip_day_zero(now.strftime("%b %d, %Y"))


def party(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"name": "", "address": [], "email": ""}
    name = str(raw.get("name") or "").strip()
    email = str(raw.get("email") or "").strip()
    address_raw = raw.get("address")
    address: list[str] = []
    if isinstance(address_raw, str) and address_raw.strip():
        address = [line.strip() for line in address_raw.splitlines() if line.strip()]
    elif isinstance(address_raw, list):
        for item in address_raw:
            text = str(item or "").strip()
            if text:
                address.append(text)
    return {"name": name, "address": address, "email": email}


def _token_line(
    *,
    description: str,
    tokens: int,
    rate: float | None,
    amount: float,
) -> dict[str, Any] | None:
    if tokens <= 0 and amount <= 0:
        return None
    rate_label = "—" if rate is None else f"${rate:g} / MTok"
    return {
        "kind": "meter",
        "description": description,
        "quantity": tokens,
        "quantity_label": f"{tokens:,}" if tokens else "—",
        "rate": rate,
        "rate_label": rate_label,
        "amount_usd": round(amount, 8),
    }


def _models_for_vendor(
    lines: list[dict[str, Any]], vendor: str, *, person: str = ""
) -> tuple[list[dict[str, Any]], float]:
    by_model: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in lines:
        if str(row.get("vendor") or "") != vendor:
            continue
        if str(row.get("person") or "") != person:
            continue
        model = str(row.get("model") or "(none)")
        if model not in by_model:
            by_model[model] = {
                "model": model,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
            }
            order.append(model)
        bucket = by_model[model]
        bucket["input_tokens"] += _int(row.get("input_tokens"))
        bucket["output_tokens"] += _int(row.get("output_tokens"))
        bucket["cost_usd"] += _float(row.get("cost_usd") or row.get("estimated_usd"))

    models: list[dict[str, Any]] = []
    list_total = 0.0
    for key in order:
        bucket = by_model[key]
        inn = int(bucket["input_tokens"])
        out = int(bucket["output_tokens"])
        cost = round(float(bucket["cost_usd"]), 8)
        weight = inn + out
        if weight > 0 and cost > 0:
            in_amount = round(cost * (inn / weight), 8) if inn else 0.0
            out_amount = round(cost - in_amount, 8) if out else 0.0
        else:
            in_amount = 0.0
            out_amount = cost if inn == 0 and out == 0 else 0.0
        in_rate = round(in_amount * 1_000_000 / inn, 6) if inn else None
        out_rate = round(out_amount * 1_000_000 / out, 6) if out else None
        meters: list[dict[str, Any]] = []
        for line in (
            _token_line(description="Input tokens", tokens=inn, rate=in_rate, amount=in_amount),
            _token_line(description="Output tokens", tokens=out, rate=out_rate, amount=out_amount),
        ):
            if line:
                meters.append(line)
        if not meters and cost > 0:
            meters.append(
                {
                    "kind": "meter",
                    "description": "Usage (unmetered)",
                    "quantity": 0,
                    "quantity_label": "—",
                    "rate": None,
                    "rate_label": "—",
                    "amount_usd": cost,
                }
            )
        model_sub = round(sum(float(m["amount_usd"]) for m in meters), 8)
        list_total += model_sub
        models.append(
            {
                "model": bucket["model"],
                "lines": meters,
                "subtotal_usd": model_sub,
                "input_tokens": inn,
                "output_tokens": out,
                "cost_usd": cost,
            }
        )
    models.sort(key=lambda item: (-float(item["subtotal_usd"]), item["model"]))
    return models, round(list_total, 8)


def build_document(
    summary: dict[str, Any],
    *,
    prepared_for: dict[str, Any] | None = None,
    from_party: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    month = str(summary.get("month") or "")
    period = month_period(month) if month else {"start": "", "end": "", "label": ""}
    issuer = party(from_party) if from_party is not None else party({"name": "Ardoise"})
    if not issuer.get("name"):
        issuer = {**issuer, "name": "Ardoise"}
    prepared = party(prepared_for)
    section_a = list(summary.get("section_a") or [])
    invoice_grade = bool(summary.get("invoice_grade")) and bool(section_a)
    estimated = _float(summary.get("estimated_usd") or summary.get("cost_usd"))
    billed = _float(summary.get("billed_usd")) if invoice_grade else 0.0
    total = billed if invoice_grade else estimated
    lines = list(summary.get("lines") or [])

    vendors_order: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in section_a:
        key = (str(row.get("vendor") or "unknown"), str(row.get("person") or ""))
        if key not in seen:
            seen.add(key)
            vendors_order.append(key)
    for row in lines:
        key = (str(row.get("vendor") or "unknown"), str(row.get("person") or ""))
        if key not in seen:
            seen.add(key)
            vendors_order.append(key)

    billed_by_scope = {
        (str(row.get("vendor") or "unknown"), str(row.get("person") or "")): row for row in section_a
    }
    groups: list[dict[str, Any]] = []
    for vendor, person in vendors_order:
        models, list_total = _models_for_vendor(lines, vendor, person=person)
        billed_row = billed_by_scope.get((vendor, person))
        if billed_row and billed_row.get("invoice_grade"):
            subtotal = round(_float(billed_row.get("billed_usd")), 2)
            tier = str(billed_row.get("tier_of_truth") or billed_row.get("tier") or "invoice")
            source = str(billed_row.get("source") or "")
            delta = round(subtotal - list_total, 8)
            adjustment = None
            if abs(delta) >= 0.0000005:
                adjustment = {
                    "kind": "adjustment",
                    "description": "Reconciling adjustment (billed vs list price)",
                    "quantity": None,
                    "quantity_label": "—",
                    "rate": None,
                    "rate_label": "—",
                    "amount_usd": delta,
                }
        else:
            subtotal = round(list_total, 8)
            tier = "T0"
            source = "T0 estimate"
            adjustment = None
        label = vendor if not person else f"{vendor} · {person}"
        groups.append(
            {
                "vendor": vendor,
                "person": person,
                "label": label,
                "period_label": period["label"],
                "subtotal_usd": subtotal,
                "list_total_usd": list_total,
                "tier": tier,
                "source": source,
                "invoice_grade": bool(billed_row and billed_row.get("invoice_grade")),
                "models": models,
                "adjustment": adjustment,
            }
        )

    return {
        "title": "Statement",
        "number": month,
        "statement_date": format_date(now),
        "period": period,
        "from": issuer,
        "prepared_for": prepared,
        "total_usd": round(total, 2) if invoice_grade else round(total, 4),
        "invoice_grade": invoice_grade,
        "estimated_usd": round(estimated, 8),
        "billed_usd": round(billed, 2) if invoice_grade else None,
        "groups": groups,
        "memo": [
            "This is a spend statement, not a tax invoice.",
            "Billed truth prefers pasted invoice, then T2 billed events, then T1 snapshot.",
            "T0 token weights allocate a billed total; Free shows list-price estimates only.",
        ],
        "notes": [str(item) for item in (summary.get("notes") or []) if item],
        "month": month,
        "entries": int(summary.get("month_entries") or 0),
    }
