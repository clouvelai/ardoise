#!/bin/sh
# Shared Claude Code + Cursor hook. Reads one JSON event on stdin.
# Never prints prompts. Always exits 0 so the agent loop is not blocked.
# Self-contained: invoke ardoise on PATH or ~/.local/bin — not a sibling shared/ tree.
set -eu
trap 'exit 0' EXIT
ARDOISE_HOOK=1
export ARDOISE_HOOK

if [ -n "${ARDOISE_BIN:-}" ] && [ -x "${ARDOISE_BIN}" ]; then
  "${ARDOISE_BIN}" capture --stdin >/dev/null 2>&1 || true
  exit 0
fi

if command -v ardoise >/dev/null 2>&1; then
  ardoise capture --stdin >/dev/null 2>&1 || true
  exit 0
fi

if [ -x "${HOME:-}/.local/bin/ardoise" ]; then
  "${HOME}/.local/bin/ardoise" capture --stdin >/dev/null 2>&1 || true
  exit 0
fi

exit 0
