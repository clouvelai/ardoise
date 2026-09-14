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

"$ROOT/install.sh" >/dev/null

# ~/.local/bin/ardoise must resolve into the staged prefix, not the clone.
LAUNCHER="$HOME/.local/bin/ardoise"
PREFIX="$HOME/.local/share/ardoise"
if [ ! -x "$LAUNCHER" ]; then
  echo "install did not link $LAUNCHER" >&2
  exit 1
fi
if [ ! -x "$PREFIX/bin/ardoise" ]; then
  echo "install did not stage $PREFIX/bin/ardoise" >&2
  exit 1
fi
python3 - "$LAUNCHER" "$PREFIX" <<'PY'
import os, sys
launcher, prefix = sys.argv[1], sys.argv[2]
resolved = os.path.realpath(launcher)
root = os.path.realpath(prefix)
if resolved != os.path.join(root, "bin", "ardoise") and not resolved.startswith(root + os.sep):
    raise SystemExit(f"launcher is not in prefix: {resolved} (prefix={root})")
PY
( cd / && "$LAUNCHER" --version >/dev/null )

# Installed hooks must be self-contained (no ../shared, no checkout sibling).
for hook in "$HOME/.ardoise/hooks/capture.sh" "$HOME/.ardoise/hooks/snapshot.sh"; do
  if [ ! -x "$hook" ]; then
    echo "missing installed hook $hook" >&2
    exit 1
  fi
  if grep -E '\.\./shared|plugins/shared' "$hook" >/dev/null; then
    echo "installed hook still references plugins/shared: $hook" >&2
    exit 1
  fi
done
if grep -E 'parents\[2\]|\.\./shared' "$HOME/.ardoise/hooks/hook_enqueue.py" >/dev/null; then
  echo "installed hook_enqueue.py still assumes a monorepo checkout" >&2
  exit 1
fi

# Marketplace isolation: only plugins/claude, no plugins/shared beside it.
MKT_PLUGIN="$BOX/marketplace/claude"
mkdir -p "$MKT_PLUGIN"
cp -R "$ROOT/plugins/claude/." "$MKT_PLUGIN/"
if [ -e "$BOX/marketplace/shared" ]; then
  echo "marketplace copy must not include plugins/shared" >&2
  exit 1
fi
for stub in "$MKT_PLUGIN/hooks/capture.sh" "$MKT_PLUGIN/hooks/snapshot.sh" \
  "$MKT_PLUGIN/.claude-plugin/plugin.json" "$MKT_PLUGIN/hooks/hooks.json"; do
  if grep -E '\.\./shared|plugins/shared' "$stub" >/dev/null; then
    echo "plugin stub still references plugins/shared: $stub" >&2
    exit 1
  fi
done
# In-repo Claude marketplace catalog + Cursor plugin scaffold.
python3 - "$ROOT" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
catalog = json.loads((root / ".claude-plugin" / "marketplace.json").read_text())
if catalog.get("name") != "ardoise":
    raise SystemExit(f"marketplace name={catalog.get('name')!r}")
plugin = (catalog.get("plugins") or [None])[0]
if not plugin or plugin.get("source") != "./plugins/claude":
    raise SystemExit(f"marketplace source={plugin}")
if not (root / "plugins" / "claude" / ".claude-plugin" / "plugin.json").is_file():
    raise SystemExit("missing plugins/claude/.claude-plugin/plugin.json")
cursor_root = json.loads((root / ".cursor-plugin" / "plugin.json").read_text())
cursor_plugin = json.loads(
    (root / "plugins" / "cursor" / ".cursor-plugin" / "plugin.json").read_text()
)
if cursor_root.get("name") != "ardoise" or cursor_plugin.get("name") != "ardoise":
    raise SystemExit("cursor plugin name mismatch")
hooks = json.loads((root / "plugins" / "cursor" / "hooks" / "hooks.json").read_text())
blob = json.dumps(hooks) + json.dumps(cursor_root) + json.dumps(catalog)
if "../shared" in blob or "plugins/shared" in blob:
    raise SystemExit("catalog/plugin still references plugins/shared")
