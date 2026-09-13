"""Supabase email OTP + JWT. No supabase-js; no passwords stored here."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

import jwt
from fastapi import Header, HTTPException, Request
from jwt import PyJWKClient

from ardoise_api.settings import Settings
from ardoise_api.store import Store

_jwks_clients: dict[str, PyJWKClient] = {}
_ASYMMETRIC_ALGS = ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "EdDSA")


class AuthError(Exception):
    def __init__(self, detail: str, status_code: int = 401) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _store(request: Request) -> Store:
    return request.app.state.store


def _normalize_email(email: str) -> str:
    email = email.strip().lower()
    if not email or "@" not in email:
        raise AuthError("valid email required", 400)
    return email


def _gotrue_headers(settings: Settings) -> dict[str, str]:
    """Gotrue OTP: `apikey` is required. Bearer copies the same key (legacy JWT or `sb_*`)."""
    key = settings.supabase_auth_key
    return {
        "Content-Type": "application/json",
        "apikey": key,
        # Legacy eyJ… keys must be Bearer. Newer sb_publishable_/sb_secret_
        # keys are not JWTs; they live on `apikey`. Kong still accepts a copy
        # on Authorization for unauthenticated OTP (same as supabase-js).
        "Authorization": f"Bearer {key}",
    }


def kickoff_otp(settings: Settings, email: str) -> dict[str, Any]:
    """POST {SUPABASE_URL}/auth/v1/otp with the public anon key."""
    email = _normalize_email(email)
    if not settings.supabase_otp_configured:
        return {
            "ok": True,
            "mocked": True,
            "email": email,
            "detail": (
                "SUPABASE_URL and a publishable/anon key unset. Browser OTP is "
                "skipped. Set SUPABASE_ANON_KEY or SUPABASE_PUBLISHABLE_KEY "
                "(legacy eyJ… or sb_publishable_…). Mint an HS256 JWT with "
                "SUPABASE_JWT_SECRET for /v1/me, or enable lab bypass only in "
                "non-production."
            ),
        }
    payload = json.dumps({"email": email, "create_user": True}).encode("utf-8")
    req = urllib.request.Request(
        settings.otp_url,
        data=payload,
        method="POST",
        headers=_gotrue_headers(settings),
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


def mint_mock_access_token(settings: Settings, email: str) -> str:
    now = int(time.time())
    issuer = settings.jwt_issuer or "http://localhost/auth/v1"
    return jwt.encode(
        {
            "aud": "authenticated",
            "role": "authenticated",
            "sub": f"mock:{email}",
            "email": email,
            "iss": issuer,
            "exp": now + 3600,
            "iat": now,
        },
        settings.supabase_jwt_secret,
        algorithm="HS256",
    )


def verify_email_otp(
    settings: Settings,
    store: Store,
    email: str,
    token: str,
) -> dict[str, Any]:
    """POST {SUPABASE_URL}/auth/v1/verify — creates the account, no card."""
    email = _normalize_email(email)
    token = token.strip()
    if not token:
        raise AuthError("one-time code required", 400)

    if not settings.supabase_otp_configured:
        if not settings.has_hs256_secret:
            return {
                "ok": False,
                "mocked": True,
                "email": email,
                "detail": (
                    "SUPABASE_URL and a publishable/anon key unset. OTP verify "
                    "is not configured. Set SUPABASE_ANON_KEY or "
                    "SUPABASE_PUBLISHABLE_KEY, or a raw SUPABASE_JWT_SECRET "
                    "(not a JWT or sb_* key) to mint a local mock session."
                ),
            }
        access_token = mint_mock_access_token(settings, email)
        account = store.upsert_account(
            external_key=email, email=email, supabase_sub=f"mock:{email}"
        )
        return {
            "ok": True,
            "mocked": True,
            "email": email,
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": 3600,
            "account": {
                "id": account["id"],
                "external_key": account["external_key"],
                "email": account["email"],
                "plan": account.get("plan") or "free",
            },
            "detail": (
                "Mock OTP verify (Supabase keys unset). Account created without "
                "a card — Turbo-style account first."
            ),
        }

    payload = json.dumps(
        {"email": email, "token": token, "type": "email"}
    ).encode("utf-8")
    req = urllib.request.Request(
        settings.otp_verify_url,
        data=payload,
        method="POST",
        headers=_gotrue_headers(settings),
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8") or "{}"
            data = json.loads(body)
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise AuthError(f"supabase otp verify failed: {err}", exc.code) from exc
    except urllib.error.URLError as exc:
        raise AuthError(f"supabase otp verify unreachable: {exc}", 502) from exc

    access_token = data.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise AuthError("supabase verify returned no access_token", 502)

    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    sub = user.get("id") if isinstance(user.get("id"), str) else None
    verified_email = email
    raw_email = user.get("email")
    if isinstance(raw_email, str) and raw_email.strip():
        verified_email = raw_email.strip().lower()
    if not sub:
        try:
            claims = decode_access_token(settings, access_token)
            _, claim_email, sub = identity_from_claims(claims)
            if claim_email:
                verified_email = claim_email
        except AuthError:
            sub = None
    if not sub:
        raise AuthError("supabase verify returned no user id", 502)

    account = store.upsert_account(
        external_key=verified_email, email=verified_email, supabase_sub=sub
    )
    return {
        "ok": True,
        "mocked": False,
        "email": verified_email,
        "access_token": access_token,
        "token_type": data.get("token_type") or "bearer",
        "expires_in": data.get("expires_in"),
        "refresh_token": data.get("refresh_token"),
        "account": {
            "id": account["id"],
            "external_key": account["external_key"],
            "email": account["email"],
            "plan": account.get("plan") or "free",
        },
    }


def _token_header(token: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        return {}
    return header if isinstance(header, dict) else {}


def _jwks_client(settings: Settings) -> PyJWKClient:
    url = settings.jwks_url
    if not url:
        raise AuthError("API has no SUPABASE_URL JWKS")
    client = _jwks_clients.get(url)
    if client is None:
        client = PyJWKClient(url, cache_jwk_set=True)
        _jwks_clients[url] = client
    return client


def _decode_kwargs(settings: Settings) -> dict[str, Any]:
    issuer = settings.jwt_issuer or None
    return {
        "audience": "authenticated",
        "issuer": issuer,
        "options": {"require": ["exp", "sub"], "verify_iss": bool(issuer)},
    }


def _prefer_jwks(settings: Settings, header: dict[str, Any]) -> bool:
    """Prefer JWKS when a signing key id is present and no HS256 secret yet."""
    if not settings.jwks_url:
        return False
    alg = str(header.get("alg") or "")
    kid = header.get("kid")
    if alg in _ASYMMETRIC_ALGS:
        return True
    if kid and not settings.has_hs256_secret:
        return True
    if not settings.has_hs256_secret:
        return True
    return False


def _decode_via_jwks(settings: Settings, token: str) -> dict[str, Any]:
    client = _jwks_client(settings)
    key = client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        key.key,
        algorithms=list(_ASYMMETRIC_ALGS),
        **_decode_kwargs(settings),
    )


def decode_access_token(settings: Settings, token: str) -> dict[str, Any]:
    header = _token_header(token)
    if _prefer_jwks(settings, header):
        return _decode_via_jwks(settings, token)
    if settings.has_hs256_secret:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            **_decode_kwargs(settings),
        )
    if settings.jwks_url:
        return _decode_via_jwks(settings, token)
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
