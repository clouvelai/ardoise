"""Resolve spend to git remotes as owner/repo."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable

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


def git_remote_url(cwd: Path | str | None, *, remote: str = "origin") -> str | None:
    if not cwd:
        return None
    root = Path(cwd)
    if not root.exists():
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
        return None
    if proc.returncode != 0:
        return None
    url = (proc.stdout or "").strip()
    return url or None


def project_from_cwd(cwd: Path | str | None) -> str | None:
    return owner_repo_from_url(git_remote_url(cwd))


def first_project(candidates: Iterable[Path | str | None]) -> str | None:
    for cwd in candidates:
        name = project_from_cwd(cwd)
        if name:
            return name
    return None


def infer_project(*, cwd: str | None = None, workspace_roots: list | None = None) -> str | None:
    ordered: list[Path | str | None] = []
    if cwd:
        ordered.append(cwd)
    if workspace_roots:
        ordered.extend(str(x) for x in workspace_roots if x)
    ordered.append(os.environ.get("PWD"))
    ordered.append(Path.cwd())
    return first_project(ordered)
