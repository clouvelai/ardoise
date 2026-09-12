"""Compatibility adapters. Implementation lives in ardoise.vendors."""

from ardoise.adapters.hook_event import event_to_entry

__all__ = ["iter_anthropic_t0", "iter_cursor", "event_to_entry"]


def __getattr__(name: str):
    if name == "iter_anthropic_t0":
        from ardoise.vendors.anthropic import iter_anthropic_t0

        return iter_anthropic_t0
    if name == "iter_cursor":
        from ardoise.vendors.cursor import iter_cursor

        return iter_cursor
    raise AttributeError(name)
