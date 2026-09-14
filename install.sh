#!/bin/sh
# Install Ardoise locally: CLI on PATH + self-contained capture hooks
# under ~/.ardoise/hooks (no ../shared at runtime).
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
JSON=0

for arg in "$@"; do
  case "$arg" in
    --no-plugin-manager) ;; # default; kept so older scripts keep working
    --json) JSON=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: ./install.sh

Install the local Ardoise CLI and self-contained Claude Code / Cursor
capture hooks under ~/.ardoise/hooks (no plugin marketplace).

Options:
  --no-plugin-manager   Accepted (this is the default)
  --json                Print machine-readable result
EOF
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      echo "Usage: $0" >&2
      exit 2
      ;;
  esac
done

BIN="$ROOT/bin/ardoise"
chmod +x "$BIN" \
  "$ROOT/plugins/shared/capture.sh" \
  "$ROOT/plugins/shared/snapshot.sh" \
  "$ROOT/plugins/claude/hooks/capture.sh" \
  "$ROOT/plugins/claude/hooks/snapshot.sh" \
  "$ROOT/plugins/cursor/capture.sh" 2>/dev/null || true

if [ "$JSON" -eq 1 ]; then
  exec "$BIN" install-hooks --no-plugin-manager --json
fi
exec "$BIN" install-hooks --no-plugin-manager
