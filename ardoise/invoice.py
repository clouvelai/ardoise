"""Paste invoice rows into the ledger. Solid dollar source for statement section A."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any, TextIO

from ardoise import db
from ardoise.vendors.contract import vendor_for_source

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_VENDOR_ALIASES = {
    "claude": "anthropic",
    "claude-code": "anthropic",
    "anthropic_t0": "anthropic",
}


def _vendor(raw: Any) -> str:
    name = str(raw or "").strip().lower()
    name = _VENDOR_ALIASES.get(name, name)
    if not name:
        raise ValueError("invoice row missing vendor")
    return vendor_for_source(name) if name not in {"anthropic", "cursor"} else name


def _cents(row: dict[str, Any]) -> int:
    if row.get("billed_cents") not in (None, ""):
        try:
            return int(row["billed_cents"])
        except (TypeError, ValueError) as exc:
            raise ValueError("billed_cents must be an integer") from exc
    for key in ("billed_usd", "amount_usd", "total_usd", "usd", "amount"):
        if row.get(key) not in (None, ""):
            try:
                return int(round(float(row[key]) * 100))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be a number") from exc
    raise ValueError("invoice row needs billed_cents or billed_usd")


def _cycle(raw: Any) -> str:
    text = str(raw or "").strip()
    if _MONTH_RE.match(text):
        return text
    if text and len(text) >= 7 and text[4] == "-":
        cand = text[:7]
        if _MONTH_RE.match(cand):
            return cand
    raise ValueError(f"invoice cycle must be YYYY-MM, got {raw!r}")


def _synthetic_id(row: dict[str, Any], cents: int) -> str:
    seed = "|".join(
        [
            str(row.get("vendor") or ""),
            str(row.get("person") or ""),
            str(row.get("cycle") or ""),
            str(cents),
            str(row.get("issued_at") or ""),
        ]
    )
    return "paste-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def normalize_row(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("invoice row must be an object")
    lowered = {str(k).strip().lower(): v for k, v in raw.items()}
    # accept Invoice ID style headers
    aliases = {
        "invoiceid": "invoice_id",
        "invoice": "invoice_id",
        "id": "invoice_id",
        "person_id": "person",
        "month": "cycle",
        "period": "cycle",
        "issued": "issued_at",
    }
    for src, dest in aliases.items():
        if dest not in lowered and src in lowered:
            lowered[dest] = lowered[src]
    cents = _cents(lowered)
    invoice_id = str(lowered.get("invoice_id") or "").strip()
    if not invoice_id:
        invoice_id = _synthetic_id(lowered, cents)
    return {
        "vendor": _vendor(lowered.get("vendor")),
        "person": str(lowered.get("person") or "").strip(),
        "cycle": _cycle(lowered.get("cycle")),
        "invoice_id": invoice_id,
        "billed_cents": cents,
        "currency": str(lowered.get("currency") or "USD"),
        "status": lowered.get("status"),
        "issued_at": lowered.get("issued_at"),
        "source": lowered.get("source") or "paste",
        "notes": lowered.get("notes"),
    }


def _parse_json_text(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError("JSONL invoice lines must be objects")
            rows.append(item)
        return rows
    if isinstance(obj, list):
        out = []
        for item in obj:
            if not isinstance(item, dict):
                raise ValueError("invoice JSON array must contain objects")
            out.append(item)
        return out
    if isinstance(obj, dict):
        if isinstance(obj.get("invoices"), list):
            return [item for item in obj["invoices"] if isinstance(item, dict)]
        return [obj]
    raise ValueError("invoice JSON must be an object or array")


def _parse_csv_text(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader if any((v or "").strip() for v in row.values())]


def parse_invoices(text: str) -> list[dict[str, Any]]:
    stripped = text.lstrip()
    if not stripped:
        return []
    if stripped[0] in "{[":
        raw_rows = _parse_json_text(text)
    else:
        raw_rows = _parse_csv_text(text)
    return [normalize_row(row) for row in raw_rows]


def paste(
    text: str | None = None,
    *,
    path: Path | None = None,
    stream: TextIO | None = None,
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if row:
        rows.append(normalize_row(row))
    elif path is not None:
        rows.extend(parse_invoices(path.read_text(encoding="utf-8")))
    elif text is not None:
        rows.extend(parse_invoices(text))
    elif stream is not None:
        rows.extend(parse_invoices(stream.read()))
    else:
        raise ValueError("invoice paste needs --file, stdin, or vendor/cycle/amount")

    counts = {"inserted": 0, "updated": 0, "rows": len(rows)}
    with db.session() as conn:
        for item in rows:
            kind = db.upsert_invoice(conn, item)
            counts[kind] = counts.get(kind, 0) + 1
    return counts
