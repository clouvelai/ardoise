"""Per-session estimate gate stub.

Prices a hypothetical token/model ask from the price table. Hooks may call
this later; it is fire-and-forget: no writes, no network, never blocks.
"""

from __future__ import annotations

import json
from typing import Any, TextIO

from ardoise import config as config_mod
from ardoise import paths, prices


def _int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _usage(raw: dict[str, Any]) -> dict[str, int]:
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    return {
        "input_tokens": _int(raw.get("input_tokens", usage.get("input_tokens"))),
        "output_tokens": _int(raw.get("output_tokens", usage.get("output_tokens"))),
        "cache_read_tokens": _int(
            raw.get("cache_read_tokens", usage.get("cache_read_input_tokens") or usage.get("cache_read_tokens"))
        ),
        "cache_creation_tokens": _int(
            raw.get(
                "cache_creation_tokens",
                raw.get("cache_write_tokens", usage.get("cache_creation_input_tokens") or usage.get("cache_creation_tokens")),
            )
        ),
        "cache_creation_5m_tokens": _int(
            raw.get("cache_creation_5m_tokens", usage.get("cache_creation_5m_tokens"))
        ),
        "cache_creation_1h_tokens": _int(
            raw.get("cache_creation_1h_tokens", usage.get("cache_creation_1h_tokens"))
        ),
    }


def _gate(usd: float, month: str | None = None) -> dict[str, Any]:
    """Informational only. `blocks` is always false (stub)."""
    gate: dict[str, Any] = {
        "mode": "stub",
        "blocks": False,
        "usd": round(float(usd), 8),
        "would_exceed_soft_cap": False,
        "remaining_usd": None,
        "cap_usd": None,
        "spent_usd": None,
        "basis": None,
    }
    try:
        cfg = config_mod.load()
        cap = (cfg.get("budgets") or {}).get("monthly_usd")
        gate["cap_usd"] = cap
        if not cap or not paths.ledger_path().is_file():
            return gate
        from ardoise.budget import month_spend
        from ardoise.status import summarize

        summary = summarize(month)
        spent, basis = month_spend(summary)
        remaining = round(max(0.0, float(cap) - spent), 6)
        gate["spent_usd"] = spent
        gate["remaining_usd"] = remaining
        gate["basis"] = basis
        gate["would_exceed_soft_cap"] = (spent + usd) > float(cap)
    except (OSError, ValueError, TypeError, KeyError):
        return gate
    return gate


def price_ask(
    *,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_creation_5m_tokens: int = 0,
    cache_creation_1h_tokens: int = 0,
    month: str | None = None,
    with_gate: bool = True,
) -> dict[str, Any]:
    usd = prices.price_usd(
        model=model,
        input_tokens=max(0, int(input_tokens or 0)),
        output_tokens=max(0, int(output_tokens or 0)),
        cache_read_tokens=max(0, int(cache_read_tokens or 0)),
        cache_creation_tokens=max(0, int(cache_creation_tokens or 0)),
        cache_creation_5m_tokens=max(0, int(cache_creation_5m_tokens or 0)),
        cache_creation_1h_tokens=max(0, int(cache_creation_1h_tokens or 0)),
    )
    data: dict[str, Any] = {
        "ok": True,
        "command": "estimate",
        "model": model or "default",
        "normalized_model": prices.normalize_model(model),
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "cache_read_tokens": int(cache_read_tokens or 0),
        "cache_creation_tokens": int(cache_creation_tokens or 0),
        "cache_creation_5m_tokens": int(cache_creation_5m_tokens or 0),
        "cache_creation_1h_tokens": int(cache_creation_1h_tokens or 0),
        "usd": usd,
        "rates": prices.rates_for(model),
        "unit": "per_million_tokens",
        "currency": "USD",
        "blocks": False,
    }
    if with_gate:
        data["gate"] = _gate(usd, month=month)
    return data


def from_payload(raw: dict[str, Any], *, month: str | None = None) -> dict[str, Any]:
    usage = _usage(raw)
    return price_ask(
        model=str(raw.get("model") or "") or None,
        month=month or (None if raw.get("month") in (None, "") else str(raw.get("month"))),
        **usage,
    )


def from_stdin(stream: TextIO, *, month: str | None = None) -> dict[str, Any]:
    try:
        text = stream.read()
    except OSError as exc:
        return {"ok": False, "error": str(exc), "blocks": False, "usd": 0.0, "command": "estimate"}
    if not str(text).strip():
        return {"ok": False, "error": "empty stdin", "blocks": False, "usd": 0.0, "command": "estimate"}
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid JSON: {exc}", "blocks": False, "usd": 0.0, "command": "estimate"}
    if not isinstance(raw, dict):
        return {"ok": False, "error": "stdin must be a JSON object", "blocks": False, "usd": 0.0, "command": "estimate"}
    return from_payload(raw, month=month)


def render_text(data: dict[str, Any]) -> str:
    if not data.get("ok"):
        return f"estimate  error={data.get('error') or 'failed'}  (never blocks)\n"
    gate = data.get("gate") if isinstance(data.get("gate"), dict) else {}
    remaining = gate.get("remaining_usd")
    extra = ""
    if remaining is not None:
        flag = "  would-exceed-soft-cap" if gate.get("would_exceed_soft_cap") else ""
        extra = f"\ngate      stub  never-blocks  remaining=${float(remaining):.2f}{flag}"
    else:
        extra = "\ngate      stub  never-blocks"
    return (
        "estimate  model={model}  in={inn}  out={out}  ${usd:.6f}{extra}\n".format(
            model=data.get("normalized_model") or data.get("model") or "default",
            inn=int(data.get("input_tokens") or 0),
            out=int(data.get("output_tokens") or 0),
            usd=float(data.get("usd") or 0),
            extra=extra,
        )
    )
