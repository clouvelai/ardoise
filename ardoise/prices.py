"""Price a usage row from prices.fallback.json (optional user override)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from ardoise import paths

_DATE_SUFFIX = re.compile(r"-\d{8}$")


def normalize_model(name: str | None) -> str:
    if not name:
        return "default"
    n = str(name).strip().lower()
    n = n.replace(".", "-")
    n = n.removeprefix("anthropic/")
    n = n.removeprefix("cursor/")
    n = _DATE_SUFFIX.sub("", n)
    return n or "default"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"price file is not an object: {path}")
    return data


@lru_cache(maxsize=4)
def load_pricebook(user_mtime: float | None = None, bundled_mtime: float | None = None) -> dict[str, Any]:
    bundled = paths.bundled_prices()
    book = _load_json(bundled) if bundled.is_file() else {"models": {"default": _default_rates()}}
    user = paths.user_prices()
    if user.is_file():
        override = _load_json(user)
        models = dict(book.get("models") or {})
        models.update(override.get("models") or {})
        book = {**book, **override, "models": models}
    return book


def _default_rates() -> dict[str, float]:
    return {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_write_5m": 3.75,
        "cache_write_1h": 6.0,
    }


def rates_for(model: str | None) -> dict[str, float]:
    user = paths.user_prices()
    bundled = paths.bundled_prices()
    book = load_pricebook(
        user.stat().st_mtime if user.is_file() else None,
        bundled.stat().st_mtime if bundled.is_file() else None,
    )
    models = book.get("models") or {}
    key = normalize_model(model)
    if key in models:
        return {**_default_rates(), **(models[key] or {})}
    parts = key.split("-")
    while len(parts) > 1:
        parts.pop()
        cand = "-".join(parts)
        if cand in models:
            return {**_default_rates(), **(models[cand] or {})}
    for known in sorted((k for k in models if k != "default"), key=len, reverse=True):
        if key.startswith(known) or known in key:
            return {**_default_rates(), **(models[known] or {})}
    return {**_default_rates(), **(models.get("default") or {})}


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
