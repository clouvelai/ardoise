"""Scan local Claude / Cursor logs into the ledger."""

from __future__ import annotations

from pathlib import Path

from ardoise import db, paths
from ardoise.capture import drain_queue
from ardoise.project import infer_project
from ardoise.vendors.anthropic import iter_anthropic_t0
from ardoise.vendors.cursor import iter_cursor


def _touch_project(entry: dict) -> None:
    if not entry.get("project"):
        entry["project"] = infer_project(cwd=entry.get("cwd"))


def backfill(
    *,
    claude: Path | None = None,
    cursor: Path | None = None,
    force: bool = False,
) -> dict[str, int]:
    paths.ensure_home()
    totals = {
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "empty": 0,
        "files": 0,
        "claude_files": 0,
        "cursor_files": 0,
    }
    claude_root = claude or paths.claude_root()
    cursor_root = cursor or paths.cursor_root()

    with db.session() as conn:
        seen_claude: set[Path] = set()
        for path, entry in iter_anthropic_t0(claude_root):
            seen_claude.add(path)
            _touch_project(entry)
            kind = db.upsert_entry(conn, entry)
            totals[kind] = totals.get(kind, 0) + 1
        for path in seen_claude:
            totals["claude_files"] += 1
            totals["files"] += 1
            try:
                stat = path.stat()
                db.mark_source(conn, path, bytes_=stat.st_size, mtime=stat.st_mtime)
            except OSError:
                pass

        seen_cursor: set[Path] = set()
        for path, entry in iter_cursor(cursor_root):
            seen_cursor.add(path)
            _touch_project(entry)
            kind = db.upsert_entry(conn, entry)
            totals[kind] = totals.get(kind, 0) + 1
        for path in seen_cursor:
            totals["cursor_files"] += 1
            totals["files"] += 1
            try:
                stat = path.stat()
                db.mark_source(conn, path, bytes_=stat.st_size, mtime=stat.st_mtime)
            except OSError:
                pass

        queued = drain_queue(conn)
        for key, value in queued.items():
            if key == "files":
                totals["files"] += value
            else:
                totals[key] = totals.get(key, 0) + value

        db.set_sync_state(conn, vendor="anthropic", kind="capture", ok=True)
        db.set_sync_state(conn, vendor="cursor", kind="capture", ok=True)

    return totals
