"""Vendor adapters implementing the VendorAdapter contract."""

from __future__ import annotations

from ardoise.vendors.contract import (
    Capabilities,
    CredentialNotConfigured,
    CredentialSpec,
    Event,
    Snapshot,
    TokenCounts,
    VendorAdapter,
    VendorTestResult,
    entry_to_event,
    result_text,
    vendor_for_source,
)

_ALIASES = {
    "claude": "anthropic",
    "claude-code": "anthropic",
    "anthropic_t0": "anthropic",
    "cursor_t0": "cursor",
}


def list_adapters() -> list[str]:
    return ["anthropic", "cursor"]


def _load(name: str):
    if name == "anthropic":
        from ardoise.vendors.anthropic import AnthropicAdapter

        return AnthropicAdapter
    if name == "cursor":
        from ardoise.vendors.cursor import CursorAdapter

        return CursorAdapter
    return None


def get_adapter(name: str) -> VendorAdapter:
    key = (name or "").strip().lower()
    key = _ALIASES.get(key, key)
    cls = _load(key)
    if cls is None:
        known = ", ".join(list_adapters())
        raise ValueError(f"unknown vendor {name!r}; known: {known}")
    return cls()


def get_vendor(name: str) -> VendorAdapter:
    """Alias used by the T1 snapshot CLI path."""
    return get_adapter(name)


def test_adapter(name: str) -> VendorTestResult:
    return get_adapter(name).test()


__all__ = [
    "Capabilities",
    "CredentialNotConfigured",
    "CredentialSpec",
    "Event",
    "Snapshot",
    "TokenCounts",
    "VendorAdapter",
    "VendorTestResult",
    "entry_to_event",
    "get_adapter",
    "get_vendor",
    "list_adapters",
    "result_text",
    "test_adapter",
    "vendor_for_source",
]
