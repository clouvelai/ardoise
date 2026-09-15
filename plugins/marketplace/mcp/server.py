#!/usr/bin/env python3
"""Hosted Ardoise MCP stub over the public usage API.

Stdlib only. Tools wrap GET /v1/usage/status and GET /v1/usage/statement.
Auth is ARDOISE_API_TOKEN (ard_… from /app/settings). Tokens are never
logged or written. A missing token returns a structured error and does
not crash the process.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

DEFAULT_API_URL = "https://api-production-ea055.up.railway.app"
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "ardoise"
SERVER_VERSION = "0.1.0"
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
PLACEHOLDER_RE = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")

# Tests replace this. Production uses urllib.request.urlopen.
urlopen: Callable[..., Any] = urllib.request.urlopen

TOOLS = (
    {
        "name": "status",
        "description": (
            "Ardoise hosted usage status for one UTC month. Thin wrapper "
            "around GET /v1/usage/status. Returns the month summary "
            "(entries, estimates, billed Section A when the account is Pro+)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "month": {
                    "type": "string",
                    "description": "UTC month as YYYY-MM. Defaults to the current month on the API.",
                }
            },
        },
    },
    {
        "name": "statement",
        "description": (
            "Ardoise hosted usage statement / spend document for one UTC "
            "month. Thin wrapper around GET /v1/usage/statement. Returns "
            "markdown, CSV, and the structured document. This is a spend "
            "statement, not a tax invoice."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "month": {
                    "type": "string",
                    "description": "UTC month as YYYY-MM. Defaults to the current month on the API.",
                }
            },
        },
    },
)


def _env_value(name: str) -> str:
    raw = (os.environ.get(name) or "").strip()
    if not raw or PLACEHOLDER_RE.match(raw):
        return ""
    return raw


def api_token() -> str:
    return _env_value("ARDOISE_API_TOKEN")


def api_url() -> str:
    override = _env_value("ARDOISE_API_URL")
    return (override or DEFAULT_API_URL).rstrip("/")


def fail_open(code: str, message: str, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"ok": False, "error": code, "message": message}
    body.update(extra)
    return body


def _month_or_error(month: Any) -> tuple[str | None, dict[str, Any] | None]:
    if month is None or month == "":
        return None, None
    value = str(month).strip()
    if not MONTH_RE.match(value):
        return None, fail_open(
            "bad_month",
            "month must be YYYY-MM (UTC).",
            month=value,
        )
    return value, None


def hosted_get(path: str, month: str | None = None) -> dict[str, Any]:
    token = api_token()
    if not token:
        return fail_open(
            "missing_token",
            "ARDOISE_API_TOKEN is not set. Mint an ard_… CLI token at "
            "hosted /app/settings, export ARDOISE_API_TOKEN, and retry. "
            "The MCP server did not crash.",
        )
    url = f"{api_url()}{path}"
    if month:
        url = f"{url}?{urllib.parse.urlencode({'month': month})}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    try:
        with urlopen(req, timeout=30.0) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            payload = json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.reason or "hosted API error"
        try:
            err_body = json.loads(exc.read().decode("utf-8") or "{}")
            if isinstance(err_body, dict) and err_body.get("detail"):
                detail = str(err_body["detail"])
        except Exception:
            pass
        return fail_open(
            f"http_{exc.code}",
            f"hosted API returned {exc.code}: {detail}",
            status=exc.code,
        )
    except urllib.error.URLError as exc:
        return fail_open("unreachable", f"cannot reach hosted API: {exc.reason}")
    except json.JSONDecodeError:
        return fail_open("bad_response", "hosted API returned non-JSON")
    except Exception as exc:  # noqa: BLE001 — fail-open, never crash a tool
        return fail_open("error", f"hosted API request failed: {exc}")
    if not isinstance(payload, dict):
        return fail_open("bad_response", "hosted API returned a non-object")
    payload.setdefault("ok", True)
    return payload


def tool_status(month: Any = None) -> dict[str, Any]:
    parsed, err = _month_or_error(month)
    if err:
        return err
    return hosted_get("/v1/usage/status", parsed)


def tool_statement(month: Any = None) -> dict[str, Any]:
    parsed, err = _month_or_error(month)
    if err:
        return err
    return hosted_get("/v1/usage/statement", parsed)


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments if isinstance(arguments, dict) else {}
    if name == "status":
        return tool_status(args.get("month"))
    if name == "statement":
        return tool_statement(args.get("month"))
    return fail_open("unknown_tool", f"unknown tool {name!r}")


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
        "isError": payload.get("ok") is False,
    }


def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    """Dispatch one JSON-RPC request. Notifications return None."""
    method = message.get("method")
    msg_id = message.get("id")
    if method is None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32600, "message": "invalid request"},
        }
    if msg_id is None:
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": list(TOOLS)}}
    if method == "tools/call":
        params = message.get("params") or {}
        name = str(params.get("name") or "")
        payload = call_tool(name, params.get("arguments") or {})
        return {"jsonrpc": "2.0", "id": msg_id, "result": _tool_result(payload)}
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


def _read_message(buf: Any) -> dict[str, Any] | None:
    header = buf.readline()
    if not header:
        return None
    if header.lower().startswith(b"content-length:"):
        try:
            length = int(header.split(b":", 1)[1].strip())
        except ValueError:
            return None
        while True:
            line = buf.readline()
            if line in (b"", b"\r\n", b"\n"):
                break
        body = buf.read(length)
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {"jsonrpc": "2.0", "id": None, "method": None}
        return data if isinstance(data, dict) else None
    text = header.decode("utf-8").strip()
    if not text:
        return _read_message(buf)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"jsonrpc": "2.0", "id": None, "method": None}
    return data if isinstance(data, dict) else None


def _write_message(buf: Any, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    buf.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw)
    buf.flush()


def serve(stdin: Any | None = None, stdout: Any | None = None) -> int:
    incoming = stdin if stdin is not None else sys.stdin.buffer
    outgoing = stdout if stdout is not None else sys.stdout.buffer
    while True:
        try:
            message = _read_message(incoming)
        except Exception:
            continue
        if message is None:
            return 0
        try:
            reply = handle_message(message)
        except Exception as exc:  # noqa: BLE001 — fail-open
            msg_id = message.get("id") if isinstance(message, dict) else None
            if msg_id is None:
                continue
            reply = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": _tool_result(
                    fail_open("error", f"tool dispatch failed: {exc}")
                ),
            }
        if reply is not None:
            try:
                _write_message(outgoing, reply)
            except Exception:
                return 0
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        sys.stderr.write(
            "Ardoise hosted MCP stub. Export ARDOISE_API_TOKEN (ard_…) "
            "and speak MCP JSON-RPC on stdio.\n"
        )
        return 0
    if args and args[0] == "--check":
        # Never print the token. Exit 0 even when unset (fail-open).
        sys.stdout.write(
            json.dumps(
                {
                    "ok": True,
                    "server": SERVER_NAME,
                    "version": SERVER_VERSION,
                    "api_url": api_url(),
                    "token_set": bool(api_token()),
                    "tools": [tool["name"] for tool in TOOLS],
                }
            )
            + "\n"
        )
        return 0
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
