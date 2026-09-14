"""Hosted companion session. Token is never written to the ledger."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ardoise import paths

DEFAULT_API_URL = "https://api-production-ea055.up.railway.app"


def session_path() -> Path:
    override = os.environ.get("ARDOISE_SESSION")
    if override:
        return Path(override).expanduser()
    return paths.ardoise_home() / "session"


def default_api_url() -> str:
    raw = (os.environ.get("ARDOISE_API_URL") or "").strip()
    return raw.rstrip("/") if raw else DEFAULT_API_URL


def load() -> dict[str, Any] | None:
    path = session_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    token = str(data.get("token") or "").strip()
    if not token:
        return None
    api_url = str(data.get("api_url") or default_api_url()).strip().rstrip("/")
    return {"token": token, "api_url": api_url or default_api_url()}


def save(*, token: str, api_url: str | None = None) -> Path:
    paths.ensure_home()
    path = session_path()
    payload = {
        "token": token.strip(),
        "api_url": (api_url or default_api_url()).rstrip("/"),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def clear() -> bool:
    path = session_path()
    if not path.is_file():
        return False
    path.unlink()
    return True
