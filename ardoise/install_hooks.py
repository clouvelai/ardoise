"""Install shared Claude Code + Cursor hooks without a plugin manager.

Canonical target is ``~/.ardoise/hooks/`` (self-contained scripts that invoke
``ardoise`` on PATH or ``~/.local/bin/ardoise``). Plugin trees under
``plugins/claude`` and ``plugins/cursor`` must not resolve ``../shared`` at
runtime — marketplace copies only ship the plugin directory.
"""

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


def _snapshot_script_path() -> Path:
    return paths.ardoise_home() / "hooks" / "snapshot.sh"


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
    install_snapshot_script()
    return dest


def install_snapshot_script() -> Path:
    """SessionStart trigger: ``ardoise snapshot anthropic`` (T1, throttled)."""
    paths.ensure_home()
    src = paths.repo_root() / "plugins" / "shared" / "snapshot.sh"
    dest = _snapshot_script_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        shutil.copyfile(src, dest)
    else:
        dest.write_text(_embedded_snapshot_sh(), encoding="utf-8")
    dest.chmod(0o755)
    return dest


def _embedded_capture_sh() -> str:
    return """#!/bin/sh
# Shared Claude Code + Cursor hook. Reads one JSON event on stdin.
# Never prints prompts. Always exits 0 so the agent loop is not blocked.
# Self-contained: invoke ardoise on PATH or ~/.local/bin — not a sibling shared/ tree.
set -eu
trap 'exit 0' EXIT
ARDOISE_HOOK=1
export ARDOISE_HOOK

if [ -n "${ARDOISE_BIN:-}" ] && [ -x "${ARDOISE_BIN}" ]; then
  "${ARDOISE_BIN}" capture --stdin >/dev/null 2>&1 || true
  exit 0
fi

if command -v ardoise >/dev/null 2>&1; then
  ardoise capture --stdin >/dev/null 2>&1 || true
  exit 0
fi

if [ -x "${HOME:-}/.local/bin/ardoise" ]; then
  "${HOME}/.local/bin/ardoise" capture --stdin >/dev/null 2>&1 || true
  exit 0
fi

exit 0
"""


def _embedded_snapshot_sh() -> str:
    return """#!/bin/sh
# Claude Code SessionStart → Anthropic T1 seat snapshot (throttled, 3 min).
# Discard hook stdin. Never print prompts. Always exit 0.
# Self-contained: invoke ardoise on PATH or ~/.local/bin — not a sibling shared/ tree.
set -eu
trap 'exit 0' EXIT
ARDOISE_HOOK=1
export ARDOISE_HOOK
cat >/dev/null || true

if [ -n "${ARDOISE_BIN:-}" ] && [ -x "${ARDOISE_BIN}" ]; then
  "${ARDOISE_BIN}" snapshot anthropic --json >/dev/null 2>&1 || true
  exit 0
fi

if command -v ardoise >/dev/null 2>&1; then
  ardoise snapshot anthropic --json >/dev/null 2>&1 || true
  exit 0
fi

if [ -x "${HOME:-}/.local/bin/ardoise" ]; then
  "${HOME}/.local/bin/ardoise" snapshot anthropic --json >/dev/null 2>&1 || true
  exit 0
fi

exit 0
"""


def _claude_command(script: Path) -> str:
    return str(script)


def _merge_claude_event(
    hooks: dict[str, Any],
    event: str,
    script: Path,
    extra_drop: tuple[Path, ...] = (),
) -> None:
    command = _claude_command(script)
    entries = hooks.get(event)
    if not isinstance(entries, list):
        entries = []
        hooks[event] = entries
    kept = []
    for item in entries:
        blob = json.dumps(item)
        if MARKER in blob or str(script) in blob:
            continue
        if any(str(path) in blob for path in extra_drop):
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


def merge_claude_settings(settings_path: Path, script: Path, snapshot_script: Path | None = None) -> None:
    data = _load_json(settings_path, {})
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks
    for event in ("Stop", "SessionEnd"):
        _merge_claude_event(hooks, event, script)
    snap = snapshot_script or _snapshot_script_path()
    _merge_claude_event(hooks, "SessionStart", snap, extra_drop=(script,))
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


def _on_path(bound: Path | None) -> bool:
    if bound is None:
        return False
    parts = (os.environ.get("PATH") or "").split(os.pathsep)
    return str(bound.parent) in parts


def render_text(result: dict[str, str]) -> str:
    bound = result.get("bin") or ""
    on_path = result.get("on_path") == "yes"
    lines = [
        "Installed Ardoise.",
        "",
        f"  binary   {bound or '(not linked)'}",
        f"  hooks    {result.get('claude_settings')} + {result.get('cursor_hooks')}",
        "",
    ]
    if bound and not on_path:
        lines.append(f"  PATH     {Path(bound).parent} is not on PATH — add it, or call the binary by full path.")
        lines.append("")
    lines.extend(
        [
            "Next:",
            "  ardoise backfill",
            "  ardoise status",
            "",
        ]
    )
    return "\n".join(lines)


def install(*, no_plugin_manager: bool = True) -> dict[str, str]:
    if not no_plugin_manager:
        # Phase 1 only supports the file-copy path.
        no_plugin_manager = True
    script = install_capture_script()
    snapshot_script = install_snapshot_script()
    claude_settings = paths.home() / ".claude" / "settings.json"
    cursor_hooks = paths.cursor_root() / "hooks.json"
    merge_claude_settings(claude_settings, script, snapshot_script)
    merge_cursor_hooks(cursor_hooks, script)
    bound = link_bin()
    plugin_note = (
        "copied self-contained hooks into ~/.ardoise/hooks and merged "
        "~/.claude/settings.json + ~/.cursor/hooks.json (no plugin manager); "
        "marketplace Claude plugin stubs resolve these hooks or ardoise on PATH"
    )
    on_path = _on_path(bound)
    return {
        "script": str(script),
        "snapshot_script": str(snapshot_script),
        "claude_settings": str(claude_settings),
        "cursor_hooks": str(cursor_hooks),
        "bin": str(bound or ""),
        "on_path": "yes" if on_path else "no",
        "next": "ardoise backfill && ardoise status",
        "mode": plugin_note,
    }
