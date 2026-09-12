#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SHARED="${HERE}/../../shared/snapshot.sh"
if [ -x "$SHARED" ]; then
  exec "$SHARED"
fi
exit 0
