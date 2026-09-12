"""Parse GET /api/oauth/usage JSON and build the Claude Code User-Agent."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from typing import Any
from urllib.request import Request

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
ANTHROPIC_BETA = "oauth-2025-04-20"
DEFAULT_CLAUDE_CODE_VERSION = "2.1.72"
_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")


def claude_code_version() -> str:
    explicit = (
        os.environ.get("CLAUDE_CODE_VERSION")
        or os.environ.get("CLAUDE_CODE_CLI_VERSION")
        or ""
    ).strip()
    if explicit:
        return explicit.lstrip("v")
    try:
        proc = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return DEFAULT_CLAUDE_CODE_VERSION
    text = f"{proc.stdout or ''} {proc.stderr or ''}"
    match = _VERSION_RE.search(text)
    return match.group(1) if match else DEFAULT_CLAUDE_CODE_VERSION


def user_agent(version: str | None = None) -> str:
    return f"claude-code/{version or claude_code_version()}"


def usage_headers(token: str, *, version: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "anthropic-beta": ANTHROPIC_BETA,
        "User-Agent": user_agent(version),
        "Accept": "application/json",
    }


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _window(obj: Any) -> dict[str, Any] | None:
    if not isinstance(obj, dict):
        return None
    utilization = _float_or_none(obj.get("utilization"))
    resets_at = obj.get("resets_at") or obj.get("resetsAt")
    if utilization is None and not resets_at:
        return None
    return {
        "utilization": utilization,
        "resets_at": str(resets_at) if resets_at else None,
    }


def parse_extra_usage(payload: dict[str, Any]) -> dict[str, Any]:
    extra = payload.get("extra_usage")
    if not isinstance(extra, dict):
        return {
            "is_enabled": False,
            "used_credits": None,
            "monthly_limit": None,
            "utilization": None,
            "currency": None,
        }
    return {
        "is_enabled": bool(extra.get("is_enabled")),
        "used_credits": _float_or_none(extra.get("used_credits")),
        "monthly_limit": _float_or_none(extra.get("monthly_limit")),
        "utilization": _float_or_none(extra.get("utilization")),
        "currency": extra.get("currency") if extra.get("currency") else None,
    }


def billed_extra_delta(
    previous_credits: float | None,
    current_credits: float | None,
) -> float | None:
    """Billed extra usage since the last snapshot (same units as used_credits).

    First snapshot has no prior point: delta is 0. A drop (billing-period
    reset) treats the new period's extra usage as the delta.
    """
    if current_credits is None:
        return None
    if previous_credits is None:
        return 0.0
    if current_credits < previous_credits:
        return float(current_credits)
    return float(current_credits - previous_credits)


def parse_usage_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize oauth/usage JSON. Returns None when the body is not usage-shaped."""
    if not isinstance(payload, dict):
        return None
    has_usage_keys = any(
        key in payload
        for key in ("five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet", "extra_usage")
    )
    if not has_usage_keys:
        return None
    extra = parse_extra_usage(payload)
    windows: dict[str, Any] = {}
    for key in (
        "five_hour",
        "seven_day",
        "seven_day_opus",
        "seven_day_sonnet",
    ):
        parsed = _window(payload.get(key))
        if parsed is not None:
            windows[key] = parsed
    return {
        "extra_usage": extra,
        "windows": windows,
    }


def looks_like_usage(payload: Any) -> bool:
    return parse_usage_payload(payload) is not None if isinstance(payload, dict) else False


def fetch_oauth_usage(
    token: str,
    *,
    timeout: float = 10.0,
    urlopen: Any = None,
    version: str | None = None,
) -> tuple[int, Any]:
    """GET api.anthropic.com/api/oauth/usage. Returns (status, json_or_text).

    ``urlopen`` is injectable so tests never need a network or a real key.
    """
    headers = usage_headers(token, version=version)
    request = Request(USAGE_URL, headers=headers, method="GET")
    opener = urlopen or urllib.request.urlopen
    try:
        with opener(request, timeout=timeout) as resp:
            body = resp.read()
            status = int(getattr(resp, "status", None) or getattr(resp, "code", 200) or 200)
    except urllib.error.HTTPError as exc:
        raw = exc.read() if hasattr(exc, "read") else b""
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
        try:
            return int(exc.code), json.loads(text) if text else {"error": text}
        except json.JSONDecodeError:
            return int(exc.code), text
    except OSError as exc:
        return 0, str(exc)

    text = body.decode("utf-8", errors="replace") if isinstance(body, (bytes, bytearray)) else str(body)
    try:
        return status, json.loads(text) if text else {}
    except json.JSONDecodeError:
        return status, text
