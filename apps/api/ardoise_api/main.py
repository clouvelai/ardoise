"""FastAPI app: health, OTP kickoff, me, Checkout Session, Stripe webhook."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from ardoise_api import __version__
from ardoise_api.auth import AuthError, kickoff_otp, require_account, verify_email_otp
from ardoise_api.settings import Settings
from ardoise_api.store import Store
from ardoise_api.stripeutil import (
    StripeError,
    create_checkout_session,
    create_subscription_checkout,
    invoice_grade,
    verify_webhook_signature,
)

EXPORT_FIELDS = [
    "source",
    "message_id",
    "request_id",
    "project",
    "model",
    "occurred_at",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
    "cache_creation_5m_tokens",
    "cache_creation_1h_tokens",
    "cost_usd",
    "session_id",
]


class OtpBody(BaseModel):
    email: str


class OtpVerifyBody(BaseModel):
    email: str
    token: str


class CheckoutBody(BaseModel):
    lookup_key: str | None = None
    price_id: str | None = None


class BillingCheckoutBody(BaseModel):
    plan: str
    success_url: str | None = None
    cancel_url: str | None = None


class UsageSyncBody(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)


def _default_sqlite(settings: Settings) -> str:
    if settings.sqlite_path:
        return settings.sqlite_path
    here = Path(__file__).resolve().parent.parent / ".data" / "local.db"
    return str(here)


def create_app(
    settings: Settings | None = None,
    store: Store | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    store = store or Store(_default_sqlite(settings))

    app = FastAPI(
        title="Ardoise API",
        version=__version__,
        description=(
            "Hosted companion. Auth: Supabase email OTP + JWT (account first). "
            "Billing: Stripe Checkout Sessions mode=subscription for Team/Business."
        ),
    )
    app.state.settings = settings
    app.state.store = store

    origins = [settings.web_origin, "http://localhost:3000", "http://127.0.0.1:3000"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(set(origins)),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Ardoise-Lab-User"],
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "ardoise-api",
            "version": __version__,
            "stripe_mock": settings.stripe_mock,
            "lab_auth_bypass": settings.lab_auth_bypass_enabled,
            "store": "sqlite",
            "database_url_configured": bool(settings.database_url),
            "urls": {
                "health": "/health",
                "otp": "/v1/auth/otp",
                "otp_verify": "/v1/auth/otp/verify",
                "me": "/v1/me",
                "checkout": "/v1/checkout/sessions",
                "billing_checkout": "/v1/billing/checkout",
                "billing_webhook": "/v1/billing/webhook",
                "webhook": "/v1/stripe/webhook",
            },
        }

    def _safe_return_url(candidate: str | None, fallback: str) -> str:
        if not candidate:
            return fallback
        allowed = (settings.web_origin, settings.public_url)
        if any(
            candidate == origin or candidate.startswith(origin + "/")
            for origin in allowed
            if origin
        ):
            return candidate
        return fallback

    def _account_public(account: dict[str, Any]) -> dict[str, Any]:
        plan = account.get("plan") or "free"
        return {
            "id": account["id"],
            "external_key": account["external_key"],
            "email": account["email"],
            "supabase_sub": account.get("supabase_sub"),
            "plan": plan,
            "invoice_grade": invoice_grade(plan),
        }

    async def _stripe_event(request: Request) -> dict[str, Any]:
        payload = await request.body()
        if not settings.stripe_mock:
            header = request.headers.get("stripe-signature", "")
            if not settings.stripe_webhook_secret:
                raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET unset")
            try:
                verify_webhook_signature(payload, header, settings.stripe_webhook_secret)
            except StripeError as exc:
                raise HTTPException(
                    status_code=exc.status_code, detail=exc.detail
                ) from exc
        try:
            event = json.loads(payload.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid json") from exc
        etype = event.get("type")
        obj = (event.get("data") or {}).get("object") or {}
        if etype != "checkout.session.completed":
            return {"ok": True, "ignored": etype}
        stripe_id = obj.get("id")
        if not stripe_id:
            raise HTTPException(status_code=400, detail="session id missing")
        metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        result = store.fulfill_checkout(
            stripe_id,
            stripe_customer_id=obj.get("customer"),
            stripe_subscription_id=obj.get("subscription"),
            plan=metadata.get("plan"),
        )
        if not result.get("ok"):
            # Persist-then-fulfill: unknown ids are acknowledged so Stripe
            # does not retry forever on scaffold gaps. Return 200 + reason.
            return {"ok": False, "reason": result.get("reason")}
        return result

    @app.post("/v1/auth/otp")
    def auth_otp(body: OtpBody) -> dict[str, Any]:
        try:
            return kickoff_otp(settings, str(body.email))
        except AuthError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @app.post("/v1/auth/otp/verify")
    def auth_otp_verify(body: OtpVerifyBody) -> dict[str, Any]:
        try:
            return verify_email_otp(
                settings, store, str(body.email), str(body.token)
            )
        except AuthError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @app.get("/v1/me")
    def me(account: dict[str, Any] = Depends(require_account)) -> dict[str, Any]:
        return {
            "account": _account_public(account),
            "credits": store.credit_balance(account["id"]),
        }

    @app.post("/v1/checkout/sessions")
    def checkout_create(
        body: CheckoutBody,
        account: dict[str, Any] = Depends(require_account),
    ) -> dict[str, Any]:
        try:
            session = create_checkout_session(
                settings,
                account=account,
                lookup_key=body.lookup_key,
                price_id=body.price_id,
            )
        except StripeError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        row = store.insert_checkout(
            account_id=account["id"],
            stripe_session_id=session["id"],
            amount_cents=session["amount_cents"],
            credits=session["credits"],
            currency=session["currency"],
            checkout_url=session["url"],
        )
        return {
            "id": row["id"],
            "stripe_session_id": session["id"],
            "url": session["url"],
            "amount_cents": session["amount_cents"],
            "credits": session["credits"],
            "currency": session["currency"],
            "mode": "payment",
            "mock": session["mock"],
        }

    @app.post("/v1/billing/checkout")
    def billing_checkout(
        body: BillingCheckoutBody,
        account: dict[str, Any] = Depends(require_account),
    ) -> dict[str, Any]:
        try:
            session = create_subscription_checkout(
                settings,
                account=account,
                plan=body.plan,
                success_url=_safe_return_url(
                    body.success_url, settings.checkout_success_url
                ),
                cancel_url=_safe_return_url(
                    body.cancel_url, settings.checkout_cancel_url
                ),
            )
        except StripeError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        row = store.insert_checkout(
            account_id=account["id"],
            stripe_session_id=session["id"],
            amount_cents=session["amount_cents"],
            credits=session["credits"],
            currency=session["currency"],
            checkout_url=session["url"],
            mode="subscription",
            plan=session["plan"],
        )
        return {
            "id": row["id"],
            "stripe_session_id": session["id"],
            "url": session["url"],
            "amount_cents": session["amount_cents"],
            "currency": session["currency"],
            "mode": "subscription",
            "plan": session["plan"],
            "mock": session["mock"],
        }

    @app.get("/v1/checkout/mock/{stripe_session_id}", response_class=HTMLResponse)
    def checkout_mock_page(stripe_session_id: str) -> str:
        if not settings.stripe_mock:
            raise HTTPException(status_code=404, detail="stripe mock is off")
        row = store.get_checkout_by_stripe_id(stripe_session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="unknown mock session")
        plan = row.get("plan") or "credits"
        mode = row.get("mode") or "payment"
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Ardoise mock Checkout</title></head>
<body style="font-family:system-ui;max-width:32rem;margin:3rem auto">
  <h1>Mock Checkout</h1>
  <p>STRIPE_MOCK session <code>{stripe_session_id}</code></p>
  <p>{mode} · {plan} · {row['amount_cents']} cents · {row['currency']}</p>
  <form method="post" action="/v1/checkout/mock/{stripe_session_id}/complete">
    <button type="submit">Pay (mock)</button>
  </form>
</body></html>"""

    @app.post("/v1/checkout/mock/{stripe_session_id}/complete")
    def checkout_mock_complete(stripe_session_id: str) -> dict[str, Any]:
        if not settings.stripe_mock:
            raise HTTPException(status_code=404, detail="stripe mock is off")
        result = store.fulfill_checkout(stripe_session_id)
        if not result.get("ok"):
            raise HTTPException(status_code=404, detail=result.get("reason"))
        return result

    @app.post("/v1/stripe/webhook")
    async def stripe_webhook(request: Request) -> dict[str, Any]:
        return await _stripe_event(request)

    @app.post("/v1/billing/webhook")
    async def billing_webhook(request: Request) -> dict[str, Any]:
        return await _stripe_event(request)

    @app.post("/v1/usage/sync")
    def usage_sync(
        body: UsageSyncBody,
        account: dict[str, Any] = Depends(require_account),
    ) -> JSONResponse:
        del body, account
        return JSONResponse(
            {
                "ok": False,
                "scaffold": True,
                "detail": (
                    "Usage sync is not implemented. A future endpoint will accept "
                    "already-priced usage rows (the same JSONL as `bin/ardoise export`) "
                    "after OTP. Never send prompts, API keys, or ~/.ardoise/ledger.db."
                ),
                "expected_fields": EXPORT_FIELDS,
            },
            status_code=501,
        )

    return app


app = create_app()
