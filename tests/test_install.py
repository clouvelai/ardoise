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
from ardoise.cli import build_parser, main as cli_main  # noqa: E402
from ardoise.install_hooks import install, render_text  # noqa: E402
from ardoise.status import render_text as render_status, summarize  # noqa: E402
from ardoise.vendors.cursor import discover_cursor_files  # noqa: E402

_HAPPY_PATH_FORBIDDEN = (
    "vendor pull cursor",
    "vendor test cursor",
    "CURSOR_ADMIN_API_KEY",
    "Admin T2",
    "Admin API",
)


class IsolatedHome(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._old_home = os.environ.get("HOME")
        self._old_ardoise = os.environ.get("ARDOISE_HOME")
        os.environ["HOME"] = self.tmp.name
        os.environ["ARDOISE_HOME"] = str(Path(self.tmp.name) / ".ardoise")
        for key in ("ARDOISE_LEDGER", "ARDOISE_QUEUE", "ARDOISE_STATEMENTS", "ARDOISE_CONFIG", "ARDOISE_PREFIX", "ARDOISE_SESSION"):
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
        self.assertIn("ardoise status", text)
        self.assertIn("invoice add (Free)", text)
        self.assertIn("T2 is Team/Enterprise", text)
        for needle in _HAPPY_PATH_FORBIDDEN:
            self.assertNotIn(needle, text)

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
        self.assertIn("ardoise status", text)
        self.assertIn("not on PATH", text)
        self.assertNotIn("vendor pull", text)
        for needle in _HAPPY_PATH_FORBIDDEN:
            self.assertNotIn(needle, text)

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
        self.assertIn("ardoise status", text)
        self.assertIn("invoice add (Free)", text)
        self.assertIn("T2 is Team/Enterprise", text)
        for needle in _HAPPY_PATH_FORBIDDEN:
            self.assertNotIn(needle, text)


class InstallNextTests(IsolatedHome):
    def test_install_stages_prefix_not_clone(self) -> None:
        result = install(no_plugin_manager=True)
        self.assertEqual(result["next"], "ardoise backfill && ardoise status")
        bound = Path(result["bin"])
        self.assertTrue(bound.exists())
        prefix = Path(self.tmp.name) / ".local" / "share" / "ardoise"
        self.assertTrue((prefix / "bin" / "ardoise").is_file())
        self.assertEqual(bound.resolve(), (prefix / "bin" / "ardoise").resolve())
        self.assertNotEqual(bound.resolve(), (ROOT / "bin" / "ardoise").resolve())
        text = render_text(result)
        self.assertIn("ardoise backfill", text)
        self.assertIn("ardoise status", text)
        for needle in _HAPPY_PATH_FORBIDDEN:
            self.assertNotIn(needle, text)
        install_sh = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertNotIn("vendor pull cursor", install_sh)
        self.assertNotIn("CURSOR_ADMIN_API_KEY", install_sh)


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


def _help_text(*argv: str) -> str:
    buf = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(buf):
        try:
            build_parser().parse_args(list(argv))
        except SystemExit as exc:
            if exc.code not in (0, None):
                raise
    return " ".join((buf.getvalue() + err.getvalue()).split())


class HappyPathHelpTests(unittest.TestCase):
    def test_top_level_help_does_not_push_admin_t2(self) -> None:
        text = _help_text("--help")
        self.assertNotIn("vendor pull cursor", text)
        self.assertNotIn("CURSOR_ADMIN_API_KEY", text)
        self.assertIn("T0 needs no keys", text)

    def test_vendor_help_marks_admin_t2_advanced(self) -> None:
        text = _help_text("vendor", "--help")
        self.assertIn("Advanced", text)
        self.assertIn("Team/Enterprise", text)
        self.assertIn("docs/meter-shape.md", text)
        self.assertIn("not a post-install step", text)
        pull = _help_text("vendor", "pull", "--help")
        self.assertIn("Advanced", pull)
        self.assertIn("Team/Enterprise", pull)
        test = _help_text("vendor", "test", "--help")
        self.assertIn("advanced", test.lower())


class CursorDiscoverTests(unittest.TestCase):
    def test_discovers_agent_transcripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            keep = root / "projects" / "app" / "chat.jsonl"
            extra = root / "projects" / "app" / "agent-transcripts" / "x.jsonl"
            keep.parent.mkdir(parents=True)
            extra.parent.mkdir(parents=True)
            keep.write_text("{}\n", encoding="utf-8")
            extra.write_text("{}\n", encoding="utf-8")
            found = {p.resolve() for p in discover_cursor_files(root)}
            self.assertIn(keep.resolve(), found)
            self.assertIn(extra.resolve(), found)


if __name__ == "__main__":
    unittest.main()
