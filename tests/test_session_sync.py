#!/usr/bin/env python3
"""CLI session, hosted sync payload, and Cursor $0 join rows."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from io import StringIO
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise.adapters.hook_event import event_to_entry  # noqa: E402
from ardoise.cli import main as cli_main  # noqa: E402
from ardoise.session import load, save, session_path  # noqa: E402
from ardoise.sync import payload  # noqa: E402


class IsolatedHome(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._old = {key: os.environ.get(key) for key in ("HOME", "ARDOISE_HOME", "ARDOISE_SESSION")}
        os.environ["HOME"] = self.tmp.name
        os.environ["ARDOISE_HOME"] = str(Path(self.tmp.name) / ".ardoise")
        os.environ.pop("ARDOISE_SESSION", None)

    def tearDown(self) -> None:
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()


class SessionTests(IsolatedHome):
    def test_login_writes_mode_600_outside_ledger(self) -> None:
        buf = StringIO()
        with redirect_stdout(buf):
            rc = cli_main(["login", "--token", "ard_test_token", "--json"])
        self.assertEqual(rc, 0)
        path = session_path()
        self.assertTrue(path.is_file())
        self.assertNotEqual(path.suffix, ".db")
        mode = stat.S_IMODE(path.stat().st_mode)
        self.assertEqual(mode, 0o600)
        data = load()
        self.assertEqual(data["token"], "ard_test_token")
        ledger = Path(self.tmp.name) / ".ardoise" / "ledger.db"
        if ledger.is_file():
            blob = ledger.read_bytes()
            self.assertNotIn(b"ard_test_token", blob)

    def test_logout_removes_session(self) -> None:
        save(token="ard_x")
        buf = StringIO()
        with redirect_stdout(buf):
            rc = cli_main(["logout"])
        self.assertEqual(rc, 0)
        self.assertIsNone(load())


class JoinRowTests(unittest.TestCase):
    def test_cursor_session_without_usage_is_kept(self) -> None:
        entry = event_to_entry(
            {
                "hook_event_name": "sessionEnd",
                "conversation_id": "conv-1",
                "model": "composer-1",
                "timestamp": "2026-09-14T12:00:00Z",
                "workspace_roots": ["/tmp/proj"],
            },
            default_source="hook",
        )
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry["vendor"], "cursor")
        self.assertEqual(entry["session_id"], "conv-1")
        self.assertEqual(entry["input_tokens"], 0)
        self.assertEqual(entry["output_tokens"], 0)

    def test_claude_stop_without_usage_is_dropped(self) -> None:
        entry = event_to_entry(
            {
                "hook_event_name": "SessionEnd",
                "session_id": "claude-sess",
                "timestamp": "2026-09-14T12:00:00Z",
            },
            default_source="hook",
        )
        self.assertIsNone(entry)


class ExportPayloadTests(IsolatedHome):
    def test_export_payload_includes_invoices_and_snapshots(self) -> None:
        from ardoise import db

        with db.session() as conn:
            db.upsert_entry(
                conn,
                {
                    "vendor": "anthropic",
                    "source": "anthropic_t0",
                    "message_id": "e1",
                    "request_id": "e1",
                    "project": "acme/one",
                    "occurred_at": "2026-09-02T00:00:00Z",
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cost_usd": 0.01,
                    "tier": "T0",
                    "cycle": "2026-09",
                },
            )
        body = payload("2026-09")
        self.assertEqual(len(body["rows"]), 1)
        self.assertIn("vendor", body["rows"][0])
        self.assertIsInstance(body["invoices"], list)
        self.assertIsInstance(body["snapshots"], list)


if __name__ == "__main__":
    unittest.main()
