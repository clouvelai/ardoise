#!/usr/bin/env python3
"""Backfill skip, project cache, and process-cwd isolation."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT)

from ardoise import backfill as backfill_mod  # noqa: E402
from ardoise.project import (  # noqa: E402
    clear_project_cache,
    git_remote_url,
    infer_project,
    without_process_cwd,
)

FIXTURE = ROOT / "tests" / "fixtures" / "anthropic_t0.jsonl"


class IsolatedHome(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._old_home = os.environ.get("HOME")
        self._old_ardoise = os.environ.get("ARDOISE_HOME")
        os.environ["HOME"] = self.tmp.name
        os.environ["ARDOISE_HOME"] = str(Path(self.tmp.name) / ".ardoise")
        for key in ("ARDOISE_LEDGER", "ARDOISE_QUEUE", "ARDOISE_STATEMENTS", "ARDOISE_CONFIG"):
            os.environ.pop(key, None)
        clear_project_cache()

    def tearDown(self) -> None:
        clear_project_cache()
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        if self._old_ardoise is None:
            os.environ.pop("ARDOISE_HOME", None)
        else:
            os.environ["ARDOISE_HOME"] = self._old_ardoise
        self.tmp.cleanup()


class BackfillSkipTests(IsolatedHome):
    def _seed_claude(self) -> tuple[Path, Path]:
        claude = Path(self.tmp.name) / ".claude"
        dest_dir = claude / "projects" / "fake"
        dest_dir.mkdir(parents=True)
        dest = dest_dir / "session.jsonl"
        dest.write_text(FIXTURE.read_text(encoding="utf-8").replace("/WORKSPACE", str(ROOT)), encoding="utf-8")
        empty_cursor = Path(self.tmp.name) / ".cursor-empty"
        empty_cursor.mkdir()
        return claude, empty_cursor

    def test_second_pass_skips_unchanged_files(self) -> None:
        claude, cursor = self._seed_claude()
        first = backfill_mod.backfill(claude=claude, cursor=cursor)
        self.assertGreaterEqual(first["inserted"], 2)
        self.assertEqual(first["skipped_files"], 0)
        self.assertGreaterEqual(first["files"], 1)
        second = backfill_mod.backfill(claude=claude, cursor=cursor)
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(second["updated"], 0)
        self.assertGreaterEqual(second["skipped_files"], 1)
        self.assertEqual(second["files"], 0)

    def test_force_rereads(self) -> None:
        claude, cursor = self._seed_claude()
        backfill_mod.backfill(claude=claude, cursor=cursor)
        forced = backfill_mod.backfill(claude=claude, cursor=cursor, force=True)
        self.assertEqual(forced["skipped_files"], 0)
        self.assertGreaterEqual(forced["files"], 1)
        self.assertGreaterEqual(forced["skipped"], 1)


class ProjectCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_project_cache()

    def tearDown(self) -> None:
        clear_project_cache()

    def test_same_repo_calls_git_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            nested = repo / "src"
            nested.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "remote", "add", "origin", "git@github.com:acme/one.git"],
                check=True,
            )
            with patch("ardoise.project.subprocess.run", wraps=subprocess.run) as wrapped:
                first = git_remote_url(nested)
                second = git_remote_url(repo)
            self.assertEqual(first, "git@github.com:acme/one.git")
            self.assertEqual(second, first)
            git_calls = [
                call
                for call in wrapped.call_args_list
                if call.args and isinstance(call.args[0], list) and call.args[0][:1] == ["git"]
            ]
            self.assertEqual(len(git_calls), 1)

    def test_missing_cwd_without_process_fallback_is_none(self) -> None:
        self.assertIsNone(infer_project(cwd="/no/such/project", allow_process_cwd=False))
        with without_process_cwd():
            self.assertIsNone(infer_project(cwd=None))


if __name__ == "__main__":
    unittest.main()