print("catalog=ok")
PY
# Isolated Cursor plugin copy (dogfood layout) must not need plugins/shared.
CUR_PLUGIN="$BOX/local/ardoise"
mkdir -p "$BOX/local"
cp -R "$ROOT/plugins/cursor/." "$CUR_PLUGIN/"
if [ -e "$BOX/local/shared" ]; then
  echo "cursor local copy must not include plugins/shared" >&2
  exit 1
fi
if [ ! -f "$CUR_PLUGIN/.cursor-plugin/plugin.json" ] || [ ! -f "$CUR_PLUGIN/hooks/hooks.json" ]; then
  echo "cursor local copy missing plugin.json or hooks/hooks.json" >&2
  exit 1
fi
if grep -E '\.\./shared|plugins/shared' "$CUR_PLUGIN/capture.sh" \
  "$CUR_PLUGIN/hooks/hooks.json" "$CUR_PLUGIN/.cursor-plugin/plugin.json" >/dev/null; then
  echo "cursor local copy still references plugins/shared" >&2
  exit 1
fi
MKT_HOME="$BOX/mkt-home"
mkdir -p "$MKT_HOME"
# No installed hooks in this HOME — stub must call ARDOISE_BIN (the linked CLI).
# Separate ARDOISE_HOME so this capture cannot touch the main fresh-box ledger.
printf '%s\n' '{"hook_event_name":"Stop"}' | \
  HOME="$MKT_HOME" ARDOISE_HOME="$MKT_HOME/.ardoise" ARDOISE_BIN="$LAUNCHER" \
  "$MKT_PLUGIN/hooks/capture.sh"
HOME="$MKT_HOME" ARDOISE_HOME="$MKT_HOME/.ardoise" ARDOISE_BIN="$LAUNCHER" \
  "$MKT_PLUGIN/hooks/snapshot.sh" </dev/null
printf '%s\n' '{"hook_event_name":"stop"}' | \
  HOME="$MKT_HOME" ARDOISE_HOME="$MKT_HOME/.ardoise" ARDOISE_BIN="$LAUNCHER" \
  "$CUR_PLUGIN/capture.sh"

# Fail-open: a crashing CLI must not block the editor.
BOOM="$BOX/boom-ardoise"
printf '%s\n' '#!/bin/sh' 'exit 7' >"$BOOM"
chmod +x "$BOOM"
HOME="$MKT_HOME" ARDOISE_HOME="$MKT_HOME/.ardoise" ARDOISE_BIN="$BOOM" \
  "$MKT_PLUGIN/hooks/capture.sh" </dev/null
HOME="$MKT_HOME" ARDOISE_HOME="$MKT_HOME/.ardoise" ARDOISE_BIN="$BOOM" \
  "$CUR_PLUGIN/capture.sh" </dev/null
ARDOISE_BIN="$BOOM" "$HOME/.ardoise/hooks/capture.sh" </dev/null
ARDOISE_BIN="$BOOM" "$HOME/.ardoise/hooks/snapshot.sh" </dev/null

# Install must not write keys.
for needle in sk-ant- ANTHROPIC_API_KEY CURSOR_ADMIN_API_KEY access_token; do
  if grep -R -F -- "$needle" "$HOME/.ardoise/hooks" "$HOME/.claude/settings.json" \
      "$HOME/.cursor/hooks.json" >/dev/null 2>&1; then
    echo "install stored credential-like $needle" >&2
    exit 1
  fi
done

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
"$BIN" backfill --json >"$BOX/backfill2.json"

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
attr_cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
for col in ("agent", "skill", "effort"):
    if col not in attr_cols:
        raise SystemExit(f"events missing attribution column {col}")
unnamed = conn.execute(
    "SELECT COUNT(*) FROM events WHERE agent IS NOT NULL OR skill IS NOT NULL OR effort IS NOT NULL"
).fetchone()[0]
if unnamed != 0:
    raise SystemExit(f"fixture rows must stay unattributed, got {unnamed} named")
for table in ("events", "snapshots", "prices", "projects", "sync_state", "invoices"):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE name = ?", (table,)
    ).fetchone()
    if row is None:
        raise SystemExit(f"missing ledger table {table}")

