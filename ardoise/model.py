"""Resolve a usage row's model id. Placeholders never become Sonnet."""

from __future__ import annotations

from typing import Any

UNKNOWN = "unknown"
PLACEHOLDERS = frozenset(
    {
        "",
        "default",
        "auto",
        "unknown",
        "none",
        "null",
        "undefined",
        "(none)",
        "(default)",
        "(unknown)",
    }
)

_DIRECT_KEYS = (
    "model",
    "model_id",
    "modelId",
    "model_name",
    "modelName",
    "selected_model",
    "selectedModel",
)
_NESTED_OBJECTS = (
    "message",
    "generation",
    "composer",
    "request",
    "metadata",
    "usage",
)


def is_placeholder(name: Any) -> bool:
    if name is None:
        return True
    return str(name).strip().lower() in PLACEHOLDERS


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in _DIRECT_KEYS:
            found = _clean(value.get(key))
            if found:
                return found
        return None
    text = str(value).strip()
    if not text or text.lower() in PLACEHOLDERS:
        return None
    return text


def _candidates(*layers: Any) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def add(raw: Any) -> None:
        cleaned = _clean(raw)
        if not cleaned:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        found.append(cleaned)

    for layer in layers:
        if not isinstance(layer, dict):
            continue
        for key in _DIRECT_KEYS:
            add(layer.get(key))
        for name in _NESTED_OBJECTS:
            nested = layer.get(name)
            if isinstance(nested, dict):
                for key in _DIRECT_KEYS:
                    add(nested.get(key))
    return found


def _specificity(name: str) -> tuple[int, int]:
    return (name.count("-") + name.count("."), len(name))


def _fast_named(*layers: Any) -> bool:
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        params = layer.get("model_params")
        if params is None:
            params = layer.get("modelParams")
        if not isinstance(params, list):
            continue
        for item in params:
            if not isinstance(item, dict):
                continue
            ident = str(item.get("id") or item.get("key") or "").strip().lower()
            if ident not in {"fast", "speed"}:
                continue
            raw = item.get("value") if item.get("value") is not None else item.get("val")
            val = str(raw or "").strip().lower()
            if val in {"true", "1", "yes", "fast"}:
                return True
    return False


def extract_model(*layers: Any) -> str | None:
    """Most specific real model slug, or None when only placeholders are present."""
    candidates = _candidates(*layers)
    if not candidates:
        return None
    picked = max(candidates, key=_specificity)
    if _fast_named(*layers) and "fast" not in picked.lower():
        return f"{picked}-fast"
    return picked


def persist_model(*layers: Any) -> str:
    """Ledger value: the real slug, or the explicit unknown sentinel."""
    return extract_model(*layers) or UNKNOWN
