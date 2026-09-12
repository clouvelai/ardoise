"""Normalize a scrubbed hook / JSONL event into a ledger row."""

from __future__ import annotations

import hashlib
import os
from typing import Any

from ardoise.privacy import _int, usage_only_event
from ardoise.project import infer_project
from ardoise.vendors.contract import cycle_of, vendor_for_source


def _cache_splits(usage: dict[str, Any]) -> tuple[int, int, int]:
    creation = _int(usage.get("cache_creation_input_tokens"))
    nested = usage.get("cache_creation") if isinstance(usage.get("cache_creation"), dict) else {}
    t5 = _int(nested.get("ephemeral_5m_input_tokens"))
    t1h = _int(nested.get("ephemeral_1h_input_tokens"))
    if t5 or t1h:
        creation = max(creation, t5 + t1h)
    return creation, t5, t1h


def synthetic_ids(event: dict[str, Any], usage: dict[str, Any]) -> tuple[str, str]:
    seed = "|".join(
        [
            str(event.get("source") or ""),
            str(event.get("session_id") or ""),
            str(event.get("timestamp") or ""),
            str(event.get("uuid") or ""),
            str(event.get("model") or ""),
            str(usage.get("input_tokens") or 0),
            str(usage.get("output_tokens") or 0),
            str(usage.get("cache_read_input_tokens") or 0),
            str(usage.get("cache_creation_input_tokens") or 0),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    return f"syn_msg_{digest}", f"syn_req_{digest}"


def event_to_entry(raw: dict[str, Any], *, default_source: str) -> dict[str, Any] | None:
    event = usage_only_event(raw)
    usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
    input_tokens = _int(usage.get("input_tokens"))
    output_tokens = _int(usage.get("output_tokens"))
    cache_read = _int(usage.get("cache_read_input_tokens"))
    cache_creation, t5, t1h = _cache_splits(usage)

    has_usage = any([input_tokens, output_tokens, cache_read, cache_creation, t5, t1h])
    if not has_usage:
        return None

    message_id = event.get("message_id")
    request_id = event.get("request_id")
    if not message_id or not request_id:
        syn_msg, syn_req = synthetic_ids(event, usage)
        message_id = message_id or syn_msg
        request_id = request_id or syn_req

    cwd = event.get("cwd")
    roots = event.get("workspace_roots") if isinstance(event.get("workspace_roots"), list) else None
    project = infer_project(cwd=str(cwd) if cwd else None, workspace_roots=roots)

    source = default_source
    hook = str(event.get("hook_event_name") or raw.get("source") or "")
    model = str(event.get("model") or raw.get("model") or "").lower()
    if hook.startswith("cursor") or default_source == "cursor" or "composer" in model:
        source = "cursor"
    elif (
        default_source == "anthropic_t0"
        or str(raw.get("type") or "") in {"assistant", "progress"}
        or "claude" in model
        or "anthropic" in model
    ):
        source = "anthropic_t0"
    elif hook:
        source = "hook"

    occurred = event.get("timestamp") or raw.get("occurred_at")
    if not occurred:
        occurred = None

    person = (os.environ.get("ARDOISE_PERSON") or "").strip()
    return {
        "vendor": vendor_for_source(source),
        "source": source,
        "person": person,
        "cycle": cycle_of(occurred),
        "tier": "T0",
        "billed_cents": None,
        "message_id": str(message_id),
        "request_id": str(request_id),
        "project": project,
        "model": event.get("model"),
        "occurred_at": occurred,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_tokens": cache_creation,
        "cache_read_tokens": cache_read,
        "cache_creation_5m_tokens": t5,
        "cache_creation_1h_tokens": t1h,
        "session_id": event.get("session_id"),
        "cwd": str(cwd) if cwd else None,
        "transcript_path": event.get("transcript_path"),
    }
