#!/bin/sh
# Marketplace-safe Claude SessionStart entrypoint.
# Prefer ~/.ardoise/hooks/snapshot.sh (install.sh); else ardoise on PATH.
# Never resolves a sibling shared/ tree relative to this plugin.
set -eu
trap 'exit 0' EXIT
ARDOISE_HOOK=1
export ARDOISE_HOOK

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HOOK_HOME="${ARDOISE_HOME:-${HOME:-}/.ardoise}"
INSTALLED="${HOOK_HOME}/hooks/snapshot.sh"
if [ -x "$INSTALLED" ] && [ "$INSTALLED" != "${HERE}/snapshot.sh" ]; then
  exec "$INSTALLED"
fi

cat >/dev/null || true

if [ -n "${ARDOISE_BIN:-}" ] && [ -x "${ARDOISE_BIN}" ]; then
  "${ARDOISE_BIN}" snapshot anthropic --json >/dev/null 2>&1 || true
  exit 0
fi

if command -v ardoise >/dev/null 2>&1; then
  ardoise snapshot anthropic --json >/dev/null 2>&1 || true
  exit 0
fi

if [ -x "${HOME:-}/.local/bin/ardoise" ]; then
  "${HOME}/.local/bin/ardoise" snapshot anthropic --json >/dev/null 2>&1 || true
  exit 0
fi

exit 0
