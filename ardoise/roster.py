"""Seat / person / roster filters for status and statements.

View only: filters never write the ledger and never block the CLI.
Unknown names become an empty view plus a soft note.

Named agents (`events.agent`) are first-class on the same flags: `--person`,
`--seat`, and `--roster` match a person *or* a named agent. Quiet chips only.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from ardoise import attribution, config as config_mod

_UNNAMED = frozenset({"", "default", "*", "(default)", "(none)"})
_SLUG_SAFE = re.compile(r"[^A-Za-z0-9._@-]+")


def fold(value: Any) -> str:
    """Case-insensitive person key. `default` / `*` are the unnamed seat."""
    text = str(value or "").strip()
    if text.casefold() in _UNNAMED:
        return ""
    return text.casefold()


def display(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.casefold() in _UNNAMED:
        return "default"
    return text


def slug(value: Any) -> str:
    label = display(value)
    cleaned = _SLUG_SAFE.sub("-", label).strip("-.")
    return cleaned or "default"


def statement_stem(month: str, person: str | None) -> str:
    if person is None:
        return month
    return f"{month}--{slug(person)}"


def _aliases_for(name: str, roster_cfg: dict[str, list[str]]) -> list[str]:
    folded = fold(name)
    out: list[str] = []
    seen: set[str] = set()
    for canonical, aliases in roster_cfg.items():
        pool = [canonical, *aliases]
        if not any(fold(item) == folded for item in pool):
            continue
        for item in pool:
            text = str(item or "").strip()
            key = fold(text)
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
    return out


def people_from_ledger(conn: sqlite3.Connection, month: str | None = None) -> list[str]:
    if month:
        rows = conn.execute(
            """
            SELECT DISTINCT person FROM events WHERE cycle = ?
            UNION
            SELECT DISTINCT person FROM snapshots WHERE cycle = ?
            UNION
            SELECT DISTINCT person FROM invoices WHERE cycle = ?
            """,
            (month, month, month),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT DISTINCT person FROM events
            UNION
            SELECT DISTINCT person FROM snapshots
            UNION
            SELECT DISTINCT person FROM invoices
            """
        ).fetchall()
    names = [str(row[0] or "") for row in rows]
    named = sorted({name for name in names if fold(name)}, key=str.casefold)
    if any(not fold(name) for name in names):
        named.append("")
    return named


