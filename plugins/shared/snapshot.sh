#!/bin/sh
# Claude Code SessionStart → Anthropic T1 seat snapshot (throttled, 3 min).
# Discard hook stdin. Never print prompts. Always exit 0.
set -eu
ARDOISE_HOOK=1
export ARDOISE_HOOK
cat >/dev/null || true

if [ -n "${ARDOISE_BIN:-}" ] && [ -x "${ARDOISE_BIN}" ]; then
  "${ARDOISE_BIN}" snapshot anthropic --json >/dev/null 2>&1 || true
  exit 0
fi

if command -v ardoise >/dev/null 2>&1; then
  ardoise snapshot anthropic --json >/dev/null 2>&1 || true
  exit 0
fi

if [ -x "${HOME}/.local/bin/ardoise" ]; then
  "${HOME}/.local/bin/ardoise" snapshot anthropic --json >/dev/null 2>&1 || true
  exit 0
fi

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -x "${HERE}/../../bin/ardoise" ]; then
  "${HERE}/../../bin/ardoise" snapshot anthropic --json >/dev/null 2>&1 || true
  exit 0
fi

exit 0
