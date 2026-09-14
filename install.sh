#!/bin/sh
# Install Ardoise: copy the engine to ~/.local/share/ardoise, link PATH,
# merge self-contained capture hooks. Works from a clone OR a lone script
# (curl | sh) via a GitHub tarball / ARDOISE_TARBALL.
set -eu

REPO_SLUG="clouvelai/ardoise"
TAG="${ARDOISE_TAG:-v0.3.2}"
PREFIX="${ARDOISE_PREFIX:-${HOME}/.local/share/ardoise}"
JSON=0

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

for arg in "$@"; do
  case "$arg" in
    --no-plugin-manager) ;; # default; kept so older scripts keep working
    --json) JSON=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: ./install.sh

Install the Ardoise engine under ~/.local/share/ardoise, link
~/.local/bin/ardoise, and merge Claude Code / Cursor capture hooks.

When this script is not next to bin/ardoise (curl | sh), it fetches a
tagged GitHub archive unless ARDOISE_TARBALL points at a local tar.gz.

Options:
  --no-plugin-manager   Accepted (this is the default)
  --json                Print machine-readable result

Env:
  ARDOISE_TAG       Release tag to fetch (default: v0.3.2)
  ARDOISE_TARBALL   Local .tar.gz (offline / tests)
  ARDOISE_PREFIX    Install prefix (default: ~/.local/share/ardoise)
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

copy_tree() {
  from=$1
  to=$2
  mkdir -p "$to"
  (CDPATH= cd -- "$from" && tar cf - .) | (CDPATH= cd -- "$to" && tar xf -)
}

stage_prefix() {
  tree=$1
  mkdir -p "$PREFIX/bin" "$PREFIX/data" "$PREFIX/plugins/shared"
  copy_tree "$tree/ardoise" "$PREFIX/ardoise"
  if [ -d "$tree/data" ]; then
    copy_tree "$tree/data" "$PREFIX/data"
  fi
  copy_tree "$tree/bin" "$PREFIX/bin"
  if [ -d "$tree/plugins/shared" ]; then
    copy_tree "$tree/plugins/shared" "$PREFIX/plugins/shared"
  fi
  chmod +x "$PREFIX/bin/ardoise" 2>/dev/null || true
  find "$PREFIX/plugins" "$PREFIX/bin" -type f -name '*.sh' -exec chmod +x {} \; 2>/dev/null || true
}

SRC=""
CLEANUP=""
if [ -x "$SCRIPT_DIR/bin/ardoise" ] && [ -d "$SCRIPT_DIR/ardoise" ]; then
  SRC="$SCRIPT_DIR"
else
  WORK=$(mktemp -d)
  CLEANUP="$WORK"
  ARCHIVE="$WORK/src.tar.gz"
  if [ -n "${ARDOISE_TARBALL:-}" ]; then
    if [ ! -f "$ARDOISE_TARBALL" ]; then
      echo "ARDOISE_TARBALL is not a file: $ARDOISE_TARBALL" >&2
      rm -rf "$WORK"
      exit 1
    fi
    ARCHIVE="$ARDOISE_TARBALL"
  else
    TAG_URL="https://github.com/${REPO_SLUG}/archive/refs/tags/${TAG}.tar.gz"
    MAIN_URL="https://github.com/${REPO_SLUG}/archive/refs/heads/main.tar.gz"
    if command -v curl >/dev/null 2>&1; then
      curl -fsSL "$TAG_URL" -o "$ARCHIVE" || curl -fsSL "$MAIN_URL" -o "$ARCHIVE"
    elif command -v wget >/dev/null 2>&1; then
      wget -q -O "$ARCHIVE" "$TAG_URL" || wget -q -O "$ARCHIVE" "$MAIN_URL"
    else
      echo "install.sh needs curl or wget to fetch ${REPO_SLUG}" >&2
      rm -rf "$WORK"
      exit 1
    fi
  fi
  tar -xzf "$ARCHIVE" -C "$WORK"
  SRC=$(find "$WORK" -maxdepth 1 -mindepth 1 -type d -name 'ardoise*' | head -n 1)
  if [ -z "$SRC" ] || [ ! -x "$SRC/bin/ardoise" ]; then
    echo "archive did not contain bin/ardoise" >&2
    rm -rf "$WORK"
    exit 1
  fi
fi

stage_prefix "$SRC"
if [ -n "$CLEANUP" ]; then
  rm -rf "$CLEANUP"
fi

chmod +x "$PREFIX/bin/ardoise" \
  "$PREFIX/plugins/shared/capture.sh" \
  "$PREFIX/plugins/shared/snapshot.sh" 2>/dev/null || true

if [ "$JSON" -eq 1 ]; then
  exec "$PREFIX/bin/ardoise" install-hooks --no-plugin-manager --json
fi
exec "$PREFIX/bin/ardoise" install-hooks --no-plugin-manager