md0 = (home / ".ardoise" / "statements" / "2026-09.md").read_text()
if "Description" not in md0 or "Quantity" not in md0 or "Rate" not in md0:
    raise SystemExit("statement missing Orb line table headers")
if "From" not in md0 or "Prepared for" not in md0:
    raise SystemExit("statement missing From / Prepared for")
if "Amount due" in md0:
    raise SystemExit("spend statement must not say Amount due")
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
if "T2a skipped" not in anth_detail and "T2a skipped" not in anth_txt:
    raise SystemExit(f"anthropic vendor test should skip T2a, got {anth_detail!r} {anth_txt!r}")
if "Free is T0" not in anth_detail and "Free is T0" not in anth_txt:
    raise SystemExit(f"anthropic vendor test should say Free is T0, got {anth_detail!r} {anth_txt!r}")
if "missing ANTHROPIC" in anth_detail or "missing ANTHROPIC" in anth_txt:
    raise SystemExit(f"anthropic vendor test should not nag missing Analytics key: {anth_detail!r} {anth_txt!r}")
if "ANTHROPIC_ANALYTICS_API_KEY" in anth_txt or "ANTHROPIC_ADMIN_API_KEY" in anth_txt or "unresolved" in anth_txt:
    raise SystemExit(f"default vendor test anthropic should stay quiet, got {anth_txt!r}")
if "ANTHROPIC_ANALYTICS_API_KEY" in anth_pull or "missing " in anth_pull:
    raise SystemExit(f"anthropic vendor pull should stay quiet, got {anth_pull!r}")
if "T2a skipped" not in anth_pull:
    raise SystemExit(f"anthropic vendor pull should skip without key, got {anth_pull!r}")
vendor_c = json.loads((box / "vendor-cursor.json").read_text())
if vendor_c.get("cred_resolved"):
    raise SystemExit("cursor cred should be unresolved offline")
if vendor_c.get("capabilities", {}).get("capture") != "yes":
    raise SystemExit(f"cursor capture cap {vendor_c.get('capabilities')}")
detail = str(vendor_c.get("detail") or "")
vendor_txt = (box / "vendor-test.txt").read_text()
if "Admin T2 skipped" not in detail and "Admin T2 skipped" not in vendor_txt:
    raise SystemExit(f"cursor vendor test should skip Admin T2, got {detail!r} {vendor_txt!r}")
if "Free is T0" not in detail and "Free is T0" not in vendor_txt:
    raise SystemExit(f"cursor vendor test should say Free is T0, got {detail!r} {vendor_txt!r}")
if "missing CURSOR_ADMIN_API_KEY" in detail or "missing CURSOR_ADMIN_API_KEY" in vendor_txt:
    raise SystemExit(f"cursor vendor test should not nag missing Admin key: {detail!r} {vendor_txt!r}")
if "CURSOR_ADMIN_API_KEY" in vendor_txt or "unresolved" in vendor_txt:
    raise SystemExit(f"default vendor test cursor should stay quiet, got {vendor_txt!r}")

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

rerun = json.loads((box / "backfill2.json").read_text())
if int(rerun.get("inserted") or 0) != 0:
    raise SystemExit(f"second backfill inserted={rerun}")
if int(rerun.get("skipped_files") or 0) < 1:
    raise SystemExit(f"second backfill should skip unchanged files: {rerun}")

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
if "Description" not in md or "19.50" not in md or "1.55" not in md:
    raise SystemExit("markdown missing invoice dollars / line table")
if "21.05" not in md and "21.05" not in html:
    raise SystemExit("statement missing invoice-grade total 21.05")
if "Reconciling adjustment" not in md:
    raise SystemExit("markdown missing reconciling adjustment")
if "spend statement, not a tax invoice" not in md:
    raise SystemExit("markdown missing spend-statement memo")
if "A_vendor" not in csv or "B_t0_allocation" not in csv:
    raise SystemExit("csv missing section A / T0 allocation rows")
if "Amount due" in md or "Amount due" in html:
    raise SystemExit("spend statement must not say Amount due")
if "@media print" not in html:
    raise SystemExit("html missing print stylesheet")