def agents_from_ledger(conn: sqlite3.Connection, month: str | None = None) -> list[str]:
    """Distinct named agents for the cycle (or the whole ledger)."""
    if month:
        rows = conn.execute(
            """
            SELECT DISTINCT agent FROM events
            WHERE cycle = ? AND agent IS NOT NULL AND TRIM(agent) != ''
            """,
            (month,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT DISTINCT agent FROM events
            WHERE agent IS NOT NULL AND TRIM(agent) != ''
            """
        ).fetchall()
    names = []
    for row in rows:
        text = str(row[0] or "").strip()
        if not text or text == attribution.UNATTRIBUTED:
            continue
        names.append(text)
    return sorted(set(names), key=str.casefold)


def collect_agents(
    conn: sqlite3.Connection | None = None,
    *,
    month: str | None = None,
) -> list[dict[str, Any]]:
    names = agents_from_ledger(conn, month) if conn is not None else []
    return [{"agent": name, "kind": "agent", "aliases": []} for name in names]


def _group_key(name: str, roster_cfg: dict[str, list[str]]) -> str:
    """Stable fold for a name, preferring the config canonical when aliased."""
    target = fold(name)
    for canonical, aliases in roster_cfg.items():
        pool = [canonical, *aliases]
        if any(fold(item) == target for item in pool):
            return fold(canonical)
    return target


def collect(
    conn: sqlite3.Connection | None = None,
    *,
    month: str | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Ledger person dimensions ∪ optional `config.roster` (aliases)."""
    cfg = config if config is not None else config_mod.load()
    roster_cfg = cfg.get("roster") if isinstance(cfg.get("roster"), dict) else {}
    ledger = people_from_ledger(conn, month) if conn is not None else []

    buckets: dict[str, dict[str, Any]] = {}

    def _add(name: str, *, extra_aliases: list[str] | None = None) -> None:
        key = _group_key(name, roster_cfg)
        bucket = buckets.get(key)
        if bucket is None:
            canonical = ""
            for cfg_name, aliases in roster_cfg.items():
                if fold(cfg_name) == key:
                    canonical = "" if not key else str(cfg_name or "").strip()
                    extra_aliases = list(aliases or []) + list(extra_aliases or [])
                    break
            if not canonical:
                canonical = "" if not key else str(name or "").strip()
            bucket = {"person": canonical, "aliases": []}
            buckets[key] = bucket
        seen = {fold(bucket["person"]), *(fold(item) for item in bucket["aliases"])}
        for item in [name, *(_aliases_for(name, roster_cfg)), *(extra_aliases or [])]:
            text = str(item or "").strip()
            folded = fold(text)
            if not text or folded in seen or folded == fold(bucket["person"]):
                continue
            seen.add(folded)
            bucket["aliases"].append(text)

    for name in ledger:
        _add(name)
    for canonical, aliases in roster_cfg.items():
        _add(canonical, extra_aliases=list(aliases or []))

    named = [row for row in buckets.values() if row["person"]]
    unnamed = [row for row in buckets.values() if not row["person"]]
    named.sort(key=lambda row: str(row["person"]).casefold())
    return named + unnamed


def resolve(
    query: str | None,
    *,
    roster: list[dict[str, Any]] | None = None,
    agents: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Build a view-only filter. `None` query means no filter."""
    if query is None:
        return None
    target = fold(query)
    keys = {target}
    canonical = display(query)
    matched = False
    person_matched = False
    for row in roster or []:
        pool = [row.get("person") or "", *(row.get("aliases") or [])]
        folds = {fold(item) for item in pool}
        if target in folds:
            matched = True
            person_matched = True
            canonical = display(row.get("person") or canonical)
            keys.update(folds)
    agent_keys: set[str] = set()
    agent_name: str | None = None
    for row in agents or []:
        name = row.get("agent") if isinstance(row, dict) else row
        text = str(name or "").strip()
        if not text:
            continue
        if fold(text) == target:
            matched = True
            agent_name = text
            agent_keys.add(fold(text))
    if agent_name and not person_matched:
        canonical = agent_name
        kind = "agent"
        person = ""
    elif agent_name and person_matched:
        kind = "both"
        person = "" if fold(canonical) == "" else canonical
    else:
        kind = "person"
        person = "" if fold(canonical) == "" else canonical
    return {
        "query": str(query),
        "person": person,
        "canonical": canonical,
        "keys": sorted(keys),
        "agent": agent_name,
        "agent_keys": sorted(agent_keys),
        "kind": kind,
        "matched": matched,
        "view_only": True,
    }


def matches(row: dict[str, Any] | None, filt: dict[str, Any] | None) -> bool:
    if not filt:
        return True
    kind = str(filt.get("kind") or "person")
    person_keys = {fold(item) for item in (filt.get("keys") or ())}
    agent_keys = {fold(item) for item in (filt.get("agent_keys") or ())}
    person_hit = fold((row or {}).get("person")) in person_keys
    agent_hit = fold((row or {}).get("agent")) in agent_keys
    if kind == "agent":
        return agent_hit
    if kind == "both":
        return person_hit or agent_hit
    return person_hit


def apply_rows(rows: list[dict[str, Any]], filt: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not filt:
        return list(rows)
    return [row for row in rows if matches(row, filt)]


def note_for(filt: dict[str, Any] | None, *, matched_rows: int) -> str | None:
    if not filt:
        return None
    label = display(filt.get("canonical") or filt.get("query"))
    role = "agent" if filt.get("kind") == "agent" else "seat"
    if matched_rows == 0:
        return (
            f"{role} filter {label}: no matching rows "
            "(view only — ledger unchanged)"
        )
    return None


def filename_for(month: str, filt: dict[str, Any] | None) -> str:
    if not filt:
        return month
    return statement_stem(month, filt.get("canonical") or filt.get("query"))
