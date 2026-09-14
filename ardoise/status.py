"""Ledger status (human + JSON).

`cost_usd` remains the T0 list-price estimate (Phase 1). Billed truth lives
in `section_a` / `billed_usd` (invoice / T1 / T2 only).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ardoise import anomaly, attribution, budget, config as config_mod, db, paths, reconcile, roster


def _month_bounds(month: str) -> tuple[str, str]:
    year, mon = month.split("-", 1)
    y, m = int(year), int(mon)
    start = f"{y:04d}-{m:02d}-01T00:00:00Z"
    if m == 12:
        end = f"{y + 1:04d}-01-01T00:00:00Z"
    else:
        end = f"{y:04d}-{m + 1:02d}-01T00:00:00Z"
    return start, end


def _capture_ran(conn) -> bool:
    """True after a backfill/capture pass, even when no usage rows landed."""
    row = conn.execute(
        "SELECT 1 FROM sync_state WHERE kind = 'capture' LIMIT 1"
    ).fetchone()
    if row:
        return True
    src = conn.execute("SELECT 1 FROM sources LIMIT 1").fetchone()
    return bool(src)


def current_month(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    return stamp.strftime("%Y-%m")


def _latest_month(conn) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT substr(occurred_at, 1, 7) AS month,
               COUNT(*) AS n,
               COALESCE(SUM(cost_usd), 0) AS usd
        FROM events
        WHERE occurred_at IS NOT NULL AND occurred_at != ''
        GROUP BY 1
        ORDER BY 1 DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None or not row["month"]:
        return None
    return {
        "month": str(row["month"]),
        "entries": int(row["n"] or 0),
        "cost_usd": round(float(row["usd"] or 0), 6),
    }


def _group(
    rows: list[dict[str, Any]],
    column: str,
    *,
    missing: str = "(none)",
) -> list[dict[str, Any]]:
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


def summarize(month: str | None = None, *, person: str | None = None) -> dict[str, Any]:
    month = month or current_month()
    paths.ensure_home()
    cfg = config_mod.load()
    with db.session() as conn:
        total_rows = db.count_entries(conn)
        lines = reconcile.flatten_month(conn, month)
        section_a = reconcile.section_a(conn, month)
        cycles = [item.as_dict() for item in reconcile.reconcile_month(conn, month)]
        members = roster.collect(conn, month=month, config=cfg)
        named_agents = roster.collect_agents(conn, month=month)
        filt = roster.resolve(person, roster=members, agents=named_agents)
        if filt:
            lines = roster.apply_rows(lines, filt)
            section_a = roster.apply_rows(section_a, filt)
            cycles = roster.apply_rows(cycles, filt)
        # Day-spike heuristics stay org-wide; skip them on a seat view.
        anomalies = anomaly.scan(
            None if filt else conn,
            month=month,
            lines=lines,
            config=cfg,
        )
        latest = _latest_month(conn) if int(total_rows or 0) else None
        backfilled = _capture_ran(conn)

    estimated = round(sum(float(row.get("estimated_usd") or row.get("cost_usd") or 0) for row in lines), 6)
    billed_usd = round(
        sum(float(row.get("billed_usd") or 0) for row in section_a if row.get("invoice_grade")),
        6,
    )
    data = {
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
        "by_project": _group(lines, "project", missing="unmapped"),
        "by_person": _group(lines, "person"),
        "by_source": _group(lines, "source"),
        "by_model": _group(lines, "model"),
        "by_tier": _group(lines, "origin_tier"),
        "by_vendor": _group(lines, "vendor"),
        "by_agent": _group(lines, "agent", missing=attribution.UNATTRIBUTED),
        "by_skill": _group(lines, "skill", missing=attribution.UNATTRIBUTED),
        "by_effort": _group(lines, "effort", missing=attribution.UNATTRIBUTED),
        "lines": lines,
        "section_a": section_a,
        "reconciled": [
            {k: v for k, v in item.items() if k != "lines"}
            for item in cycles
        ],
        "anomalies": anomalies,
        "roster": members,
        "agents": named_agents,
        "filter": filt,
        "latest_month": latest,
        "backfilled": backfilled,
    }
    data["budgets"] = budget.evaluate(data, cfg)
    notes: list[str] = []
    if cfg.get("load_error"):
        notes.append(str(cfg["load_error"]))
    notes.extend(budget.notes_from(data["budgets"]))
    notes.extend(str(item.get("note") or "") for item in anomalies if item.get("note"))
    filter_note = roster.note_for(filt, matched_rows=len(section_a) + len(lines))
    if filter_note:
        notes.append(filter_note)
    cursor_join = sum(
        1
        for row in lines
        if str(row.get("vendor") or "") == "cursor"
        and int(row.get("input_tokens") or 0) == 0
        and int(row.get("output_tokens") or 0) == 0
        and float(row.get("estimated_usd") or row.get("cost_usd") or 0) == 0
    )
    data["cursor_join_sessions"] = cursor_join
    if cursor_join:
        notes.append(
            f"Cursor: {cursor_join} session(s), $0 — Team Admin or usage-shaped "
            "events needed for cents"
        )
    data["notes"] = [item for item in notes if item]
    return data


def render_text(data: dict[str, Any]) -> str:
    billed = data.get("billed_usd")
    section_a = data.get("section_a") or []
    if any(row.get("invoice_grade") for row in section_a):
        billed_line = f"billed    ${float(billed or 0):.2f}  (invoice / T1 / T2)"
    else:
        billed_line = "billed    (none)  — invoice add (Free); T2 is Team/Enterprise"
    filt = data.get("filter") or {}
    roster_rows = data.get("roster") or []
    header = [
        f"Ardoise  {data['month']}",
        f"ledger   {data['ledger']}",
        f"entries  {data['month_entries']} this month / {data['entries']} total",
        billed_line,
        f"estimated ${data['cost_usd']:.4f}  (T0 allocate only — not billed)",
        f"tokens   in={data['input_tokens']} out={data['output_tokens']} "
        f"cache_read={data['cache_read_tokens']} cache_write={data['cache_creation_tokens']}",
    ]
    chips = attribution.spend_chips(data)
    if filt:
        label = roster.display(filt.get("canonical") or filt.get("query"))
        extra = ""
        if filt.get("kind") == "agent" and chips:
            extra = f"  ${float(chips[0].get('cost_usd') or 0):.4f}"
        header.append(f"filter   {label}{extra}  (view only — ledger unchanged)")
    else:
        if len(roster_rows) > 1:
            names = [roster.display(row.get("person")) for row in roster_rows]
            header.append("roster   " + ", ".join(names))
        if chips:
            header.append("agents   " + ", ".join(attribution.chip_text(row) for row in chips))
    lines = header + ["", "section A — vendor lines"]
    if not section_a:
        lines.append("  (empty)")
    for row in section_a:
        usd = float(row.get("billed_usd") or 0)
        tier = row.get("tier_of_truth") or row.get("tier") or "T0"
        fmt = f"${usd:.2f}" if row.get("invoice_grade") else f"${usd:.4f}"
        person = str(row.get("person") or "").strip()
        scope = f"  {person}" if person else ""
        lines.append(f"  {str(row.get('vendor') or ''):<16} {fmt}  {tier}  {row.get('source')}{scope}")
    people = data.get("by_person") or []
    if filt or len(people) > 1:
        lines.append("by person (T0 allocation)")
        if not people:
            lines.append("  (empty)")
        for row in people:
            label = roster.display(row.get("person"))
            lines.append(
                f"  {label:<32} est=${row['cost_usd']:.4f}  n={row['entries']}  T0"
            )
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
    models = data.get("by_model") or []
    if models:
        lines.append("by model (T0 allocation)")
        shown = models[:8]
        for row in shown:
            lines.append(
                f"  {str(row.get('model') or ''):<32} est=${row['cost_usd']:.4f}  n={row['entries']}  T0"
            )
        extra = len(models) - len(shown)
        if extra > 0:
            lines.append(f"  … {extra} more")
    if attribution.any_present(data):
        lines.append("attribution (when present)")
        for dim in attribution.DIMENSIONS:
            rows = attribution.present(data.get(f"by_{dim}"), dim)
            extra = 0
            if len(rows) > 8:
                extra = len(rows) - 8
                rows = rows[:8]
            for row in rows:
                lines.append(
                    f"  {dim:<8} {str(row[dim]):<24} "
                    f"est=${row['cost_usd']:.4f}  n={row['entries']}"
                )
            if extra:
                lines.append(f"  {dim:<8} … {extra} more")
    budgets = data.get("budgets") or {}
    if budgets.get("configured"):
        lines.append("soft caps (warn only — never blocks)")
        for row in budgets.get("checks") or []:
            flag = "  OVER" if row.get("over") else ""
            scope = str(row.get("scope") or "(default)")
            pct = row.get("pct")
            pct_txt = f"{pct:.0f}%" if pct is not None else "—"
            lines.append(
                f"  {str(row.get('kind') or ''):<8} {scope:<24} "
                f"${float(row.get('spent_usd') or 0):.2f} / "
                f"${float(row.get('cap_usd') or 0):.2f}  {pct_txt}{flag}"
            )
    notes = data.get("notes") or []
    if notes:
        lines.append("notes (soft)")
        for note in notes:
            lines.append(f"  {note}")
    if int(data.get("entries") or 0) == 0:
        if data.get("backfilled"):
            lines.extend(
                [
                    "",
                    "ledger is empty — already backfilled, no usage rows",
                    "  prompt-only trees stay empty until a usage-shaped export or hook lands",
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "ledger is empty — ingest local Claude Code / Cursor logs:",
                    "  ardoise backfill",
                    "  ardoise status",
                ]
            )
    else:
        latest = data.get("latest_month") or {}
        latest_month = str(latest.get("month") or "")
        if int(data.get("month_entries") or 0) == 0 and latest_month and latest_month != data.get("month"):
            lines.extend(
                [
                    "",
                    f"this month is empty. latest T0 activity is {latest_month}  "
                    f"est=${float(latest.get('cost_usd') or 0):.2f}  n={int(latest.get('entries') or 0)}",
                    f"  ardoise status --month {latest_month}",
                ]
            )
    return "\n".join(lines) + "\n"
