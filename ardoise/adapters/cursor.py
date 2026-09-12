"""Compatibility wrapper — implementation lives in ardoise.vendors.cursor."""

from ardoise.vendors.cursor import (
    discover_cursor_files,
    iter_cursor,
    parse_cursor_line,
)

__all__ = ["discover_cursor_files", "iter_cursor", "parse_cursor_line"]
