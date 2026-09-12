"""Record Anthropic T1 seat snapshots into the ledger ``snapshots`` table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from ardoise import db, paths
from ardoise.project import infer_project
from ardoise.vendors import get_adapter
from ardoise.vendors.anthropic.adapter import SNAPSHOT_MIN_INTERVAL_S
from ardoise.vendors.anthropic.usage import billed_extra_delta
from ardoise.vendors.contract import CredentialNotConfigured, Snapshot, cycle_of


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def _empty(vendor: str, reason: str, *, capabilities: list[str] | None = None) -> dict[str, Any]:
    return {
        "vendor": vendor,
        "empty": True,
        "reason": reason,
        "recorded": False,
        "throttled": reason == "throttled",
        "capabilities": capabilities or ["T0"],
        "extra_usage": None,
        "windows": {},
    }


def record_vendor_snapshot(
    vendor: str = "anthropic",
    *,
    force: bool = False,
    now: datetime | None = None,
    fetch: Callable[..., tuple[int, Any]] | None = None,
    resolve: Callable[..., Any] | None = None,
    from_hook: bool = False,
    cwd: str | None = None,
    person: str | None = None,
    cycle: str | None = None,
) -> dict[str, Any]:
    """Run vendor.snapshot() and persist a contract ``snapshots`` row.

    Missing OAuth and throttle skips are not written (hooks stay quiet).
    Successful fetches upsert ``billed_cents`` = extra_usage.used_credits;
    the delta vs the previous snapshot is billed extra usage.
    """
    del from_hook  # reserved: hook path uses the same empty-on-miss policy
    paths.ensure_home()
    try:
        adapter = get_adapter(vendor)
    except ValueError as exc:
        return _empty(vendor, str(exc), capabilities=[])

    if resolve is not None:
        adapter._resolve = resolve  # tests inject a resolver

    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    person_key = person or ""
    cycle_key = cycle or cycle_of(stamp.strftime("%Y-%m-%dT%H:%M:%SZ")) or stamp.strftime("%Y-%m")
    project = infer_project(cwd=cwd)
    tiers = list(adapter.tier_capabilities()) if hasattr(adapter, "tier_capabilities") else ["T0"]

    with db.session() as conn:
        state = db.get_sync_state(conn, vendor=adapter.name, kind="t1_snapshot", person=person_key)
        last_attempt = _parse_iso((state or {}).get("updated_at"))
        if not force and last_attempt is not None:
            if (stamp - last_attempt).total_seconds() < SNAPSHOT_MIN_INTERVAL_S:
                return {
                    **_empty(adapter.name, "throttled", capabilities=tiers),
                    "interval_s": SNAPSHOT_MIN_INTERVAL_S,
                    "project": project,
                    "captured_at": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }

        prev = db.latest_snapshot(conn, vendor=adapter.name, person=person_key, cycle=cycle_key)
        previous_credits = None
        if prev is not None and prev.get("billed_cents") not in (None, ""):
            previous_credits = float(prev["billed_cents"])

        try:
            snap = adapter.snapshot(
                person=person_key,
                cycle=cycle_key,
                now=stamp,
                previous_credits=previous_credits,
                force=True,
                fetch=fetch,
            )
        except CredentialNotConfigured as exc:
            need = getattr(exc, "need", "") or str(exc)
            reason = "oauth_unavailable"
            if "throttled" in need:
                reason = "throttled"
            elif "http_" in need:
                reason = need.rsplit(" ", 1)[-1]
            elif "invalid_usage" in need:
                reason = "invalid_usage_json"
            if reason != "oauth_unavailable":
                db.set_sync_state(
                    conn,
                    vendor=adapter.name,
                    kind="t1_snapshot",
                    person=person_key,
                    ok=False,
                    last_error=reason,
                )
            return {
                **_empty(adapter.name, reason, capabilities=tiers),
                "interval_s": SNAPSHOT_MIN_INTERVAL_S,
                "project": project,
                "captured_at": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }

        if not isinstance(snap, Snapshot):
            return _empty(adapter.name, "invalid_snapshot", capabilities=tiers)

        extra = getattr(snap, "extra_usage", None)
        extra = extra if isinstance(extra, dict) else {}
        used = extra.get("used_credits")
        if snap.billed_cents is not None and used is None:
            used = float(snap.billed_cents)
        delta = extra.get("delta")
        if delta is None:
            delta = billed_extra_delta(previous_credits, used)
        extra = {**extra, "delta": delta}

        row = snap.to_row()
        db.upsert_snapshot(conn, row)
        db.set_sync_state(
            conn,
            vendor=adapter.name,
            kind="t1_snapshot",
            person=person_key,
            cursor=snap.as_of,
            ok=True,
        )
        return {
            "vendor": adapter.name,
            "empty": False,
            "reason": None,
            "recorded": True,
            "throttled": False,
            "capabilities": tiers,
            "captured_at": snap.as_of,
            "cycle": snap.cycle,
            "billed_cents": snap.billed_cents,
            "extra_usage": extra,
            "windows": getattr(snap, "windows", {}),
            "user_agent": getattr(snap, "user_agent", None),
            "oauth_source": getattr(snap, "oauth_source", None),
            "interval_s": SNAPSHOT_MIN_INTERVAL_S,
            "project": project,
        }
