#!/usr/bin/env python3
"""Claude marketplace catalog + Cursor plugin scaffold stay coherent."""

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

from ardoise.install_hooks import install  # noqa: E402

SHARED_FORBIDDEN = ("../shared", "../../shared", "plugins/shared")
SECRET_NEEDLES = (
    "sk-ant-",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_ANALYTICS_API_KEY",
    "CURSOR_ADMIN_API_KEY",
    "access_token",
    "Bearer ",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_no_shared(test: unittest.TestCase, path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for needle in SHARED_FORBIDDEN:
        test.assertNotIn(needle, text, f"{path} still references {needle!r}")
    for needle in SECRET_NEEDLES:
        test.assertNotIn(needle, text, f"{path} stored {needle!r}")


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


class CatalogShapeTests(unittest.TestCase):
    def test_claude_marketplace_points_at_plugins_claude(self) -> None:
        catalog = ROOT / ".claude-plugin" / "marketplace.json"
        self.assertTrue(catalog.is_file(), "missing .claude-plugin/marketplace.json")
        data = _load(catalog)
        self.assertEqual(data["name"], "ardoise")
        self.assertEqual(data["owner"]["name"], "clouvelai")
        self.assertTrue(data["plugins"], "marketplace has no plugins")
        plugin = data["plugins"][0]
        self.assertEqual(plugin["name"], "ardoise")
        self.assertEqual(plugin["source"], "./plugins/claude")
        source = ROOT / "plugins" / "claude"
        self.assertTrue((source / ".claude-plugin" / "plugin.json").is_file())
        self.assertTrue((source / "hooks" / "hooks.json").is_file())
        self.assertTrue((source / "hooks" / "capture.sh").is_file())
        self.assertTrue((source / "hooks" / "snapshot.sh").is_file())
        _assert_no_shared(self, catalog)

    def test_claude_plugin_manifest_matches_catalog(self) -> None:
        catalog = _load(ROOT / ".claude-plugin" / "marketplace.json")
        manifest = _load(ROOT / "plugins" / "claude" / ".claude-plugin" / "plugin.json")
        entry = catalog["plugins"][0]
        self.assertEqual(manifest["name"], entry["name"])
        self.assertEqual(manifest["version"], entry["version"])
        self.assertEqual(manifest["hooks"], "./hooks/hooks.json")
        hooks = _load(ROOT / "plugins" / "claude" / "hooks" / "hooks.json")
        commands = json.dumps(hooks)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/capture.sh", commands)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/snapshot.sh", commands)
        _assert_no_shared(self, ROOT / "plugins" / "claude" / ".claude-plugin" / "plugin.json")
        _assert_no_shared(self, ROOT / "plugins" / "claude" / "hooks" / "hooks.json")

    def test_cursor_plugin_manifests_and_hooks_layout(self) -> None:
        root_manifest = ROOT / ".cursor-plugin" / "plugin.json"
        plugin_manifest = ROOT / "plugins" / "cursor" / ".cursor-plugin" / "plugin.json"
        hooks = ROOT / "plugins" / "cursor" / "hooks" / "hooks.json"
        capture = ROOT / "plugins" / "cursor" / "capture.sh"
        for path in (root_manifest, plugin_manifest, hooks, capture):
            self.assertTrue(path.is_file(), f"missing {path}")
            if path.suffix == ".json":
                _assert_no_shared(self, path)
        root = _load(root_manifest)
        nested = _load(plugin_manifest)
        self.assertEqual(root["name"], "ardoise")
        self.assertEqual(nested["name"], "ardoise")
        self.assertEqual(nested["hooks"], "./hooks/hooks.json")
        root_blob = json.dumps(root["hooks"])
        self.assertIn("${CURSOR_PLUGIN_ROOT}/plugins/cursor/capture.sh", root_blob)
        hook_blob = json.dumps(_load(hooks))
        self.assertIn("${CURSOR_PLUGIN_ROOT}/capture.sh", hook_blob)
        self.assertNotIn("../shared", hook_blob)
        for event in ("stop", "sessionEnd", "afterAgentResponse"):
            self.assertIn(event, root["hooks"])
            self.assertIn(event, _load(hooks)["hooks"])

    def test_cursor_marketplace_points_at_plugins_marketplace(self) -> None:
        catalog = ROOT / ".cursor-plugin" / "marketplace.json"
        self.assertTrue(catalog.is_file(), "missing .cursor-plugin/marketplace.json")
        data = _load(catalog)
        self.assertEqual(data["name"], "ardoise")
        plugin = data["plugins"][0]
        self.assertEqual(plugin["name"], "ardoise")
        self.assertEqual(plugin["source"], "./plugins/marketplace")
        source = ROOT / "plugins" / "marketplace"
        self.assertTrue((source / "plugin.json").is_file())
        self.assertTrue((source / "mcp.json").is_file())
        self.assertTrue((source / ".cursor-plugin" / "plugin.json").is_file())
        self.assertTrue((source / "mcp" / "server.py").is_file())
        self.assertTrue((source / "skills" / "ardoise-usage" / "SKILL.md").is_file())
        _assert_no_shared(self, catalog)
        _assert_no_shared(self, source / "plugin.json")
        _assert_no_shared(self, source / "mcp.json")
        _assert_no_shared(self, source / ".cursor-plugin" / "plugin.json")
        cursor = _load(source / ".cursor-plugin" / "plugin.json")
        self.assertIn("ARDOISE_API_TOKEN", cursor["variables"]["properties"])
        self.assertNotIn("hooks", _load(source / "plugin.json"))


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


class CursorPluginIsolationTests(IsolatedHome):
    def test_cursor_local_copy_without_shared_uses_cli(self) -> None:
        dest = Path(self.tmp.name) / "local" / "ardoise"
        shutil.copytree(ROOT / "plugins" / "cursor", dest)
        self.assertFalse((dest.parent / "shared").exists())
        self.assertTrue((dest / ".cursor-plugin" / "plugin.json").is_file())
        self.assertTrue((dest / "hooks" / "hooks.json").is_file())
        _assert_no_shared(self, dest / "capture.sh")
        fake, log = _fake_cli(Path(self.tmp.name))
        env = os.environ.copy()
        env["ARDOISE_BIN"] = str(fake)
        proc = subprocess.run(
            [str(dest / "capture.sh")],
            input='{"hook_event_name":"stop"}\n',
            text=True,
            capture_output=True,
            env=env,
            cwd=str(dest),
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(log.read_text(encoding="utf-8").strip(), "capture --stdin")

    def test_install_hooks_merge_still_writes_cursor_hooks_json(self) -> None:
        result = install(no_plugin_manager=True)
        cursor = json.loads(Path(result["cursor_hooks"]).read_text(encoding="utf-8"))
        script = result["script"]
        self.assertIn(script, json.dumps(cursor["hooks"]["stop"]))
        self.assertIn("~/.ardoise/hooks", result["mode"])
        self.assertIn("no plugin manager", result["mode"])


if __name__ == "__main__":
    unittest.main()
