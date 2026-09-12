"""Strip prompts, credentials, and other secrets. Ledger stores usage only."""

from __future__ import annotations

import re
from typing import Any

# Exact keys dropped from any captured JSON (case-insensitive).
_DROP_KEYS = frozenset(
    {
        "prompt",
        "prompts",
        "content",
        "contents",
        "text",
        "message",
        "messages",
        "body",
        "input",
        "tool_input",
        "tool_output",
        "attachments",
        "credential",
        "credentials",
        "authorization",
        "cookie",
        "cookies",
        "password",
        "passwd",
        "secret",
        "secrets",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "id_token",
        "private_key",
        "token",
        "env",
        "environment",
        "system",
        "system_prompt",
        "user_prompt",
        "thinking",
        "transcript",
    }
)

_DROP_KEY_RE = re.compile(
    r"(prompt|secret|password|credential|authorization|api[_-]?key|cookie|private[_-]?key)",
    re.IGNORECASE,
)


def is_dropped_key(key: str) -> bool:
    k = str(key).strip().lower()
    if k in _DROP_KEYS:
        return True
    if k.endswith("tokens"):
        return False
    if k == "token" or k.endswith("_token"):
        return True
    return bool(_DROP_KEY_RE.search(k))


def scrub(value: Any) -> Any:
    """Deep-copy JSON-like data with prompts/credentials removed."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if is_dropped_key(str(key)):
                continue
            out[str(key)] = scrub(item)
        return out
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, tuple):
        return [scrub(item) for item in value]
    return value


def usage_only_event(event: dict[str, Any]) -> dict[str, Any]:
    """Keep identifiers + usage. Drop message bodies even if nested."""
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    usage = event.get("usage")
    if not isinstance(usage, dict) and isinstance(message, dict):
        usage = message.get("usage")
    usage = usage if isinstance(usage, dict) else {}

    model = (
        event.get("model")
        or (message.get("model") if isinstance(message, dict) else None)
        or event.get("model_name")
    )
    message_id = event.get("message_id") or event.get("messageId")
    if not message_id and isinstance(message, dict):
        message_id = message.get("id")
    request_id = (
        event.get("requestId")
        or event.get("request_id")
        or event.get("generation_id")
        or event.get("generationId")
    )
    return {
        "source": event.get("source") or event.get("hook_event_name") or event.get("hook_event"),
        "type": event.get("type"),
        "cwd": event.get("cwd"),
        "session_id": event.get("sessionId") or event.get("session_id") or event.get("conversation_id"),
        "transcript_path": event.get("transcript_path") or event.get("transcriptPath"),
        "timestamp": event.get("timestamp") or event.get("ts") or event.get("occurred_at"),
        "uuid": event.get("uuid"),
        "version": event.get("version"),
        "model": model,
        "message_id": message_id,
        "request_id": request_id,
        "usage": {
            "input_tokens": _int(usage.get("input_tokens")),
            "output_tokens": _int(usage.get("output_tokens")),
            "cache_creation_input_tokens": _int(usage.get("cache_creation_input_tokens")),
            "cache_read_input_tokens": _int(usage.get("cache_read_input_tokens")),
            "cache_creation": scrub(usage.get("cache_creation"))
            if isinstance(usage.get("cache_creation"), dict)
            else {},
        },
        "workspace_roots": event.get("workspace_roots")
        if isinstance(event.get("workspace_roots"), list)
        else None,
        "hook_event_name": event.get("hook_event_name") or event.get("hook_event"),
    }


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
