#!/bin/sh
# Install Ardoise locally. Phase 1 path: --no-plugin-manager
# Copies shared hooks into ~/.claude/settings.json and ~/.cursor/hooks.json.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NO_PLUGIN_MANAGER=0
JSON=0

for arg in "$@"; do
  case "$arg" in
    --no-plugin-manager) NO_PLUGIN_MANAGER=1 ;;
    --json) JSON=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: ./install.sh --no-plugin-manager

Install the local Ardoise CLI and shared Claude Code / Cursor capture hooks
without invoking any plugin marketplace or plugin manager.

Options:
  --no-plugin-manager   Required Phase 1 mode (file-copy hooks)
  --json                Print machine-readable result
EOF
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      echo "Phase 1 expects: ./install.sh --no-plugin-manager" >&2
      exit 2
      ;;
  esac
done

if [ "$NO_PLUGIN_MANAGER" -ne 1 ]; then
  echo "Phase 1 installs hooks by copying files." >&2
  echo "Re-run: $0 --no-plugin-manager" >&2
  exit 2
fi

BIN="$ROOT/bin/ardoise"
chmod +x "$BIN" \
  "$ROOT/plugins/shared/capture.sh" \
  "$ROOT/plugins/claude/hooks/capture.sh" \
  "$ROOT/plugins/cursor/capture.sh" 2>/dev/null || true

if [ "$JSON" -eq 1 ]; then
  exec "$BIN" install-hooks --no-plugin-manager --json
fi
exec "$BIN" install-hooks --no-plugin-manager
