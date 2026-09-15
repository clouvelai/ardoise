#!/usr/bin/env python3
"""Cursor marketplace Agent Plugin + hosted MCP stub."""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "marketplace"
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from mcp import server as mcp_server  # noqa: E402

SECRET_NEEDLES = (
    "sk-ant-",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_ANALYTICS_API_KEY",
    "CURSOR_ADMIN_API_KEY",
    "access_token",
    "Bearer ",
)
PLUGIN_FILES = (
    PLUGIN / "plugin.json",
    PLUGIN / "mcp.json",
    PLUGIN / ".cursor-plugin" / "plugin.json",
    PLUGIN / "skills" / "ardoise-usage" / "SKILL.md",
    PLUGIN / "README.md",
    ROOT / ".cursor-plugin" / "marketplace.json",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class _FakeHTTPError(HTTPError):
    def __init__(self, url: str, code: int, body: bytes) -> None:
        super().__init__(url, code, f"HTTP {code}", hdrs=None, fp=io.BytesIO(body))


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._raw = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class CatalogShapeTests(unittest.TestCase):
    def test_agent_plugin_manifest_and_mcp_json(self) -> None:
        manifest = _load(PLUGIN / "plugin.json")
        self.assertEqual(
            manifest["$schema"],
            "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        )
        self.assertEqual(manifest["name"], "ardoise")
        self.assertEqual(manifest["license"], "MIT")
        self.assertNotIn("hooks", manifest)
        self.assertNotIn("mcpServers", manifest)

        mcp = _load(PLUGIN / "mcp.json")
        self.assertEqual(
            mcp["$schema"],
            "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
        )
        self.assertEqual(set(mcp.keys()), {"$schema", "mcpServers"})
        server = mcp["mcpServers"]["ardoise"]
        self.assertEqual(server["type"], "stdio")
        self.assertEqual(server["command"], "python3")
        self.assertEqual(server["args"], ["./mcp/server.py"])
        self.assertEqual(server["env"]["ARDOISE_API_TOKEN"], "${ARDOISE_API_TOKEN}")
        self.assertTrue((PLUGIN / "mcp" / "server.py").is_file())
        self.assertTrue((PLUGIN / "skills" / "ardoise-usage" / "SKILL.md").is_file())

    def test_cursor_variables_schema_documents_token(self) -> None:
        cursor = _load(PLUGIN / ".cursor-plugin" / "plugin.json")
        self.assertEqual(cursor["name"], "ardoise")
        variables = cursor["variables"]
        self.assertEqual(variables["type"], "object")
        token = variables["properties"]["ARDOISE_API_TOKEN"]
        self.assertEqual(token["type"], "string")
        self.assertIn("ard_", token["description"])
        self.assertIn("ARDOISE_API_TOKEN", variables["required"])
        default_url = variables["properties"]["ARDOISE_API_URL"]["default"]
        self.assertEqual(default_url, mcp_server.DEFAULT_API_URL)

    def test_repo_marketplace_points_at_plugins_marketplace(self) -> None:
        catalog = _load(ROOT / ".cursor-plugin" / "marketplace.json")
        self.assertEqual(catalog["name"], "ardoise")
        plugin = catalog["plugins"][0]
        self.assertEqual(plugin["name"], "ardoise")
        self.assertEqual(plugin["source"], "./plugins/marketplace")
        self.assertTrue((PLUGIN / "plugin.json").is_file())

    def test_pack_has_no_secrets_or_hooks_scaffold(self) -> None:
        for path in PLUGIN_FILES:
            text = path.read_text(encoding="utf-8")
            for needle in SECRET_NEEDLES:
                self.assertNotIn(needle, text, f"{path} stored {needle!r}")
            self.assertNotIn("../shared", text)
            self.assertNotIn("plugins/shared", text)
        server = (PLUGIN / "mcp" / "server.py").read_text(encoding="utf-8")
        self.assertNotIn("sk-ant-", server)
        self.assertNotIn("CURSOR_ADMIN_API_KEY", server)
        self.assertNotIn("from ardoise", server)


class IsolatedEnv(unittest.TestCase):
    def setUp(self) -> None:
        self._old = {
            key: os.environ.get(key)
            for key in ("ARDOISE_API_TOKEN", "ARDOISE_API_URL")
        }
        os.environ.pop("ARDOISE_API_TOKEN", None)
        os.environ.pop("ARDOISE_API_URL", None)

    def tearDown(self) -> None:
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class FailOpenTests(IsolatedEnv):
    def test_missing_token_returns_error_without_raising(self) -> None:
        status = mcp_server.tool_status()
        self.assertFalse(status["ok"])
        self.assertEqual(status["error"], "missing_token")
        self.assertIn("ARDOISE_API_TOKEN", status["message"])
        self.assertIn("did not crash", status["message"])

        statement = mcp_server.tool_statement("2026-09")
        self.assertFalse(statement["ok"])
        self.assertEqual(statement["error"], "missing_token")

    def test_unexpanded_placeholder_is_treated_as_missing(self) -> None:
        os.environ["ARDOISE_API_TOKEN"] = "${ARDOISE_API_TOKEN}"
        os.environ["ARDOISE_API_URL"] = "${ARDOISE_API_URL}"
        self.assertEqual(mcp_server.api_token(), "")
        self.assertEqual(mcp_server.api_url(), mcp_server.DEFAULT_API_URL)
        body = mcp_server.call_tool("status", {})
        self.assertEqual(body["error"], "missing_token")

    def test_check_exits_zero_without_token(self) -> None:
        buf = io.StringIO()
        with patch.object(sys, "stdout", buf):
            rc = mcp_server.main(["--check"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["token_set"])
        self.assertEqual(payload["tools"], ["status", "statement"])
        self.assertNotIn("ard_", buf.getvalue())


class MockHttpTests(IsolatedEnv):
    def setUp(self) -> None:
        super().setUp()
        os.environ["ARDOISE_API_TOKEN"] = "ard_test_token_not_real"
        self.calls: list[Any] = []

    def _urlopen(self, request: Any, timeout: float | None = None) -> _FakeResponse:
        self.calls.append((request, timeout))
        url = request.full_url
        if url.endswith("/v1/usage/status?month=2026-09"):
            return _FakeResponse(
                {
                    "month": "2026-09",
                    "month_entries": 2,
                    "invoice_grade": False,
                    "notes": ["Free estimates"],
                }
            )
        if url.endswith("/v1/usage/statement?month=2026-09"):
            return _FakeResponse(
                {
                    "ok": True,
                    "month": "2026-09",
                    "markdown": "| Description | Quantity | Rate | Amount |",
                    "csv": "section,usd\n",
                    "document": {"title": "Statement"},
                }
            )
        raise AssertionError(f"unexpected url {url}")

    def test_status_and_statement_wrap_hosted_routes(self) -> None:
        with patch.object(mcp_server, "urlopen", self._urlopen):
            status = mcp_server.call_tool("status", {"month": "2026-09"})
            statement = mcp_server.call_tool("statement", {"month": "2026-09"})
        self.assertTrue(status["ok"])
        self.assertEqual(status["month_entries"], 2)
        self.assertTrue(statement["ok"])
        self.assertIn("Description", statement["markdown"])
        self.assertEqual(len(self.calls), 2)
        status_req, statement_req = self.calls[0][0], self.calls[1][0]
        self.assertTrue(status_req.full_url.endswith("/v1/usage/status?month=2026-09"))
        self.assertTrue(
            statement_req.full_url.endswith("/v1/usage/statement?month=2026-09")
        )
        self.assertEqual(
            status_req.get_header("Authorization"),
            "Bearer ard_test_token_not_real",
        )
        self.assertEqual(status_req.full_url.split("/v1/")[0], mcp_server.DEFAULT_API_URL)

    def test_http_error_is_fail_open(self) -> None:
        def boom(request: Any, timeout: float | None = None) -> Any:
            raise _FakeHTTPError(
                request.full_url,
                401,
                json.dumps({"detail": "invalid token"}).encode("utf-8"),
            )

        with patch.object(mcp_server, "urlopen", boom):
            body = mcp_server.tool_status("2026-09")
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "http_401")
        self.assertEqual(body["status"], 401)
        self.assertIn("invalid token", body["message"])

    def test_network_error_is_fail_open(self) -> None:
        def boom(request: Any, timeout: float | None = None) -> Any:
            raise URLError("timed out")

        with patch.object(mcp_server, "urlopen", boom):
            body = mcp_server.tool_statement()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "unreachable")

    def test_custom_api_url_and_bad_month(self) -> None:
        os.environ["ARDOISE_API_URL"] = "http://127.0.0.1:8787/"

        def capture(request: Any, timeout: float | None = None) -> _FakeResponse:
            self.calls.append(request.full_url)
            return _FakeResponse({"month": "2026-09"})

        with patch.object(mcp_server, "urlopen", capture):
            mcp_server.tool_status("2026-09")
        self.assertEqual(
            self.calls[-1],
            "http://127.0.0.1:8787/v1/usage/status?month=2026-09",
        )
        bad = mcp_server.tool_status("September")
        self.assertEqual(bad["error"], "bad_month")


class ProtocolTests(IsolatedEnv):
    def test_initialize_and_tools_list(self) -> None:
        init = mcp_server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        self.assertEqual(init["result"]["serverInfo"]["name"], "ardoise")
        listed = mcp_server.handle_message(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        names = [tool["name"] for tool in listed["result"]["tools"]]
        self.assertEqual(names, ["status", "statement"])

    def test_tools_call_missing_token_sets_is_error(self) -> None:
        reply = mcp_server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "status", "arguments": {}},
            }
        )
        self.assertTrue(reply["result"]["isError"])
        body = json.loads(reply["result"]["content"][0]["text"])
        self.assertEqual(body["error"], "missing_token")

    def test_tools_call_status_with_mock_http(self) -> None:
        os.environ["ARDOISE_API_TOKEN"] = "ard_test_token_not_real"

        def fake(request: Any, timeout: float | None = None) -> _FakeResponse:
            return _FakeResponse({"month": "2026-09", "month_entries": 1})

        with patch.object(mcp_server, "urlopen", fake):
            reply = mcp_server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "status",
                        "arguments": {"month": "2026-09"},
                    },
                }
            )
        self.assertFalse(reply["result"]["isError"])
        body = json.loads(reply["result"]["content"][0]["text"])
        self.assertEqual(body["month_entries"], 1)

    def test_unknown_method_does_not_raise(self) -> None:
        reply = mcp_server.handle_message(
            {"jsonrpc": "2.0", "id": 9, "method": "nope/nope"}
        )
        self.assertEqual(reply["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
