"""Supabase email OTP + JWT. No supabase-js; no passwords stored here."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import jwt
from fastapi import Header, HTTPException, Request
from jwt import PyJWKClient

from ardoise_api.settings import Settings
from ardoise_api.store import Store

_jwks_clients: dict[str, PyJWKClient] = {}


class AuthError(Exception):
    def __init__(self, detail: str, status_code: int = 401) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _store(request: Request) -> Store:
    return request.app.state.store


def kickoff_otp(settings: Settings, email: str) -> dict[str, Any]:
    """POST {SUPABASE_URL}/auth/v1/otp with the public anon key."""
    email = email.strip().lower()
    if not email or "@" not in email:
        raise AuthError("valid email required", 400)
    if not settings.supabase_url or not settings.supabase_anon_key:
        return {
            "ok": True,
            "mocked": True,
            "email": email,
            "detail": (
                "SUPABASE_URL / SUPABASE_ANON_KEY unset. Browser OTP is skipped. "
                "Mint an HS256 JWT with SUPABASE_JWT_SECRET for /v1/me, or enable "
                "lab bypass only in non-production."
            ),
        }
    payload = json.dumps({"email": email, "create_user": True}).encode("utf-8")
    req = urllib.request.Request(
        settings.otp_url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "apikey": settings.supabase_anon_key,
            "Authorization": f"Bearer {settings.supabase_anon_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8") or "{}"
            data = json.loads(body)
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise AuthError(f"supabase otp failed: {err}", exc.code) from exc
    except urllib.error.URLError as exc:
        raise AuthError(f"supabase otp unreachable: {exc}", 502) from exc
    return {"ok": True, "mocked": False, "email": email, "supabase": data}


def decode_access_token(settings: Settings, token: str) -> dict[str, Any]:
    options = {"require": ["exp", "sub"]}
    audience = "authenticated"
    issuer = settings.jwt_issuer or None
    if settings.supabase_jwt_secret:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=audience,
            issuer=issuer,
            options={**options, "verify_iss": bool(issuer)},
        )
    if settings.jwks_url:
        client = _jwks_clients.get(settings.jwks_url)
        if client is None:
            client = PyJWKClient(settings.jwks_url, cache_jwk_set=True)
            _jwks_clients[settings.jwks_url] = client
        key = client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            key.key,
            algorithms=["RS256", "ES256", "EdDSA"],
            audience=audience,
            issuer=issuer,
            options={**options, "verify_iss": bool(issuer)},
        )
    raise AuthError("API has no SUPABASE_JWT_SECRET or SUPABASE_URL JWKS")


def identity_from_claims(claims: dict[str, Any]) -> tuple[str, str | None, str | None]:
    email = claims.get("email") or None
    if isinstance(email, str):
        email = email.strip().lower() or None
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise AuthError("token missing sub")
    external_key = email or sub
    return external_key, email, sub


def lab_identity(request: Request, settings: Settings) -> tuple[str, str, str] | None:
    if not settings.lab_auth_bypass_enabled:
        return None
    header = request.headers.get("x-ardoise-lab-user", "").strip().lower()
    if not header or "@" not in header:
        return None
    return header, header, f"lab:{header}"


def require_account(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    settings = _settings(request)
    store = _store(request)
    lab = lab_identity(request, settings)
    if lab is not None:
        external_key, email, sub = lab
        return store.upsert_account(
            external_key=external_key, email=email, supabase_sub=sub
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization: Bearer required")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="empty bearer token")
    try:
        claims = decode_access_token(settings, token)
        external_key, email, sub = identity_from_claims(claims)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid jwt: {exc}") from exc
    return store.upsert_account(
        external_key=external_key, email=email, supabase_sub=sub
    )
