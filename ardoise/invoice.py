"""Owner-received invoice totals (paste). Solid dollars for statement section A.

No live Stripe/vendor API. `invoice add` is idempotent on (vendor, cycle, person).
"""

from __future__ import annotations

import csv
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
_SOURCES = frozenset({"paste", "t1", "t2"})


def _vendor(raw: Any) -> str:
    name = str(raw or "").strip().lower()
    name = _VENDOR_ALIASES.get(name, name)
    if not name:
        raise ValueError("invoice row missing vendor")
    return vendor_for_source(name) if name not in {"anthropic", "cursor"} else name


def _usd_cents(row: dict[str, Any]) -> int:
    for key in ("usd_cents", "billed_cents"):
        if row.get(key) not in (None, ""):
            try:
                return int(row[key])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be an integer") from exc
    for key in ("usd", "billed_usd", "amount_usd", "total_usd", "amount"):
        if row.get(key) not in (None, ""):
            try:
                return int(round(float(row[key]) * 100))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be a number") from exc
    raise ValueError("invoice needs usd_cents or usd")


def _cycle(raw: Any) -> str:
    text = str(raw or "").strip()
    if _MONTH_RE.match(text):
        return text
    if text and len(text) >= 7 and text[4] == "-":
        cand = text[:7]
        if _MONTH_RE.match(cand):
            return cand
    raise ValueError(f"invoice cycle must be YYYY-MM, got {raw!r}")


def _source(raw: Any) -> str:
    source = str(raw or "paste").strip().lower()
    if source not in _SOURCES:
        raise ValueError("invoice source must be paste, t1, or t2")
    return source


def _notes(row: dict[str, Any]) -> str | None:
    parts = []
    for key in ("notes", "note", "invoice_id", "invoice_ref"):
        val = row.get(key)
        if val not in (None, ""):
            parts.append(str(val))
    if not parts:
        return None
    # Prefer an explicit notes field; otherwise keep a pasted invoice id.
    if row.get("notes") not in (None, ""):
        return str(row["notes"])
    return parts[0]


def normalize_row(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("invoice row must be an object")
    lowered = {str(k).strip().lower().replace("-", "_"): v for k, v in raw.items()}
    aliases = {
        "invoiceid": "invoice_id",
        "invoice": "invoice_id",
        "id": "invoice_id",
        "person_id": "person",
        "scope": "person",
        "month": "cycle",
        "period": "cycle",
        "usd_cents": "usd_cents",
        "billed_cents": "billed_cents",
    }
    for src, dest in aliases.items():
        if dest not in lowered and src in lowered:
            lowered[dest] = lowered[src]
    if "person" not in lowered and lowered.get("scope") not in (None, ""):
        lowered["person"] = lowered["scope"]
    return {
        "vendor": _vendor(lowered.get("vendor")),
        "person": str(lowered.get("person") or "").strip(),
        "cycle": _cycle(lowered.get("cycle")),
        "usd_cents": _usd_cents(lowered),
        "source": _source(lowered.get("source")),
        "notes": _notes(lowered),
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


def add(
    *,
    vendor: str,
    cycle: str,
    usd_cents: int | None = None,
    usd: float | None = None,
    person: str = "",
    notes: str | None = None,
    source: str = "paste",
) -> dict[str, Any]:
    """Paste one owner-received vendor/Stripe total. Idempotent on (vendor, cycle, person)."""
    row = normalize_row(
        {
            "vendor": vendor,
            "cycle": cycle,
            "person": person,
            "usd_cents": usd_cents,
            "usd": usd,
            "notes": notes,
            "source": source,
        }
    )
    with db.session() as conn:
        kind = db.upsert_invoice(conn, row)
    return {
        "result": kind,
        "inserted": 1 if kind == "inserted" else 0,
        "updated": 1 if kind == "updated" else 0,
        "rows": 1,
        "vendor": row["vendor"],
        "cycle": row["cycle"],
        "person": row["person"],
        "usd_cents": row["usd_cents"],
        "source": row["source"],
    }


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
        raise ValueError("invoice paste needs --file, stdin, or invoice add flags")

    counts = {"inserted": 0, "updated": 0, "rows": len(rows)}
    with db.session() as conn:
        for item in rows:
            kind = db.upsert_invoice(conn, item)
            counts[kind] = counts.get(kind, 0) + 1
    return counts
