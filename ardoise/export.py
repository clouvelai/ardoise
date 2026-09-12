"""Export ledger rows as JSONL (usage only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO

from ardoise import db, paths
from ardoise.status import _month_bounds


def export_rows(month: str | None = None) -> list[dict[str, Any]]:
    paths.ensure_home()
    sql = """
        SELECT source, message_id, request_id, project, model, occurred_at,
               input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
               cache_creation_5m_tokens, cache_creation_1h_tokens, cost_usd,
               session_id
        FROM entries
    """
    args: tuple = ()
    if month:
        start, end = _month_bounds(month)
        sql += " WHERE occurred_at >= ? AND occurred_at < ?"
        args = (start, end)
    sql += " ORDER BY occurred_at ASC, id ASC"
    with db.session() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def write_export(out: Path | TextIO | None = None, *, month: str | None = None) -> int:
    rows = export_rows(month)
    close = False
    if out is None:
        import sys

        stream: TextIO = sys.stdout
    elif isinstance(out, Path):
        out.parent.mkdir(parents=True, exist_ok=True)
        stream = out.open("w", encoding="utf-8")
        close = True
    else:
        stream = out
    try:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=True, separators=(",", ":")) + "\n")
    finally:
        if close:
            stream.close()
    return len(rows)
