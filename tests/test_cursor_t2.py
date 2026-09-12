#!/usr/bin/env python3
"""Cursor T2 scaffold tests — fixture JSON only, no live Admin API key."""

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
from ardoise.privacy import usage_only_event  # noqa: E402
from ardoise.vendors import cursor as cursor_t2  # noqa: E402
from ardoise.vendors.cursor import UNATTRIBUTED  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


class FixtureTransport:
    """Replay Admin API fixture JSON. Records calls for assertions."""

    def __init__(self) -> None:
        self.members = _load("cursor_t2_members.json")
        self.events = _load("cursor_t2_events.json")
        self.spend = _load("cursor_t2_spend.json")
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def __call__(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((method, path, body))
        if path == "/teams/members":
            return self.members
        if path == "/teams/spend":
            return self.spend
        if path == "/teams/filtered-usage-events":
            return self.events
        raise KeyError(path)


class CursorT2Tests(unittest.TestCase):
    def test_capabilities_without_cred(self) -> None:
        caps = cursor_t2.capabilities(environ={})
        self.assertTrue(caps["t0"])
        self.assertFalse(caps["t2"])
        self.assertFalse(caps["has_cred"])

    def test_capabilities_with_cred(self) -> None:
        caps = cursor_t2.capabilities(environ={"CURSOR_ADMIN_API_KEY": "key_test"})
        self.assertTrue(caps["t2"])
        self.assertTrue(caps["has_cred"])

    def test_parse_fixture_event_id_and_cost(self) -> None:
        raw = _load("cursor_t2_events.json")["usageEvents"][0]
        parsed = cursor_t2.parse_event(raw)
        assert parsed is not None
        self.assertEqual(parsed["event_id"], "evt_t2_matched")
        self.assertEqual(parsed["message_id"], "evt_t2_matched")
        self.assertEqual(parsed["request_id"], "evt_t2_matched")
        self.assertEqual(parsed["conversation_id"], "conv_proj_1")
        self.assertEqual(parsed["input_tokens"], 126)
        self.assertEqual(parsed["output_tokens"], 450)
        self.assertEqual(parsed["cache_creation_tokens"], 6112)
        self.assertEqual(parsed["cache_read_tokens"], 11964)
        self.assertAlmostEqual(parsed["cost_usd"], 0.2136232, places=6)
        self.assertEqual(parsed["source"], "cursor_t2")

    def test_event_id_stable_without_explicit_id(self) -> None:
        raw = dict(_load("cursor_t2_events.json")["usageEvents"][0])
        raw.pop("id")
        first = cursor_t2.event_id(raw)
        second = cursor_t2.event_id(raw)
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("cur_"))

    def test_t0_hook_keeps_conversation_id(self) -> None:
        event = usage_only_event(
            {
                "conversationId": "conv_proj_1",
                "model": "composer-2.5",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )
        self.assertEqual(event["session_id"], "conv_proj_1")

    def test_vendor_test_missing_cred(self) -> None:
        data = cursor_t2.test_vendor(environ={})
        self.assertTrue(data["ok"])
        self.assertTrue(data["skipped"])
        self.assertEqual(data["reason"], "missing_cred")
        self.assertIn("missing CURSOR_ADMIN_API_KEY", data["message"])
        self.assertIn("T0-only", cursor_t2.render_test(data))

    def test_vendor_test_fixture_roster_role_events(self) -> None:
        transport = FixtureTransport()
        data = cursor_t2.test_vendor(transport=transport, environ={})
        self.assertTrue(data["ok"])
        self.assertEqual(data["roster"], 2)
        self.assertEqual(data["role"], "member,owner")
        self.assertEqual(data["events_7d"], 3)
        text = cursor_t2.render_test(data)
        self.assertIn("roster=2", text)
        self.assertIn("role=member,owner", text)
        self.assertIn("events_7d=3", text)
        paths = {c[1] for c in transport.calls}
        self.assertEqual(
            paths,
            {"/teams/members", "/teams/spend", "/teams/filtered-usage-events"},
        )

    def test_pull_without_cred_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.db"
            result = cursor_t2.pull(db_path=ledger, environ={})
            self.assertTrue(result["skipped"])
            self.assertEqual(result["reason"], "missing_cred")
            self.assertFalse(ledger.exists())

    def test_pull_joins_conversation_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["ARDOISE_HOME"] = tmp
            ledger = Path(tmp) / "ledger.db"
            transport = FixtureTransport()
            with db.session(ledger) as conn:
                db.upsert_entry(
                    conn,
                    {
                        "source": "cursor",
                        "message_id": "msg_hook_1",
                        "request_id": "req_hook_1",
                        "project": "clouvelai/ardoise",
                        "model": "composer-2.5",
                        "occurred_at": "2026-09-12T10:00:00Z",
                        "input_tokens": 10,
                        "output_tokens": 4,
                        "session_id": "conv_proj_1",
                        "cost_usd": 0.0,
                    },
                )
                first = cursor_t2.pull(conn=conn, transport=transport, environ={})
                second = cursor_t2.pull(conn=conn, transport=transport, environ={})

                self.assertEqual(first["inserted"], 3)
                self.assertEqual(first["attributed"], 1)
                self.assertEqual(first["unattributed"], 2)
                self.assertEqual(second["inserted"], 0)
                self.assertEqual(second["skipped_rows"], 3)

                matched = conn.execute(
                    "SELECT * FROM entries WHERE message_id = 'evt_t2_matched'"
                ).fetchone()
                self.assertIsNotNone(matched)
                self.assertEqual(matched["project"], "clouvelai/ardoise")
                self.assertEqual(matched["source"], "cursor_t2")
                self.assertEqual(matched["session_id"], "conv_proj_1")
                self.assertAlmostEqual(float(matched["cost_usd"]), 0.2136232, places=6)

                unmatched = conn.execute(
                    "SELECT project FROM entries WHERE message_id = 'evt_t2_unmatched'"
                ).fetchone()
                self.assertEqual(unmatched["project"], UNATTRIBUTED)

                no_conv = conn.execute(
                    "SELECT project FROM entries WHERE message_id = 'evt_t2_no_conv'"
                ).fetchone()
                self.assertEqual(no_conv["project"], UNATTRIBUTED)

                mark = db.get_sync_watermark(conn, "cursor", "usage_events")
                self.assertIsNotNone(mark)
                self.assertTrue(str(mark).isdigit())

            blob = ledger.read_bytes()
            for needle in (b"developer@example.com", b"admin@example.com", b"key_test"):
                self.assertNotIn(needle, blob)

            t2_count = 0
            with db.session(ledger) as conn:
                t2_count = conn.execute(
                    "SELECT COUNT(*) FROM entries WHERE source = 'cursor_t2'"
                ).fetchone()[0]
            self.assertEqual(t2_count, 3)

    def test_reattribute_on_later_t0_hook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["ARDOISE_HOME"] = tmp
            ledger = Path(tmp) / "ledger.db"
            transport = FixtureTransport()
            with db.session(ledger) as conn:
                first = cursor_t2.pull(conn=conn, transport=transport, environ={})
                self.assertEqual(first["unattributed"], 3)
                db.upsert_entry(
                    conn,
                    {
                        "source": "hook",
                        "message_id": "msg_late",
                        "request_id": "req_late",
                        "project": "clouvelai/Arbusteia",
                        "model": "composer-2.5",
                        "occurred_at": "2026-09-12T11:00:00Z",
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "session_id": "conv_proj_1",
                        "cost_usd": 0.0,
                    },
                )
                again = cursor_t2.pull(conn=conn, transport=transport, environ={})
                self.assertGreaterEqual(again["updated"], 1)
                matched = conn.execute(
                    "SELECT project FROM entries WHERE message_id = 'evt_t2_matched'"
                ).fetchone()
                self.assertEqual(matched["project"], "clouvelai/Arbusteia")

    def test_cli_vendor_test_missing_cred(self) -> None:
        env_home = tempfile.TemporaryDirectory()
        try:
            os.environ["ARDOISE_HOME"] = env_home.name
            os.environ.pop("CURSOR_ADMIN_API_KEY", None)
            os.environ.pop("CURSOR_API_KEY", None)
            from io import StringIO
            from contextlib import redirect_stdout

            buf = StringIO()
            with redirect_stdout(buf):
                code = cli_main(["vendor", "test", "cursor"])
            self.assertEqual(code, 0)
            out = buf.getvalue()
            self.assertIn("missing CURSOR_ADMIN_API_KEY", out)
            self.assertIn("T0-only", out)
        finally:
            env_home.cleanup()


if __name__ == "__main__":
    unittest.main()
