#!/bin/sh
# Dogfood: install.sh → drop named-agent fixtures → plain backfill → status chips.
# Isolated HOME. No keys. Must print DOGFOOD-OK offline.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BOX=$(mktemp -d)
trap 'rm -rf "$BOX"' EXIT

export HOME="$BOX/home"
export ARDOISE_HOME="$HOME/.ardoise"
unset ARDOISE_LEDGER ARDOISE_QUEUE ARDOISE_STATEMENTS ARDOISE_CLAUDE_ROOT ARDOISE_CURSOR_ROOT
unset ARDOISE_CLOUD_AGENT_ROOT ARDOISE_AGENT_DATA ARDOISE_TRANSCRIPT_PATHS ARDOISE_TRANSCRIPTS
unset CURSOR_ADMIN_API_KEY CURSOR_API_KEY ANTHROPIC_ANALYTICS_API_KEY ANTHROPIC_ANALYTICS_KEY
mkdir -p "$HOME"

# Empty Claude/Cursor trees so this path is transcripts-only.
mkdir -p "$HOME/.claude" "$HOME/.cursor"

chmod +x "$ROOT/bin/ardoise" "$ROOT/install.sh"
"$ROOT/install.sh" >/dev/null

LAUNCHER="$HOME/.local/bin/ardoise"
if [ ! -x "$LAUNCHER" ]; then
  echo "install did not link $LAUNCHER" >&2
  exit 1
fi

# Default drop folder created by install / ensure_home.
mkdir -p "$ARDOISE_HOME/transcripts"
cp -R "$ROOT/tests/fixtures/dogfood/agent-data" "$ARDOISE_HOME/transcripts/"

# Same one-liner UX: backfill with no extra flags.
"$LAUNCHER" backfill --json >"$BOX/backfill.json"
"$LAUNCHER" status --month 2026-09 >"$BOX/status.txt"
"$LAUNCHER" status --json --month 2026-09 >"$BOX/status.json"
"$LAUNCHER" status --month 2026-09 --roster Craie >"$BOX/status-craie.txt"
"$LAUNCHER" status --json --month 2026-09 --roster Craie >"$BOX/status-craie.json"

python3 - "$BOX" "$HOME" <<'PY'
import json, sqlite3, sys
from pathlib import Path

box = Path(sys.argv[1])
home = Path(sys.argv[2])
text = (box / "status.txt").read_text()
status = json.loads((box / "status.json").read_text())
craie_txt = (box / "status-craie.txt").read_text()
craie = json.loads((box / "status-craie.json").read_text())

names = {row.get("agent") for row in status.get("agents") or []}
if names != {"Craie", "Encre", "captain"}:
    raise SystemExit(f"status agents={names}")
if "agents   " not in text:
    raise SystemExit("status missing agent chips")
for name in ("Craie", "Encre", "captain"):
    if f"{name} $" not in text:
        raise SystemExit(f"status chip missing spend for {name}: {text}")
spend = {
    row["agent"]: float(row.get("cost_usd") or 0)
    for row in status.get("by_agent") or []
    if row.get("agent") and row.get("agent") != "(unattributed)"
}
if any(value <= 0 for value in spend.values()) or set(spend) != names:
    raise SystemExit(f"named-agent spend missing: {spend}")

if craie.get("filter", {}).get("kind") != "agent":
    raise SystemExit(f"Craie filter {craie.get('filter')}")
if craie.get("filter", {}).get("view_only") is not True:
    raise SystemExit("Craie filter must be view_only")
if float(craie.get("cost_usd") or 0) <= 0:
    raise SystemExit(f"Craie spend {craie.get('cost_usd')}")
if "filter   Craie" not in craie_txt or "$" not in craie_txt.split("filter   Craie", 1)[1][:24]:
    raise SystemExit(f"Craie filter chip missing spend: {craie_txt}")
named = {
    row.get("agent")
    for row in craie.get("by_agent") or []
    if row.get("agent") and row.get("agent") != "(unattributed)"
}
if named != {"Craie"}:
    raise SystemExit(f"Craie view leaked other agents: {named}")

conn = sqlite3.connect(home / ".ardoise" / "ledger.db")
conn.row_factory = sqlite3.Row
for mid, agent in (
    ("msg_grok_craie", "Craie"),
    ("msg_grok_encre", "Encre"),
    ("msg_grok_captain", "captain"),
):
    row = conn.execute("SELECT agent FROM events WHERE message_id = ?", (mid,)).fetchone()
    if row is None or row["agent"] != agent:
        raise SystemExit(f"{mid} agent={None if row is None else row['agent']} want {agent}")
blob = (home / ".ardoise" / "ledger.db").read_bytes()
for needle in (b"SECRET_GROK_PROMPT", b"SECRET_ENCRE_BODY", b"SECRET_CAPTAIN_PROMPT"):
    if needle in blob:
        raise SystemExit(f"ledger stored secret {needle!r}")
print("dogfood=ok agents=Craie,Encre,captain chips=spend")
PY

echo "DOGFOOD-OK"
