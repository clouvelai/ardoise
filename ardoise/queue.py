"""Shared on-disk hook queue (~/.ardoise/queue)."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Iterator

from ardoise import paths
from ardoise.privacy import usage_only_event


def enqueue(event: dict[str, Any], *, directory: Path | None = None) -> Path:
    dest = directory or paths.queue_dir()
    dest.mkdir(parents=True, exist_ok=True)
    # Whitelist usage + ids. Do not persist the raw event.
    safe = usage_only_event(event if isinstance(event, dict) else {})
    name = f"{uuid.uuid4().hex}.json"
    tmp = dest / f".{name}.tmp"
    final = dest / name
    tmp.write_text(json.dumps(safe, separators=(",", ":"), ensure_ascii=True) + "\n", encoding="utf-8")
    os.replace(tmp, final)
    return final


def iter_queue(directory: Path | None = None) -> Iterator[tuple[Path, dict[str, Any]]]:
    dest = directory or paths.queue_dir()
    if not dest.exists():
        return
    for path in sorted(dest.glob("*.json")):
        if path.name.startswith("."):
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict):
            yield path, obj


def remove(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass
