#!/usr/bin/env python3
"""Standalone hook helper: strip secrets and enqueue a usage event.

Copy-safe: no repo-relative imports. Missing ardoise package → exit 0.
"""

from __future__ import annotations

import sys

try:
    from ardoise.cli import main
except ImportError:
    sys.exit(0)

if __name__ == "__main__":
    raise SystemExit(main(["capture", "--stdin"]))
