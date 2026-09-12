"""Anthropic vendor adapter — T0 Claude Code JSONL; T1 snapshot stub."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

from ardoise import paths
from ardoise.adapters.hook_event import event_to_entry
from ardoise.privacy import scrub
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
    # Never pass message bodies into the ledger path.
    safe = scrub(obj)
    # Restore usage + ids that scrub() may have dropped with key "message".
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


class AnthropicAdapter:
    name = "anthropic"
    tools = ("claude-code",)
    credential_spec = CredentialSpec(
        fields=(
            CredentialField(
                key="admin_api_key",
                env="ANTHROPIC_ADMIN_API_KEY",
                purpose="T1 usage snapshot",
                optional=True,
            ),
        )
    )
    capabilities = Capabilities(
        capture="yes",
        snapshot="stub",
        pull="no",
        test="yes",
    )

    def capture(self, *, root: Path | None = None) -> Iterator[Event]:
        base = root or paths.claude_root()
        for _path, entry in iter_anthropic_t0(base):
            yield entry_to_event(entry)

    def snapshot(self, *, person: str | None = None, cycle: str | None = None) -> Snapshot:
        # Live Admin API is out of scope. T0 capture does not call this.
        raise CredentialNotConfigured(self.name, "T1 snapshot")

    def pull(self, *, person: str | None = None, cycle: str | None = None) -> Iterator[Event]:
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
            detail="T0 capture works without credentials. T1 snapshot is a stub.",
        )
