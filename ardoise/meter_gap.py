"""Honest meter-gap: roots scanned, no usage objects.

Never invents spend. Does not recommend Admin T2. Stdlib only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ardoise import db, paths, queue
from ardoise.adapters.cloud_agent import (
    _has_direct_usage,
    discover_transcript_files,
    iter_transcript_objects,
    transcript_roots,
)

KIND_PROMPT_ONLY = "prompt_only"
KIND_NO_LOGS = "no_logs"
PROMPT_ONLY_HINT = (
    "roots scanned, no usage objects — prompt-only trees stay empty "
    "until a usage-shaped export or hook lands"
)
NO_LOGS_HINT = "no local logs found to ingest"
USAGE_NAMES = frozenset({"usage.json", "usage.jsonl"})


def persist_scan(conn: Any, totals: dict[str, Any]) -> dict[str, Any]:
    """Store the last backfill scan so status can describe a prompt-only gap."""
    payload = {
        "files": int(totals.get("files") or 0),
        "transcript_files": int(totals.get("transcript_files") or 0),
        "cursor_files": int(totals.get("cursor_files") or 0),
        "claude_files": int(totals.get("claude_files") or 0),
        "inserted": int(totals.get("inserted") or 0),
        "updated": int(totals.get("updated") or 0),
    }
    payload["usage_rows"] = payload["inserted"] + payload["updated"]
    db.set_sync_state(
        conn,
        vendor="ardoise",
        kind="meter_gap",
        cursor=json.dumps(payload, separators=(",", ":"), ensure_ascii=True),
        ok=True,
    )
    return payload


def load_scan(conn: Any) -> dict[str, Any]:
    row = db.get_sync_state(conn, vendor="ardoise", kind="meter_gap")
    if not row or not row.get("cursor"):
        return {}
    try:
        data = json.loads(str(row["cursor"]))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _file_has_usage(path: Path) -> bool:
    try:
        for obj in iter_transcript_objects(path):
            if _has_direct_usage(obj):
                return True
    except (OSError, TypeError, ValueError):
        return False
    return False


def probe_usage_paths(*, config: dict[str, Any] | None = None) -> dict[str, int]:
    """Count usage.json / hook-queue files. Read-only; never inserts."""
    found = 0
    shaped = 0
    try:
        roots = transcript_roots(config=config)
    except (OSError, TypeError):
        roots = []
    for root in roots:
        try:
            files = discover_transcript_files(root)
        except OSError:
            continue
        for path in files:
            if path.name.lower() not in USAGE_NAMES:
                continue
            found += 1
            if _file_has_usage(path):
                shaped += 1
    hook_queue = 0
    try:
        hook_queue = sum(1 for _ in queue.iter_queue(paths.queue_dir()))
    except OSError:
        hook_queue = 0
    return {
        "usage_json": found,
        "usage_shaped": shaped,
        "hook_queue": hook_queue,
    }


def describe(
    *,
    scan: dict[str, Any] | None,
    backfilled: bool,
    month_cost: float,
    probe: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Structured gap for ``status --json``. Null kind when spend already landed."""
    scan = scan or {}
    probe = probe or {}
    files = int(scan.get("files") or 0)
    usage_rows = int(scan.get("usage_rows") or 0)
    usage_json = int(probe.get("usage_json") or 0)
    usage_shaped = int(probe.get("usage_shaped") or 0)
    hook_queue = int(probe.get("hook_queue") or 0)
    scanned = bool(backfilled or files or usage_json)
    kind = None
    hint = ""
    if float(month_cost or 0) > 0 or usage_rows > 0 or usage_shaped > 0:
        kind = None
    elif files > 0 or (usage_json and usage_shaped == 0):
        kind = KIND_PROMPT_ONLY
        hint = PROMPT_ONLY_HINT
    elif backfilled:
        kind = KIND_NO_LOGS
        hint = NO_LOGS_HINT
    return {
        "kind": kind,
        "scanned": scanned,
        "files": files,
        "usage_rows": usage_rows,
        "usage_json": usage_json,
        "usage_shaped": usage_shaped,
        "hook_queue": hook_queue,
        "hint": hint,
    }


def note_for(gap: dict[str, Any] | None) -> str | None:
    """Soft status note when roots were scanned but no usage landed."""
    if not gap or gap.get("kind") != KIND_PROMPT_ONLY:
        return None
    return str(gap.get("hint") or PROMPT_ONLY_HINT)
