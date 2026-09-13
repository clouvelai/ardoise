#!/usr/bin/env python3
"""Install + first-run CLI: symlink launcher, default status, empty hint."""

from __future__ import annotations

import io
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

from ardoise.cli import main as cli_main  # noqa: E402
from ardoise.install_hooks import render_text  # noqa: E402
from ardoise.status import render_text as render_status  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
