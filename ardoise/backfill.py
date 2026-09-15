"""Scan local Claude / Cursor logs into the ledger."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

from ardoise import config as config_mod, db, paths
from ardoise.adapters.cloud_agent import (
    discover_transcript_files,
    iter_transcript_objects,
    parse_line as parse_cloud_line,
    sidecar_meta,
    transcript_roots,
)
from ardoise.capture import drain_queue
from ardoise.project import (
    clear_project_cache,
    infer_project,
    without_process_cwd,
)
from ardoise.vendors.anthropic import discover_t0_files, parse_t0_line
from ardoise.vendors.cursor import discover_cursor_files, parse_cursor_line
from ardoise.vendors.jsonl import iter_jsonl

Progress = Callable[[int, int, Path, dict[str, int]], None]
COMMIT_EVERY = 25


def _touch_project(entry: dict) -> None:
    if not entry.get("project"):
        entry["project"] = infer_project(cwd=entry.get("cwd"), allow_process_cwd=False)


def _ingest_file(
    conn: Any,
    path: Path,
    parse_line: Callable[[dict[str, Any]], dict[str, Any] | None],
    totals: dict[str, int],
    *,
    force: bool,
) -> None:
    try:
        stat = path.stat()
    except OSError:
        return
    if not force and db.source_unchanged(conn, path, bytes_=stat.st_size, mtime=stat.st_mtime):
        totals["skipped_files"] = totals.get("skipped_files", 0) + 1
        return
    for obj in iter_jsonl(path):
        entry = parse_line(obj)
        if not entry:
            continue
        _touch_project(entry)
        kind = db.upsert_entry(conn, entry)
        totals[kind] = totals.get(kind, 0) + 1
    db.mark_source(conn, path, bytes_=stat.st_size, mtime=stat.st_mtime)
    totals["files"] = totals.get("files", 0) + 1


def _ingest_transcript_file(
    conn: Any,
    path: Path,
    totals: dict[str, int],
    *,
    force: bool,
) -> None:
    try:
        stat = path.stat()
    except OSError:
        return
    if not force and db.source_unchanged(conn, path, bytes_=stat.st_size, mtime=stat.st_mtime):
        totals["skipped_files"] = totals.get("skipped_files", 0) + 1
        return
    inherited = sidecar_meta(path)
    for obj in iter_transcript_objects(path):
        entry = parse_cloud_line(obj, inherited=inherited)
        if not entry:
            continue
        _touch_project(entry)
        kind = db.upsert_entry(conn, entry)
        totals[kind] = totals.get(kind, 0) + 1
    db.mark_source(conn, path, bytes_=stat.st_size, mtime=stat.st_mtime)
    totals["files"] = totals.get("files", 0) + 1


def backfill(
    *,
    claude: Path | None = None,
    cursor: Path | None = None,
    transcripts: Path | list[Path] | None = None,
    force: bool = False,
    progress: Progress | None = None,
) -> dict[str, Any]:
    paths.ensure_home()
    clear_project_cache()
    totals = {
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "empty": 0,
        "files": 0,
        "claude_files": 0,
        "cursor_files": 0,
        "transcript_files": 0,
        "skipped_files": 0,
    }
    claude_root = claude or paths.claude_root()
    cursor_root = cursor or paths.cursor_root()
    extra: list[Path] = []
    if transcripts is None:
        extra = []
    elif isinstance(transcripts, (list, tuple)):
        extra = [Path(item) for item in transcripts]
    else:
        extra = [Path(transcripts)]
    cfg = config_mod.load()
    roots = transcript_roots(extra=extra, config=cfg)
    jobs: list[tuple[str, Path, Callable | None]] = [
        ("anthropic", path, parse_t0_line) for path in discover_t0_files(claude_root)
    ]
    jobs.extend(("cursor", path, parse_cursor_line) for path in discover_cursor_files(cursor_root))
    jobs.extend(
        ("cloud_agent", path, None)
        for root in roots
        for path in discover_transcript_files(root)
    )
    n = len(jobs)

    with db.session() as conn, without_process_cwd():
        prior = conn.execute(
            "SELECT 1 FROM sync_state WHERE kind = 'capture' LIMIT 1"
        ).fetchone()
        totals["prior_capture"] = bool(prior)
        since_commit = 0
        for i, (vendor, path, parse_line) in enumerate(jobs, 1):
            if vendor == "cloud_agent":
                _ingest_transcript_file(conn, path, totals, force=force)
                totals["transcript_files"] += 1
            else:
                _ingest_file(conn, path, parse_line, totals, force=force)
                if vendor == "anthropic":
                    totals["claude_files"] += 1
                else:
                    totals["cursor_files"] += 1
            since_commit += 1
            if since_commit >= COMMIT_EVERY:
                conn.commit()
                since_commit = 0
            if progress is not None:
                progress(i, n, path, totals)

        queued = drain_queue(conn)
        for key, value in queued.items():
            if key == "files":
                totals["files"] += value
            else:
                totals[key] = totals.get(key, 0) + value

        db.set_sync_state(conn, vendor="anthropic", kind="capture", ok=True)
        db.set_sync_state(conn, vendor="cursor", kind="capture", ok=True)

    return totals


def empty_ledger_tip(totals: dict[str, Any], *, prior_capture: bool | None = None) -> str | None:
    """Text tip when backfill wrote no usage rows.

    Distinguishes already-ingested prompt-only trees from a first run
    that never found local logs. Returns None when rows were written.
    """
    if int(totals.get("inserted") or 0) or int(totals.get("updated") or 0):
        return None
    skipped_files = int(totals.get("skipped_files") or 0)
    files = int(totals.get("files") or 0)
    if prior_capture is None:
        prior_capture = bool(totals.get("prior_capture"))
    if skipped_files or prior_capture:
        return "already backfilled, no usage rows"
    if files:
        return (
            "no usage rows in scanned logs (prompt-only trees stay empty; "
            "drop usage-shaped JSON in ~/.ardoise/transcripts)"
        )
    return "no local logs found to ingest"


def tty_progress(i: int, n: int, path: Path, totals: dict[str, int]) -> None:
    sys.stderr.write(
        f"\rbackfill {i}/{n}  inserted={totals.get('inserted', 0)}  "
        f"skipped_files={totals.get('skipped_files', 0)}  {path.name[:48]}"
    )
    sys.stderr.flush()
