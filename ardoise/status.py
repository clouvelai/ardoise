"""Ledger status (human + JSON)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ardoise import db, paths


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


def summarize(month: str | None = None) -> dict[str, Any]:
    month = month or current_month()
    start, end = _month_bounds(month)
    paths.ensure_home()
    with db.session() as conn:
        total_rows = db.count_entries(conn)
        month_rows = conn.execute(
            """
            SELECT COUNT(*) AS n,
                   COALESCE(SUM(cost_usd), 0) AS cost,
                   COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(cache_read_tokens), 0) AS cache_read_tokens,
                   COALESCE(SUM(cache_creation_tokens), 0) AS cache_creation_tokens
            FROM entries
            WHERE occurred_at >= ? AND occurred_at < ?
            """,
            (start, end),
        ).fetchone()

        def group(column: str) -> list[dict[str, Any]]:
            rows = conn.execute(
                f"""
                SELECT COALESCE({column}, '(none)') AS key,
                       COUNT(*) AS n,
                       COALESCE(SUM(cost_usd), 0) AS cost,
                       COALESCE(SUM(input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(output_tokens), 0) AS output_tokens
                FROM entries
                WHERE occurred_at >= ? AND occurred_at < ?
                GROUP BY 1
                ORDER BY cost DESC, n DESC
                """,
                (start, end),
            ).fetchall()
            return [
                {
                    column: r["key"],
                    "entries": int(r["n"]),
                    "cost_usd": round(float(r["cost"]), 6),
                    "input_tokens": int(r["input_tokens"]),
                    "output_tokens": int(r["output_tokens"]),
                }
                for r in rows
            ]

        return {
            "ok": True,
            "ledger": str(paths.ledger_path()),
            "home": str(paths.ardoise_home()),
            "entries": total_rows,
            "month": month,
            "month_entries": int(month_rows["n"]),
            "cost_usd": round(float(month_rows["cost"]), 6),
            "input_tokens": int(month_rows["input_tokens"]),
            "output_tokens": int(month_rows["output_tokens"]),
            "cache_read_tokens": int(month_rows["cache_read_tokens"]),
            "cache_creation_tokens": int(month_rows["cache_creation_tokens"]),
            "by_project": group("project"),
            "by_source": group("source"),
            "by_model": group("model"),
        }


def render_text(data: dict[str, Any]) -> str:
    lines = [
        f"Ardoise  {data['month']}",
        f"ledger   {data['ledger']}",
        f"entries  {data['month_entries']} this month / {data['entries']} total",
        f"spend    ${data['cost_usd']:.4f}",
        f"tokens   in={data['input_tokens']} out={data['output_tokens']} "
        f"cache_read={data['cache_read_tokens']} cache_write={data['cache_creation_tokens']}",
        "",
        "by project",
    ]
    if not data["by_project"]:
        lines.append("  (empty)")
    for row in data["by_project"]:
        lines.append(
            f"  {row['project']:<32} ${row['cost_usd']:.4f}  n={row['entries']}"
        )
    lines.append("by source")
    for row in data["by_source"]:
        lines.append(
            f"  {row['source']:<32} ${row['cost_usd']:.4f}  n={row['entries']}"
        )
    return "\n".join(lines) + "\n"
