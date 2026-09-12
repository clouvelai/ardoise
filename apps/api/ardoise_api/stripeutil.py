"""Stripe Checkout Sessions (mode=payment) via raw HTTPS. Secrets stay here."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import string
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ardoise_api.settings import Settings


class StripeError(Exception):
    def __init__(self, detail: str, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _flatten(obj: Any, prefix: str, pairs: list[tuple[str, str]]) -> None:
    if obj is None:
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            nxt = f"{prefix}[{key}]" if prefix else str(key)
            _flatten(value, nxt, pairs)
        return
    if isinstance(obj, list):
        for i, value in enumerate(obj):
            _flatten(value, f"{prefix}[{i}]", pairs)
        return
    if isinstance(obj, bool):
        pairs.append((prefix, "true" if obj else "false"))
        return
    pairs.append((prefix, str(obj)))


def _form(data: dict[str, Any]) -> bytes:
    pairs: list[tuple[str, str]] = []
    _flatten(data, "", pairs)
    return urllib.parse.urlencode(pairs).encode("utf-8")


def stripe_request(
    settings: Settings,
    method: str,
    path: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if settings.stripe_mock or not settings.stripe_secret_key:
        raise StripeError("stripe mock is on; no live Stripe call", 400)
    url = f"https://api.stripe.com{path}"
    body = _form(data) if data is not None else None
    headers = {
        "Authorization": f"Bearer {settings.stripe_secret_key}",
        "Stripe-Version": "2026-07-29.dahlia",
    }
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise StripeError(f"stripe {path} failed: {err}", 502) from exc
    except urllib.error.URLError as exc:
        raise StripeError(f"stripe unreachable: {exc}", 502) from exc


def _get(settings: Settings, path: str, params: dict[str, Any]) -> dict[str, Any]:
    pairs: list[tuple[str, str]] = []
    _flatten(params, "", pairs)
    qs = urllib.parse.urlencode(pairs)
    url = f"https://api.stripe.com{path}"
    if qs:
        url = f"{url}?{qs}"
    headers = {
        "Authorization": f"Bearer {settings.stripe_secret_key}",
        "Stripe-Version": "2026-07-29.dahlia",
    }
    req = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise StripeError(f"stripe {path} failed: {err}", 502) from exc


def resolve_price(
    settings: Settings,
    *,
    lookup_key: str | None = None,
    price_id: str | None = None,
) -> dict[str, Any]:
    """Pin → lookup_key → inline price_data. Amount/credits come from settings if inline."""
    pin = price_id or settings.stripe_price_id
    if pin:
        return {
            "kind": "price",
            "price": pin,
            "amount_cents": settings.default_amount_cents,
            "credits": settings.default_credits,
        }
    key = lookup_key or settings.stripe_price_lookup_key
    if key and not settings.stripe_mock:
        listing = _get(
            settings,
            "/v1/prices",
            {"lookup_keys": [key], "active": True},
        )
        data = listing.get("data") or []
        if data:
            price = data[0]
            amount = int(price.get("unit_amount") or settings.default_amount_cents)
            return {
                "kind": "price",
                "price": price["id"],
                "amount_cents": amount,
                "credits": settings.default_credits,
            }
    return {
        "kind": "price_data",
        "amount_cents": settings.default_amount_cents,
        "credits": settings.default_credits,
    }


def integration_identifier() -> str:
    suffix = "".join(secrets.choice(string.ascii_lowercase) for _ in range(8))
    return f"ardoise_chk_{suffix}"


def mock_session_id() -> str:
    return "cs_mock_" + secrets.token_hex(12)


def create_checkout_session(
    settings: Settings,
    *,
    account: dict[str, Any],
    lookup_key: str | None = None,
    price_id: str | None = None,
) -> dict[str, Any]:
    resolved = resolve_price(settings, lookup_key=lookup_key, price_id=price_id)
    amount = int(resolved["amount_cents"])
    credits = int(resolved["credits"])
    ident = integration_identifier()
    metadata = {
        "account_id": account["id"],
        "external_key": account["external_key"],
        "credits": str(credits),
    }
    if settings.stripe_mock:
        stripe_id = mock_session_id()
        url = f"{settings.public_url}/v1/checkout/mock/{stripe_id}"
        return {
            "id": stripe_id,
            "url": url,
            "amount_cents": amount,
            "credits": credits,
            "currency": "usd",
            "mock": True,
            "mode": "payment",
            "integration_identifier": ident,
        }

    line_item: dict[str, Any] = {"quantity": 1}
    if resolved["kind"] == "price":
        line_item["price"] = resolved["price"]
    else:
        line_item["price_data"] = {
            "currency": "usd",
            "unit_amount": amount,
            "product_data": {"name": f"Ardoise credits ({credits})"},
        }
    payload: dict[str, Any] = {
        "mode": "payment",
        "success_url": settings.checkout_success_url,
        "cancel_url": settings.checkout_cancel_url,
        "client_reference_id": account["id"],
        "metadata": metadata,
        "line_items": [line_item],
        "integration_identifier": ident,
    }
    if account.get("email"):
        payload["customer_email"] = account["email"]
    # Do not pass payment_method_types — dynamic methods from the Dashboard.
    session = stripe_request(settings, "POST", "/v1/checkout/sessions", payload)
    return {
        "id": session["id"],
        "url": session["url"],
        "amount_cents": int(session.get("amount_total") or amount),
        "credits": credits,
        "currency": session.get("currency") or "usd",
        "mock": False,
        "mode": "payment",
        "integration_identifier": ident,
    }


def verify_webhook_signature(
    payload: bytes,
    header: str,
    secret: str,
    *,
    tolerance: int = 300,
) -> None:
    items: dict[str, list[str]] = {}
    for part in header.split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        items.setdefault(key.strip(), []).append(value.strip())
    try:
        timestamp = int(items["t"][0])
    except (KeyError, IndexError, ValueError) as exc:
        raise StripeError("malformed Stripe-Signature", 400) from exc
    signed = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    candidates = items.get("v1") or []
    if not any(hmac.compare_digest(expected, c) for c in candidates):
        raise StripeError("invalid Stripe-Signature", 400)
    if abs(int(time.time()) - timestamp) > tolerance:
        raise StripeError("stale Stripe-Signature", 400)