if "@page" not in html or "table-header-group" not in html:
    raise SystemExit("html missing print page / repeating header rules")
if "group-period" not in html:
    raise SystemExit("html missing section period row")
if "List price" not in html:
    raise SystemExit("html missing list-price totals footer")

conn = sqlite3.connect(home / ".ardoise" / "ledger.db")
n_inv = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
if n_inv != 2:
    raise SystemExit(f"invoices table count={n_inv}")
print("invoice-paste=ok section_a=21.05 t0_estimate=0.02105")
PY

# Phase 3: estimate stub + soft-cap warn (never blocks)
"$BIN" estimate --model claude-sonnet-4-6 --input-tokens 1000 --output-tokens 400 --json \
  >"$BOX/estimate.json"
python3 - "$BOX" "$HOME" <<'PY'
import json, sys
from pathlib import Path

box = Path(sys.argv[1])
home = Path(sys.argv[2])
est = json.loads((box / "estimate.json").read_text())
if abs(float(est.get("usd") or 0) - 0.009) > 1e-6:
    raise SystemExit(f"estimate usd={est.get('usd')} want 0.009")
if est.get("blocks") or (est.get("gate") or {}).get("blocks"):
    raise SystemExit("estimate must never block")
if not est.get("ok"):
    raise SystemExit(f"estimate not ok: {est}")

cfg = home / ".ardoise" / "config.json"
cfg.write_text(
    '{"budgets":{"monthly_usd":1,"project":{"clouvelai/Arbusteia":0.01}},'
    '"anomalies":{"min_day_usd":0.02,"min_month_usd":0.02,"min_days":1,'
    '"day_multiple":1.5,"project_share":0.5}}'
)
print("estimate=ok usd=0.009")
PY

"$BIN" status --json --month 2026-09 >"$BOX/status-phase3.json"
"$BIN" statement 2026-09 --out-dir "$HOME/.ardoise/statements" >"$BOX/statement-phase3.json"
"$BIN" estimate --stdin --json <<'JSON' >"$BOX/estimate-stdin.json"
{"model":"claude-haiku-4-5","input_tokens":500,"output_tokens":100}
JSON

python3 - "$BOX" "$HOME" <<'PY'
import json, sys
from pathlib import Path

box = Path(sys.argv[1])
home = Path(sys.argv[2])
status = json.loads((box / "status-phase3.json").read_text())
if "budgets" not in status or "anomalies" not in status:
    raise SystemExit("status missing budgets/anomalies")
if not status["budgets"].get("over_cap"):
    raise SystemExit(f"soft cap should flag over: {status.get('budgets')}")
if status["budgets"].get("blocks"):
    raise SystemExit("soft cap must not set blocks")
month = next(c for c in status["budgets"]["checks"] if c["kind"] == "month")
if month.get("pct") is None or not month.get("over"):
    raise SystemExit(f"month vs-cap missing: {month}")
md = (home / ".ardoise" / "statements" / "2026-09.md").read_text()
if "Notes (soft)" not in md:
    raise SystemExit("statement missing soft notes after cap")
if "never block" not in md:
    raise SystemExit("statement notes must say they never block")
stdin_est = json.loads((box / "estimate-stdin.json").read_text())
if abs(float(stdin_est.get("usd") or 0) - 0.001) > 1e-6:
    raise SystemExit(f"stdin estimate {stdin_est.get('usd')} want 0.001")
print("phase3=ok over_cap=1 notes=soft estimate-stdin=0.001")
PY

# Phase 3 roster filter: view-only seat slice (does not mutate the ledger)
"$BIN" invoice add --vendor anthropic --cycle 2026-09 --usd-cents 400 --person alice --json \
  >"$BOX/invoice-alice.json"
"$BIN" status --json --month 2026-09 --person alice >"$BOX/status-alice.json"
"$BIN" statement 2026-09 --person alice --out-dir "$HOME/.ardoise/statements" \
  >"$BOX/statement-alice.json"
"$BIN" status --json --month 2026-09 --seat nobody >"$BOX/status-nobody.json"
"$BIN" statement 2026-09 --person alice --out-dir "$HOME/.ardoise/statements" \
  >"$BOX/statement-alice-rerun.json"

