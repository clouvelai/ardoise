"""Compatibility adapters. Implementation lives in ardoise.vendors."""

from __future__ import annotations

from ardoise.adapters.hook_event import event_to_entry

__all__ = ["iter_anthropic_t0", "iter_cursor", "iter_cloud_agent", "event_to_entry"]


def __getattr__(name: str):
    if name == "iter_anthropic_t0":
        from ardoise.vendors.anthropic import iter_anthropic_t0

        return iter_anthropic_t0
    if name == "iter_cursor":
        from ardoise.vendors.cursor import iter_cursor

        return iter_cursor
    if name == "iter_cloud_agent":
        from ardoise.adapters.cloud_agent import iter_cloud_agent

        return iter_cloud_agent
    raise AttributeError(name)
