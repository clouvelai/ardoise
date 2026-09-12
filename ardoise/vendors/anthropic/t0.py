"""Anthropic T0 Claude Code JSONL — no credentials required."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

from ardoise.adapters.hook_event import event_to_entry
from ardoise.privacy import scrub
from ardoise.vendors.jsonl import iter_jsonl


def _person() -> str | None:
    raw = os.environ.get("ARDOISE_PERSON")
    return raw.strip() if raw and raw.strip() else None


def looks_like_t0(obj: dict[str, Any]) -> bool:
    if obj.get("type") in {"assistant", "progress"}:
        return True
    message = obj.get("message")
    if isinstance(message, dict) and isinstance(message.get("usage"), dict):
        return True
    return isinstance(obj.get("usage"), dict) and bool(obj.get("requestId") or obj.get("request_id"))


def parse_t0_line(obj: dict[str, Any]) -> dict[str, Any] | None:
    if not looks_like_t0(obj):
        return None
    safe = scrub(obj)
    message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
    if message:
        safe["message"] = {
            "id": message.get("id"),
            "model": message.get("model"),
            "role": message.get("role"),
            "usage": message.get("usage") if isinstance(message.get("usage"), dict) else {},
        }
    if "usage" in obj and isinstance(obj["usage"], dict):
        safe["usage"] = obj["usage"]
    entry = event_to_entry(safe, default_source="anthropic_t0")
    if entry:
        entry["vendor"] = "anthropic"
        entry["tier"] = "T0"
        entry["person"] = _person() or ""
        if not entry.get("cwd") and obj.get("cwd"):
            entry["cwd"] = obj.get("cwd")
    return entry


def discover_t0_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    projects = root / "projects"
    search_roots = [projects if projects.is_dir() else root]
    for base in search_roots:
        if not base.exists():
            continue
        for path in base.rglob("*.jsonl"):
            if path.is_file():
                files.append(path)
    return sorted(files)


def iter_anthropic_t0(root: Path) -> Iterator[tuple[Path, dict[str, Any]]]:
    for path in discover_t0_files(root):
        for obj in iter_jsonl(path):
            entry = parse_t0_line(obj)
            if entry:
                yield path, entry
