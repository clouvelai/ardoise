"""Cursor vendor adapter — T0 transcripts; T2 pull stub."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

from ardoise import paths
from ardoise.adapters.hook_event import event_to_entry
from ardoise.privacy import scrub
from ardoise.vendors.anthropic import parse_t0_line
from ardoise.vendors.contract import (
    Capabilities,
    CredentialField,
    CredentialNotConfigured,
    CredentialSpec,
    Event,
    Snapshot,
    VendorTestResult,
    entry_to_event,
)
from ardoise.vendors.jsonl import iter_jsonl


def _person() -> str | None:
    raw = os.environ.get("ARDOISE_PERSON")
    return raw.strip() if raw and raw.strip() else None


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
        entry["vendor"] = "cursor"
        entry["tier"] = "T0"
        entry["person"] = _person() or ""
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
        entry["vendor"] = "cursor"
        entry["tier"] = "T0"
        entry["person"] = _person() or ""
    return entry


def iter_cursor(root: Path) -> Iterator[tuple[Path, dict[str, Any]]]:
    for path in discover_cursor_files(root):
        for obj in iter_jsonl(path):
            entry = parse_cursor_line(obj)
            if entry:
                yield path, entry


class CursorAdapter:
    name = "cursor"
    tools = ("cursor",)
    credential_spec = CredentialSpec(
        fields=(
            CredentialField(
                key="api_key",
                env="CURSOR_API_KEY",
                purpose="T2 usage event pull",
                optional=True,
            ),
        )
    )
    capabilities = Capabilities(
        capture="yes",
        snapshot="no",
        pull="stub",
        test="yes",
    )

    def capture(self, *, root: Path | None = None) -> Iterator[Event]:
        base = root or paths.cursor_root()
        for _path, entry in iter_cursor(base):
            yield entry_to_event(entry)

    def snapshot(self, *, person: str | None = None, cycle: str | None = None) -> Snapshot:
        raise CredentialNotConfigured(self.name, "T1 snapshot")

    def pull(self, *, person: str | None = None, cycle: str | None = None) -> Iterator[Event]:
        # Live Cursor usage API is out of scope. T0 capture does not call this.
        raise CredentialNotConfigured(self.name, "T2 pull")
        yield  # pragma: no cover — makes this a generator

    def test(self) -> VendorTestResult:
        from ardoise.vendors.creds import resolve_status

        status = resolve_status(self.credential_spec)
        resolved = any(item.present for item in status)
        return VendorTestResult(
            name=self.name,
            tools=self.tools,
            capabilities=self.capabilities,
            credentials=status,
            cred_resolved=resolved,
            ok=True,
            detail="T0 capture works without credentials. T2 pull is a stub.",
        )