python3 - "$BOX" "$HOME" <<'PY'
import json, sqlite3, sys
from pathlib import Path

box = Path(sys.argv[1])
home = Path(sys.argv[2])
added = json.loads((box / "invoice-alice.json").read_text())
if added.get("result") != "inserted" or added.get("person") != "alice":
    raise SystemExit(f"alice invoice add {added}")

alice = json.loads((box / "status-alice.json").read_text())
if abs(float(alice.get("billed_usd") or 0) - 4.0) > 1e-6:
    raise SystemExit(f"alice billed_usd={alice.get('billed_usd')} want 4.0")
if any(row.get("person") not in {"alice"} for row in alice.get("section_a") or []):
    raise SystemExit(f"alice filter leaked other seats: {alice.get('section_a')}")
if alice.get("filter", {}).get("view_only") is not True:
    raise SystemExit("alice filter must be view_only")
if int(alice.get("entries") or 0) != 3:
    raise SystemExit(f"filter mutated ledger entries={alice.get('entries')}")

nobody = json.loads((box / "status-nobody.json").read_text())
if nobody.get("section_a") or nobody.get("lines"):
    raise SystemExit("unknown seat should be an empty view")
if not any("view only" in str(note) for note in nobody.get("notes") or []):
    raise SystemExit("unknown seat should note view-only empty match")

written = json.loads((box / "statement-alice.json").read_text())
rerun = json.loads((box / "statement-alice-rerun.json").read_text())
if written.get("md") != rerun.get("md"):
    raise SystemExit("filtered statement path changed on rerun")
for key in ("md", "html", "csv"):
    path = Path(written[key])
    if not path.is_file() or "2026-09--alice" not in path.name:
        raise SystemExit(f"missing filtered statement {path}")
    text = path.read_text()
    if "alice" not in text:
        raise SystemExit(f"{path.name} missing alice marker")
    if "view only" not in text.lower().replace("-", " "):
        raise SystemExit(f"{path.name} missing view-only marker")
    if "19.50" in text or "1.55" in text:
        raise SystemExit(f"{path.name} leaked unfiltered invoice dollars")
    # Orb layout uses a few small tables; denser roster tables are the smell.

org = home / ".ardoise" / "statements" / "2026-09.md"
if not org.is_file():
    raise SystemExit("org statement was clobbered by seat filter")
conn = sqlite3.connect(home / ".ardoise" / "ledger.db")
if conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] != 3:
    raise SystemExit("roster filter wrote events")
if conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] != 3:
    raise SystemExit("unexpected invoice count after alice add")
print("roster-filter=ok alice=4.00 view_only=1")
PY

# Grok Bot dogfood: drop fixtures in the default folder, then plain `backfill`.
mkdir -p "$HOME/.ardoise/transcripts"
cp -R "$ROOT/tests/fixtures/dogfood/agent-data" "$HOME/.ardoise/transcripts/"
"$BIN" backfill --json >"$BOX/backfill-grok.json"
"$BIN" status --month 2026-09 >"$BOX/status-grok.txt"
"$BIN" status --json --month 2026-09 >"$BOX/status-grok.json"
"$BIN" status --month 2026-09 --roster Craie >"$BOX/status-craie.txt"
"$BIN" status --json --month 2026-09 --roster Craie >"$BOX/status-craie.json"
"$BIN" statement 2026-09 --person Craie --out-dir "$HOME/.ardoise/statements" \
  >"$BOX/statement-craie.json"

python3 - "$BOX" "$HOME" <<'PY'
import json, sqlite3, sys
from pathlib import Path

box = Path(sys.argv[1])
home = Path(sys.argv[2])
conn = sqlite3.connect(home / ".ardoise" / "ledger.db")
conn.row_factory = sqlite3.Row
craie = conn.execute(
    "SELECT agent, skill, effort FROM events WHERE message_id = 'msg_grok_craie'"
).fetchone()
if craie is None or craie["agent"] != "Craie":
    raise SystemExit(f"grok fixture missing agent=Craie: {None if craie is None else dict(craie)}")
