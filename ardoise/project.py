"""Resolve spend to git remotes as owner/repo."""

from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_REMOTE_CACHE: dict[tuple[str, str], str | None] = {}
_PROCESS_CWD_FALLBACK = True


def clear_project_cache() -> None:
    _REMOTE_CACHE.clear()


@contextmanager
def without_process_cwd() -> Iterator[None]:
    """During historical backfill, do not attribute rows to the CLI's cwd."""
    global _PROCESS_CWD_FALLBACK
    prev = _PROCESS_CWD_FALLBACK
    _PROCESS_CWD_FALLBACK = False
    try:
        yield
    finally:
        _PROCESS_CWD_FALLBACK = prev


def owner_repo_from_url(url: str | None) -> str | None:
    if not url:
        return None
    raw = url.strip().split()[0]
    if not raw:
        return None
    raw = raw.removesuffix(".git")
    if raw.startswith("git@"):
        try:
            path = raw.split(":", 1)[1]
        except IndexError:
            return None
    elif "://" in raw:
        rest = raw.split("://", 1)[1]
        if "@" in rest.split("/")[0]:
            rest = rest.split("@", 1)[1]
        parts = rest.split("/")
        path = "/".join(parts[1:]) if len(parts) >= 2 else rest
    else:
        path = raw
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def _repo_key(root: Path) -> str:
    try:
        cur = root.resolve() if root.exists() else root
    except OSError:
        cur = root
    parents = [cur]
    try:
        parents.extend(cur.parents)
    except (OSError, AttributeError):
        pass
    for parent in parents:
        try:
            if (parent / ".git").exists():
                return str(parent)
        except OSError:
            continue
    return str(cur)


def git_remote_url(cwd: Path | str | None, *, remote: str = "origin") -> str | None:
    if not cwd:
        return None
    root = Path(cwd)
    key = (_repo_key(root), remote)
    if key in _REMOTE_CACHE:
        return _REMOTE_CACHE[key]
    if not root.exists():
        _REMOTE_CACHE[key] = None
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", remote],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        _REMOTE_CACHE[key] = None
        return None
    if proc.returncode != 0:
        _REMOTE_CACHE[key] = None
        return None
    url = (proc.stdout or "").strip() or None
    _REMOTE_CACHE[key] = url
    return url


def project_from_cwd(cwd: Path | str | None) -> str | None:
    return owner_repo_from_url(git_remote_url(cwd))


def first_project(candidates: list[Path | str | None]) -> str | None:
    for cwd in candidates:
        name = project_from_cwd(cwd)
        if name:
            return name
    return None


def infer_project(
    *,
    cwd: str | None = None,
    workspace_roots: list | None = None,
    allow_process_cwd: bool | None = None,
) -> str | None:
    ordered: list[Path | str | None] = []
    if cwd:
        ordered.append(cwd)
    if workspace_roots:
        ordered.extend(str(x) for x in workspace_roots if x)
    use_process = _PROCESS_CWD_FALLBACK if allow_process_cwd is None else allow_process_cwd
    if use_process:
        ordered.append(os.environ.get("PWD"))
        ordered.append(Path.cwd())
    return first_project(ordered)
