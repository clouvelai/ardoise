#!/bin/sh
# Offline acceptance: isolated HOME, fixture logs, FRESH-BOX-OK.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BOX=$(mktemp -d)
trap 'rm -rf "$BOX"' EXIT

export HOME="$BOX/home"
export ARDOISE_HOME="$HOME/.ardoise"
unset ARDOISE_LEDGER ARDOISE_QUEUE ARDOISE_STATEMENTS ARDOISE_CLAUDE_ROOT ARDOISE_CURSOR_ROOT
unset CURSOR_ADMIN_API_KEY CURSOR_API_KEY CURSOR_ADMIN_API_BASE
unset ANTHROPIC_ANALYTICS_API_KEY ANTHROPIC_ANALYTICS_KEY ANTHROPIC_ANALYTICS_API_BASE
mkdir -p "$HOME"

PROJ="$BOX/proj"
mkdir -p "$PROJ"
git init -q -b main "$PROJ"
git -C "$PROJ" remote add origin git@github.com:clouvelai/Arbusteia.git

chmod +x "$ROOT/bin/ardoise" \
  "$ROOT/install.sh" \
  "$ROOT/plugins/shared/capture.sh" \
  "$ROOT/plugins/shared/snapshot.sh" \
  "$ROOT/plugins/claude/hooks/capture.sh" \
  "$ROOT/plugins/claude/hooks/snapshot.sh" \
  "$ROOT/plugins/cursor/capture.sh"

"$ROOT/install.sh" --no-plugin-manager >/dev/null

# --- fixtures with this box's project cwd ---
CLAUDE_DIR="$HOME/.claude/projects/-tmp-proj"
CURSOR_DIR="$HOME/.cursor/projects/proj"
mkdir -p "$CLAUDE_DIR" "$CURSOR_DIR"
sed "s|/WORKSPACE|$PROJ|g" "$ROOT/tests/fixtures/anthropic_t0.jsonl" \
  > "$CLAUDE_DIR/session.jsonl"
sed "s|/WORKSPACE|$PROJ|g" "$ROOT/tests/fixtures/cursor.jsonl" \
  > "$CURSOR_DIR/chat.jsonl"

# hook queue: duplicate of msg_01AAA plus a unique cursor-shaped event
python3 - "$PROJ" "$HOME/.ardoise/queue" "$ROOT/tests/fixtures/hook_event.json" <<'PY'
import json, sys
from pathlib import Path
proj, qdir, hook = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
qdir.mkdir(parents=True, exist_ok=True)
raw = json.loads(hook.read_text())
raw["cwd"] = proj
# leave prompt in the file we feed through capture --stdin to prove stripping
stdin_path = qdir.parent / "hook-stdin.json"
stdin_path.write_text(json.dumps(raw))
PY

BIN="$ROOT/bin/ardoise"

# capture stdin (hook path) then backfill transcripts
HOOK_STDIN="$HOME/.ardoise/hook-stdin.json"
"$BIN" capture --stdin < "$HOOK_STDIN"
"$BIN" backfill --json >"$BOX/backfill.json"

"$BIN" status --json --month 2026-09 >"$BOX/status.json"
"$BIN" statement 2026-09 --out-dir "$HOME/.ardoise/statements" >"$BOX/statement.json"
"$BIN" export --month 2026-09 --out "$BOX/export.jsonl" >"$BOX/export-meta.json"
"$BIN" vendor test anthropic --json >"$BOX/vendor-anthropic.json"
"$BIN" vendor test anthropic >"$BOX/vendor-anthropic.txt"
"$BIN" vendor pull anthropic >"$BOX/vendor-pull-anthropic.txt"
"$BIN" vendor test cursor --json >"$BOX/vendor-cursor.json"
"$BIN" vendor test cursor >"$BOX/vendor-test.txt"
"$BIN" snapshot anthropic --json >"$BOX/snapshot.json"

python3 - "$BOX" "$HOME" <<'PY'
import json, sqlite3, sys
from pathlib import Path

box = Path(sys.argv[1])
home = Path(sys.argv[2])
status = json.loads((box / "status.json").read_text())
ledger = home / ".ardoise" / "ledger.db"
conn = sqlite3.connect(ledger)
conn.row_factory = sqlite3.Row
n = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
if n != 3:
    raise SystemExit(f"expected 3 ledger rows after dedupe, got {n}")

aaa = conn.execute(
    "SELECT * FROM entries WHERE message_id = 'msg_01AAA' AND request_id = 'req_01AAA'"
).fetchone()
if aaa is None:
    raise SystemExit("missing deduped anthropic row")
if int(aaa["output_tokens"]) != 400:
    raise SystemExit(f"dedupe kept output_tokens={aaa['output_tokens']}, want 400")
if abs(float(aaa["cost_usd"]) - 0.0195) > 1e-6:
    raise SystemExit(f"sonnet cost {aaa['cost_usd']} != 0.0195")
