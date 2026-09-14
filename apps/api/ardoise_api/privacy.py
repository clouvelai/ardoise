"""Reject prompt/credential-shaped keys on inbound sync payloads."""

from __future__ import annotations

from typing import Any

_SECRET_KEYS = frozenset(
    {
        "credential",
        "credentials",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "authorization",
        "password",
        "secret",
        "token",
        "admin_api_key",
        "cursor_api_key",
        "anthropic_admin_api_key",
        "anthropic_api_key",
        "prompt",
        "prompts",
        "content",
        "contents",
        "private_key",
    }
)


def secret_keys_in(value: Any, *, found: list[str] | None = None) -> list[str]:
    hits = found if found is not None else []
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).strip().lower()
            if lowered in _SECRET_KEYS or lowered.endswith("_token"):
                hits.append(str(key))
                continue
            secret_keys_in(item, found=hits)
    elif isinstance(value, list):
        for item in value:
            secret_keys_in(item, found=hits)
    return hits


def reject_secrets(payload: Any) -> None:
    hits = secret_keys_in(payload)
    if hits:
        raise ValueError("payload must not include prompts or credentials")
