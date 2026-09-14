"""Agent / skill / effort identifiers from T0 transcripts and hook payloads.

Missing fields stay unattributed. Nothing is invented from prompts or defaults.
"""

from __future__ import annotations

import re
from typing import Any

UNATTRIBUTED = "(unattributed)"
DIMENSIONS = ("agent", "skill", "effort")
MAX_ID_LEN = 200

# Stable keys already emitted by Claude Code / Cursor / Grok Bot transcripts.
# First match wins. Prefer a human name/type over an opaque id when both exist.
_AGENT_KEYS = (
    "agent",
    "agentName",
    "agent_name",
    "botName",
    "bot_name",
    "bot",
    "agentType",
    "agent_type",
    "subagentType",
    "subagent_type",
    "agentId",
    "agent_id",
)
_CLOUD_RUN_HINTS = frozenset(
    {"status", "env", "repos", "latestRunId", "latest_run_id", "url"}
)
_OPAQUE_ID = re.compile(
    r"^(?:bc-|run-)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_SKILL_KEYS = (
    "skill",
    "skillName",
    "skill_name",
    "attributionSkill",
    "attribution_skill",
    "skillId",
    "skill_id",
)
_EFFORT_KEYS = (
    "effort",
    "effortLevel",
    "effort_level",
    "thinkingEffort",
    "thinking_effort",
    "effortId",
    "effort_id",
)

_NESTED_OBJECTS = ("attribution", "metadata", "message")
_DICT_NAME_KEYS = (
    "name",
    "type",
    "agent",
    "agentName",
    "agent_name",
    "botName",
    "bot_name",
    "bot",
    "agentType",
    "agent_type",
    "skill",
    "skillName",
    "skill_name",
    "id",
    "agentId",
    "agent_id",
    "skillId",
    "skill_id",
)

_SECRET_SNIPS = ("sk-ant", "bearer ", "api_key", "apikey", "-----begin")


def _looks_like_cloud_run(value: dict[str, Any]) -> bool:
    if _CLOUD_RUN_HINTS & set(value):
        return True
    ident = str(value.get("id") or value.get("bcId") or value.get("bc_id") or "")
    return ident.startswith("bc-") or bool(_OPAQUE_ID.match(ident))


def clean_id(value: Any) -> str | None:
    """Return a short identifier or None. Dicts yield name/type/id; never invent."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        if _looks_like_cloud_run(value):
            # Run wrappers expose a job title on `name` — that is not agent identity.
            for key in ("agentName", "agent_name", "botName", "bot_name", "bot"):
                found = clean_id(value.get(key))
                if found:
                    return found
            return None
        for key in _DICT_NAME_KEYS:
            found = clean_id(value.get(key))
            if found:
                return found
        return None
    if isinstance(value, (list, tuple)):
        return None
    text = str(value).strip()
    if not text or len(text) > MAX_ID_LEN:
        return None
    if any(ch in text for ch in "\n\r\x00"):
        return None
    if text.lower().startswith("bc-") or _OPAQUE_ID.match(text):
        return None
    lower = text.lower()
    if any(snip in lower for snip in _SECRET_SNIPS):
        return None
    return text


def _first(obj: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if key not in obj:
            continue
        found = clean_id(obj.get(key))
        if found:
            return found
    return None


def extract(raw: dict[str, Any] | None) -> dict[str, str | None]:
    """Pull agent/skill/effort from a transcript or hook object.

    Looks at top-level keys and a few stable nested objects (`attribution`,
    `metadata`, `message`). Does not walk message content or prompts.
    """
    out: dict[str, str | None] = {"agent": None, "skill": None, "effort": None}
    if not isinstance(raw, dict):
        return out
    layers: list[dict[str, Any]] = [raw]
    for name in _NESTED_OBJECTS:
        nested = raw.get(name)
        if isinstance(nested, dict):
            layers.append(nested)
    for layer in layers:
        if out["agent"] is None:
            out["agent"] = _first(layer, _AGENT_KEYS)
        if out["skill"] is None:
            out["skill"] = _first(layer, _SKILL_KEYS)
        if out["effort"] is None:
            out["effort"] = _first(layer, _EFFORT_KEYS)
    if out["effort"] is None:
        out["effort"] = _effort_from_params(raw)
    return out


def _effort_from_params(raw: dict[str, Any]) -> str | None:
    """Cursor/Grok `model_params: [{id: effort, value: high}]` — already named."""
    params = raw.get("model_params")
    if params is None:
        params = raw.get("modelParams")
    if not isinstance(params, list):
        return None
    for item in params:
        if not isinstance(item, dict):
            continue
        ident = str(item.get("id") or item.get("key") or "").strip().lower()
        if ident not in {"effort", "effort_level", "effortlevel", "thinking_effort", "thinkingeffort"}:
            continue
        found = clean_id(item.get("value") if item.get("value") is not None else item.get("val"))
        if found:
            return found
    return None


def bind(row: dict[str, Any] | None) -> dict[str, str | None]:
    """Canonical agent/skill/effort for a ledger row (aliases already resolved)."""
    found = extract(row)
    return {
        "agent": found["agent"],
        "skill": found["skill"],
        "effort": found["effort"],
    }


def label(value: Any) -> str:
    cleaned = clean_id(value)
    return cleaned if cleaned else UNATTRIBUTED


def present(groups: list[dict[str, Any]] | None, column: str) -> list[dict[str, Any]]:
    """Keep buckets that actually carry this dimension."""
    out: list[dict[str, Any]] = []
    for row in groups or []:
        key = row.get(column)
        if key and key != UNATTRIBUTED:
            out.append(row)
    return out


def any_present(summary: dict[str, Any] | None) -> bool:
    data = summary or {}
    return any(present(data.get(f"by_{dim}"), dim) for dim in DIMENSIONS)