if aaa["project"] != "clouvelai/Arbusteia":
    raise SystemExit(f"project={aaa['project']!r}, want clouvelai/Arbusteia")

haiku = conn.execute(
    "SELECT * FROM entries WHERE message_id = 'msg_01BBB'"
).fetchone()
if haiku is None or abs(float(haiku["cost_usd"]) - 0.001) > 1e-6:
    raise SystemExit(f"haiku row missing or bad cost: {None if haiku is None else haiku['cost_usd']}")

cur = conn.execute(
    "SELECT * FROM entries WHERE message_id = 'msg_cursor_1'"
).fetchone()
if cur is None:
    raise SystemExit("missing cursor row")
if cur["source"] != "cursor":
    raise SystemExit(f"cursor source={cur['source']!r}")

# privacy: no prompts in sqlite or export
blob = Path(ledger).read_bytes()
for needle in (b"SECRET_PROMPT", b"SECRET_ASSISTANT", b"HOOK_SECRET"):
    if needle in blob:
        raise SystemExit(f"ledger stored secret {needle!r}")

export = (box / "export.jsonl").read_text()
for needle in ("SECRET_PROMPT", "SECRET_ASSISTANT", "HOOK_SECRET", "prompt"):
    if needle in export:
        raise SystemExit(f"export leaked {needle!r}")

# statements exist
for ext in ("md", "html", "csv"):
    p = home / ".ardoise" / "statements" / f"2026-09.{ext}"
    if not p.is_file() or p.stat().st_size < 20:
        raise SystemExit(f"missing statement {p}")
    text = p.read_text()
    if "SECRET" in text:
        raise SystemExit(f"statement leaked secret: {p}")

if status.get("month") != "2026-09":
    raise SystemExit(f"status month {status.get('month')}")
if int(status.get("month_entries") or 0) != 3:
    raise SystemExit(f"status month_entries={status.get('month_entries')}")
if abs(float(status.get("cost_usd") or 0) - 0.02105) > 1e-6:
    raise SystemExit(f"status cost {status.get('cost_usd')} != 0.02105")

# hooks installed without a plugin manager
claude = json.loads((home / ".claude" / "settings.json").read_text())
if "Stop" not in claude.get("hooks", {}):
    raise SystemExit("claude Stop hook missing")
if "SessionStart" not in claude.get("hooks", {}):
    raise SystemExit("claude SessionStart snapshot hook missing")
cursor = json.loads((home / ".cursor" / "hooks.json").read_text())
if "stop" not in cursor.get("hooks", {}):
    raise SystemExit("cursor stop hook missing")

# Phase 2 schema + first statement splits billed vs T0
for table in ("events", "snapshots", "prices", "projects", "sync_state", "invoices"):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE name = ?", (table,)
    ).fetchone()
    if row is None:
        raise SystemExit(f"missing ledger table {table}")

md0 = (home / ".ardoise" / "statements" / "2026-09.md").read_text()
if "A. Vendor lines" not in md0 or "B. T0 allocation" not in md0:
    raise SystemExit("statement missing section A / T0 allocation")
if "No invoice, T2 billed events, or T1 snapshot" not in md0:
    raise SystemExit("pre-paste section A must not treat T0 as billed")
inv_cols = {row[1] for row in conn.execute("PRAGMA table_info(invoices)")}
for col in ("vendor", "cycle", "person", "usd_cents", "source", "notes", "created_at"):
    if col not in inv_cols:
        raise SystemExit(f"invoices missing column {col}")

vendor_a = json.loads((box / "vendor-anthropic.json").read_text())
if vendor_a.get("capabilities", {}).get("capture") != "yes":
    raise SystemExit(f"anthropic capture cap {vendor_a.get('capabilities')}")
if vendor_a.get("cred_resolved"):
    raise SystemExit("anthropic cred should be unresolved offline")
if vendor_a.get("capabilities", {}).get("pull") != "yes":
    raise SystemExit(f"anthropic pull cap {vendor_a.get('capabilities')}")
anth_detail = str(vendor_a.get("detail") or "")
anth_txt = (box / "vendor-anthropic.txt").read_text()
anth_pull = (box / "vendor-pull-anthropic.txt").read_text()
if "ANTHROPIC_ANALYTICS_API_KEY" not in anth_detail and "ANTHROPIC_ANALYTICS_API_KEY" not in anth_txt:
    raise SystemExit(f"anthropic vendor test missing Analytics key line: {anth_detail!r} {anth_txt!r}")
if "T2a skipped" not in anth_detail and "T2a skipped" not in anth_txt:
    raise SystemExit(f"anthropic vendor test should skip T2a, got {anth_detail!r} {anth_txt!r}")
