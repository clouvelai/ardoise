"""Price a usage row from prices.fallback.json (optional user override)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from ardoise import paths
from ardoise.model import UNKNOWN, is_placeholder

_DATE_SUFFIX = re.compile(r"-\d{8}$")
_SPACES = re.compile(r"[\s/]+")
_MULTI_DASH = re.compile(r"-{2,}")
_CLAUDE_FLIP = re.compile(
    r"^claude-(\d+(?:-\d+)?)-(sonnet|opus|haiku|fable)(?:-(.+))?$"
)
_PROVIDER_PREFIXES = (
    "anthropic/",
    "cursor/",
    "openai/",
    "google/",
    "xai/",
    "x-ai/",
    "spacexai/",
    "meta/",
    "bedrock/",
    "vertex/",
    "vertex-ai/",
    "vertex_ai/",
)
_CURSOR_PREFIX = "cursor-"
_PEEL = frozenset({"fast", "xhigh", "high", "medium", "low", "max", "thinking"})
_SENTINELS = frozenset({UNKNOWN, "default"})


def _flip_claude_slug(name: str) -> str:
    """Cursor Admin / picker ``claude-4.5-sonnet`` → book ``claude-sonnet-4-5``."""
    match = _CLAUDE_FLIP.match(name)
    if not match:
        return name
    version, tier, rest = match.group(1), match.group(2), match.group(3)
    out = f"claude-{tier}-{version}"
    if rest:
        out = f"{out}-{rest}"
    return out


def normalize_model(name: str | None) -> str:
    if is_placeholder(name):
        return UNKNOWN
    n = str(name).strip().lower()
    if "[" in n:
        n = n.split("[", 1)[0].strip()
    n = n.replace(".", "-")
    for prefix in _PROVIDER_PREFIXES:
        n = n.removeprefix(prefix)
    n = n.replace("_", "-")
    n = _SPACES.sub("-", n)
    n = _MULTI_DASH.sub("-", n).strip("-")
    n = _DATE_SUFFIX.sub("", n)
    if n.startswith(_CURSOR_PREFIX):
        n = n[len(_CURSOR_PREFIX) :]
    n = _flip_claude_slug(n)
    return n or UNKNOWN


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"price file is not an object: {path}")
    return data


@lru_cache(maxsize=4)
def load_pricebook(user_mtime: float | None = None, bundled_mtime: float | None = None) -> dict[str, Any]:
    bundled = paths.bundled_prices()
    book = _load_json(bundled) if bundled.is_file() else {"models": {UNKNOWN: _zero_rates()}}
    user = paths.user_prices()
    if user.is_file():
        override = _load_json(user)
        models = dict(book.get("models") or {})
        models.update(override.get("models") or {})
        book = {**book, **override, "models": models}
    models = book.setdefault("models", {})
    if UNKNOWN not in models:
        models[UNKNOWN] = _zero_rates()
    return book


def _zero_rates() -> dict[str, float]:
    return {
        "input": 0.0,
        "output": 0.0,
        "cache_read": 0.0,
        "cache_write_5m": 0.0,
        "cache_write_1h": 0.0,
    }


def _fill(rates: dict[str, Any] | None) -> dict[str, float]:
    return {**_zero_rates(), **(rates or {})}


def _book() -> dict[str, Any]:
    user = paths.user_prices()
    bundled = paths.bundled_prices()
    return load_pricebook(
        user.stat().st_mtime if user.is_file() else None,
        bundled.stat().st_mtime if bundled.is_file() else None,
    )


def _resolve_key(key: str, models: dict[str, Any]) -> str:
    if key in models and key not in _SENTINELS:
        return key
    tokens = key.split("-")
    fast = False
    peeled = list(tokens)
    while peeled and peeled[-1] in _PEEL:
        if peeled[-1] == "fast":
            fast = True
        peeled.pop()
    base = "-".join(peeled)
    if fast and base:
        cand = f"{base}-fast"
        if cand in models:
            return cand
    if base and base in models and base not in _SENTINELS:
        return base
    for source in (key, base):
        if not source:
            continue
        parts = source.split("-")
        while len(parts) > 1:
            parts.pop()
            cand = "-".join(parts)
            if cand in models and cand not in _SENTINELS:
                return cand
    for known in sorted((k for k in models if k not in _SENTINELS), key=len, reverse=True):
        if key.startswith(known) or (len(known) >= 8 and known in key):
            return known
    return UNKNOWN


def lookup(model: str | None) -> dict[str, Any]:
    """Resolve list-price rates. Unknown / default never inherit Sonnet."""
    models = (_book().get("models") or {})
    key = _resolve_key(normalize_model(model), models)
    unknown = key == UNKNOWN or key not in models
    if unknown:
        return {"key": UNKNOWN, "rates": _fill(models.get(UNKNOWN)), "unknown": True}
    return {"key": key, "rates": _fill(models.get(key)), "unknown": False}


def rates_for(model: str | None) -> dict[str, float]:
    return lookup(model)["rates"]


def price_usd(
    *,
    model: str | None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_creation_5m_tokens: int = 0,
    cache_creation_1h_tokens: int = 0,
) -> float:
    rates = rates_for(model)
    write_5m = cache_creation_5m_tokens
    write_1h = cache_creation_1h_tokens
    leftover = cache_creation_tokens - write_5m - write_1h
    if leftover > 0:
        write_5m += leftover
    usd = (
        input_tokens * float(rates["input"])
        + output_tokens * float(rates["output"])
        + cache_read_tokens * float(rates["cache_read"])
        + write_5m * float(rates["cache_write_5m"])
        + write_1h * float(rates["cache_write_1h"])
    ) / 1_000_000.0
    return round(usd, 8)
