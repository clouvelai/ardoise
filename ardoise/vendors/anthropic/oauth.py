"""Resolve Anthropic / Claude Code OAuth credentials.

Looks at env, then macOS Keychain, then ``~/.claude/.credentials.json``.
API keys (``ANTHROPIC_API_KEY`` / ``sk-ant-api…``) are not OAuth and do
not enable T1. Tokens are returned in memory only — never persist them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ardoise import paths

# Dedicated OAuth env vars. ANTHROPIC_API_KEY is intentionally absent.
OAUTH_ENV_KEYS = (
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_OAUTH_TOKEN",
)

KEYCHAIN_SERVICE = "Claude Code-credentials"
API_KEY_PREFIXES = ("sk-ant-api", "sk-ant-admin")
OAUTH_PREFIXES = ("sk-ant-oat",)


class OAuthCred:
    """In-memory OAuth access token plus where it was found (no secret in repr)."""

    __slots__ = ("source", "access_token")

    def __init__(self, source: str, access_token: str) -> None:
        self.source = source
        self.access_token = access_token

    def __repr__(self) -> str:
        return f"OAuthCred(source={self.source!r})"


def looks_like_api_key(value: str) -> bool:
    text = (value or "").strip()
    return any(text.startswith(prefix) for prefix in API_KEY_PREFIXES)


def looks_like_oauth_token(value: str) -> bool:
    text = (value or "").strip()
    if not text or looks_like_api_key(text):
        return False
    if any(text.startswith(prefix) for prefix in OAUTH_PREFIXES):
        return True
    # setup-token / JSON blobs are accepted only when the env key is OAuth-named.
    return bool(text)


def _first_token_from_mapping(obj: dict[str, Any]) -> str | None:
    oauth = obj.get("claudeAiOauth")
    if isinstance(oauth, dict):
        token = oauth.get("accessToken") or oauth.get("access_token")
        if isinstance(token, str) and token.strip():
            return token.strip()
    for key in ("accessToken", "access_token", "oauth_token", "oauthToken"):
        token = obj.get(key)
        if isinstance(token, str) and token.strip():
            return token.strip()
    return None


def parse_credentials_blob(raw: str) -> str | None:
    """Extract an access token from a raw env value or credentials JSON."""
    text = (raw or "").strip()
    if not text:
        return None
    if text[0] in "{[":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            token = _first_token_from_mapping(parsed)
            if token and not looks_like_api_key(token):
                return token
        return None
    if looks_like_api_key(text):
        return None
    return text


def _env_cred() -> OAuthCred | None:
    for key in OAUTH_ENV_KEYS:
        raw = os.environ.get(key)
        if not raw or not raw.strip():
            continue
        token = parse_credentials_blob(raw)
        if not token:
            continue
        # ANTHROPIC_AUTH_TOKEN is shared with API-key mode — require OAuth shape.
        if key == "ANTHROPIC_AUTH_TOKEN" and not any(
            token.startswith(prefix) for prefix in OAUTH_PREFIXES
        ):
            continue
        return OAuthCred(source=f"env:{key}", access_token=token)
    return None


def _keychain_cred() -> OAuthCred | None:
    if sys.platform != "darwin":
        return None
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    token = parse_credentials_blob(proc.stdout)
    if not token:
        return None
    return OAuthCred(source="keychain", access_token=token)


def credentials_path(claude_root: Path | None = None) -> Path:
    root = claude_root or paths.claude_root()
    return root / ".credentials.json"


def _file_cred(claude_root: Path | None = None) -> OAuthCred | None:
    path = credentials_path(claude_root)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    token = parse_credentials_blob(raw)
    if not token:
        return None
    return OAuthCred(source="credentials.json", access_token=token)


def resolve_oauth(*, claude_root: Path | None = None) -> OAuthCred | None:
    """Return an OAuth cred when env/keychain/file yields one; else None."""
    return _env_cred() or _keychain_cred() or _file_cred(claude_root)
