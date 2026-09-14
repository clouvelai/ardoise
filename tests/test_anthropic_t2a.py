#!/usr/bin/env python3
"""Anthropic T2a Analytics scaffold tests — fixture JSON only, no live key."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise import db  # noqa: E402
from ardoise.cli import main as cli_main  # noqa: E402
from ardoise.vendors.anthropic import AnthropicAdapter  # noqa: E402
from ardoise.vendors.anthropic import t2a  # noqa: E402
from ardoise.vendors.anthropic.t2a import UNATTRIBUTED  # noqa: E402
from ardoise.vendors.contract import CredentialNotConfigured  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures"

_ENV = (
    "HOME",
    "ANTHROPIC_ANALYTICS_API_KEY",
    "ANTHROPIC_ANALYTICS_KEY",
    "ANTHROPIC_ANALYTICS_API_BASE",
    "ARDOISE_PERSON",
    "ARDOISE_HOME",
    "ARDOISE_LEDGER",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_OAUTH_TOKEN",
    "ANTHROPIC_ADMIN_API_KEY",
)


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


class FixtureTransport:
    """Replay Analytics API fixture JSON. Records calls for assertions."""

    def __init__(self) -> None:
        self.summaries = _load("anthropic_t2a_summaries.json")
        self.usage = _load("anthropic_t2a_usage.json")
        self.cost = _load("anthropic_t2a_cost.json")
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def __call__(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((method, path, body))
        if path.startswith("/v1/organizations/analytics/summaries"):
            return self.summaries
        if path.startswith("/v1/organizations/analytics/usage_report"):
            return self.usage
        if path.startswith("/v1/organizations/analytics/cost_report"):
            return self.cost
        raise KeyError(path)


class IsolatedHomeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old = {key: os.environ.get(key) for key in _ENV}
        os.environ["ARDOISE_HOME"] = str(Path(self._tmp.name) / ".ardoise")
        os.environ["HOME"] = self._tmp.name
        for key in _ENV:
            if key in {"ARDOISE_HOME", "HOME"}:
                continue
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()


class AnthropicT2aTests(IsolatedHomeTest):
    def test_capabilities_without_cred(self) -> None:
        caps = t2a.capabilities(environ={})
        self.assertTrue(caps["t0"])
        self.assertFalse(caps["t2a"])
        self.assertFalse(caps["has_cred"])

    def test_capabilities_with_cred(self) -> None:
        caps = t2a.capabilities(environ={"ANTHROPIC_ANALYTICS_API_KEY": "key_test"})
        self.assertTrue(caps["t2a"])
        self.assertTrue(caps["has_cred"])

    def test_alias_env(self) -> None:
        self.assertEqual(
            t2a.analytics_api_key(environ={"ANTHROPIC_ANALYTICS_KEY": "alias_key"}),
            "alias_key",
        )

    def test_parse_fixture_event_id_and_tokens(self) -> None:
        raw = _load("anthropic_t2a_usage.json")["data"][0]["results"][0]
        parsed = t2a.parse_event(raw)
        assert parsed is not None
        self.assertEqual(parsed["event_id"], "evt_t2a_matched")
        self.assertEqual(parsed["message_id"], "evt_t2a_matched")
        self.assertEqual(parsed["request_id"], "evt_t2a_matched")
        self.assertEqual(parsed["session_id"], "sess_proj_1")
        self.assertEqual(parsed["input_tokens"], 1000)
        self.assertEqual(parsed["output_tokens"], 400)
        self.assertEqual(parsed["cache_creation_tokens"], 2000)
        self.assertEqual(parsed["cache_read_tokens"], 10000)
        self.assertEqual(parsed["source"], "anthropic_t2a")
        self.assertEqual(parsed["tier"], "T2")
        self.assertNotIn("email", parsed)
        self.assertNotIn("jane@example.com", json.dumps(parsed))

    def test_event_id_stable_without_explicit_id(self) -> None:
        raw = dict(_load("anthropic_t2a_usage.json")["data"][0]["results"][0])
        raw.pop("id")
        first = t2a.event_id(raw)
        second = t2a.event_id(raw)
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("ant_"))

    def test_merge_cost_sets_amount(self) -> None:
        usage = t2a.iter_analytics_rows(_load("anthropic_t2a_usage.json"))
        cost = t2a.iter_analytics_rows(_load("anthropic_t2a_cost.json"))
        merged = t2a.merge_cost_into_usage(usage, cost)
        matched = next(r for r in merged if r.get("id") == "evt_t2a_matched")
        self.assertEqual(matched["amount"], "195.000000")
        parsed = t2a.parse_event(matched)
        assert parsed is not None
        self.assertAlmostEqual(parsed["cost_usd"], 1.95, places=6)
        self.assertEqual(parsed["billed_cents"], 195)

    def test_vendor_test_missing_cred(self) -> None:
        data = t2a.test_vendor(environ={})
        self.assertTrue(data["ok"])
        self.assertTrue(data["skipped"])
        self.assertEqual(data["reason"], "missing_cred")
        self.assertIn("Analytics T2a skipped", data["message"])
        self.assertIn("Free is T0", data["message"])
        self.assertIn("Team/Enterprise", data["message"])
        self.assertNotIn("ANTHROPIC_ANALYTICS_API_KEY", data["message"])
        self.assertNotIn("missing ", data["message"])
        self.assertIn("T2a skipped", t2a.render_test(data))

    def test_vendor_test_fixture_summaries_and_usage(self) -> None:
        transport = FixtureTransport()
        data = t2a.test_vendor(transport=transport, environ={})
        self.assertTrue(data["ok"])
        self.assertEqual(data["summaries"], 1)
        self.assertEqual(data["usage_rows"], 3)
        text = t2a.render_test(data)
        self.assertIn("summaries=1", text)
        self.assertIn("usage_rows=3", text)
        paths = {c[1].split("?", 1)[0] for c in transport.calls}
        self.assertEqual(
            paths,
            {
                "/v1/organizations/analytics/summaries",
                "/v1/organizations/analytics/usage_report",
            },
        )

    def test_pull_without_cred_is_noop(self) -> None:
        ledger = Path(self._tmp.name) / "ledger.db"
        result = t2a.pull(db_path=ledger, environ={})
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "missing_cred")
        self.assertFalse(ledger.exists())

    def test_pull_joins_session_and_is_idempotent(self) -> None:
        ledger = Path(os.environ["ARDOISE_HOME"]) / "ledger.db"
        transport = FixtureTransport()
        with db.session(ledger) as conn:
            db.upsert_entry(
                conn,
                {
                    "source": "anthropic_t0",
                    "vendor": "anthropic",
                    "message_id": "msg_hook_1",
                    "request_id": "req_hook_1",
                    "project": "clouvelai/ardoise",
                    "model": "claude-sonnet-4-6",
                    "occurred_at": "2026-09-12T10:00:00Z",
                    "input_tokens": 10,
                    "output_tokens": 4,
                    "session_id": "sess_proj_1",
                    "cost_usd": 0.0,
                    "tier": "T0",
                },
            )
            first = t2a.pull(conn=conn, transport=transport, environ={})
            second = t2a.pull(conn=conn, transport=transport, environ={})

            self.assertEqual(first["inserted"], 3)
            self.assertEqual(first["attributed"], 1)
            self.assertEqual(first["unattributed"], 2)
            self.assertEqual(second["inserted"], 0)
            self.assertEqual(second["skipped_rows"], 3)

            matched = conn.execute(
                "SELECT * FROM entries WHERE message_id = 'evt_t2a_matched'"
            ).fetchone()
            self.assertIsNotNone(matched)
            self.assertEqual(matched["project"], "clouvelai/ardoise")
            self.assertEqual(matched["source"], "anthropic_t2a")
            self.assertEqual(matched["session_id"], "sess_proj_1")
            self.assertEqual(matched["tier"], "T2")
            self.assertAlmostEqual(float(matched["cost_usd"]), 1.95, places=6)
            self.assertEqual(int(matched["billed_cents"]), 195)

            unmatched = conn.execute(
                "SELECT project FROM entries WHERE message_id = 'evt_t2a_unmatched'"
            ).fetchone()
            self.assertEqual(unmatched["project"], UNATTRIBUTED)

            no_sess = conn.execute(
                "SELECT project FROM entries WHERE message_id = 'evt_t2a_no_session'"
            ).fetchone()
            self.assertEqual(no_sess["project"], UNATTRIBUTED)

            mark = db.get_sync_watermark(conn, "anthropic", "analytics_usage")
            self.assertIsNotNone(mark)

        blob = ledger.read_bytes()
        for needle in (b"jane@example.com", b"key_test", b"sk-ant-"):
            self.assertNotIn(needle, blob)

        with db.session(ledger) as conn:
            t2_count = conn.execute(
                "SELECT COUNT(*) FROM entries WHERE source = 'anthropic_t2a'"
            ).fetchone()[0]
        self.assertEqual(t2_count, 3)

    def test_reattribute_on_later_t0_hook(self) -> None:
        ledger = Path(os.environ["ARDOISE_HOME"]) / "ledger.db"
        transport = FixtureTransport()
        with db.session(ledger) as conn:
            first = t2a.pull(conn=conn, transport=transport, environ={})
            self.assertEqual(first["unattributed"], 3)
            db.upsert_entry(
                conn,
                {
                    "source": "hook",
                    "vendor": "anthropic",
                    "message_id": "msg_late",
                    "request_id": "req_late",
                    "project": "clouvelai/Arbusteia",
                    "model": "claude-sonnet-4-6",
                    "occurred_at": "2026-09-12T11:00:00Z",
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "session_id": "sess_proj_1",
                    "cost_usd": 0.0,
                    "tier": "T0",
                },
            )
            again = t2a.pull(conn=conn, transport=transport, environ={})
            self.assertGreaterEqual(again["updated"], 1)
            matched = conn.execute(
                "SELECT project FROM entries WHERE message_id = 'evt_t2a_matched'"
            ).fetchone()
            self.assertEqual(matched["project"], "clouvelai/Arbusteia")

    def test_project_slug_on_payload_wins(self) -> None:
        parsed = t2a.parse_event(
            {
                "id": "evt_slug",
                "model": "claude-sonnet-4-6",
                "output_tokens": 1,
                "project": "acme/ledger",
            }
        )
        assert parsed is not None
        self.assertEqual(parsed["project"], "acme/ledger")
        self.assertEqual(t2a.attribute_project(None, parsed), "acme/ledger")

    def test_adapter_pull_raises_without_cred(self) -> None:
        vendor = AnthropicAdapter()
        self.assertEqual(vendor.tier_capabilities(), frozenset({"T0"}))
        self.assertEqual(vendor.capabilities.pull, "yes")
        with self.assertRaises(CredentialNotConfigured) as ctx:
            next(vendor.pull())
        self.assertIn("T2a pull", str(ctx.exception))

    def test_adapter_tier_t2_when_analytics_key(self) -> None:
        os.environ["ANTHROPIC_ANALYTICS_API_KEY"] = "key_test"
        vendor = AnthropicAdapter()
        self.assertEqual(vendor.tier_capabilities(), frozenset({"T0", "T2"}))

    def test_cli_vendor_test_and_pull_missing_cred(self) -> None:
        from contextlib import redirect_stdout
        from io import StringIO

        buf = StringIO()
        with redirect_stdout(buf):
            code = cli_main(["vendor", "test", "anthropic"])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("Analytics T2a skipped", out)
        self.assertIn("Free is T0", out)
        self.assertIn("Team/Enterprise", out)
        self.assertNotIn("missing ANTHROPIC", out)
        self.assertNotIn("ANTHROPIC_ANALYTICS_API_KEY", out)
        self.assertNotIn("ANTHROPIC_ADMIN_API_KEY", out)
        self.assertNotIn("unresolved", out)

        buf_json = StringIO()
        with redirect_stdout(buf_json):
            code_json = cli_main(["vendor", "test", "anthropic", "--json"])
        self.assertEqual(code_json, 0)
        payload = json.loads(buf_json.getvalue())
        creds = payload.get("credentials") or []
        self.assertTrue(any(item.get("env") == "ANTHROPIC_ANALYTICS_API_KEY" for item in creds))
        self.assertIn("Analytics T2a skipped", str(payload.get("detail") or ""))
        self.assertNotIn("ANTHROPIC_ANALYTICS_API_KEY", str(payload.get("detail") or ""))

        buf_verbose = StringIO()
        with redirect_stdout(buf_verbose):
            code_verbose = cli_main(["vendor", "test", "anthropic", "--verbose"])
        self.assertEqual(code_verbose, 0)
        verbose = buf_verbose.getvalue()
        self.assertIn("ANTHROPIC_ADMIN_API_KEY", verbose)
        self.assertIn("ANTHROPIC_ANALYTICS_API_KEY", verbose)
        self.assertIn("unresolved", verbose)

        buf2 = StringIO()
        with redirect_stdout(buf2):
            code2 = cli_main(["vendor", "pull", "anthropic"])
        self.assertEqual(code2, 0)
        pull = buf2.getvalue()
        self.assertIn("T2a skipped", pull)
        self.assertNotIn("ANTHROPIC_ANALYTICS_API_KEY", pull)
        self.assertNotIn("missing ", pull)

    def test_cli_vendor_test_stays_quiet_with_oauth(self) -> None:
        from contextlib import redirect_stdout
        from io import StringIO

        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "sk-ant-oat01-not-used"
        buf = StringIO()
        with redirect_stdout(buf):
            code = cli_main(["vendor", "test", "anthropic"])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("Analytics T2a skipped", out)
        self.assertNotIn("ANTHROPIC_ADMIN_API_KEY", out)
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", out)
        self.assertNotIn("unresolved", out)


if __name__ == "__main__":
    unittest.main()
