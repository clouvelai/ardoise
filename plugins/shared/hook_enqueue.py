#!/usr/bin/env python3
"""Standalone hook helper: strip secrets and enqueue a usage event."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Prefer the package when the repo is on PYTHONPATH; otherwise copy-safe no-op.
try:
    from ardoise.cli import main
except ImportError:
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    try:
        from ardoise.cli import main
    except ImportError:
        sys.exit(0)

if __name__ == "__main__":
    raise SystemExit(main(["capture", "--stdin"]))
