"""bin/ardoise — status, statement, export, backfill, capture."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from ardoise import __version__, backfill as backfill_mod, capture as capture_mod
from ardoise import export as export_mod
from ardoise import install_hooks, paths, statement, status as status_mod

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _die(message: str, code: int = 2) -> int:
    print(message, file=sys.stderr)
    return code


def _add_month(parser: argparse.ArgumentParser, *, required: bool = False) -> None:
    parser.add_argument(
        "month" if required else "--month",
        nargs="?" if not required else None,
        help="YYYY-MM (UTC)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ardoise",
        description="Local AI spend ledger for Claude Code and Cursor.",
    )
    parser.add_argument("--version", action="version", version=f"ardoise {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("status", help="Show ledger totals")
    st.add_argument("--json", action="store_true", help="Print JSON")
    st.add_argument("--month", help="YYYY-MM (default: current UTC month)")

    sm = sub.add_parser("statement", help="Write MD+HTML+CSV for a month")
    sm.add_argument("month", help="YYYY-MM")
    sm.add_argument("--out-dir", help="Output directory")

    ex = sub.add_parser("export", help="Export ledger JSONL (usage only)")
    ex.add_argument("--month", help="YYYY-MM")
    ex.add_argument("--out", help="Write to file instead of stdout")

    bf = sub.add_parser("backfill", help="Ingest ~/.claude and ~/.cursor logs")
    bf.add_argument("--claude-root", help="Override Claude config root")
    bf.add_argument("--cursor-root", help="Override Cursor config root")
    bf.add_argument("--json", action="store_true")

    cap = sub.add_parser("capture", help="Drain hook queue or ingest stdin")
    cap.add_argument("--stdin", action="store_true", help="Read one JSON event from stdin")
    cap.add_argument("--queue", help="Override queue directory")
    cap.add_argument("--json", action="store_true")

    inst = sub.add_parser("install-hooks", help="Install shared Claude/Cursor hooks")
    inst.add_argument(
        "--no-plugin-manager",
        action="store_true",
        default=True,
        help="Copy hooks into user settings (default, Phase 1)",
    )
    inst.add_argument("--json", action="store_true")
    return parser


def _check_month(value: str | None) -> str | None:
    if value is None:
        return None
    if not _MONTH_RE.match(value):
        raise ValueError(f"month must be YYYY-MM, got {value!r}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths.ensure_home()
    try:
        if args.cmd == "status":
            month = _check_month(args.month)
            data = status_mod.summarize(month)
            if args.json:
                print(json.dumps(data, indent=2, ensure_ascii=True))
            else:
                sys.stdout.write(status_mod.render_text(data))
            return 0

        if args.cmd == "statement":
            month = _check_month(args.month)
            if not month:
                return _die("statement requires YYYY-MM")
            out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
            written = statement.write_statement(month, out_dir=out_dir)
            print(json.dumps(written, indent=2, ensure_ascii=True))
            return 0

        if args.cmd == "export":
            month = _check_month(args.month)
            dest = Path(args.out).expanduser() if args.out else None
            n = export_mod.write_export(dest, month=month)
            if dest:
                print(json.dumps({"written": n, "out": str(dest)}, indent=2))
            return 0

        if args.cmd == "backfill":
            result = backfill_mod.backfill(
                claude=Path(args.claude_root).expanduser() if args.claude_root else None,
                cursor=Path(args.cursor_root).expanduser() if args.cursor_root else None,
            )
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(
                    "backfill inserted={inserted} updated={updated} skipped={skipped} files={files}".format(
                        **result
                    )
                )
            return 0

        if args.cmd == "capture":
            result = capture_mod.capture(
                stdin=bool(args.stdin),
                queue_path=Path(args.queue).expanduser() if args.queue else None,
            )
            # Hooks treat stdout as protocol. Stay silent unless --json.
            if args.json:
                print(json.dumps(result, indent=2))
            elif not args.stdin:
                print(
                    "capture inserted={inserted} updated={updated} skipped={skipped}".format(
                        **{k: result.get(k, 0) for k in ("inserted", "updated", "skipped")}
                    )
                )
            return 0

        if args.cmd == "install-hooks":
            result = install_hooks.install(no_plugin_manager=True)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                for key, value in result.items():
                    print(f"{key}: {value}")
            return 0
    except ValueError as exc:
        return _die(str(exc))
    return _die(f"unknown command: {args.cmd}")
