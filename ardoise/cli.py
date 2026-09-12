"""bin/ardoise — status, statement, export, backfill, capture, snapshot, budget."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from ardoise import __version__, backfill as backfill_mod, capture as capture_mod
from ardoise import budget as budget_mod, export as export_mod
from ardoise import install_hooks, invoice as invoice_mod, paths, snapshot as snapshot_mod
from ardoise import statement, status as status_mod
from ardoise.vendors import get_adapter, list_adapters, result_text

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

    vendor = sub.add_parser("vendor", help="Vendor adapter tools")
    vsub = vendor.add_subparsers(dest="vendor_cmd", required=True)
    vt = vsub.add_parser("test", help="Print capabilities and whether credentials resolve")
    vt.add_argument("name", help="Vendor name (anthropic, cursor)")
    vt.add_argument("--json", action="store_true")
    vp = vsub.add_parser("pull", help="Pull T2 usage events into the ledger")
    vp.add_argument("name", help="Vendor name (cursor)")
    vp.add_argument("--json", action="store_true")

    snap = sub.add_parser("snapshot", help="Record a vendor T1 seat snapshot")
    snap.add_argument(
        "vendor",
        nargs="?",
        default="anthropic",
        help="Vendor name (default: anthropic)",
    )
    snap.add_argument("--json", action="store_true")
    snap.add_argument(
        "--force",
        action="store_true",
        help="Bypass the 3-minute T1 throttle",
    )

    inv = sub.add_parser("invoice", help="Owner-received vendor totals for statement section A")
    isub = inv.add_subparsers(dest="invoice_cmd", required=True)
    ia = isub.add_parser("add", help="Paste one Stripe/vendor total (idempotent on vendor+cycle+person)")
    ia.add_argument("--vendor", required=True, help="anthropic or cursor")
    ia.add_argument("--cycle", required=True, help="YYYY-MM")
    ia.add_argument("--usd-cents", type=int, dest="usd_cents", help="Integer USD cents")
    ia.add_argument("--usd", type=float, help="USD dollars (converted to cents)")
    ia.add_argument("--person", default="", help="Person/scope (default: empty)")
    ia.add_argument("--notes", help="Free-text (invoice id, Stripe memo) — not a secret")
    ia.add_argument("--source", default="paste", choices=("paste", "t1", "t2"))
    ia.add_argument("--json", action="store_true")
    ip = isub.add_parser("paste", help="Bulk ingest JSON / JSONL / CSV (same upsert as add)")
    ip.add_argument("--file", help="Invoice file (otherwise stdin)")
    ip.add_argument("--json", action="store_true")

    bud = sub.add_parser("budget", help="Soft spend caps (warn only, never block)")
    bsub = bud.add_subparsers(dest="budget_cmd", required=True)
    bs = bsub.add_parser("set", help="Upsert a day or month cap (usd or tokens)")
    bs.add_argument("--period", required=True, help="day or month")
    bs.add_argument("--usd", type=float, help="USD cap")
    bs.add_argument("--tokens", type=int, dest="tokens", help="input+output token cap")
    bs.add_argument("--json", action="store_true")
    bl = bsub.add_parser("list", help="Show configured caps")
    bl.add_argument("--json", action="store_true")
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

        if args.cmd == "vendor":
            if args.vendor_cmd == "test":
                try:
                    adapter = get_adapter(args.name)
                except ValueError as exc:
                    return _die(f"{exc}\nknown: {', '.join(list_adapters())}")
                result = adapter.test()
                if args.json:
                    print(json.dumps(result.as_dict(), indent=2, ensure_ascii=True))
                else:
                    sys.stdout.write(result_text(result))
                return 0
            if args.vendor_cmd == "pull":
                try:
                    adapter = get_adapter(args.name)
                except ValueError as exc:
                    return _die(f"{exc}\nknown: {', '.join(list_adapters())}")
                if adapter.name != "cursor":
                    return _die(f"T2 pull is implemented for cursor only, not {adapter.name}")
                from ardoise.vendors import cursor as cursor_mod

                data = cursor_mod.pull()
                if args.json:
                    print(json.dumps(data, indent=2, ensure_ascii=True))
                else:
                    sys.stdout.write(cursor_mod.render_pull(data))
                return 0 if data.get("ok") else 2
            return _die(f"unknown vendor command: {args.vendor_cmd}")

        if args.cmd == "snapshot":
            result = snapshot_mod.record_vendor_snapshot(
                args.vendor,
                force=bool(args.force),
            )
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=True))
            else:
                vendor = result.get("vendor") or args.vendor
                reason = result.get("reason") or "ok"
                extra = result.get("extra_usage") if isinstance(result.get("extra_usage"), dict) else {}
                delta = extra.get("delta")
                recorded = "recorded" if result.get("recorded") else "not-recorded"
                print(
                    f"snapshot vendor={vendor} empty={bool(result.get('empty'))} "
                    f"reason={reason} delta={delta} {recorded}"
                )
            return 0

        if args.cmd == "invoice":
            if args.invoice_cmd == "add":
                if args.usd_cents is None and args.usd is None:
                    return _die("invoice add needs --usd-cents or --usd")
                result = invoice_mod.add(
                    vendor=args.vendor,
                    cycle=_check_month(args.cycle) or args.cycle,
                    usd_cents=args.usd_cents,
                    usd=args.usd,
                    person=args.person or "",
                    notes=args.notes,
                    source=args.source,
                )
                if args.json:
                    print(json.dumps(result, indent=2, ensure_ascii=True))
                else:
                    print(
                        "invoice add {result} vendor={vendor} cycle={cycle} "
                        "person={person!r} usd_cents={usd_cents} source={source}".format(**result)
                    )
                return 0
            if args.invoice_cmd == "paste":
                if args.file:
                    result = invoice_mod.paste(path=Path(args.file).expanduser())
                else:
                    result = invoice_mod.paste(stream=sys.stdin)
                if args.json:
                    print(json.dumps(result, indent=2, ensure_ascii=True))
                else:
                    print(
                        "invoice paste inserted={inserted} updated={updated} rows={rows}".format(
                            **result
                        )
                    )
                return 0
            return _die(f"unknown invoice command: {args.invoice_cmd}")

        if args.cmd == "budget":
            if args.budget_cmd == "set":
                if (args.usd is None) == (args.tokens is None):
                    return _die("budget set needs exactly one of --usd or --tokens")
                metric = "usd" if args.usd is not None else "tokens"
                limit = args.usd if args.usd is not None else args.tokens
                result = budget_mod.upsert(period=args.period, metric=metric, limit=float(limit))
                if args.json:
                    print(json.dumps(result, indent=2, ensure_ascii=True))
                else:
                    print(
                        "budget {result} {id} limit={limit}".format(
                            result=result["result"],
                            id=result["id"],
                            limit=result["limit"],
                        )
                    )
                return 0
            if args.budget_cmd == "list":
                rows = budget_mod.load()
                if args.json:
                    print(json.dumps({"budgets": rows, "path": str(paths.budgets_path())}, indent=2))
                elif not rows:
                    print(f"(no budgets — {paths.budgets_path()})")
                else:
                    print(f"{'period':<8} {'metric':<8} limit")
                    for row in rows:
                        limit = row["limit"]
                        shown = f"{int(limit)}" if row["metric"] == "tokens" else f"{limit:.2f}"
                        print(f"{row['period']:<8} {row['metric']:<8} {shown}")
                return 0
            return _die(f"unknown budget command: {args.budget_cmd}")
    except ValueError as exc:
        return _die(str(exc))
    return _die(f"unknown command: {args.cmd}")
