#!/usr/bin/env python3
"""Python 3.9 import safety — macOS Xcode python3 is 3.9.6.

``from __future__ import annotations`` postpones function/variable
annotations but not type-alias *assignments*. A PEP 604 ``dict[str, Any] | None``
inside ``Transport = Callable[...]`` is evaluated at import and raises:

    TypeError: unsupported operand type(s) for |: 'types.GenericAlias' and 'NoneType'
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCAN_ROOTS = (
    ROOT / "ardoise",
    ROOT / "plugins" / "marketplace" / "mcp",
    ROOT / "plugins" / "shared",
    ROOT / "bin",
)


def _looks_like_type(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and node.value is None:
        return True
    if isinstance(node, ast.Subscript):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return True
    return False


def _has_pep604_type_union(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.BinOp) or not isinstance(child.op, ast.BitOr):
            continue
        if _looks_like_type(child.left) or _looks_like_type(child.right):
            return True
    return False


def _runtime_pep604_hits(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _has_pep604_type_union(node.value):
            hits.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        elif (
            isinstance(node, ast.AnnAssign)
            and node.value is not None
            and _has_pep604_type_union(node.value)
        ):
            hits.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return hits


def _has_future_annotations(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if any(alias.name == "annotations" for alias in node.names):
                return True
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Expr)):
            continue
        break
    return False


def _uses_annotations(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and (
            node.returns is not None or any(a.annotation for a in node.args.args)
        ):
            return True
        if isinstance(node, ast.AnnAssign):
            return True
        if isinstance(node, ast.ClassDef) and any(
            isinstance(child, ast.AnnAssign) for child in node.body
        ):
            return True
    return False


class Py39ImportTests(unittest.TestCase):
    def test_cli_entry_imports(self) -> None:
        from ardoise.cli import main

        self.assertTrue(callable(main))

    def test_t2a_module_imports(self) -> None:
        from ardoise.vendors.anthropic import t2a
        from ardoise.vendors import cursor
        from ardoise import document

        self.assertIsNotNone(t2a.Transport)
        self.assertIsNotNone(cursor.Transport)
        self.assertIsNotNone(document.RateFn)

    def test_runtime_type_aliases_avoid_pep604(self) -> None:
        """Rebuild the aliases the way 3.9 evaluates them at import."""
        from typing import Any, Callable, Optional

        from ardoise import document
        from ardoise.vendors import cursor
        from ardoise.vendors.anthropic import t2a

        expected = Callable[[str, str, Optional[dict[str, Any]]], dict[str, Any]]
        self.assertEqual(t2a.Transport, expected)
        self.assertEqual(cursor.Transport, expected)
        self.assertEqual(
            document.RateFn,
            Callable[[Optional[str], str], Optional[float]],
        )

    def test_no_runtime_pep604_unions_in_package(self) -> None:
        hits: list[str] = []
        for root in SCAN_ROOTS:
            if not root.exists():
                continue
            paths = [root] if root.is_file() else sorted(root.rglob("*.py"))
            for path in paths:
                if path.is_file() and path.suffix == ".py":
                    hits.extend(_runtime_pep604_hits(path))
        self.assertEqual(
            hits,
            [],
            "PEP 604 `|` in a runtime assignment crashes Python 3.9 at import "
            "(macOS Xcode python3). Use Optional/Union for type aliases.",
        )

    def test_annotated_modules_postpone_hints(self) -> None:
        missing: list[str] = []
        for root in (ROOT / "ardoise", ROOT / "plugins" / "marketplace" / "mcp"):
            for path in sorted(root.rglob("*.py")):
                if _uses_annotations(path) and not _has_future_annotations(path):
                    missing.append(str(path.relative_to(ROOT)))
        self.assertEqual(
            missing,
            [],
            "modules with annotations need from __future__ import annotations "
            "so PEP 585/604 hints stay import-safe on Python 3.9",
        )


if __name__ == "__main__":
    unittest.main()
