"""Filesystem locations. All overridable for tests / fresh-box."""

from __future__ import annotations

import os
from pathlib import Path


def home() -> Path:
    return Path(os.environ.get("HOME") or Path.home()).expanduser()


def ardoise_home() -> Path:
    override = os.environ.get("ARDOISE_HOME")
    if override:
        return Path(override).expanduser()
    return home() / ".ardoise"


def ledger_path() -> Path:
    override = os.environ.get("ARDOISE_LEDGER")
    if override:
        return Path(override).expanduser()
    return ardoise_home() / "ledger.db"


def queue_dir() -> Path:
    override = os.environ.get("ARDOISE_QUEUE")
    if override:
        return Path(override).expanduser()
    return ardoise_home() / "queue"


def statements_dir() -> Path:
    override = os.environ.get("ARDOISE_STATEMENTS")
    if override:
        return Path(override).expanduser()
    return ardoise_home() / "statements"


def claude_root() -> Path:
    override = os.environ.get("ARDOISE_CLAUDE_ROOT") or os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return home() / ".claude"


def cursor_root() -> Path:
    override = os.environ.get("ARDOISE_CURSOR_ROOT")
    if override:
        return Path(override).expanduser()
    return home() / ".cursor"


def repo_root() -> Path:
    override = os.environ.get("ARDOISE_REPO")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parent.parent


def bundled_prices() -> Path:
    return repo_root() / "data" / "prices.fallback.json"


def user_prices() -> Path:
    return ardoise_home() / "prices.json"


def ensure_home() -> Path:
    root = ardoise_home()
    root.mkdir(parents=True, exist_ok=True)
    queue_dir().mkdir(parents=True, exist_ok=True)
    statements_dir().mkdir(parents=True, exist_ok=True)
    (root / "hooks").mkdir(parents=True, exist_ok=True)
    return root
