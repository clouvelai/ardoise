"""Ingest hook queue, stdin events, and optional transcript files."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from ardoise import db, paths, queue
from ardoise.adapters.anthropic_t0 import iter_jsonl, parse_t0_line
from ardoise.adapters.cursor import parse_cursor_line
from ardoise.adapters.hook_event import event_to_entry
from ardoise.project import infer_project


def _ingest_entry(conn, entry: dict[str, Any]) -> str:
    if not entry.get("occurred_at"):
        from datetime import datetime, timezone

        entry["occurred_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not entry.get("project"):
        entry["project"] = infer_project(cwd=entry.get("cwd"))
    return db.upsert_entry(conn, entry)


def _maybe_t1_snapshot(raw: dict[str, Any]) -> None:
    """SessionStart (and aliases) trigger an Anthropic T1 snapshot when wired to capture."""
    name = str(
        raw.get("hook_event_name")
        or raw.get("hook_event")
        or raw.get("event")
        or ""
    )
    if name not in {"SessionStart", "sessionStart"}:
        return
    try:
        from ardoise.snapshot import record_vendor_snapshot

        record_vendor_snapshot("anthropic", from_hook=True, cwd=raw.get("cwd"))
    except Exception:
        return


def ingest_event(conn, raw: dict[str, Any], *, default_source: str = "hook") -> dict[str, int]:
    _maybe_t1_snapshot(raw)
    counts = {"inserted": 0, "updated": 0, "skipped": 0, "empty": 0}
    entry = event_to_entry(raw, default_source=default_source)
    transcript = raw.get("transcript_path") or raw.get("transcriptPath")
    if entry:
        kind = _ingest_entry(conn, entry)
        counts[kind] = counts.get(kind, 0) + 1
    elif not transcript:
        counts["empty"] += 1

    if transcript:
        tpath = Path(str(transcript)).expanduser()
        if tpath.is_file():
            extra = ingest_transcript(conn, tpath)
            for key, value in extra.items():
                counts[key] = counts.get(key, 0) + value
    return counts


def ingest_transcript(conn, path: Path) -> dict[str, int]:
    counts = {"inserted": 0, "updated": 0, "skipped": 0, "empty": 0}
    try:
        stat = path.stat()
    except OSError:
        counts["empty"] += 1
        return counts
    if db.source_unchanged(conn, path, bytes_=stat.st_size, mtime=stat.st_mtime):
        return counts
    for obj in iter_jsonl(path):
        entry = parse_t0_line(obj) or parse_cursor_line(obj)
        if not entry:
            continue
        kind = _ingest_entry(conn, entry)
        counts[kind] = counts.get(kind, 0) + 1
    db.mark_source(conn, path, bytes_=stat.st_size, mtime=stat.st_mtime)
    return counts


def drain_queue(conn, directory: Path | None = None) -> dict[str, int]:
    totals = {"inserted": 0, "updated": 0, "skipped": 0, "empty": 0, "files": 0}
    for path, obj in queue.iter_queue(directory):
        totals["files"] += 1
        source = str(obj.get("source") or "hook")
        if "cursor" in source.lower():
            default = "cursor"
        elif "anthropic" in source.lower() or "claude" in source.lower():
            default = "anthropic_t0"
        else:
            default = "hook"
        part = ingest_event(conn, obj, default_source=default)
        for key, value in part.items():
            totals[key] = totals.get(key, 0) + value
        queue.remove(path)
    return totals


def capture_stdin(stream: TextIO | None = None) -> dict[str, int]:
    raw_text = (stream or sys.stdin).read()
    if not raw_text.strip():
        return {"inserted": 0, "updated": 0, "skipped": 0, "empty": 1, "files": 0}
    try:
        obj = json.loads(raw_text)
    except json.JSONDecodeError:
        return {"inserted": 0, "updated": 0, "skipped": 0, "empty": 1, "files": 0}
    if not isinstance(obj, dict):
        return {"inserted": 0, "updated": 0, "skipped": 0, "empty": 1, "files": 0}
    queue.enqueue(obj)
    with db.session() as conn:
        return drain_queue(conn)


def capture(*, stdin: bool = False, queue_path: Path | None = None) -> dict[str, int]:
    paths.ensure_home()
    if stdin:
        return capture_stdin()
    with db.session() as conn:
        return drain_queue(conn, queue_path)
