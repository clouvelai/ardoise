"""FastAPI app: health, OTP kickoff, me, Checkout Session, Stripe webhook."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from ardoise_api import __version__
from ardoise_api.auth import AuthError, kickoff_otp, require_account, verify_email_otp
from ardoise_api.ledger import current_month, render_csv, render_markdown, summarize as summarize_usage
from ardoise_api.privacy import reject_secrets
from ardoise_api.settings import Settings
from ardoise_api.store import AccountStore, open_store
from ardoise_api.stripeutil import (
    StripeError,
    create_checkout_session,
    create_subscription_checkout,
    invoice_grade,
    verify_webhook_signature,
)

EXPORT_FIELDS = [
    "source",
    "vendor",
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
    "billed_cents",
    "tier",
    "person",
    "cycle",
    "session_id",
    "agent",
    "skill",
    "effort",
]


class OtpBody(BaseModel):
    email: str
    next: str | None = None


class OtpVerifyBody(BaseModel):
    email: str | None = None
    token: str | None = None
    token_hash: str | None = None
    type: str | None = None
    code: str | None = None


class CheckoutBody(BaseModel):
    lookup_key: str | None = None
    price_id: str | None = None


class BillingCheckoutBody(BaseModel):
    plan: str
    success_url: str | None = None
    cancel_url: str | None = None


class UsageSyncBody(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)
    invoices: list[dict[str, Any]] = Field(default_factory=list)
    snapshots: list[dict[str, Any]] = Field(default_factory=list)


class InvoicePasteBody(BaseModel):
    vendor: str
    cycle: str
    usd_cents: int | None = None
    usd: float | None = None
    person: str = ""
    notes: str | None = None
    source: str = "paste"


def _store_error_name(exc: BaseException) -> str:
    """Exception type only — never echo DSN / password from driver messages."""
    return type(exc).__name__


def create_app(
    settings: Settings | None = None,
    store: AccountStore | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    store = store or open_store(settings)

    app = FastAPI(
        title="Ardoise API",
        version=__version__,
        description=(
            "Hosted companion. Auth: Supabase email OTP + JWT (account first). "
            "Billing: Stripe Checkout Sessions mode=subscription for Pro/Team."
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
        store_error = None
        try:
            store.ping()
            store_ok = True
        except Exception as exc:
            store_ok = False
            store_error = _store_error_name(exc)
        body: dict[str, Any] = {
            "ok": store_ok,
            "service": "ardoise-api",
            "version": __version__,
            "stripe_mock": settings.stripe_mock,
            "lab_auth_bypass": settings.lab_auth_bypass_enabled,
            "supabase_otp_configured": settings.supabase_otp_configured,
            "store": getattr(store, "kind", "sqlite"),
            "store_ok": store_ok,
            "database_url_configured": bool((settings.database_url or "").strip()),
            "urls": {
                "health": "/health",
                "otp": "/v1/auth/otp",
                "otp_verify": "/v1/auth/otp/verify",
                "me": "/v1/me",
                "cli_tokens": "/v1/cli/tokens",
                "usage_sync": "/v1/usage/sync",
                "usage_status": "/v1/usage/status",
                "usage_statement": "/v1/usage/statement",
                "invoices": "/v1/invoices",
                "checkout": "/v1/checkout/sessions",
                "billing_checkout": "/v1/billing/checkout",
                "billing_webhook": "/v1/billing/webhook",
                "webhook": "/v1/stripe/webhook",
            },
        }
        if store_error:
            body["store_error"] = store_error
        return body

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
            return kickoff_otp(settings, str(body.email), next_path=body.next)
        except AuthError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @app.post("/v1/auth/otp/verify")
    def auth_otp_verify(body: OtpVerifyBody) -> dict[str, Any]:
        try:
            return verify_email_otp(
                settings,
                store,
                body.email,
                body.token,
                token_hash=body.token_hash,
                otp_type=body.type,
                code=body.code,
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

    @app.post("/v1/checkout/mock/{stripe_session_id}/complete", response_model=None)
    def checkout_mock_complete(
        request: Request, stripe_session_id: str
    ) -> dict[str, Any] | RedirectResponse:
        if not settings.stripe_mock:
            raise HTTPException(status_code=404, detail="stripe mock is off")
        result = store.fulfill_checkout(stripe_session_id)
        if not result.get("ok"):
            raise HTTPException(status_code=404, detail=result.get("reason"))
        accept = (request.headers.get("accept") or "").lower()
        if "text/html" in accept:
            return RedirectResponse(
                url=settings.checkout_success_url, status_code=303
            )
        return result

    @app.post("/v1/stripe/webhook")
    async def stripe_webhook(request: Request) -> dict[str, Any]:
        return await _stripe_event(request)

    @app.post("/v1/billing/webhook")
    async def billing_webhook(request: Request) -> dict[str, Any]:
        return await _stripe_event(request)

    @app.post("/v1/cli/tokens")
    def create_cli_token(account: dict[str, Any] = Depends(require_account)) -> dict[str, Any]:
        raw = "ard_" + secrets.token_urlsafe(32)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        meta = store.create_cli_token(account["id"], raw_token=raw, token_hash=digest)
        return {
            "ok": True,
            "token": raw,
            "id": meta["id"],
            "prefix": meta["prefix"],
            "created_at": meta["created_at"],
        }

    @app.post("/v1/usage/sync")
    def usage_sync(
        body: UsageSyncBody,
        account: dict[str, Any] = Depends(require_account),
    ) -> dict[str, Any]:
        payload = body.model_dump()
        try:
            reject_secrets(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        upserted = store.upsert_usage_rows(account["id"], body.rows)
        invoices_n = store.upsert_invoices(account["id"], body.invoices)
        snapshots_n = store.upsert_snapshots(account["id"], body.snapshots)
        return {
            "ok": True,
            "upserted": upserted,
            "invoices_upserted": invoices_n,
            "snapshots_upserted": snapshots_n,
            "rows": upserted,
            "invoices": invoices_n,
            "snapshots": snapshots_n,
            "expected_fields": EXPORT_FIELDS,
        }

    def _month_or_400(month: str | None) -> str:
        value = month or current_month()
        if not re.match(r"^\d{4}-\d{2}$", value):
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")
        return value

    def _usage_summary(account: dict[str, Any], month: str) -> dict[str, Any]:
        plan = account.get("plan") or "free"
        return summarize_usage(
            rows=store.list_usage(account["id"], month=month),
            invoices=store.list_invoices(account["id"], month=month),
            snapshots=store.list_snapshots(account["id"], month=month),
            month=month,
            invoice_grade=invoice_grade(plan),
        )

    @app.get("/v1/usage/status")
    def usage_status(
        month: str | None = Query(default=None),
        account: dict[str, Any] = Depends(require_account),
    ) -> dict[str, Any]:
        return _usage_summary(account, _month_or_400(month))

    @app.get("/v1/usage/statement")
    def usage_statement(
        month: str | None = Query(default=None),
        account: dict[str, Any] = Depends(require_account),
    ) -> dict[str, Any]:
        summary = _usage_summary(account, _month_or_400(month))
        return {
            "ok": True,
            "month": summary["month"],
            "invoice_grade": summary["invoice_grade"],
            "markdown": render_markdown(summary),
            "csv": render_csv(summary),
            "summary": summary,
        }

    @app.post("/v1/invoices")
    def paste_invoice(
        body: InvoicePasteBody,
        account: dict[str, Any] = Depends(require_account),
    ) -> dict[str, Any]:
        if not invoice_grade(account.get("plan")):
            raise HTTPException(status_code=403, detail="invoice paste is a Pro feature")
        cents = body.usd_cents
        if cents is None and body.usd is not None:
            cents = int(round(float(body.usd) * 100))
        if cents is None:
            raise HTTPException(status_code=400, detail="usd_cents or usd required")
        n = store.upsert_invoices(
            account["id"],
            [
                {
                    "vendor": body.vendor,
                    "cycle": body.cycle,
                    "person": body.person,
                    "usd_cents": cents,
                    "source": body.source or "paste",
                    "notes": body.notes,
                }
            ],
        )
        return {"ok": True, "upserted": n}

    return app


app = create_app()
