"""POST already-priced usage to the hosted companion. Stdlib urllib only."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from ardoise import db, export, session as session_mod


class SyncError(Exception):
    def __init__(self, detail: str, status: int | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


def _request(
    method: str,
    url: str,
    *,
    token: str,
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            payload = json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.reason or "sync failed"
        try:
            err_body = json.loads(exc.read().decode("utf-8") or "{}")
            if isinstance(err_body, dict) and err_body.get("detail"):
                detail = str(err_body["detail"])
        except Exception:
            pass
        raise SyncError(detail, exc.code) from exc
    except urllib.error.URLError as exc:
        raise SyncError(f"cannot reach API: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise SyncError("API returned non-JSON") from exc
    if not isinstance(payload, dict):
        raise SyncError("API returned a non-object")
    return payload


def _snapshots(month: str | None) -> list[dict[str, Any]]:
    with db.session() as conn:
        return db.list_snapshots(conn, cycle=month)


def _invoices(month: str | None) -> list[dict[str, Any]]:
    with db.session() as conn:
        return db.list_invoices(conn, cycle=month)


def payload(month: str | None = None) -> dict[str, Any]:
    return {
        "rows": export.export_rows(month),
        "invoices": _invoices(month),
        "snapshots": _snapshots(month),
    }


def sync(*, month: str | None = None, session: dict[str, Any] | None = None) -> dict[str, Any]:
    creds = session or session_mod.load()
    if not creds:
        raise SyncError("not logged in — run `ardoise login` with a token from /app/settings")
    api_url = str(creds.get("api_url") or session_mod.default_api_url()).rstrip("/")
    override = (os.environ.get("ARDOISE_API_URL") or "").strip()
    if override:
        api_url = override.rstrip("/")
    body = payload(month)
    result = _request(
        "POST",
        f"{api_url}/v1/usage/sync",
        token=str(creds["token"]),
        body=body,
    )
    result.setdefault("ok", True)
    result.setdefault("rows", len(body["rows"]))
    result.setdefault("invoices", len(body["invoices"]))
    result.setdefault("snapshots", len(body["snapshots"]))
    return result
