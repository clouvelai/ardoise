"""Environment. Stripe and JWT secrets never leave this process."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _truthy(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    env: str
    public_url: str
    web_origin: str
    supabase_url: str
    supabase_anon_key: str
    supabase_jwt_secret: str
    database_url: str
    sqlite_path: str
    stripe_secret_key: str
    stripe_webhook_secret: str
    stripe_price_lookup_key: str
    stripe_price_id: str
    stripe_mock_flag: bool
    default_amount_cents: int
    default_credits: int
    lab_bypass_flag: bool
    checkout_success_url: str
    checkout_cancel_url: str

    @classmethod
    def from_env(cls) -> Settings:
        public_url = os.environ.get("ARDOISE_PUBLIC_URL", "http://127.0.0.1:8787").rstrip(
            "/"
        )
        web_origin = os.environ.get("ARDOISE_WEB_ORIGIN", "http://localhost:3000").rstrip(
            "/"
        )
        return cls(
            env=os.environ.get("ARDOISE_ENV", "development").strip() or "development",
            public_url=public_url,
            web_origin=web_origin,
            supabase_url=os.environ.get("SUPABASE_URL", "").rstrip("/"),
            supabase_anon_key=os.environ.get("SUPABASE_ANON_KEY", ""),
            supabase_jwt_secret=os.environ.get("SUPABASE_JWT_SECRET", ""),
            database_url=os.environ.get("DATABASE_URL", ""),
            sqlite_path=os.environ.get("ARDOISE_API_SQLITE", ""),
            stripe_secret_key=os.environ.get("STRIPE_SECRET_KEY", ""),
            stripe_webhook_secret=os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
            stripe_price_lookup_key=os.environ.get(
                "STRIPE_PRICE_LOOKUP_KEY", "ardoise_credits_20"
            ),
            stripe_price_id=os.environ.get("STRIPE_PRICE_ID", ""),
            stripe_mock_flag=_truthy("STRIPE_MOCK", "false"),
            default_amount_cents=_int("STRIPE_DEFAULT_AMOUNT_CENTS", 2000),
            default_credits=_int("STRIPE_DEFAULT_CREDITS", 2000),
            lab_bypass_flag=_truthy("ARDOISE_LAB_AUTH_BYPASS", "false"),
            checkout_success_url=os.environ.get(
                "CHECKOUT_SUCCESS_URL", f"{web_origin}/billing/success"
            ),
            checkout_cancel_url=os.environ.get(
                "CHECKOUT_CANCEL_URL", f"{web_origin}/billing/cancel"
            ),
        )

    @property
    def stripe_mock(self) -> bool:
        return self.stripe_mock_flag or not self.stripe_secret_key

    @property
    def production(self) -> bool:
        return self.env.lower() in {"production", "prod"}

    @property
    def lab_auth_bypass_enabled(self) -> bool:
        if self.production:
            return False
        return self.lab_bypass_flag

    @property
    def jwks_url(self) -> str:
        if not self.supabase_url:
            return ""
        return f"{self.supabase_url}/auth/v1/.well-known/jwks.json"

    @property
    def otp_url(self) -> str:
        if not self.supabase_url:
            return ""
        return f"{self.supabase_url}/auth/v1/otp"

    @property
    def jwt_issuer(self) -> str:
        if not self.supabase_url:
            return ""
        return f"{self.supabase_url}/auth/v1"
