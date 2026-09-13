#!/usr/bin/env python3
"""Install + first-run CLI: symlink launcher, default status, empty hint."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT)

from ardoise import db  # noqa: E402
from ardoise.cli import main as cli_main  # noqa: E402
from ardoise.install_hooks import render_text  # noqa: E402
from ardoise.status import render_text as render_status, summarize  # noqa: E402
from ardoise.vendors.cursor import discover_cursor_files  # noqa: E402


class IsolatedHome(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._old_home = os.environ.get("HOME")
        self._old_ardoise = os.environ.get("ARDOISE_HOME")
        os.environ["HOME"] = self.tmp.name
        os.environ["ARDOISE_HOME"] = str(Path(self.tmp.name) / ".ardoise")
        for key in ("ARDOISE_LEDGER", "ARDOISE_QUEUE", "ARDOISE_STATEMENTS", "ARDOISE_CONFIG"):
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
        self.tmp.cleanup()


class LauncherTests(unittest.TestCase):
    def test_symlink_launcher_resolves_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "ardoise"
            dest.symlink_to((ROOT / "bin" / "ardoise").resolve())
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            proc = subprocess.run(
                [str(dest), "--version"],
                cwd="/",
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("ardoise", proc.stdout)


class DefaultStatusTests(IsolatedHome):
    def test_no_args_prints_status_and_empty_hint(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main([])
        self.assertEqual(rc, 0)
        text = buf.getvalue()
        self.assertIn("Ardoise", text)
        self.assertIn("ledger is empty", text)
        self.assertIn("ardoise backfill", text)

    def test_empty_status_json_still_ok(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main(["status", "--json"])
        self.assertEqual(rc, 0)
        self.assertIn('"ok": true', buf.getvalue())


class InstallCopyTests(unittest.TestCase):
    def test_render_text_names_next_commands(self) -> None:
        text = render_text(
            {
                "bin": "/tmp/.local/bin/ardoise",
                "on_path": "no",
                "claude_settings": "/tmp/.claude/settings.json",
                "cursor_hooks": "/tmp/.cursor/hooks.json",
            }
        )
        self.assertIn("Installed Ardoise", text)
        self.assertIn("ardoise backfill", text)
        self.assertIn("not on PATH", text)

    def test_status_empty_hint_helper(self) -> None:
        text = render_status(
            {
                "month": "2026-09",
                "ledger": "/tmp/ledger.db",
                "month_entries": 0,
                "entries": 0,
                "billed_usd": 0,
                "cost_usd": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
                "section_a": [],
                "by_project": [],
                "by_source": [],
            }
        )
        self.assertIn("ledger is empty", text)
        self.assertIn("ardoise backfill", text)


class LatestMonthTests(IsolatedHome):
    def test_empty_current_month_points_at_latest(self) -> None:
        with db.session() as conn:
            db.upsert_entry(
                conn,
                {
                    "vendor": "anthropic",
                    "source": "anthropic_t0",
                    "message_id": "hist-1",
                    "request_id": "hist-1",
                    "project": "acme/one",
                    "model": "claude-sonnet-4-6",
                    "occurred_at": "2026-03-10T12:00:00Z",
                    "input_tokens": 10,
                    "output_tokens": 10,
                    "cost_usd": 1.25,
                    "tier": "T0",
                },
            )
        data = summarize("2026-09")
        self.assertEqual(data["month_entries"], 0)
        self.assertEqual(data["entries"], 1)
        self.assertEqual((data.get("latest_month") or {}).get("month"), "2026-03")
        text = render_status(data)
        self.assertIn("this month is empty", text)
        self.assertIn("ardoise status --month 2026-03", text)
        self.assertNotIn("ledger is empty", text)

    def test_cli_json_omits_per_event_lines(self) -> None:
        with db.session() as conn:
            db.upsert_entry(
                conn,
                {
                    "vendor": "anthropic",
                    "source": "anthropic_t0",
                    "message_id": "j1",
                    "request_id": "j1",
                    "project": "acme/one",
                    "model": "claude-sonnet-4-6",
                    "occurred_at": "2026-09-02T12:00:00Z",
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cost_usd": 0.01,
                    "tier": "T0",
                },
            )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main(["status", "--json", "--month", "2026-09"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertNotIn("lines", payload)
        self.assertEqual(payload["month_entries"], 1)
        self.assertIn("by_project", payload)


class CursorDiscoverTests(unittest.TestCase):
    def test_skips_agent_transcripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            keep = root / "projects" / "app" / "chat.jsonl"
            skip = root / "projects" / "app" / "agent-transcripts" / "x.jsonl"
            keep.parent.mkdir(parents=True)
            skip.parent.mkdir(parents=True)
            keep.write_text("{}\n", encoding="utf-8")
            skip.write_text("{}\n", encoding="utf-8")
            found = {p.resolve() for p in discover_cursor_files(root)}
            self.assertIn(keep.resolve(), found)
            self.assertNotIn(skip.resolve(), found)


if __name__ == "__main__":
    unittest.main()
