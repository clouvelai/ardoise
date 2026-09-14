#!/usr/bin/env python3
"""Hooks must run without a monorepo plugins/shared sibling."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise.install_hooks import (  # noqa: E402
    _embedded_capture_sh,
    _embedded_snapshot_sh,
    install,
)

SHARED_FORBIDDEN = ("../shared", "../../shared", "plugins/shared")


def _assert_no_shared_path(test: unittest.TestCase, path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for needle in SHARED_FORBIDDEN:
        test.assertNotIn(needle, text, f"{path} still references {needle!r}")


def _fake_cli(tmp: Path, name: str = "fake-ardoise") -> tuple[Path, Path]:
    log = tmp / f"{name}.log"
    fake = tmp / name
    fake.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{log}"\n'
        "cat >/dev/null || true\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake, log


class IsolatedHome(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self._old_home = os.environ.get("HOME")
        self._old_ardoise = os.environ.get("ARDOISE_HOME")
        os.environ["HOME"] = str(self.home)
        os.environ["ARDOISE_HOME"] = str(self.home / ".ardoise")
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


class SourceTreeTests(unittest.TestCase):
    def test_plugin_entrypoints_do_not_reference_shared(self) -> None:
        paths = [
            ROOT / "plugins" / "shared" / "capture.sh",
            ROOT / "plugins" / "shared" / "snapshot.sh",
            ROOT / "plugins" / "shared" / "hook_enqueue.py",
            ROOT / "plugins" / "claude" / "hooks" / "capture.sh",
            ROOT / "plugins" / "claude" / "hooks" / "snapshot.sh",
            ROOT / "plugins" / "cursor" / "capture.sh",
        ]
        for path in paths:
            _assert_no_shared_path(self, path)
        enqueue = (ROOT / "plugins" / "shared" / "hook_enqueue.py").read_text(encoding="utf-8")
        self.assertNotIn("parents[2]", enqueue)
        self.assertNotIn("parents[1]", enqueue)
        for path in paths:
            if path.suffix == ".sh":
                self.assertIn("trap 'exit 0' EXIT", path.read_text(encoding="utf-8"))

    def test_embedded_fallback_matches_shared_files(self) -> None:
        self.assertEqual(
            _embedded_capture_sh(),
            (ROOT / "plugins" / "shared" / "capture.sh").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            _embedded_snapshot_sh(),
            (ROOT / "plugins" / "shared" / "snapshot.sh").read_text(encoding="utf-8"),
        )


class MarketplaceIsolationTests(IsolatedHome):
    def _copy_plugin(self, src: Path) -> Path:
        dest = Path(self.tmp.name) / "marketplace" / src.name
        shutil.copytree(src, dest)
        self.assertFalse((dest.parent / "shared").exists())
        return dest

    def test_claude_plugin_capture_without_shared_uses_cli(self) -> None:
        isolated = self._copy_plugin(ROOT / "plugins" / "claude")
        _assert_no_shared_path(self, isolated / "hooks" / "capture.sh")
        fake, log = _fake_cli(Path(self.tmp.name))
        env = os.environ.copy()
        env["ARDOISE_BIN"] = str(fake)
        proc = subprocess.run(
            [str(isolated / "hooks" / "capture.sh")],
            input='{"hook_event_name":"Stop"}\n',
            text=True,
            capture_output=True,
            env=env,
            cwd=str(isolated),
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(log.read_text(encoding="utf-8").strip(), "capture --stdin")

    def test_claude_plugin_snapshot_without_shared_uses_cli(self) -> None:
        isolated = self._copy_plugin(ROOT / "plugins" / "claude")
        _assert_no_shared_path(self, isolated / "hooks" / "snapshot.sh")
        fake, log = _fake_cli(Path(self.tmp.name), "fake-snapshot")
        env = os.environ.copy()
        env["ARDOISE_BIN"] = str(fake)
        proc = subprocess.run(
            [str(isolated / "hooks" / "snapshot.sh")],
            input="{}\n",
            text=True,
            capture_output=True,
            env=env,
            cwd=str(isolated),
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(log.read_text(encoding="utf-8").strip(), "snapshot anthropic --json")

    def test_cursor_plugin_capture_without_shared_uses_cli(self) -> None:
        isolated = self._copy_plugin(ROOT / "plugins" / "cursor")
        _assert_no_shared_path(self, isolated / "capture.sh")
        fake, log = _fake_cli(Path(self.tmp.name))
        env = os.environ.copy()
        env["ARDOISE_BIN"] = str(fake)
        proc = subprocess.run(
            [str(isolated / "capture.sh")],
            input='{"hook_event_name":"stop"}\n',
            text=True,
            capture_output=True,
            env=env,
            cwd=str(isolated),
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(log.read_text(encoding="utf-8").strip(), "capture --stdin")

    def test_claude_stub_prefers_installed_hook(self) -> None:
        hook_dir = Path(os.environ["ARDOISE_HOME"]) / "hooks"
        hook_dir.mkdir(parents=True, exist_ok=True)
        marker = Path(self.tmp.name) / "installed-ran"
        installed = hook_dir / "capture.sh"
        installed.write_text(
            "#!/bin/sh\n"
            f'printf installed > "{marker}"\n'
            "cat >/dev/null || true\n",
            encoding="utf-8",
        )
        installed.chmod(0o755)
        isolated = self._copy_plugin(ROOT / "plugins" / "claude")
        fake, log = _fake_cli(Path(self.tmp.name))
        env = os.environ.copy()
        env["ARDOISE_BIN"] = str(fake)
        proc = subprocess.run(
            [str(isolated / "hooks" / "capture.sh")],
            input="{}\n",
            text=True,
            capture_output=True,
            env=env,
            cwd=str(isolated),
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "installed")
        self.assertFalse(log.exists())

    def test_hooks_fail_open_when_cli_errors(self) -> None:
        isolated = self._copy_plugin(ROOT / "plugins" / "claude")
        boom = Path(self.tmp.name) / "boom"
        boom.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
        boom.chmod(0o755)
        env = os.environ.copy()
        env["ARDOISE_BIN"] = str(boom)
        env["PATH"] = "/usr/bin:/bin"
        for script in (
            isolated / "hooks" / "capture.sh",
            isolated / "hooks" / "snapshot.sh",
        ):
            proc = subprocess.run(
                [str(script)],
                input="{}\n",
                text=True,
                capture_output=True,
                env=env,
                cwd=str(isolated),
                check=False,
            )
            self.assertEqual(proc.returncode, 0, f"{script} blocked: {proc.stderr}")

    def test_hooks_fail_open_without_cli_or_home(self) -> None:
        isolated = self._copy_plugin(ROOT / "plugins" / "claude")
        env = os.environ.copy()
        env.pop("ARDOISE_BIN", None)
        env.pop("ARDOISE_HOME", None)
        env.pop("HOME", None)
        env["PATH"] = "/usr/bin:/bin"
        proc = subprocess.run(
            [str(isolated / "hooks" / "capture.sh")],
            input="{}\n",
            text=True,
            capture_output=True,
            env=env,
            cwd=str(isolated),
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


class InstallCopyTests(IsolatedHome):
    def test_install_writes_self_contained_hooks(self) -> None:
        result = install(no_plugin_manager=True)
        script = Path(result["script"])
        snap = Path(result["snapshot_script"])
        self.assertTrue(script.is_file())
        self.assertTrue(os.access(script, os.X_OK))
        _assert_no_shared_path(self, script)
        _assert_no_shared_path(self, snap)
        self.assertEqual(script.read_text(encoding="utf-8"), _embedded_capture_sh())
        self.assertIn("ardoise", script.read_text(encoding="utf-8"))
        enqueue = script.parent / "hook_enqueue.py"
        self.assertTrue(enqueue.is_file())
        _assert_no_shared_path(self, enqueue)

        claude = json.loads(Path(result["claude_settings"]).read_text(encoding="utf-8"))
        cursor = json.loads(Path(result["cursor_hooks"]).read_text(encoding="utf-8"))
        self.assertIn(str(script), json.dumps(claude["hooks"]["Stop"]))
        self.assertIn(str(snap), json.dumps(claude["hooks"]["SessionStart"]))
        self.assertIn(str(script), json.dumps(cursor["hooks"]["stop"]))
        self.assertIn("~/.ardoise/hooks", result["mode"])

        fake, log = _fake_cli(Path(self.tmp.name))
        env = os.environ.copy()
        env["ARDOISE_BIN"] = str(fake)
        proc = subprocess.run(
            [str(script)],
            input='{"hook_event_name":"Stop"}\n',
            text=True,
            capture_output=True,
            env=env,
            cwd="/",
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(log.read_text(encoding="utf-8").strip(), "capture --stdin")

        forbidden_keys = (
            "sk-ant-",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_ANALYTICS_API_KEY",
            "CURSOR_ADMIN_API_KEY",
            "access_token",
            "Bearer ",
        )
        installed_root = script.parent
        for path in (script, snap, enqueue, Path(result["claude_settings"]), Path(result["cursor_hooks"])):
            blob = path.read_text(encoding="utf-8")
            for needle in forbidden_keys:
                self.assertNotIn(needle, blob, f"{path} stored {needle!r}")
        for child in installed_root.iterdir():
            if child.is_file() and child.suffix in {".env", ".pem", ".key"}:
                self.fail(f"install wrote a key-like file {child}")


if __name__ == "__main__":
    unittest.main()
