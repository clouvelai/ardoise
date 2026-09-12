"""Compatibility wrapper — implementation lives in ardoise.vendors.anthropic."""

from ardoise.vendors.jsonl import iter_jsonl
from ardoise.vendors.anthropic import (
    discover_t0_files,
    iter_anthropic_t0,
    looks_like_t0,
    parse_t0_line,
)

__all__ = [
    "discover_t0_files",
    "iter_anthropic_t0",
    "iter_jsonl",
    "looks_like_t0",
    "parse_t0_line",
]
