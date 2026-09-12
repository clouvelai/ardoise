#!/usr/bin/env python3
"""Fixture/unit tests for Anthropic T1 snapshots. No real keys or network."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise import db, snapshot as snapshot_mod  # noqa: E402
from ardoise.install_hooks import merge_claude_settings  # noqa: E402
from ardoise.privacy import scrub  # noqa: E402
from ardoise.vendors.anthropic import AnthropicAdapter  # noqa: E402
from ardoise.vendors.anthropic.adapter import SNAPSHOT_MIN_INTERVAL_S  # noqa: E402
from ardoise.vendors.contract import CredentialNotConfigured  # noqa: E402
from ardoise.vendors.anthropic.oauth import (  # noqa: E402
    parse_credentials_blob,
    resolve_oauth,
)
from ardoise.vendors.anthropic.usage import (  # noqa: E402
    billed_extra_delta,
    fetch_oauth_usage,
    parse_extra_usage,
    parse_usage_payload,
    usage_headers,
    user_agent,
)

FIXTURE_ENABLED = ROOT / "tests" / "fixtures" / "anthropic_oauth_usage.json"
FIXTURE_DISABLED = ROOT / "tests" / "fixtures" / "anthropic_oauth_usage_disabled.json"
FIXTURE_CREDS = ROOT / "tests" / "fixtures" / "anthropic_credentials.json"

_OAUTH_ENV = (
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_OAUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_VERSION",
    "CLAUDE_CONFIG_DIR",
    "ARDOISE_CLAUDE_ROOT",
    "ARDOISE_LEDGER",
    "ARDOISE_QUEUE",
)


class IsolatedHomeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name) / "home"
        self.home.mkdir()
        self._old_env = {key: os.environ.get(key) for key in _OAUTH_ENV}
        self._old_home = os.environ.get("HOME")
        self._old_ardoise = os.environ.get("ARDOISE_HOME")
        os.environ["HOME"] = str(self.home)
        os.environ["ARDOISE_HOME"] = str(self.home / ".ardoise")
        for key in _OAUTH_ENV:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        if self._old_ardoise is None:
            os.environ.pop("ARDOISE_HOME", None)
        else:
            os.environ["ARDOISE_HOME"] = self._old_ardoise
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()


class UsageParseTests(unittest.TestCase):
    def test_parse_enabled_extra_usage(self) -> None:
        payload = json.loads(FIXTURE_ENABLED.read_text(encoding="utf-8"))
        parsed = parse_usage_payload(payload)
        self.assertIsNotNone(parsed)
        extra = parsed["extra_usage"]
        self.assertTrue(extra["is_enabled"])
        self.assertEqual(extra["used_credits"], 500.0)
        self.assertEqual(extra["monthly_limit"], 10000.0)
        self.assertEqual(extra["currency"], "USD")
        self.assertEqual(parsed["windows"]["five_hour"]["utilization"], 33.0)
        self.assertEqual(parsed["windows"]["seven_day"]["utilization"], 13.0)
        self.assertEqual(parsed["windows"]["seven_day_sonnet"]["utilization"], 1.0)
        self.assertNotIn("seven_day_opus", parsed["windows"])

    def test_parse_disabled_extra_usage(self) -> None:
        payload = json.loads(FIXTURE_DISABLED.read_text(encoding="utf-8"))
        extra = parse_extra_usage(payload)
        self.assertFalse(extra["is_enabled"])
        self.assertIsNone(extra["used_credits"])
        parsed = parse_usage_payload(payload)
        self.assertEqual(parsed["windows"]["five_hour"]["utilization"], 7.0)

    def test_rejects_unrelated_json(self) -> None:
        self.assertIsNone(parse_usage_payload({"error": {"type": "rate_limit_error"}}))
        self.assertIsNone(parse_usage_payload({"model": "claude-sonnet-4-6"}))

    def test_billed_extra_delta(self) -> None:
        self.assertEqual(billed_extra_delta(None, 500.0), 0.0)
        self.assertEqual(billed_extra_delta(500.0, 510.0), 10.0)
        self.assertEqual(billed_extra_delta(500.0, 500.0), 0.0)
        # billing-period reset
        self.assertEqual(billed_extra_delta(900.0, 40.0), 40.0)
        self.assertIsNone(billed_extra_delta(100.0, None))

    def test_user_agent_is_claude_code(self) -> None:
        os.environ["CLAUDE_CODE_VERSION"] = "2.1.72"
        try:
            self.assertEqual(user_agent(), "claude-code/2.1.72")
            headers = usage_headers("sk-ant-oat01-x")
            self.assertEqual(headers["User-Agent"], "claude-code/2.1.72")
            self.assertEqual(headers["anthropic-beta"], "oauth-2025-04-20")
            self.assertTrue(headers["Authorization"].startswith("Bearer "))
        finally:
            os.environ.pop("CLAUDE_CODE_VERSION", None)


class CredentialsTests(IsolatedHomeTest):
    def test_parse_credentials_json(self) -> None:
        raw = FIXTURE_CREDS.read_text(encoding="utf-8")
        token = parse_credentials_blob(raw)
        self.assertEqual(token, "sk-ant-oat01-TESTTOKEN_DO_NOT_STORE")

    def test_parse_raw_oauth_token(self) -> None:
        self.assertEqual(parse_credentials_blob("sk-ant-oat01-abc"), "sk-ant-oat01-abc")

    def test_api_key_is_not_oauth(self) -> None:
        self.assertIsNone(parse_credentials_blob("sk-ant-api03-not-oauth"))
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-api03-not-oauth"
        self.assertIsNone(resolve_oauth())
        vendor = AnthropicAdapter()
        self.assertEqual(vendor.tier_capabilities(), frozenset({"T0"}))

    def test_env_oauth_resolves(self) -> None:
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "sk-ant-oat01-from-env"
        cred = resolve_oauth()
        self.assertIsNotNone(cred)
        self.assertEqual(cred.source, "env:CLAUDE_CODE_OAUTH_TOKEN")
        self.assertEqual(cred.access_token, "sk-ant-oat01-from-env")
        self.assertNotIn("sk-ant-oat01-from-env", repr(cred))

    def test_auth_token_api_key_rejected(self) -> None:
        os.environ["ANTHROPIC_AUTH_TOKEN"] = "sk-ant-api03-nope"
        self.assertIsNone(resolve_oauth())

    def test_file_credentials(self) -> None:
        dest = self.home / ".claude" / ".credentials.json"
        dest.parent.mkdir(parents=True)
        dest.write_text(FIXTURE_CREDS.read_text(encoding="utf-8"), encoding="utf-8")
        cred = resolve_oauth()
        self.assertIsNotNone(cred)
        self.assertEqual(cred.source, "credentials.json")
        self.assertEqual(cred.access_token, "sk-ant-oat01-TESTTOKEN_DO_NOT_STORE")


class AdapterTests(IsolatedHomeTest):
    def test_snapshot_without_oauth_is_empty(self) -> None:
        vendor = AnthropicAdapter()
        self.assertEqual(vendor.tier_capabilities(), frozenset({"T0"}))
        with self.assertRaises(CredentialNotConfigured) as ctx:
            vendor.snapshot()
        self.assertIn("credential not configured", str(ctx.exception))
        result = snapshot_mod.record_vendor_snapshot("anthropic")
        self.assertTrue(result["empty"])
        self.assertEqual(result["reason"], "oauth_unavailable")
        self.assertEqual(result["capabilities"], ["T0"])
        self.assertFalse(result["recorded"])

    def test_snapshot_with_mock_fetch(self) -> None:
        payload = json.loads(FIXTURE_ENABLED.read_text(encoding="utf-8"))

        def fake_fetch(token: str, **_kwargs: object) -> tuple[int, object]:
            self.assertEqual(token, "sk-ant-oat01-mock")
            return 200, payload

        vendor = AnthropicAdapter(
            resolve=lambda: type("C", (), {"source": "test", "access_token": "sk-ant-oat01-mock"})(),
            fetch=fake_fetch,
        )
        self.assertEqual(vendor.tier_capabilities(), frozenset({"T0", "T1"}))
        result = vendor.snapshot(previous_credits=480.0)
        self.assertEqual(result.billed_cents, 500)
        self.assertEqual(result.extra_usage["used_credits"], 500.0)
        self.assertEqual(result.extra_usage["delta"], 20.0)
        self.assertTrue(result.user_agent.startswith("claude-code/"))
        self.assertNotIn("sk-ant-oat01-mock", json.dumps(result.to_row()))

    def test_throttle(self) -> None:
        payload = json.loads(FIXTURE_ENABLED.read_text(encoding="utf-8"))
        calls = {"n": 0}

        def fake_fetch(token: str, **_kwargs: object) -> tuple[int, object]:
            calls["n"] += 1
            return 200, payload

        vendor = AnthropicAdapter(
            resolve=lambda: type("C", (), {"source": "test", "access_token": "sk-ant-oat01-mock"})(),
            fetch=fake_fetch,
        )
        now = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
        first = vendor.snapshot(now=now, last_attempt_at=None)
        self.assertEqual(first.billed_cents, 500)
        with self.assertRaises(CredentialNotConfigured) as ctx:
            vendor.snapshot(now=now + timedelta(seconds=30), last_attempt_at=now)
        self.assertIn("throttled", str(ctx.exception))
        self.assertEqual(calls["n"], 1)
        forced = vendor.snapshot(
            now=now + timedelta(seconds=30),
            last_attempt_at=now,
            force=True,
        )
        self.assertEqual(forced.billed_cents, 500)
        self.assertEqual(calls["n"], 2)
        later = vendor.snapshot(
            now=now + timedelta(seconds=SNAPSHOT_MIN_INTERVAL_S),
            last_attempt_at=now,
        )
        self.assertEqual(later.billed_cents, 500)
        self.assertEqual(calls["n"], 3)

    def test_http_error_reason(self) -> None:
        vendor = AnthropicAdapter(
            resolve=lambda: type("C", (), {"source": "test", "access_token": "sk-ant-oat01-mock"})(),
            fetch=lambda token, **_: (401, {"error": "unauthorized"}),
        )
        with self.assertRaises(CredentialNotConfigured) as ctx:
            vendor.snapshot()
        self.assertIn("http_401", str(ctx.exception))
        result = snapshot_mod.record_vendor_snapshot(
            "anthropic",
            resolve=lambda: type("C", (), {"source": "test", "access_token": "sk-ant-oat01-mock"})(),
            fetch=lambda token, **_: (401, {"error": "unauthorized"}),
        )
        self.assertTrue(result["empty"])
        self.assertEqual(result["reason"], "http_401")


class RecordTests(IsolatedHomeTest):
    def test_records_snapshot_row_without_storing_token(self) -> None:
        payload = json.loads(FIXTURE_ENABLED.read_text(encoding="utf-8"))
        cred = type("C", (), {"source": "test", "access_token": "sk-ant-oat01-SECRET"})()

        result = snapshot_mod.record_vendor_snapshot(
            "anthropic",
            resolve=lambda: cred,
            fetch=lambda token, **_: (200, payload),
        )
        self.assertTrue(result["recorded"])
        self.assertEqual(result["extra_usage"]["delta"], 0.0)

        with db.session() as conn:
            n = conn.execute("SELECT COUNT(*) FROM snapshots WHERE vendor = 'anthropic'").fetchone()[0]
            self.assertEqual(n, 1)
            row = db.latest_snapshot(conn, vendor="anthropic", person="", cycle=result["cycle"])
            self.assertEqual(int(row["billed_cents"]), 500)
            self.assertEqual(row["tier"], "T1")
            blob = Path(os.environ["ARDOISE_HOME"], "ledger.db").read_bytes()
        self.assertNotIn(b"sk-ant-oat01-SECRET", blob)
        self.assertNotIn("sk-ant-oat01-SECRET", json.dumps(result))
        self.assertNotIn("access_token", json.dumps(scrub(result)))

    def test_second_snapshot_delta_is_billed_extra(self) -> None:
        first = json.loads(FIXTURE_ENABLED.read_text(encoding="utf-8"))
        second = json.loads(json.dumps(first))
        second["extra_usage"]["used_credits"] = 530.0
        state = {"n": 0}

        def fetch(token: str, **_kwargs: object) -> tuple[int, object]:
            state["n"] += 1
            return 200, first if state["n"] == 1 else second

        cred = type("C", (), {"source": "test", "access_token": "sk-ant-oat01-x"})()
        t0 = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
        snapshot_mod.record_vendor_snapshot(
            "anthropic",
            resolve=lambda: cred,
            fetch=fetch,
            now=t0,
        )
        later = snapshot_mod.record_vendor_snapshot(
            "anthropic",
            resolve=lambda: cred,
            fetch=fetch,
            now=t0 + timedelta(minutes=4),
        )
        self.assertEqual(later["extra_usage"]["delta"], 30.0)
        self.assertEqual(later["billed_cents"], 530)
        with db.session() as conn:
            n = conn.execute("SELECT COUNT(*) FROM snapshots WHERE vendor = 'anthropic'").fetchone()[0]
            self.assertEqual(n, 2)
            row = db.latest_snapshot(conn, vendor="anthropic", person="", cycle="2026-09")
            self.assertEqual(int(row["billed_cents"]), 530)

    def test_cli_snapshot_without_keys(self) -> None:
        from ardoise.cli import main

        rc = main(["snapshot", "anthropic", "--json"])
        self.assertEqual(rc, 0)

    def test_session_start_hook_installed(self) -> None:
        settings = self.home / ".claude" / "settings.json"
        capture = self.home / ".ardoise" / "hooks" / "capture.sh"
        snap = self.home / ".ardoise" / "hooks" / "snapshot.sh"
        merge_claude_settings(settings, capture, snap)
        data = json.loads(settings.read_text(encoding="utf-8"))
        self.assertIn("SessionStart", data["hooks"])
        blob = json.dumps(data["hooks"]["SessionStart"])
        self.assertIn("snapshot.sh", blob)
        self.assertNotIn("capture.sh", blob)


class FetchHeaderTests(unittest.TestCase):
    def test_fetch_sends_claude_code_user_agent(self) -> None:
        payload = json.loads(FIXTURE_ENABLED.read_text(encoding="utf-8"))
        captured = {}

        class FakeResp:
            status = 200
            code = 200

            def read(self) -> bytes:
                return json.dumps(payload).encode("utf-8")

            def __enter__(self) -> "FakeResp":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        def fake_urlopen(request, timeout=None):
            captured["ua"] = request.get_header("User-agent") or request.headers.get("User-Agent")
            captured["beta"] = request.get_header("Anthropic-beta") or request.headers.get(
                "anthropic-beta"
            )
            captured["url"] = request.full_url
            return FakeResp()

        status, body = fetch_oauth_usage(
            "sk-ant-oat01-x",
            urlopen=fake_urlopen,
            version="2.1.69",
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["extra_usage"]["used_credits"], 500.0)
        self.assertEqual(captured["ua"], "claude-code/2.1.69")
        self.assertEqual(captured["beta"], "oauth-2025-04-20")
        self.assertEqual(captured["url"], "https://api.anthropic.com/api/oauth/usage")


if __name__ == "__main__":
    unittest.main()
