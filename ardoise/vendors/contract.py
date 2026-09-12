"""VendorAdapter contract and Event / Snapshot shapes (tiers of truth).

T0 — local estimate (JSONL / hooks × pricebook)
T1 — vendor-stated snapshot for a billing cycle
T2 — vendor-billed usage events
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator, Protocol, Sequence

TIERS = ("T0", "T1", "T2")


def cycle_of(occurred_at: str | None, fallback: str | None = None) -> str:
    if occurred_at and len(occurred_at) >= 7 and occurred_at[4] == "-":
        return occurred_at[:7]
    return fallback or ""


@dataclass(frozen=True)
class TokenCounts:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_creation_5m_tokens: int = 0
    cache_creation_1h_tokens: int = 0

    @property
    def total(self) -> int:
        return (
            int(self.input_tokens)
            + int(self.output_tokens)
            + int(self.cache_read_tokens)
            + int(self.cache_creation_tokens)
        )

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "TokenCounts":
        data = data or {}
        return cls(
            input_tokens=int(data.get("input_tokens") or 0),
            output_tokens=int(data.get("output_tokens") or 0),
            cache_read_tokens=int(data.get("cache_read_tokens") or 0),
            cache_creation_tokens=int(data.get("cache_creation_tokens") or 0),
            cache_creation_5m_tokens=int(data.get("cache_creation_5m_tokens") or 0),
            cache_creation_1h_tokens=int(data.get("cache_creation_1h_tokens") or 0),
        )


@dataclass
class Event:
    """Usage event. Tokens plus optional vendor-billed cents and a truth tier."""

    vendor: str
    source: str
    message_id: str
    request_id: str
    occurred_at: str
    tokens: TokenCounts = field(default_factory=TokenCounts)
    billed_cents: int | None = None
    tier: str = "T0"
    person: str | None = None
    cycle: str | None = None
    project: str | None = None
    model: str | None = None
    session_id: str | None = None
    cwd: str | None = None
    cost_usd: float | None = None
    agent: str | None = None
    skill: str | None = None
    effort: str | None = None

    def to_row(self) -> dict[str, Any]:
        tokens = self.tokens
        return {
            "vendor": self.vendor,
            "source": self.source,
            "message_id": self.message_id,
            "request_id": self.request_id,
            "occurred_at": self.occurred_at,
            "input_tokens": tokens.input_tokens,
            "output_tokens": tokens.output_tokens,
            "cache_read_tokens": tokens.cache_read_tokens,
            "cache_creation_tokens": tokens.cache_creation_tokens,
            "cache_creation_5m_tokens": tokens.cache_creation_5m_tokens,
            "cache_creation_1h_tokens": tokens.cache_creation_1h_tokens,
            "billed_cents": self.billed_cents,
            "tier": self.tier or "T0",
            "person": self.person or "",
            "cycle": self.cycle or cycle_of(self.occurred_at),
            "project": self.project,
            "model": self.model,
            "session_id": self.session_id,
            "cwd": self.cwd,
            "cost_usd": self.cost_usd,
            "agent": self.agent,
            "skill": self.skill,
            "effort": self.effort,
        }


@dataclass
class Snapshot:
    """Cycle snapshot. Tokens plus optional vendor-billed cents and a truth tier."""

    vendor: str
    cycle: str
    as_of: str
    tokens: TokenCounts = field(default_factory=TokenCounts)
    billed_cents: int | None = None
    tier: str = "T1"
    person: str | None = None
    cost_usd: float | None = None

    def to_row(self) -> dict[str, Any]:
        tokens = self.tokens
        return {
            "vendor": self.vendor,
            "person": self.person or "",
            "cycle": self.cycle,
            "as_of": self.as_of,
            "input_tokens": tokens.input_tokens,
            "output_tokens": tokens.output_tokens,
            "cache_read_tokens": tokens.cache_read_tokens,
            "cache_creation_tokens": tokens.cache_creation_tokens,
            "billed_cents": self.billed_cents,
            "cost_usd": self.cost_usd,
            "tier": self.tier or "T1",
        }


@dataclass(frozen=True)
class CredentialField:
    key: str
    env: str
    purpose: str
    optional: bool = True
    alt_envs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CredentialSpec:
    fields: tuple[CredentialField, ...] = ()


@dataclass(frozen=True)
class Capabilities:
    """yes = works offline / without admin creds; stub = needs creds / not live; no = absent."""

    capture: str = "no"
    snapshot: str = "no"
    pull: str = "no"
    test: str = "yes"

    def as_dict(self) -> dict[str, str]:
        return {
            "capture": self.capture,
            "snapshot": self.snapshot,
            "pull": self.pull,
            "test": self.test,
        }


@dataclass(frozen=True)
class ResolvedField:
    key: str
    env: str
    purpose: str
    present: bool
    source: str | None
    optional: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "env": self.env,
            "purpose": self.purpose,
            "present": self.present,
            "source": self.source,
            "optional": self.optional,
        }


@dataclass
class VendorTestResult:
    name: str
    tools: tuple[str, ...]
    capabilities: Capabilities
    credentials: tuple[ResolvedField, ...]
    cred_resolved: bool
    ok: bool = True
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tools": list(self.tools),
            "capabilities": self.capabilities.as_dict(),
            "credentials": [item.as_dict() for item in self.credentials],
            "cred_resolved": self.cred_resolved,
            "ok": self.ok,
            "detail": self.detail,
        }


class CredentialNotConfigured(Exception):
    def __init__(self, vendor: str, need: str) -> None:
        self.vendor = vendor
        self.need = need
        super().__init__(f"credential not configured: {vendor} {need}")


class VendorAdapter(Protocol):
    name: str
    tools: Sequence[str]
    credential_spec: CredentialSpec
    capabilities: Capabilities

    def capture(self, *, root: Path | None = None) -> Iterator[Event]:
        """T0 local capture. Must work with no admin credentials."""

    def snapshot(self, *, person: str | None = None, cycle: str | None = None) -> Snapshot:
        """T1 vendor snapshot. Stub may raise CredentialNotConfigured."""

    def pull(self, *, person: str | None = None, cycle: str | None = None) -> Iterator[Event]:
        """T2 vendor events. Stub may raise CredentialNotConfigured."""

    def test(self) -> VendorTestResult:
        """Capabilities + whether credentials resolve. Never prints secrets."""


def entry_to_event(entry: dict[str, Any]) -> Event:
    return Event(
        vendor=str(entry.get("vendor") or vendor_for_source(entry.get("source"))),
        source=str(entry.get("source") or "unknown"),
        message_id=str(entry.get("message_id") or ""),
        request_id=str(entry.get("request_id") or ""),
        occurred_at=str(entry.get("occurred_at") or ""),
        tokens=TokenCounts.from_mapping(entry),
        billed_cents=_opt_int(entry.get("billed_cents")),
        tier=str(entry.get("tier") or "T0"),
        person=entry.get("person") or None,
        cycle=entry.get("cycle") or cycle_of(entry.get("occurred_at")),
        project=entry.get("project"),
        model=entry.get("model"),
        session_id=entry.get("session_id"),
        cwd=entry.get("cwd"),
        cost_usd=entry.get("cost_usd"),
        agent=entry.get("agent"),
        skill=entry.get("skill"),
        effort=entry.get("effort"),
    )


def vendor_for_source(source: str | None) -> str:
    text = (source or "").lower()
    if "cursor" in text:
        return "cursor"
    if "anthropic" in text or "claude" in text:
        return "anthropic"
    if text in {"hook", ""}:
        return "unknown"
    return text or "unknown"


def _opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def result_text(result: VendorTestResult) -> str:
    caps = result.capabilities
    lines = [
        f"vendor        {result.name}",
        f"tools         {', '.join(result.tools) or '(none)'}",
        f"capabilities  capture={caps.capture} snapshot={caps.snapshot} "
        f"pull={caps.pull} test={caps.test}",
        f"cred          {'resolved' if result.cred_resolved else 'not configured'}",
    ]
    if result.credentials:
        lines.append("credentials")
        for item in result.credentials:
            state = f"{item.source}" if item.present else "unresolved"
            opt = "optional" if item.optional else "required"
            lines.append(f"  {item.env:<28} {state:<12} {opt}  {item.purpose}")
    if result.detail:
        lines.append(result.detail)
    return "\n".join(lines) + "\n"


def dump_public(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "as_dict"):
        return obj.as_dict()
    if dataclass_instance(obj):
        return asdict(obj)
    raise TypeError(type(obj))


def dataclass_instance(obj: Any) -> bool:
    return hasattr(obj, "__dataclass_fields__")
