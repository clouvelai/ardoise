"""Anthropic VendorAdapter: T0 capture always; T1 snapshot when OAuth resolves;
T2a Analytics pull when ANTHROPIC_ANALYTICS_API_KEY is set.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from ardoise import paths
from . import oauth, t2a, usage
from .t0 import iter_anthropic_t0
from ardoise.vendors.contract import (
    Capabilities,
    CredentialField,
    CredentialNotConfigured,
    CredentialSpec,
    Event,
    Snapshot,
    TokenCounts,
    VendorTestResult,
    cycle_of,
    entry_to_event,
)
from ardoise.vendors.creds import resolve_status

SNAPSHOT_MIN_INTERVAL_S = 180  # at most every 3 minutes


def _now_iso(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _current_cycle(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    return stamp.strftime("%Y-%m")


class AnthropicAdapter:
    name = "anthropic"
    tools = ("claude-code",)
    credential_spec = CredentialSpec(
        fields=(
            CredentialField(
                key="oauth_token",
                env="CLAUDE_CODE_OAUTH_TOKEN",
                purpose="T1 oauth/usage snapshot",
                optional=True,
                alt_envs=("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_OAUTH_TOKEN"),
            ),
            CredentialField(
                key="admin_api_key",
                env="ANTHROPIC_ADMIN_API_KEY",
                purpose="T1 usage snapshot",
                optional=True,
            ),
            CredentialField(
                key="analytics_api_key",
                env="ANTHROPIC_ANALYTICS_API_KEY",
                purpose="T2a Analytics API usage/cost pull",
                optional=True,
                alt_envs=("ANTHROPIC_ANALYTICS_KEY",),
            ),
        )
    )
    capabilities = Capabilities(
        capture="yes",
        snapshot="stub",
        pull="yes",
        test="yes",
    )

    def __init__(
        self,
        *,
        resolve: Callable[[], oauth.OAuthCred | None] | None = None,
        fetch: Callable[..., tuple[int, Any]] | None = None,
    ) -> None:
        self._resolve = resolve or oauth.resolve_oauth
        self._fetch = fetch

    def capture(self, *, root: Path | None = None) -> Iterator[Event]:
        base = root or paths.claude_root()
        for _path, entry in iter_anthropic_t0(base):
            yield entry_to_event(entry)

    def tier_capabilities(self) -> frozenset[str]:
        caps = {"T0"}
        if self._resolve() is not None:
            caps.add("T1")
        if t2a.analytics_api_key() is not None:
            caps.add("T2")
        return frozenset(caps)

    def snapshot(
        self,
        *,
        person: str | None = None,
        cycle: str | None = None,
        now: datetime | None = None,
        previous_credits: float | None = None,
        force: bool = False,
        last_attempt_at: datetime | None = None,
        fetch: Callable[..., tuple[int, Any]] | None = None,
    ) -> Snapshot:
        """T1 seat snapshot via GET /api/oauth/usage.

        Raises CredentialNotConfigured when no ANTHROPIC/Claude OAuth cred
        resolves (capabilities stay T0). ``fetch`` is injectable so tests
        never need keys or a network.
        """
        cred = self._resolve()
        if cred is None:
            raise CredentialNotConfigured(self.name, "T1 snapshot")

        stamp = now or datetime.now(timezone.utc)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        if not force and last_attempt_at is not None:
            prior = last_attempt_at
            if prior.tzinfo is None:
                prior = prior.replace(tzinfo=timezone.utc)
            if (stamp - prior).total_seconds() < SNAPSHOT_MIN_INTERVAL_S:
                raise CredentialNotConfigured(self.name, "T1 snapshot throttled")

        fetcher = fetch or self._fetch or usage.fetch_oauth_usage
        status, body = fetcher(cred.access_token)
        if status != 200 or not isinstance(body, dict):
            raise CredentialNotConfigured(self.name, f"T1 snapshot http_{status or 0}")

        parsed = usage.parse_usage_payload(body)
        if parsed is None:
            raise CredentialNotConfigured(self.name, "T1 snapshot invalid_usage_json")

        extra = parsed["extra_usage"]
        used = extra.get("used_credits")
        delta = usage.billed_extra_delta(previous_credits, used)
        billed = None
        if used is not None:
            billed = int(round(float(used)))
        cost = (billed / 100.0) if billed is not None else None
        as_of = _now_iso(stamp)
        cycle_key = cycle or cycle_of(as_of) or _current_cycle(stamp)
        snap = Snapshot(
            vendor=self.name,
            cycle=cycle_key,
            as_of=as_of,
            tokens=TokenCounts(),
            billed_cents=billed,
            tier="T1",
            person=person or "",
            cost_usd=cost,
        )
        # CLI / recorder extras (not persisted as secrets).
        snap.extra_usage = {**extra, "delta": delta}  # type: ignore[attr-defined]
        snap.windows = parsed["windows"]  # type: ignore[attr-defined]
        snap.user_agent = usage.user_agent()  # type: ignore[attr-defined]
        snap.oauth_source = cred.source  # type: ignore[attr-defined]
        return snap

    def pull(self, *, person: str | None = None, cycle: str | None = None) -> Iterator[Event]:
        key = t2a.analytics_api_key()
        if not key:
            raise CredentialNotConfigured(self.name, "T2a pull")
            yield  # pragma: no cover
        transport = t2a.make_transport(key, t2a.api_base())
        stamp = datetime.now(timezone.utc)
        ending_at = stamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        starting_at = (stamp - t2a.DEFAULT_LOOKBACK).strftime("%Y-%m-%dT%H:%M:%SZ")
        yield from t2a.iter_pull_events(
            transport=transport,
            starting_at=starting_at,
            ending_at=ending_at,
            person=person,
        )

    def test(self) -> VendorTestResult:
        status = resolve_status(self.credential_spec)
        resolved = any(item.present for item in status)
        data = t2a.test_vendor()
        detail = (
            "T0 capture works without credentials. T1 snapshot uses OAuth "
            "(env/keychain) when present. "
            + str(data.get("message") or "")
        )
        return VendorTestResult(
            name=self.name,
            tools=self.tools,
            capabilities=self.capabilities,
            credentials=status,
            cred_resolved=resolved,
            ok=bool(data.get("ok", True)),
            detail=detail.strip(),
        )
