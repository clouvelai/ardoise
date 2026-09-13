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


def _env(*names: str) -> str:
    """First non-empty environment value among *names* (aliases)."""
    for name in names:
        raw = os.environ.get(name)
        if raw is None:
            continue
        value = raw.strip()
        if value:
            return value
    return ""


def is_legacy_jwt_api_key(value: str) -> bool:
    """Legacy anon / service_role keys are long-lived HS256 JWTs (`eyJ…`)."""
    if not value.startswith("eyJ"):
        return False
    return value.count(".") == 2


def is_sb_api_key(value: str) -> bool:
    """Newer Dashboard keys: `sb_publishable_…` / `sb_secret_…` (not JWTs)."""
    return value.startswith("sb_publishable_") or value.startswith("sb_secret_")


def is_usable_hs256_secret(value: str) -> bool:
    """True when *value* is a raw HMAC secret, not an API key or JWT."""
    if not value:
        return False
    if is_sb_api_key(value) or is_legacy_jwt_api_key(value):
        return False
    return True


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
    supabase_service_role_key: str = ""
    stripe_price_team: str = ""
    stripe_price_business: str = ""

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
            supabase_url=_env("SUPABASE_URL").rstrip("/"),
            supabase_anon_key=_env(
                "SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY"
            ),
            supabase_jwt_secret=_env("SUPABASE_JWT_SECRET"),
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
            supabase_service_role_key=_env(
                "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY"
            ),
            stripe_price_team=os.environ.get("STRIPE_PRICE_TEAM", ""),
            stripe_price_business=os.environ.get("STRIPE_PRICE_BUSINESS", ""),
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
    def otp_verify_url(self) -> str:
        if not self.supabase_url:
            return ""
        return f"{self.supabase_url}/auth/v1/verify"

    @property
    def jwt_issuer(self) -> str:
        if not self.supabase_url:
            return ""
        return f"{self.supabase_url}/auth/v1"

    @property
    def supabase_auth_key(self) -> str:
        """Publishable/anon preferred; secret/service_role is server-only fallback."""
        return self.supabase_anon_key or self.supabase_service_role_key

    @property
    def supabase_otp_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_auth_key)

    @property
    def has_hs256_secret(self) -> bool:
        """Legacy JWT Secret from the Dashboard — not an API key or JWT."""
        return is_usable_hs256_secret(self.supabase_jwt_secret)
