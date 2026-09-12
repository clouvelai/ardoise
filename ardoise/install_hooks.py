"""Install shared Claude Code + Cursor hooks without a plugin manager."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from ardoise import paths

MARKER = "ardoise-capture"


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    return data if isinstance(data, type(default)) else default


def _dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _script_path() -> Path:
    dest = paths.ardoise_home() / "hooks" / "capture.sh"
    return dest


def install_capture_script() -> Path:
    paths.ensure_home()
    src = paths.repo_root() / "plugins" / "shared" / "capture.sh"
    dest = _script_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        shutil.copyfile(src, dest)
    else:
        dest.write_text(_embedded_capture_sh(), encoding="utf-8")
    dest.chmod(0o755)
    enqueue = paths.repo_root() / "plugins" / "shared" / "hook_enqueue.py"
    if enqueue.is_file():
        target = dest.parent / "hook_enqueue.py"
        shutil.copyfile(enqueue, target)
    return dest


def _embedded_capture_sh() -> str:
    return """#!/bin/sh
set -eu
if [ -n "${ARDOISE_BIN:-}" ] && [ -x "$ARDOISE_BIN" ]; then
  exec "$ARDOISE_BIN" capture --stdin || exit 0
fi
if command -v ardoise >/dev/null 2>&1; then
  exec ardoise capture --stdin || exit 0
fi
if [ -x "$HOME/.local/bin/ardoise" ]; then
  exec "$HOME/.local/bin/ardoise" capture --stdin || exit 0
fi
exit 0
"""


def _claude_command(script: Path) -> str:
    return str(script)


def merge_claude_settings(settings_path: Path, script: Path) -> None:
    data = _load_json(settings_path, {})
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks
    command = _claude_command(script)
    for event in ("Stop", "SessionEnd"):
        entries = hooks.get(event)
        if not isinstance(entries, list):
            entries = []
            hooks[event] = entries
        # Drop previous Ardoise entries
        kept = []
        for item in entries:
            blob = json.dumps(item)
            if MARKER in blob or str(script) in blob:
                continue
            kept.append(item)
        kept.append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                    }
                ]
            }
        )
        hooks[event] = kept
    _dump_json(settings_path, data)


def merge_cursor_hooks(hooks_path: Path, script: Path) -> None:
    data = _load_json(hooks_path, {"version": 1, "hooks": {}})
    if "hooks" not in data or not isinstance(data["hooks"], dict):
        data["hooks"] = {}
    data.setdefault("version", 1)
    command = str(script)
    for event in ("stop", "sessionEnd", "afterAgentResponse"):
        entries = data["hooks"].get(event)
        if not isinstance(entries, list):
            entries = []
        kept = []
        for item in entries:
            if MARKER in json.dumps(item) or str(script) in json.dumps(item):
                continue
            kept.append(item)
        kept.append({"command": command})
        data["hooks"][event] = kept
    _dump_json(hooks_path, data)


def link_bin() -> Path | None:
    src = paths.repo_root() / "bin" / "ardoise"
    if not src.is_file():
        return None
    dest_dir = Path.home() / ".local" / "bin"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "ardoise"
    try:
        if dest.is_symlink() or dest.exists():
            dest.unlink()
        dest.symlink_to(src.resolve())
        dest.chmod(0o755)
        return dest
    except OSError:
        shutil.copyfile(src, dest)
        dest.chmod(0o755)
        return dest


def install(*, no_plugin_manager: bool = True) -> dict[str, str]:
    if not no_plugin_manager:
        # Phase 1 only supports the file-copy path.
        no_plugin_manager = True
    script = install_capture_script()
    claude_settings = paths.home() / ".claude" / "settings.json"
    cursor_hooks = paths.cursor_root() / "hooks.json"
    merge_claude_settings(claude_settings, script)
    merge_cursor_hooks(cursor_hooks, script)
    bound = link_bin()
    plugin_note = "copied hooks into ~/.claude/settings.json and ~/.cursor/hooks.json (no plugin manager)"
    return {
        "script": str(script),
        "claude_settings": str(claude_settings),
        "cursor_hooks": str(cursor_hooks),
        "bin": str(bound or ""),
        "mode": plugin_note,
    }