if "ANTHROPIC_ANALYTICS_API_KEY" not in anth_pull or "T2a skipped" not in anth_pull:
    raise SystemExit(f"anthropic vendor pull should skip without key, got {anth_pull!r}")
vendor_c = json.loads((box / "vendor-cursor.json").read_text())
if vendor_c.get("cred_resolved"):
    raise SystemExit("cursor cred should be unresolved offline")
if vendor_c.get("capabilities", {}).get("capture") != "yes":
    raise SystemExit(f"cursor capture cap {vendor_c.get('capabilities')}")
detail = str(vendor_c.get("detail") or "")
vendor_txt = (box / "vendor-test.txt").read_text()
if "missing CURSOR_ADMIN_API_KEY" not in detail and "missing CURSOR_ADMIN_API_KEY" not in vendor_txt:
    raise SystemExit(f"cursor vendor test missing cred line: {detail!r} {vendor_txt!r}")
if "T0-only" not in detail and "T0-only" not in vendor_txt:
    raise SystemExit(f"cursor vendor test should say T0-only, got {detail!r} {vendor_txt!r}")

# T1 snapshot is a no-op without OAuth (capabilities stay T0)
snap = json.loads((box / "snapshot.json").read_text())
if not snap.get("empty"):
    raise SystemExit(f"offline snapshot should be empty, got {snap}")
if snap.get("reason") != "oauth_unavailable":
    raise SystemExit(f"snapshot reason={snap.get('reason')!r}, want oauth_unavailable")
caps = set(snap.get("capabilities") or [])
if "T0" not in caps or "T1" in caps:
    raise SystemExit(f"capabilities={caps}, want T0 without T1 when OAuth is missing")
n_snap = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
if n_snap != 0:
    raise SystemExit(f"empty snapshot should not write rows, got {n_snap}")
for needle in (b"sk-ant-oat", b"access_token", b"Bearer "):
    if needle in blob:
        raise SystemExit(f"ledger stored credential-like {needle!r}")

print("checks=ok entries=3 cost=0.02105 project=clouvelai/Arbusteia")
PY

# paste-in invoices are the solid dollar source for section A
"$BIN" invoice paste --file "$ROOT/tests/fixtures/invoices.jsonl" --json >"$BOX/invoice-paste.json"
"$BIN" statement 2026-09 --out-dir "$HOME/.ardoise/statements" >"$BOX/statement-billed.json"
"$BIN" status --json --month 2026-09 >"$BOX/status-billed.json"

python3 - "$BOX" "$HOME" <<'PY'
import json, sqlite3, sys
from pathlib import Path

box = Path(sys.argv[1])
home = Path(sys.argv[2])
paste = json.loads((box / "invoice-paste.json").read_text())
if int(paste.get("inserted") or 0) != 2:
    raise SystemExit(f"invoice paste inserted={paste}")

status = json.loads((box / "status-billed.json").read_text())
if abs(float(status.get("billed_usd") or 0) - 21.05) > 1e-6:
    raise SystemExit(f"section A billed_usd={status.get('billed_usd')} want 21.05")
if abs(float(status.get("cost_usd") or 0) - 0.02105) > 1e-6:
    raise SystemExit(f"T0 estimated cost_usd={status.get('cost_usd')} want 0.02105")
if float(status.get("estimated_usd") or 0) >= float(status.get("billed_usd") or 0):
    raise SystemExit("T0 estimate must not replace invoice billed total")
tiers = {row.get("tier_of_truth") for row in status.get("section_a") or []}
if tiers != {"invoice"}:
    raise SystemExit(f"section A tiers {tiers}, want invoice")

md = (home / ".ardoise" / "statements" / "2026-09.md").read_text()
html = (home / ".ardoise" / "statements" / "2026-09.html").read_text()
csv = (home / ".ardoise" / "statements" / "2026-09.csv").read_text()
for blob, label in ((md, "md"), (html, "html"), (csv, "csv")):
    if "invoice" not in blob:
        raise SystemExit(f"{label} missing invoice tier")
    if "Trivelta" in blob:
        raise SystemExit(f"{label} leaked Trivelta")
if "A. Vendor lines" not in md or "19.50" not in md or "1.55" not in md:
    raise SystemExit("markdown section A missing invoice dollars")
if "| invoice |" not in md:
    raise SystemExit("markdown section A missing invoice tier label")
if "B. T0 allocation" not in md:
    raise SystemExit("markdown missing T0 allocation section")
if "A_vendor" not in csv or "B_t0_allocation" not in csv:
    raise SystemExit("csv missing section A / T0 allocation rows")

conn = sqlite3.connect(home / ".ardoise" / "ledger.db")
n_inv = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
if n_inv != 2:
    raise SystemExit(f"invoices table count={n_inv}")
print("invoice-paste=ok section_a=21.05 t0_estimate=0.02105")
PY

echo "FRESH-BOX-OK"
