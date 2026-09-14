"""bin/ardoise — status, statement, export, backfill, capture, estimate, snapshot."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from ardoise import __version__, backfill as backfill_mod, capture as capture_mod
from ardoise import estimate as estimate_mod, export as export_mod
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
        description=(
            "Local AI spend ledger for Claude Code and Cursor. "
            "With no command, prints status."
        ),
    )
    parser.add_argument("--version", action="version", version=f"ardoise {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=False)
    parser.set_defaults(cmd="status", json=False, month=None, person=None, estimate=False)

    st = sub.add_parser("status", help="Show ledger totals")
    st.add_argument("--json", action="store_true", help="Print JSON")
    st.add_argument("--month", help="YYYY-MM (default: current UTC month)")
    st.add_argument(
        "--person",
        "--seat",
        "--roster",
        dest="person",
        default=None,
        help="Filter to one seat/person or named agent (view only; does not write the ledger)",
    )
    st.add_argument(
        "--estimate",
        action="store_true",
        help="Also print a $0 estimate stub (use `ardoise estimate` for a real ask)",
    )

    sm = sub.add_parser("statement", help="Write MD+HTML+CSV for a month")
    sm.add_argument("month", help="YYYY-MM")
    sm.add_argument("--out-dir", help="Output directory")
    sm.add_argument(
        "--person",
        "--seat",
        "--roster",
        dest="person",
        default=None,
        help="Filter to one seat/person or named agent (view only; does not write the ledger)",
    )

    ex = sub.add_parser("export", help="Export ledger JSONL (usage only)")
    ex.add_argument("--month", help="YYYY-MM")
    ex.add_argument("--out", help="Write to file instead of stdout")

    bf = sub.add_parser("backfill", help="Ingest ~/.claude and ~/.cursor logs")
    bf.add_argument("--claude-root", help="Override Claude config root")
    bf.add_argument("--cursor-root", help="Override Cursor config root")
    bf.add_argument(
        "--cloud-agent-root",
        "--transcripts",
        dest="transcripts",
        help=(
            "Extra Grok Bot / cloud-agent transcript dir "
            "(also ARDOISE_CLOUD_AGENT_ROOT, config transcripts.paths)"
        ),
    )
    bf.add_argument(
        "--force",
        action="store_true",
        help="Re-read files even when size and mtime match the last ingest",
    )
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

    vendor = sub.add_parser(
        "vendor",
        help="Vendor adapter tools (T0 needs no keys)",
        description=(
            "Vendor adapter tools. T0 capture needs no keys. "
            "Admin T2 and Analytics T2a are advanced (Team/Enterprise) "
            "and stay skipped without a key — not a post-install step."
        ),
        epilog=(
            "Advanced (optional, Team/Enterprise only): "
            "vendor test cursor / vendor pull cursor use CURSOR_ADMIN_API_KEY only. "
            "CURSOR_API_KEY is not an Admin key. Individual Cursor plans have no "
            "Team Admin API. Skipped probe stays T0 (exit 0). See docs/meter-shape.md."
        ),
    )
    vsub = vendor.add_subparsers(dest="vendor_cmd", required=True)
    vt = vsub.add_parser(
        "test",
        help="Print T0 capabilities (advanced: probe optional T2/T2a if a key is set)",
        description=(
            "Print T0 capabilities. Advanced: probe optional T2/T2a if a "
            "Team/Enterprise key is set. Missing key stays T0-only."
        ),
    )
    vt.add_argument("name", help="Vendor name (anthropic, cursor)")
    vt.add_argument("--json", action="store_true")
    vt.add_argument(
        "--verbose",
        action="store_true",
        help="Include unresolved optional credentials (default text stays quiet)",
    )
    vp = vsub.add_parser(
        "pull",
        help="Advanced: pull optional T2/T2a billed events when a Team/Enterprise key is set",
        description=(
            "Advanced: pull optional T2/T2a billed events when a "
            "Team/Enterprise key is set. Individual Cursor plans have no "
            "Team Admin API. Missing key stays T0-only."
        ),
    )
    vp.add_argument("name", help="Vendor name (anthropic, cursor)")
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

    est = sub.add_parser(
        "estimate",
        help="Price a hypothetical token/model ask (stub; never blocks)",
    )
    est.add_argument("--model", default="", help="Model name (price table + prefix match)")
    est.add_argument("--input-tokens", "--input", type=int, default=0, dest="input_tokens")
    est.add_argument("--output-tokens", "--output", type=int, default=0, dest="output_tokens")
    est.add_argument("--cache-read", type=int, default=0, dest="cache_read_tokens")
    est.add_argument("--cache-write", type=int, default=0, dest="cache_creation_tokens")
    est.add_argument("--month", help="YYYY-MM for optional soft-cap remaining (default: current UTC)")
    est.add_argument("--json", action="store_true", help="Print JSON (hook-friendly)")
    est.add_argument("--stdin", action="store_true", help="Read one JSON ask from stdin")

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
    if args.cmd != "estimate":
        paths.ensure_home()
    try:
        if args.cmd == "status":
            month = _check_month(args.month)
            data = status_mod.summarize(month, person=getattr(args, "person", None))
            if args.estimate:
                data["estimate"] = estimate_mod.price_ask(month=month)
            if args.json:
                payload = {k: v for k, v in data.items() if k != "lines"}
                print(json.dumps(payload, indent=2, ensure_ascii=True))
            else:
                sys.stdout.write(status_mod.render_text(data))
                if args.estimate:
                    sys.stdout.write(estimate_mod.render_text(data["estimate"]))
            return 0

        if args.cmd == "estimate":
            month = _check_month(getattr(args, "month", None))
            if args.stdin:
                data = estimate_mod.from_stdin(sys.stdin, month=month)
            else:
                data = estimate_mod.price_ask(
                    model=args.model or None,
                    input_tokens=int(args.input_tokens or 0),
                    output_tokens=int(args.output_tokens or 0),
                    cache_read_tokens=int(args.cache_read_tokens or 0),
                    cache_creation_tokens=int(args.cache_creation_tokens or 0),
                    month=month,
                )
            if args.json:
                print(json.dumps(data, indent=2, ensure_ascii=True))
            else:
                sys.stdout.write(estimate_mod.render_text(data))
            return 0  # fire-and-forget: never fail the caller

        if args.cmd == "statement":
            month = _check_month(args.month)
            if not month:
                return _die("statement requires YYYY-MM")
            out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
            written = statement.write_statement(
                month,
                out_dir=out_dir,
                person=getattr(args, "person", None),
            )
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
            progress = None
            if sys.stderr.isatty() and not args.json:
                progress = backfill_mod.tty_progress
            result = backfill_mod.backfill(
                claude=Path(args.claude_root).expanduser() if args.claude_root else None,
                cursor=Path(args.cursor_root).expanduser() if args.cursor_root else None,
                transcripts=Path(args.transcripts).expanduser() if getattr(args, "transcripts", None) else None,
                force=bool(args.force),
                progress=progress,
            )
            if progress is not None:
                sys.stderr.write("\n")
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(
                    "backfill inserted={inserted} updated={updated} skipped={skipped} "
                    "files={files} skipped_files={skipped_files}".format(**result)
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
                sys.stdout.write(install_hooks.render_text(result))
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
                elif (
                    adapter.name == "cursor"
                    and not result.cred_resolved
                    and not getattr(args, "verbose", False)
                ):
                    detail = str(result.detail or "").rstrip()
                    sys.stdout.write((detail + "\n") if detail else "")
                else:
                    sys.stdout.write(result_text(result))
                return 0
            if args.vendor_cmd == "pull":
                try:
                    adapter = get_adapter(args.name)
                except ValueError as exc:
                    return _die(f"{exc}\nknown: {', '.join(list_adapters())}")
                if adapter.name == "cursor":
                    from ardoise.vendors import cursor as cursor_mod

                    data = cursor_mod.pull()
                    render = cursor_mod.render_pull
                elif adapter.name == "anthropic":
                    from ardoise.vendors.anthropic import t2a as t2a_mod

                    data = t2a_mod.pull()
                    render = t2a_mod.render_pull
                else:
                    return _die(f"T2 pull is implemented for anthropic and cursor, not {adapter.name}")
                if args.json:
                    print(json.dumps(data, indent=2, ensure_ascii=True))
                else:
                    sys.stdout.write(render(data))
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
    except ValueError as exc:
        return _die(str(exc))
    return _die(f"unknown command: {args.cmd}")
