"""Strip prompts, credentials, and other secrets. Ledger stores usage only."""

from __future__ import annotations

import re
from typing import Any

from ardoise.attribution import extract
from ardoise.model import persist_model

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
    if not isinstance(usage, dict):
        usage = event.get("tokenUsage") or event.get("token_usage") or {}
    usage = usage if isinstance(usage, dict) else {}

    def _pick(*keys: str) -> Any:
        for key in keys:
            if key in usage and usage.get(key) not in (None, ""):
                return usage.get(key)
            if key in event and event.get(key) not in (None, ""):
                return event.get(key)
        return 0

    model = persist_model(event, message if isinstance(message, dict) else {})
    message_id = event.get("message_id") or event.get("messageId")
    if not message_id and isinstance(message, dict):
        message_id = message.get("id")
    request_id = (
        event.get("requestId")
        or event.get("request_id")
        or event.get("generation_id")
        or event.get("generationId")
    )
    attrs = extract(event)
    return {
        "source": event.get("source") or event.get("hook_event_name") or event.get("hook_event"),
        "type": event.get("type"),
        "cwd": event.get("cwd"),
        "session_id": (
            event.get("sessionId")
            or event.get("session_id")
            or event.get("conversation_id")
            or event.get("conversationId")
        ),
        "transcript_path": event.get("transcript_path") or event.get("transcriptPath"),
        "timestamp": event.get("timestamp") or event.get("ts") or event.get("occurred_at"),
        "uuid": event.get("uuid"),
        "version": event.get("version"),
        "model": model,
        "model_id": event.get("model_id")
        or event.get("modelId")
        or (message.get("model_id") if isinstance(message, dict) else None)
        or (message.get("modelId") if isinstance(message, dict) else None),
        "model_params": event.get("model_params") or event.get("modelParams"),
        "message_id": message_id,
        "request_id": request_id,
        "usage": {
            "input_tokens": _int(_pick("input_tokens", "inputTokens")),
            "output_tokens": _int(_pick("output_tokens", "outputTokens")),
            "cache_creation_input_tokens": _int(
                _pick(
                    "cache_creation_input_tokens",
                    "cacheWriteTokens",
                    "cache_write_tokens",
                    "cache_creation_tokens",
                )
            ),
            "cache_read_input_tokens": _int(
                _pick(
                    "cache_read_input_tokens",
                    "cacheReadTokens",
                    "cache_read_tokens",
                )
            ),
            "cache_creation": scrub(usage.get("cache_creation"))
            if isinstance(usage.get("cache_creation"), dict)
            else {},
        },
        "workspace_roots": event.get("workspace_roots")
        if isinstance(event.get("workspace_roots"), list)
        else None,
        "hook_event_name": event.get("hook_event_name") or event.get("hook_event"),
        "agent": attrs.get("agent"),
        "skill": attrs.get("skill"),
        "effort": attrs.get("effort"),
    }


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
