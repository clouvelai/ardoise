"""Recompute T0 cost_usd from the current price book.

Does not re-read transcripts. Safe to run more than once. Unknown models
stay $0 (same fail-open as status / estimate). T1/T2 billed cents are
left alone — they are not list-price estimates.
"""

from __future__ import annotations

from typing import Any

from ardoise import db, prices
from ardoise.model import is_placeholder

_EPS = 1e-8
_BILLED_TIERS = frozenset({"T1", "T2", "T2A"})


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _billed_truth(row: Any) -> bool:
    """Invoice-grade / Admin rows keep their stored cost."""
    tier = str(row["tier"] or "T0").strip().upper()
    if tier in _BILLED_TIERS:
        return True
    return row["billed_cents"] is not None


def _month_clause(month: str | None) -> tuple[str, tuple[str, ...]]:
    if not month:
        return "", ()
    return (
        " WHERE cycle = ? OR substr(occurred_at, 1, 7) = ?",
        (month, month),
    )


def reprice(*, month: str | None = None) -> dict[str, Any]:
    """Rewrite T0 ``cost_usd`` from the bundled / user price book."""
    updated = 0
    skipped = 0
    unknown = 0
    scanned = 0
    with db.session() as conn:
        db.seed_prices(conn)
        where, args = _month_clause(month)
        rows = conn.execute(
            f"""
            SELECT id, model, input_tokens, output_tokens,
                   cache_read_tokens, cache_creation_tokens,
                   cache_creation_5m_tokens, cache_creation_1h_tokens,
                   cost_usd, billed_cents, tier
            FROM events{where}
            ORDER BY id ASC
            """,
            args,
        ).fetchall()
        for row in rows:
            scanned += 1
            if _billed_truth(row):
                skipped += 1
                continue
            looked = prices.lookup(row["model"])
            if looked["unknown"] or is_placeholder(row["model"]):
                unknown += 1
            new_cost = prices.price_usd(
                model=row["model"],
                input_tokens=_int(row["input_tokens"]),
                output_tokens=_int(row["output_tokens"]),
                cache_read_tokens=_int(row["cache_read_tokens"]),
                cache_creation_tokens=_int(row["cache_creation_tokens"]),
                cache_creation_5m_tokens=_int(row["cache_creation_5m_tokens"]),
                cache_creation_1h_tokens=_int(row["cache_creation_1h_tokens"]),
            )
            old = float(row["cost_usd"] or 0)
            if abs(old - new_cost) < _EPS:
                skipped += 1
                continue
            conn.execute(
                "UPDATE events SET cost_usd = ? WHERE id = ?",
                (float(new_cost), int(row["id"])),
            )
            updated += 1
    return {
        "ok": True,
        "command": "reprice",
        "month": month,
        "scanned": scanned,
        "updated": updated,
        "skipped": skipped,
        "unknown": unknown,
    }


def render_text(data: dict[str, Any]) -> str:
    month = data.get("month")
    extra = f"  month={month}" if month else ""
    return (
        "reprice{extra}  updated={updated}  skipped={skipped}  unknown={unknown}\n".format(
            extra=extra,
            updated=int(data.get("updated") or 0),
            skipped=int(data.get("skipped") or 0),
            unknown=int(data.get("unknown") or 0),
        )
    )
