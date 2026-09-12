"""Cursor transcripts + hook-shaped JSONL (usage only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from ardoise.adapters.anthropic_t0 import iter_jsonl, parse_t0_line
from ardoise.adapters.hook_event import event_to_entry
from ardoise.privacy import scrub


def discover_cursor_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for pattern in (
        "projects/**/*.jsonl",
        "ai-tracking/**/*.jsonl",
        "chats/**/*.jsonl",
        "transcripts/**/*.jsonl",
        "**/*transcript*.jsonl",
    ):
        files.extend(p for p in root.glob(pattern) if p.is_file())
    # Deduplicate while preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for path in files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(path)
    return out


def parse_cursor_line(obj: dict[str, Any]) -> dict[str, Any] | None:
    # Cursor sometimes mirrors Anthropic T0; otherwise accept hook-shaped usage.
    entry = parse_t0_line(obj)
    if entry:
        entry["source"] = "cursor"
        return entry
    safe = scrub(obj)
    if isinstance(obj.get("usage"), dict):
        safe["usage"] = obj["usage"]
    if obj.get("model"):
        safe["model"] = obj.get("model")
    if obj.get("requestId") or obj.get("request_id"):
        safe["requestId"] = obj.get("requestId") or obj.get("request_id")
    if obj.get("message_id") or (isinstance(obj.get("message"), dict) and obj["message"].get("id")):
        safe["message_id"] = obj.get("message_id") or obj["message"]["id"]
    entry = event_to_entry(safe, default_source="cursor")
    if entry:
        entry["source"] = "cursor"
    return entry


def iter_cursor(root: Path) -> Iterator[tuple[Path, dict[str, Any]]]:
    for path in discover_cursor_files(root):
        for obj in iter_jsonl(path):
            entry = parse_cursor_line(obj)
            if entry:
                yield path, entry
