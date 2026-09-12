"""Vendor spend preference: invoice → T2 → T1 snapshot → T0 estimated.

T0 list-price estimates are weights for section B only when an invoice / T1 / T2
total exists. They may appear on section A vendor lines as the last-resort tier.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from ardoise.vendors.contract import TokenCounts

BILLED_TIERS = ("invoice", "T2", "T1")


@dataclass
class BilledRow:
    vendor: str
    person: str
    cycle: str
    billed_cents: int
    billed_usd: float
    tier: str
    source: str
    invoice_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReconciledLine:
    vendor: str
    person: str
    cycle: str
    source: str
    project: str | None
    model: str | None
    occurred_at: str
    message_id: str
    request_id: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    cost_usd: float
    billed_cents: int | None
    tier: str
    origin_tier: str
    estimated_usd: float = 0.0
    allocated_billed_usd: float | None = None
    role: str = "t0_allocation"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReconciledCycle:
    vendor: str
    person: str
    cycle: str
    preferred_tier: str
    lines: list[ReconciledLine]
    cost_usd: float
    billed_cents: int | None
    input_tokens: int
    output_tokens: int
    note: str
    billed: BilledRow | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "person": self.person,
            "cycle": self.cycle,
            "preferred_tier": self.preferred_tier,
            "cost_usd": self.cost_usd,
            "billed_cents": self.billed_cents,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "note": self.note,
            "billed": self.billed.as_dict() if self.billed else None,
            "lines": [line.as_dict() for line in self.lines],
        }


def _row_tokens(row: dict[str, Any]) -> TokenCounts:
    return TokenCounts.from_mapping(row)


def _events(
    conn: sqlite3.Connection,
    *,
    vendor: str,
    person: str,
    cycle: str,
    tier: str | None = None,
) -> list[dict[str, Any]]:
    sql = """
        SELECT * FROM events
        WHERE vendor = ? AND person = ? AND cycle = ?
    """
    args: list[Any] = [vendor, person, cycle]
    if tier:
        sql += " AND tier = ?"
        args.append(tier)
    sql += " ORDER BY occurred_at ASC, id ASC"
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def _line(
    row: dict[str, Any],
    *,
    tier: str,
    cost_usd: float | None = None,
    billed_cents: int | None = None,
    allocated_billed_usd: float | None = None,
    role: str = "t0_allocation",
) -> ReconciledLine:
    estimated = float(row.get("cost_usd") or 0)
    cost = float(estimated if cost_usd is None else cost_usd)
    billed = row.get("billed_cents") if billed_cents is None else billed_cents
    try:
        billed_i = int(billed) if billed is not None else None
    except (TypeError, ValueError):
        billed_i = None
    return ReconciledLine(
        vendor=str(row.get("vendor") or ""),
        person=str(row.get("person") or ""),
        cycle=str(row.get("cycle") or ""),
        source=str(row.get("source") or ""),
        project=row.get("project"),
        model=row.get("model"),
        occurred_at=str(row.get("occurred_at") or ""),
        message_id=str(row.get("message_id") or ""),
        request_id=str(row.get("request_id") or ""),
        input_tokens=int(row.get("input_tokens") or 0),
        output_tokens=int(row.get("output_tokens") or 0),
        cache_read_tokens=int(row.get("cache_read_tokens") or 0),
        cache_creation_tokens=int(row.get("cache_creation_tokens") or 0),
        cost_usd=round(estimated, 8),
        billed_cents=billed_i,
        tier=tier,
        origin_tier=str(row.get("tier") or "T0"),
        estimated_usd=round(estimated, 8),
        allocated_billed_usd=(
            None if allocated_billed_usd is None else round(float(allocated_billed_usd), 8)
        ),
        role=role,
    )


def _summarize(lines: list[ReconciledLine]) -> tuple[float, int | None, int, int]:
    cost = round(sum(line.estimated_usd for line in lines), 8)
    cents = [line.billed_cents for line in lines if line.billed_cents is not None]
    billed = sum(cents) if cents else None
    return (
        cost,
        billed,
        sum(line.input_tokens for line in lines),
        sum(line.output_tokens for line in lines),
    )


def _weights(events: list[dict[str, Any]]) -> list[int]:
    weights = [max(_row_tokens(row).total, 0) for row in events]
    if not weights:
        return []
    if sum(weights) <= 0:
        return [1] * len(events)
    return weights


def allocate_billed(events: list[dict[str, Any]], billed_cents: int, *, tier: str) -> list[ReconciledLine]:
    """Spread invoice/T1/T2 billed cents across T0 events by token share."""
    if not events:
        return []
    weights = _weights(events)
    total_w = sum(weights)
    remaining = int(billed_cents)
    out: list[ReconciledLine] = []
    for i, row in enumerate(events):
        if i == len(events) - 1:
            cents = remaining
        else:
            cents = int(round(billed_cents * (weights[i] / total_w)))
            remaining -= cents
        out.append(
            _line(
                row,
                tier=tier,
                billed_cents=cents,
                allocated_billed_usd=cents / 100.0,
                role="t0_allocation",
            )
        )
    return out


def allocate_snapshot(events: list[dict[str, Any]], snap: dict[str, Any]) -> list[ReconciledLine]:
    billed = snap.get("billed_cents")
    try:
        billed_i = int(billed) if billed is not None and billed != "" else None
    except (TypeError, ValueError):
        billed_i = None
    if billed_i is None:
        return [_line(row, tier="T1", role="t0_allocation") for row in events]
    return allocate_billed(events, billed_i, tier="T1")


def billed_truth(
    conn: sqlite3.Connection,
    vendor: str,
    person: str | None,
    cycle: str,
) -> BilledRow | None:
    """Invoice, else T2 billed events, else T1 snapshot. Never T0."""
    from ardoise import db

    person_key = person or ""
    invoices = db.list_invoices(conn, cycle=cycle, vendor=vendor, person=person_key)
    if invoices:
        cents = sum(int(row.get("usd_cents") or row.get("billed_cents") or 0) for row in invoices)
        note = next((str(row.get("notes") or "") for row in invoices if row.get("notes")), "")
        src = next((str(row.get("source") or "paste") for row in invoices), "paste")
        return BilledRow(
            vendor=vendor,
            person=person_key,
            cycle=cycle,
            billed_cents=cents,
            billed_usd=round(cents / 100.0, 6),
            tier="invoice",
            source=note or src or "paste",
            invoice_id=note or None,
        )

    t2 = _events(conn, vendor=vendor, person=person_key, cycle=cycle, tier="T2")
    t2_billed = []
    for row in t2:
        raw = row.get("billed_cents")
        if raw is None or raw == "":
            continue
        try:
            t2_billed.append(int(raw))
        except (TypeError, ValueError):
            continue
    if t2_billed:
        cents = sum(t2_billed)
        return BilledRow(
            vendor=vendor,
            person=person_key,
            cycle=cycle,
            billed_cents=cents,
            billed_usd=round(cents / 100.0, 6),
            tier="T2",
            source="T2 events",
        )

    snap = db.latest_snapshot(conn, vendor=vendor, person=person_key, cycle=cycle)
    if snap is not None and snap.get("billed_cents") not in (None, ""):
        try:
            cents = int(snap["billed_cents"])
        except (TypeError, ValueError):
            cents = None
        if cents is not None:
            return BilledRow(
                vendor=vendor,
                person=person_key,
                cycle=cycle,
                billed_cents=cents,
                billed_usd=round(cents / 100.0, 6),
                tier="T1",
                source="T1 snapshot",
            )
    return None


def reconcile(
    conn: sqlite3.Connection,
    vendor: str,
    person: str | None,
    cycle: str,
) -> ReconciledCycle:
    person_key = person or ""
    t0 = _events(conn, vendor=vendor, person=person_key, cycle=cycle, tier="T0")
    billed = billed_truth(conn, vendor, person_key, cycle)
    if billed is not None:
        lines = allocate_billed(t0, billed.billed_cents, tier=billed.tier)
        cost, _ignored, inn, out = _summarize(lines)
        return ReconciledCycle(
            vendor=vendor,
            person=person_key,
            cycle=cycle,
            preferred_tier=billed.tier,
            lines=lines,
            cost_usd=cost,
            billed_cents=billed.billed_cents,
            input_tokens=inn,
            output_tokens=out,
            note=f"{billed.tier} billed truth; T0 allocates only",
            billed=billed,
        )

    lines = [_line(row, tier="T0", role="t0_allocation") for row in t0]
    cost, _billed, inn, out = _summarize(lines)
    return ReconciledCycle(
        vendor=vendor,
        person=person_key,
        cycle=cycle,
        preferred_tier="T0",
        lines=lines,
        cost_usd=cost,
        billed_cents=None,
        input_tokens=inn,
        output_tokens=out,
        note="T0 allocate only; not billed truth",
        billed=None,
    )


def _cycle_keys(conn: sqlite3.Connection, month: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT DISTINCT vendor, person, cycle FROM events WHERE cycle = ?
        UNION
        SELECT DISTINCT vendor, person, cycle FROM snapshots WHERE cycle = ?
        UNION
        SELECT DISTINCT vendor, person, cycle FROM invoices WHERE cycle = ?
        ORDER BY 1, 2, 3
        """,
        (month, month, month),
    ).fetchall()


