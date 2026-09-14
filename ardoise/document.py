"""Orb-shaped spend statement document (not a tax invoice / A/R bill).

Builds a structured document from a status summary: parties, number, period,
vendor → model → token rows (qty × rate), and a reconciling adjustment when
invoice-grade billed differs from T0 list-price sum.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timezone
from typing import Any, Callable

from ardoise import attribution, prices, roster

RateFn = Callable[[str | None, str], float | None]


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


def _strip_day_zero(label: str) -> str:
    # "Sep 01, 2026" → "Sep 1, 2026"
    parts = label.split(" ", 1)
    if len(parts) != 2:
        return label
    mon, rest = parts
    if rest.startswith("0") and len(rest) > 1 and rest[1].isdigit():
        rest = rest[1:]
    return f"{mon} {rest}"


def format_date(stamp: datetime | None = None) -> str:
    now = stamp or datetime.now(timezone.utc)
    return _strip_day_zero(now.strftime("%b %d, %Y"))


def party_from_config(raw: Any) -> dict[str, Any]:
    """Normalize optional statement.from / prepared_for blocks."""
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


def _local_rate(model: str | None, kind: str) -> float | None:
    rates = prices.rates_for(model)
    key = {"input": "input", "output": "output"}.get(kind)
    if not key:
        return None
    try:
        return float(rates[key])
    except (KeyError, TypeError, ValueError):
        return None


def _amount_from_tokens(tokens: int, rate_per_mtok: float | None) -> float:
    if not tokens or rate_per_mtok is None:
        return 0.0
    return round(tokens * float(rate_per_mtok) / 1_000_000.0, 8)


def _rate_label(rate: float | None) -> str:
    if rate is None:
        return "—"
    return f"${rate:g} / MTok"


def _qty_label(tokens: int) -> str:
    return f"{tokens:,}"


def _token_line(
    *,
    description: str,
    tokens: int,
    rate: float | None,
    amount: float,
) -> dict[str, Any] | None:
    if tokens <= 0 and amount <= 0:
        return None
    return {
        "kind": "meter",
        "description": description,
        "quantity": tokens,
        "quantity_label": _qty_label(tokens) if tokens else "—",
        "rate": rate,
        "rate_label": _rate_label(rate),
        "amount_usd": round(amount, 8),
    }


def _models_for_vendor(
    lines: list[dict[str, Any]],
    vendor: str,
    *,
    person: str = "",
    rate_fn: RateFn,
    derive_rate: bool,
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
                "allocated_billed_usd": 0.0,
                "has_allocated": False,
            }
            order.append(model)
        bucket = by_model[model]
        bucket["input_tokens"] += _int(row.get("input_tokens"))
        bucket["output_tokens"] += _int(row.get("output_tokens"))
        bucket["cost_usd"] += _float(row.get("estimated_usd") or row.get("cost_usd"))
        if row.get("allocated_billed_usd") is not None:
            bucket["allocated_billed_usd"] += _float(row["allocated_billed_usd"])
            bucket["has_allocated"] = True

    models: list[dict[str, Any]] = []
    list_total = 0.0
    for key in order:
        bucket = by_model[key]
        model = bucket["model"]
        inn = int(bucket["input_tokens"])
        out = int(bucket["output_tokens"])
        cost = round(float(bucket["cost_usd"]), 8)

        if derive_rate:
            # Hosted rows are already priced; split cost by token weight, then
            # back out $/MTok so the Orb table still shows qty × rate.
            weight_in = inn
            weight_out = out
            total_w = weight_in + weight_out
            if total_w > 0 and cost > 0:
                in_amount = round(cost * (weight_in / total_w), 8) if weight_in else 0.0
                out_amount = round(cost - in_amount, 8) if weight_out else 0.0
            else:
                in_amount = 0.0
                out_amount = cost if out == 0 and inn == 0 else 0.0
            in_rate = round(in_amount * 1_000_000 / inn, 6) if inn else None
            out_rate = round(out_amount * 1_000_000 / out, 6) if out else None
        else:
            in_rate = rate_fn(model if model != "(none)" else None, "input")
            out_rate = rate_fn(model if model != "(none)" else None, "output")
            in_amount = _amount_from_tokens(inn, in_rate)
            out_amount = _amount_from_tokens(out, out_rate)

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
                "model": model,
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
    config: dict[str, Any] | None = None,
    prepared_for_override: dict[str, Any] | None = None,
    from_override: dict[str, Any] | None = None,
    rate_fn: RateFn | None = None,
    derive_rate: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build Orb-floor statement document from a summarize() payload."""
    cfg = config or {}
    stmt_cfg = cfg.get("statement") if isinstance(cfg.get("statement"), dict) else {}
    from_party = party_from_config(from_override if from_override is not None else (stmt_cfg or {}).get("from"))
    if not from_party.get("name"):
        from_party = {**from_party, "name": "Ardoise"}

    prepared = party_from_config(
        prepared_for_override if prepared_for_override is not None else (stmt_cfg or {}).get("prepared_for")
    )
    filt = summary.get("filter") or {}
    if not prepared.get("name"):
        label = roster.display(filt.get("canonical") or filt.get("query")) if filt else ""
        if label:
            kind = str(filt.get("kind") or "person")
            prepared = {
                **prepared,
                "name": label,
                "email": prepared.get("email") or "",
                "address": prepared.get("address") or [],
                "kind": kind,
            }

    month = str(summary.get("month") or "")
    period = month_period(month) if month else {"start": "", "end": "", "label": ""}
    number = roster.filename_for(month, filt if filt else None)
    section_a = list(summary.get("section_a") or [])
    invoice_grade = bool(summary.get("invoice_grade")) or any(
        row.get("invoice_grade") for row in section_a
    )
    estimated = _float(summary.get("estimated_usd") or summary.get("cost_usd"))
    billed = _float(summary.get("billed_usd")) if invoice_grade else 0.0
    total = billed if invoice_grade and section_a else estimated
    lines = list(summary.get("lines") or [])
    rates = rate_fn or _local_rate

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

    billed_by_scope: dict[tuple[str, str], dict[str, Any]] = {}
    for row in section_a:
        billed_by_scope[(str(row.get("vendor") or "unknown"), str(row.get("person") or ""))] = row

    groups: list[dict[str, Any]] = []
    for vendor, person in vendors_order:
        models, list_total = _models_for_vendor(
            lines, vendor, person=person, rate_fn=rates, derive_rate=derive_rate
        )
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
            source = "T0 local estimate"
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

    memo = [
        "This is a spend statement, not a tax invoice.",
        "Billed truth prefers pasted invoice, then T2 billed events, then T1 snapshot.",
        "T0 token × list price is allocation weight only when a billed total exists.",
    ]
    notes = [str(item) for item in (summary.get("notes") or []) if item]

    if prepared.get("name") and filt:
        kind = str(filt.get("kind") or "person")
        noun = "Agent" if kind == "agent" else "Seat"
        spend = ""
        if kind == "agent":
            chips = attribution.spend_chips(summary)
            if chips:
                spend = f" · ${float(chips[0].get('cost_usd') or 0):.4f}"
        notes = [
            f"{noun} filter {prepared['name']}{spend} (view only — ledger unchanged).",
            *notes,
        ]
    elif not filt:
        chips = attribution.spend_chips(summary)
        if chips:
            bits = " · ".join(
                f"{row['agent']} ${float(row.get('cost_usd') or 0):.4f}" for row in chips
            )
            notes = [f"Agents · {bits}", *notes]

    return {
        "title": "Statement",
        "number": number,
        "statement_date": format_date(now),
        "period": period,
        "from": from_party,
        "prepared_for": prepared,
        "total_usd": round(total, 2) if invoice_grade and section_a else round(total, 4),
        "invoice_grade": bool(invoice_grade and section_a),
        "estimated_usd": round(estimated, 8),
        "billed_usd": round(billed, 2) if invoice_grade else None,
        "groups": groups,
        "memo": memo,
        "notes": notes,
        "month": month,
        "entries": int(summary.get("month_entries") or 0),
    }
