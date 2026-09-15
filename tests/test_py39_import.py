#!/usr/bin/env python3
"""Python 3.9 import / parse safety — macOS Xcode python3 is 3.9.6.

``from __future__ import annotations`` postpones function/variable
annotations but not type-alias *assignments*. A PEP 604 ``dict[str, Any] | None``
inside ``Transport = Callable[...]`` is evaluated at import and raises:

    TypeError: unsupported operand type(s) for |: 'types.GenericAlias' and 'NoneType'

Nested same-quote f-string indexes (pre-PEP 701) are a SyntaxError on 3.9:

    SyntaxError: f-string: unmatched '['
"""

from __future__ import annotations

import ast
import os
import re
import sys
import tempfile
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


# Pre-PEP 701 (3.9–3.11): same quote as the f-string delimiter inside `{...}`
# is a SyntaxError (`f"{row["k"]}"`). ast.parse on CI's 3.12+ will not catch it.
_FSTRING_SAME_QUOTE_INDEX = (
    re.compile(r'(?i)(?:r)?f"(?:[^"\\]|\\.)*\{(?:[^{}"\\]|\\.)*\["', re.S),
    re.compile(r"(?i)(?:r)?f'(?:[^'\\]|\\.)*\{(?:[^{}'\\]|\\.)*\['", re.S),
)


def _fstring_same_quote_index_hits_text(text: str, label: str) -> list[str]:
    hits: list[str] = []
    for pattern in _FSTRING_SAME_QUOTE_INDEX:
        for match in pattern.finditer(text):
            lineno = text.count("\n", 0, match.start()) + 1
            hits.append(f"{label}:{lineno}")
    return hits


def _fstring_same_quote_index_hits(path: Path) -> list[str]:
    return _fstring_same_quote_index_hits_text(
        path.read_text(encoding="utf-8"),
        str(path.relative_to(ROOT)),
    )


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

    def test_launcher_shebang_stays_env_python3(self) -> None:
        """Mac Homebrew may ship 3.13/3.14; env python3 is still Xcode 3.9.6."""
        text = (ROOT / "bin" / "ardoise").read_text(encoding="utf-8")
        first = text.splitlines()[0]
        self.assertEqual(first, "#!/usr/bin/env python3")
        self.assertNotIn("homebrew", first.lower())
        self.assertNotRegex(first, r"python3\.\d+")

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

    def test_fstring_heuristic_flags_the_mac_crash_shape(self) -> None:
        """Lock: the 3.9 SyntaxError at statement.py:338 stays detectable on 3.12."""
        bad = 'cell = f"{float(r["allocated_billed_usd"]):.2f}"\n'
        good = 'alloc = r["allocated_billed_usd"]\ncell = f"{float(alloc):.2f}"\n'
        also_good = "cell = f'{float(r[\"allocated_billed_usd\"]):.2f}'\n"
        self.assertEqual(
            _fstring_same_quote_index_hits_text(bad, "crash.py"),
            ["crash.py:1"],
        )
        self.assertEqual(_fstring_same_quote_index_hits_text(good, "ok.py"), [])
        self.assertEqual(_fstring_same_quote_index_hits_text(also_good, "ok2.py"), [])

    def test_no_nested_same_quote_fstring_indexes(self) -> None:
        """3.9 rejects same-quote indexes inside f-strings (pre-PEP 701).

        ``f"{row['k']}"`` is fine; matching quotes are a SyntaxError.
        ast.parse on CI's 3.12+ accepts the bad form, so this is a source scan.
        """
        hits: list[str] = []
        for root in SCAN_ROOTS:
            if not root.exists():
                continue
            paths = [root] if root.is_file() else sorted(root.rglob("*.py"))
            for path in paths:
                if path.is_file() and path.suffix == ".py":
                    hits.extend(_fstring_same_quote_index_hits(path))
        self.assertEqual(
            hits,
            [],
            "nested same-quote f-string index is a SyntaxError on Python 3.9 "
            "(macOS Xcode python3). Pull the value out or use the other quote.",
        )

    def test_statement_html_formats_allocated_billed_usd(self) -> None:
        """Regression for statement.py:338 — import + render the HTML row."""
        from ardoise.statement import _html_page, _md

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.environ["HOME"] = tmp.name
        os.environ["ARDOISE_HOME"] = str(Path(tmp.name) / ".ardoise")
        for key in ("ARDOISE_LEDGER", "ARDOISE_QUEUE", "ARDOISE_STATEMENTS"):
            os.environ.pop(key, None)

        summary = {
            "month": "2026-09",
            "by_agent": [
                {
                    "agent": "Explore",
                    "entries": 3,
                    "cost_usd": 0.1234,
                    "allocated_billed_usd": 12.5,
                }
            ],
            "by_skill": [
                {
                    "skill": "session-retrospective",
                    "entries": 1,
                    "cost_usd": 0.01,
                    "allocated_billed_usd": None,
                }
            ],
        }
        html = _html_page(summary)
        md = _md(summary)
        self.assertIn("Explore", html)
        self.assertIn("12.50", html)
        self.assertIn("Allocated billed", html)
        attr = html.split('section class="quiet"')[1]
        self.assertIn("session-retrospective", attr)
        self.assertRegex(attr, r">—<")
        self.assertIn("| Explore | 3 | 0.1234 | 12.50 |", md)
        self.assertIn("| session-retrospective | 1 | 0.0100 | — |", md)

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