def reconcile_month(conn: sqlite3.Connection, month: str) -> list[ReconciledCycle]:
    return [
        reconcile(conn, str(row["vendor"]), str(row["person"] or ""), str(row["cycle"]))
        for row in _cycle_keys(conn, month)
    ]


def section_a(conn: sqlite3.Connection, month: str) -> list[dict[str, Any]]:
    """One vendor line per scope. Prefer invoice, else T2, else T1, else T0 estimated."""
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for rec in reconcile_month(conn, month):
        key = (rec.vendor, rec.person, rec.cycle)
        if key in seen:
            continue
        seen.add(key)
        if rec.billed is not None:
            item = rec.billed.as_dict()
            item["usd_cents"] = rec.billed.billed_cents
            item["tier_of_truth"] = rec.billed.tier
            item["invoice_grade"] = True
            rows.append(item)
            continue
        cents = int(round(float(rec.cost_usd) * 100))
        rows.append(
            {
                "vendor": rec.vendor,
                "person": rec.person,
                "cycle": rec.cycle,
                "billed_cents": cents,
                "usd_cents": cents,
                "billed_usd": round(float(rec.cost_usd), 6),
                "tier": "T0",
                "tier_of_truth": "T0",
                "source": "T0 estimated",
                "invoice_id": None,
                "invoice_grade": False,
            }
        )
    rows.sort(key=lambda row: (row.get("vendor") or "", row.get("person") or "", row.get("cycle") or ""))
    return rows


def flatten_month(conn: sqlite3.Connection, month: str) -> list[dict[str, Any]]:
    """T0 allocation lines (estimates + optional allocated billed)."""
    lines: list[dict[str, Any]] = []
    for rec in reconcile_month(conn, month):
        for line in rec.lines:
            item = line.as_dict()
            item["preferred_tier"] = rec.preferred_tier
            item["section"] = "T0_allocation"
            lines.append(item)
    lines.sort(key=lambda row: (row.get("occurred_at") or "", row.get("message_id") or ""))
    return lines
