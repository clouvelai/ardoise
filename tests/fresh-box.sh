#!/bin/sh
# Offline acceptance: isolated HOME, fixture logs, FRESH-BOX-OK.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BOX=$(mktemp -d)
trap 'rm -rf "$BOX"' EXIT

export HOME="$BOX/home"
export ARDOISE_HOME="$HOME/.ardoise"
unset ARDOISE_LEDGER ARDOISE_QUEUE ARDOISE_STATEMENTS ARDOISE_CLAUDE_ROOT ARDOISE_CURSOR_ROOT
mkdir -p "$HOME"

PROJ="$BOX/proj"
mkdir -p "$PROJ"
git init -q -b main "$PROJ"
git -C "$PROJ" remote add origin git@github.com:clouvelai/Arbusteia.git

chmod +x "$ROOT/bin/ardoise" \
  "$ROOT/install.sh" \
  "$ROOT/plugins/shared/capture.sh" \
  "$ROOT/plugins/claude/hooks/capture.sh" \
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
cursor = json.loads((home / ".cursor" / "hooks.json").read_text())
if "stop" not in cursor.get("hooks", {}):
    raise SystemExit("cursor stop hook missing")

print("checks=ok entries=3 cost=0.02105 project=clouvelai/Arbusteia")
PY

echo "FRESH-BOX-OK"