encre = conn.execute(
    "SELECT agent FROM events WHERE message_id = 'msg_grok_encre'"
).fetchone()
if encre is None or encre["agent"] != "Encre":
    raise SystemExit(f"grok fixture missing agent=Encre: {None if encre is None else dict(encre)}")
captain = conn.execute(
    "SELECT agent FROM events WHERE message_id = 'msg_grok_captain'"
).fetchone()
if captain is None or captain["agent"] != "captain":
    raise SystemExit(f"grok fixture missing agent=captain: {None if captain is None else dict(captain)}")
blob = (home / ".ardoise" / "ledger.db").read_bytes()
for needle in (b"SECRET_GROK_PROMPT", b"SECRET_ENCRE_BODY", b"SECRET_CAPTAIN_PROMPT"):
    if needle in blob:
        raise SystemExit(f"ledger stored grok secret {needle!r}")

status = json.loads((box / "status-grok.json").read_text())
text = (box / "status-grok.txt").read_text()
names = {row.get("agent") for row in status.get("agents") or []}
if names != {"Craie", "Encre", "captain"}:
    raise SystemExit(f"status agents={names}")
for name in ("Craie", "Encre", "captain"):
    if f"{name} $" not in text:
        raise SystemExit(f"status missing spend chip for {name}")
spend = {
    row["agent"]: float(row.get("cost_usd") or 0)
    for row in status.get("by_agent") or []
    if row.get("agent") and row.get("agent") != "(unattributed)"
}
if any(value <= 0 for value in spend.values()) or set(spend) != names:
    raise SystemExit(f"named-agent spend missing: {spend}")
filtered = json.loads((box / "status-craie.json").read_text())
craie_txt = (box / "status-craie.txt").read_text()
if filtered.get("filter", {}).get("kind") != "agent":
    raise SystemExit(f"Craie filter kind={filtered.get('filter')}")
if filtered.get("filter", {}).get("view_only") is not True:
    raise SystemExit("Craie filter must be view_only")
if float(filtered.get("cost_usd") or 0) <= 0:
    raise SystemExit(f"Craie spend {filtered.get('cost_usd')}")
if "filter   Craie" not in craie_txt or "$" not in craie_txt.split("filter   Craie", 1)[1][:24]:
    raise SystemExit(f"Craie filter missing spend: {craie_txt}")
named = {
    row.get("agent")
    for row in filtered.get("by_agent") or []
    if row.get("agent") and row.get("agent") != "(unattributed)"
}
if named != {"Craie"}:
    raise SystemExit(f"Craie view leaked other agents: {named}")
written = json.loads((box / "statement-craie.json").read_text())
html = Path(written["html"]).read_text()
if "Craie" not in html or "view only" not in html.lower():
    raise SystemExit("filtered statement missing Craie / view-only")
if "Agent filter Craie" not in html and "Prepared for" not in html:
    raise SystemExit("filtered statement missing agent prepared-for / note")
if "$" not in html:
    raise SystemExit("filtered statement missing agent spend")
if "roster table" in html.lower():
    raise SystemExit("agent statement grew a roster table")
print("grok-bot=ok agent=Craie chips=spend")
PY

# curl | sh failure mode: only install.sh on disk + a local tarball.
ALT="$BOX/curl-home"
ONLY="$BOX/curl-only"
PACK="$BOX/pack/ardoise-src"
mkdir -p "$ALT" "$ONLY" "$PACK"
cp "$ROOT/install.sh" "$ONLY/install.sh"
cp -R "$ROOT/ardoise" "$ROOT/data" "$ROOT/bin" "$ROOT/plugins" "$PACK/"
TARBALL="$BOX/ardoise-src.tar.gz"
tar -czf "$TARBALL" -C "$BOX/pack" ardoise-src
HOME="$ALT" ARDOISE_TARBALL="$TARBALL" sh "$ONLY/install.sh" >/dev/null
ALT_BIN="$ALT/.local/bin/ardoise"
if [ ! -x "$ALT_BIN" ]; then
  echo "tarball install did not link $ALT_BIN" >&2
  exit 1
fi
HOME="$ALT" "$ALT_BIN" --version >/dev/null
echo "tarball-install=ok"

echo "FRESH-BOX-OK"
