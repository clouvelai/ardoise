#!/bin/sh
# Marketplace-safe Cursor capture entrypoint.
# Prefer ~/.ardoise/hooks/capture.sh (install.sh); else ardoise on PATH.
# Never resolves a sibling shared/ tree relative to this plugin.
set -eu
trap 'exit 0' EXIT
ARDOISE_HOOK=1
export ARDOISE_HOOK

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HOOK_HOME="${ARDOISE_HOME:-${HOME:-}/.ardoise}"
INSTALLED="${HOOK_HOME}/hooks/capture.sh"
if [ -x "$INSTALLED" ] && [ "$INSTALLED" != "${HERE}/capture.sh" ]; then
  exec "$INSTALLED"
fi

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
