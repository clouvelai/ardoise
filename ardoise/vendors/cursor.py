"""Cursor vendor adapter — T0 transcripts plus T2 Admin API pull.

T0 capture works with no credentials. Live Admin T2 probe/pull is gated
on CURSOR_ADMIN_API_KEY only. CURSOR_API_KEY is not accepted (personal
keys 401). Events join T0 hook/transcript rows on conversation_id
(session_id) for project, and on conversation_id / cloudAgentId (bcId)
for ``agent=`` when a T0 row or local sidecar already names that run.
Unmatched project → ``unattributed``. Unknown agent ids stay unset.
Never invents agent names.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from ardoise import db, paths, prices
from ardoise.adapters.hook_event import event_to_entry
from ardoise.attribution import DIMENSIONS, bind, clean_id, extract
from ardoise.privacy import scrub
from ardoise.vendors.anthropic import parse_t0_line
from ardoise.vendors.contract import (
    Capabilities,
    CredentialField,
    CredentialNotConfigured,
    CredentialSpec,
    Event,
    Snapshot,
    VendorTestResult,
    cycle_of,
    entry_to_event,
)
from ardoise.vendors.jsonl import iter_jsonl

VENDOR = "cursor"
SOURCE = "cursor_t2"
STREAM_EVENTS = "usage_events"
UNATTRIBUTED = "unattributed"
ADMIN_ENV = "CURSOR_ADMIN_API_KEY"
ALIAS_ENV = "CURSOR_API_KEY"  # personal/solo; not a live Admin probe
ENV_KEYS = (ADMIN_ENV,)
DEFAULT_BASE = "https://api.cursor.com"
PAGE_SIZE = 100
DEFAULT_LOOKBACK = timedelta(days=7)
OVERLAP = timedelta(hours=1)
T0_SOURCES = ("cursor", "hook", "anthropic_t0")
# Fail-open copy for vendor test 401 / Invalid Team API Key. Never interpolates the key.
# Minting path stays in docs/meter-shape.md only — no dashboard / admin:* hunt here.
_AUTH_REJECTED = "cursor: not a Team Admin key — T0 unchanged"
# Explicit vendor test/pull only. Do not surface this as a post-install next step.
_MISSING_CRED = "cursor: Admin T2 skipped (Team/Enterprise only; Free is T0)"
_ALIAS_REJECTED = "cursor: CURSOR_API_KEY is not a Team Admin key — T0 unchanged"

Transport = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]


def _person() -> str | None:
    raw = os.environ.get("ARDOISE_PERSON")
    return raw.strip() if raw and raw.strip() else None


def discover_cursor_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for pattern in (
        "projects/**/*.jsonl",
        "ai-tracking/**/*.jsonl",
        "chats/**/*.jsonl",
        "transcripts/**/*.jsonl",
        "**/*transcript*.jsonl",
    ):
        files.extend(p for p in root.glob(pattern) if p.is_file())
    seen: set[Path] = set()
    out: list[Path] = []
    skip_parts = {"agent-transcripts", "subagents"}
    for path in files:
        if any(part in skip_parts for part in path.parts):
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(path)
    return out


def parse_cursor_line(obj: dict[str, Any]) -> dict[str, Any] | None:
    entry = parse_t0_line(obj)
    if entry:
        entry["source"] = "cursor"
        entry["vendor"] = "cursor"
        entry["tier"] = "T0"
        entry["person"] = _person() or ""
        return entry
    safe = scrub(obj)
    if isinstance(obj.get("usage"), dict):
        safe["usage"] = obj["usage"]
    if obj.get("model"):
        safe["model"] = obj.get("model")
    if obj.get("requestId") or obj.get("request_id"):
        safe["requestId"] = obj.get("requestId") or obj.get("request_id")
    if obj.get("message_id") or (isinstance(obj.get("message"), dict) and obj["message"].get("id")):
        safe["message_id"] = obj.get("message_id") or obj["message"]["id"]
    entry = event_to_entry(safe, default_source="cursor")
    if entry:
        entry["source"] = "cursor"
        entry["vendor"] = "cursor"
        entry["tier"] = "T0"
        entry["person"] = _person() or ""
        attrs = extract(obj)
        for key in DIMENSIONS:
            if not entry.get(key):
                entry[key] = attrs.get(key)
    return entry


def iter_cursor(root: Path) -> Iterator[tuple[Path, dict[str, Any]]]:
    for path in discover_cursor_files(root):
        for obj in iter_jsonl(path):
            entry = parse_cursor_line(obj)
            if entry:
                yield path, entry


def admin_api_key(environ: dict[str, str] | None = None) -> str | None:
    """Live Admin probe/pull. CURSOR_API_KEY is ignored (accidental 401s)."""
    env = environ if environ is not None else os.environ
    value = str(env.get(ADMIN_ENV) or "").strip()
    return value or None


def _personal_alias_set(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    if admin_api_key(environ):
        return False
    return bool(str(env.get(ALIAS_ENV) or "").strip())


def api_base(environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    raw = str(env.get("CURSOR_ADMIN_API_BASE") or DEFAULT_BASE).strip()
    return raw.rstrip("/") or DEFAULT_BASE


def capabilities(environ: dict[str, str] | None = None) -> dict[str, Any]:
    has = bool(admin_api_key(environ))
    return {
        "vendor": VENDOR,
        "t0": True,
        "t1": False,
        "t2": has,
        "has_cred": has,
    }


def event_id(event: dict[str, Any]) -> str:
    explicit = event.get("id") or event.get("eventId") or event.get("event_id")
    if explicit:
        return str(explicit)
    usage = event.get("tokenUsage") if isinstance(event.get("tokenUsage"), dict) else {}
    seed = "|".join(
        [
            str(event.get("timestamp") or ""),
            str(event.get("userEmail") or event.get("user_email") or ""),
            str(event.get("conversationId") or event.get("conversation_id") or ""),
            str(
                event.get("cloudAgentId")
                or event.get("cloud_agent_id")
                or event.get("bcId")
                or event.get("bc_id")
                or ""
            ),
            str(event.get("model") or ""),
            str(usage.get("inputTokens") or usage.get("input_tokens") or 0),
            str(usage.get("outputTokens") or usage.get("output_tokens") or 0),
            str(event.get("chargedCents") or event.get("charged_cents") or ""),
        ]
    )
    return "cur_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _ms_to_iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str) and "T" in value:
        return value if value.endswith("Z") or "+" in value[10:] else value + "Z"
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return str(value)
    seconds = ms / 1000.0 if ms > 10**12 else float(ms)
    return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_ms(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, str) and "T" in value:
        stamp = value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(stamp)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n * 1000 if n < 10**12 else n


def parse_event(event: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    usage = event.get("tokenUsage") if isinstance(event.get("tokenUsage"), dict) else {}
    input_tokens = int(usage.get("inputTokens") or usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("outputTokens") or usage.get("output_tokens") or 0)
    cache_write = int(usage.get("cacheWriteTokens") or usage.get("cache_write_tokens") or 0)
    cache_read = int(usage.get("cacheReadTokens") or usage.get("cache_read_tokens") or 0)
    charged = event.get("chargedCents")
    if charged is None:
        charged = event.get("charged_cents")
    if charged is None and usage.get("totalCents") is not None:
        charged = usage.get("totalCents")
    try:
        charged_f = float(charged) if charged is not None else None
    except (TypeError, ValueError):
        charged_f = None
    if not any([input_tokens, output_tokens, cache_write, cache_read, charged_f]):
        return None
    eid = event_id(event)
    conversation = event.get("conversationId") or event.get("conversation_id")
    bc = (
        event.get("cloudAgentId")
        or event.get("cloud_agent_id")
        or event.get("bcId")
        or event.get("bc_id")
    )
    attrs = extract(event)
    occurred = _ms_to_iso(event.get("timestamp")) or db._now()
    if charged_f is not None:
        cost = round(charged_f / 100.0, 8)
        billed = int(round(charged_f))
    else:
        cost = prices.price_usd(
            model=event.get("model"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_write,
        )
        billed = None
    return {
        "vendor": VENDOR,
        "source": SOURCE,
        "tier": "T2",
        "message_id": eid,
        "request_id": eid,
        "event_id": eid,
        "conversation_id": str(conversation) if conversation else None,
        "bc_id": str(bc) if bc else None,
        "session_id": str(conversation or bc) if (conversation or bc) else None,
        "model": event.get("model"),
        "agent": attrs.get("agent"),
        "skill": attrs.get("skill"),
        "effort": attrs.get("effort"),
        "occurred_at": occurred,
        "cycle": cycle_of(occurred),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_tokens": cache_write,
        "cache_read_tokens": cache_read,
        "cache_creation_5m_tokens": 0,
        "cache_creation_1h_tokens": 0,
        "cost_usd": cost,
        "billed_cents": billed,
        "person": _person() or "",
    }


def make_transport(api_key: str, base_url: str | None = None) -> Transport:
    base = (base_url or DEFAULT_BASE).rstrip("/")

    def send(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = base + path
        payload = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method=method)
        token = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
        req.add_header("Authorization", f"Basic {token}")
        req.add_header("Accept", "application/json")
        if payload is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"cursor admin API {method} {path} failed: HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"cursor admin API unreachable: {exc.reason}") from None
        if not raw.strip():
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise RuntimeError("cursor admin API returned a non-object")
        return data

    return send


def fetch_members(transport: Transport) -> list[dict[str, Any]]:
    data = transport("GET", "/teams/members", None)
    rows = data.get("teamMembers")
    if rows is None:
        rows = data.get("members")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def fetch_spend(transport: Transport, *, page: int = 1, page_size: int = 100) -> dict[str, Any]:
    data = transport(
        "POST",
        "/teams/spend",
        {"page": page, "pageSize": page_size, "sortBy": "amount", "sortDirection": "desc"},
    )
    return data if isinstance(data, dict) else {}


def fetch_usage_events(
    transport: Transport,
    *,
    start_ms: int,
    end_ms: int,
    page_size: int = PAGE_SIZE,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    page = 1
    while True:
        data = transport(
            "POST",
            "/teams/filtered-usage-events",
            {"startDate": start_ms, "endDate": end_ms, "page": page, "pageSize": page_size},
        )
        batch = data.get("usageEvents") if isinstance(data, dict) else None
        if isinstance(batch, list):
            events.extend(r for r in batch if isinstance(r, dict))
        pagination = data.get("pagination") if isinstance(data, dict) else None
        has_next = bool(pagination.get("hasNextPage")) if isinstance(pagination, dict) else False
        if not has_next:
            break
        page += 1
        if page > 10_000:
            break
    return events


def _id_list(*values: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def event_join_ids(*layers: dict[str, Any] | None) -> list[str]:
    """conversationId + cloudAgentId / bcId from an Admin event or parsed row."""
    values: list[Any] = []
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        values.extend(
            [
                layer.get("conversationId"),
                layer.get("conversation_id"),
                layer.get("cloudAgentId"),
                layer.get("cloud_agent_id"),
                layer.get("bcId"),
                layer.get("bc_id"),
                layer.get("session_id"),
            ]
        )
    return _id_list(*values)


def project_for_conversation(conn: Any, conversation_id: str | None) -> str:
    if not conversation_id:
        return UNATTRIBUTED
    placeholders = ",".join("?" for _ in T0_SOURCES)
    row = conn.execute(
        f"""
        SELECT project FROM entries
        WHERE session_id = ?
          AND source IN ({placeholders})
          AND project IS NOT NULL
          AND project != ''
          AND project != ?
        ORDER BY ingested_at DESC
        LIMIT 1
        """,
        (conversation_id, *T0_SOURCES, UNATTRIBUTED),
    ).fetchone()
    if row and row["project"]:
        return str(row["project"])
    return UNATTRIBUTED


def project_for_ids(conn: Any, ids: list[str] | None) -> str:
    for ident in ids or []:
        found = project_for_conversation(conn, ident)
        if found != UNATTRIBUTED:
            return found
    return UNATTRIBUTED


def _agent_from_ledger(conn: Any, ident: str) -> str | None:
    placeholders = ",".join("?" for _ in T0_SOURCES)
    row = conn.execute(
        f"""
        SELECT agent FROM events
        WHERE session_id = ?
          AND source IN ({placeholders})
          AND agent IS NOT NULL
          AND TRIM(agent) != ''
        ORDER BY ingested_at DESC
        LIMIT 1
        """,
        (ident, *T0_SOURCES),
    ).fetchone()
    if not row:
        return None
    return clean_id(row["agent"])


def agent_for_ids(
    conn: Any | None,
    ids: list[str] | None,
    *,
    raw: dict[str, Any] | None = None,
    parsed: dict[str, Any] | None = None,
    run_agents: dict[str, str] | None = None,
) -> str | None:
    """Named agent already present on the event, a T0 row, or a sidecar map.

    Never invents. Job titles, prompts, and unknown ids stay unset.
    """
    named = extract(raw).get("agent") if raw else None
    if not named and parsed:
        named = bind(parsed).get("agent")
    if named:
        return named
    for ident in ids or []:
        if conn is not None:
            found = _agent_from_ledger(conn, ident)
            if found:
                return found
        mapped = (run_agents or {}).get(ident)
        cleaned = clean_id(mapped)
        if cleaned:
            return cleaned
    return None


def upsert_t2_entry(conn: Any, row: dict[str, Any]) -> str:
    """Idempotent upsert keyed by event id. Writes the events table (entries is a view)."""
    occurred = row.get("occurred_at") or db._now()
    attrs = bind(row)
    payload = {
        "vendor": VENDOR,
        "source": SOURCE,
        "person": row.get("person") or "",
        "cycle": row.get("cycle") or cycle_of(occurred),
        "message_id": str(row["message_id"]),
        "request_id": str(row["request_id"]),
        "project": row.get("project") or UNATTRIBUTED,
        "model": row.get("model"),
        "occurred_at": occurred,
        "input_tokens": int(row.get("input_tokens") or 0),
        "output_tokens": int(row.get("output_tokens") or 0),
        "cache_creation_tokens": int(row.get("cache_creation_tokens") or 0),
        "cache_read_tokens": int(row.get("cache_read_tokens") or 0),
        "cache_creation_5m_tokens": int(row.get("cache_creation_5m_tokens") or 0),
        "cache_creation_1h_tokens": int(row.get("cache_creation_1h_tokens") or 0),
        "billed_cents": row.get("billed_cents"),
        "cost_usd": float(row["cost_usd"]),
        "tier": "T2",
        "session_id": row.get("session_id") or row.get("conversation_id") or row.get("bc_id"),
        "cwd": row.get("cwd"),
        "agent": attrs.get("agent"),
        "skill": attrs.get("skill"),
        "effort": attrs.get("effort"),
        "ingested_at": db._now(),
    }
    existing = conn.execute(
        """
        SELECT project, model, input_tokens, output_tokens,
               cache_creation_tokens, cache_read_tokens, cost_usd, session_id, agent
        FROM events WHERE message_id = ? AND request_id = ?
        """,
        (payload["message_id"], payload["request_id"]),
    ).fetchone()
    if existing is None:
        conn.execute(
            """
            INSERT INTO events (
              vendor, source, person, cycle, message_id, request_id, project, model,
              occurred_at, input_tokens, output_tokens, cache_creation_tokens,
              cache_read_tokens, cache_creation_5m_tokens, cache_creation_1h_tokens,
              billed_cents, cost_usd, tier, session_id, cwd, agent, skill, effort,
              ingested_at
            ) VALUES (
              :vendor, :source, :person, :cycle, :message_id, :request_id, :project, :model,
              :occurred_at, :input_tokens, :output_tokens, :cache_creation_tokens,
              :cache_read_tokens, :cache_creation_5m_tokens, :cache_creation_1h_tokens,
              :billed_cents, :cost_usd, :tier, :session_id, :cwd, :agent, :skill, :effort,
              :ingested_at
            )
            """,
            payload,
        )
        return "inserted"
    same = (
        str(existing["project"] or "") == payload["project"]
        and str(existing["model"] or "") == str(payload["model"] or "")
        and int(existing["input_tokens"] or 0) == payload["input_tokens"]
        and int(existing["output_tokens"] or 0) == payload["output_tokens"]
        and int(existing["cache_creation_tokens"] or 0) == payload["cache_creation_tokens"]
        and int(existing["cache_read_tokens"] or 0) == payload["cache_read_tokens"]
        and abs(float(existing["cost_usd"] or 0) - payload["cost_usd"]) < 1e-8
        and str(existing["session_id"] or "") == str(payload["session_id"] or "")
        and str(existing["agent"] or "") == str(payload["agent"] or "")
    )
    if same:
        return "skipped"
    conn.execute(
        """
        UPDATE events SET
          source = :source,
          vendor = :vendor,
          project = :project,
          model = COALESCE(:model, model),
          occurred_at = :occurred_at,
          cycle = :cycle,
          input_tokens = :input_tokens,
          output_tokens = :output_tokens,
          cache_creation_tokens = :cache_creation_tokens,
          cache_read_tokens = :cache_read_tokens,
          billed_cents = :billed_cents,
          cost_usd = :cost_usd,
          tier = :tier,
          session_id = COALESCE(:session_id, session_id),
          cwd = COALESCE(:cwd, cwd),
          agent = COALESCE(:agent, agent),
          skill = COALESCE(:skill, skill),
          effort = COALESCE(:effort, effort),
          ingested_at = :ingested_at
        WHERE message_id = :message_id AND request_id = :request_id
        """,
        payload,
    )
    return "updated"


def _window_ms(*, conn: Any, now: datetime, since_ms: int | None) -> tuple[int, int]:
    end_ms = int(now.timestamp() * 1000)
    if since_ms is not None:
        return int(since_ms), end_ms
    raw = db.get_sync_watermark(conn, VENDOR, STREAM_EVENTS)
    if raw:
        start = _to_ms(raw)
        if start is not None:
            return max(0, start - int(OVERLAP.total_seconds() * 1000)), end_ms
    return int((now - DEFAULT_LOOKBACK).timestamp() * 1000), end_ms


def _skip_result(*, action: str, reason: str, message: str) -> dict[str, Any]:
    return {
        "vendor": VENDOR,
        "ok": True,
        "has_cred": False,
        "t0": True,
        "t2": False,
        "skipped": True,
        "reason": reason,
        "action": action,
        "message": message,
    }


def _missing_cred_result(*, action: str, environ: dict[str, str] | None = None) -> dict[str, Any]:
    if _personal_alias_set(environ):
        return _skip_result(action=action, reason="alias_not_admin", message=_ALIAS_REJECTED)
    return _skip_result(action=action, reason="missing_cred", message=_MISSING_CRED)


def pull(
    *,
    db_path: Any = None,
    conn: Any = None,
    transport: Transport | None = None,
    environ: dict[str, str] | None = None,
    now: datetime | None = None,
    since_ms: int | None = None,
    run_agents: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Ingest T2 events (join + unattributed). No-op without credentials."""
    key = admin_api_key(environ)
    if transport is None:
        if not key:
            return _missing_cred_result(action="pull", environ=environ)
        transport = make_transport(key, api_base(environ))
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    if run_agents is None:
        from ardoise.adapters.cloud_agent import load_named_run_agents

        sidecar_agents = load_named_run_agents()
    else:
        sidecar_agents = run_agents

    def _run(cx: Any) -> dict[str, Any]:
        start_ms, end_ms = _window_ms(conn=cx, now=stamp, since_ms=since_ms)
        events = fetch_usage_events(transport, start_ms=start_ms, end_ms=end_ms)
        totals = {
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "unattributed": 0,
            "attributed": 0,
            "agent_attributed": 0,
            "agent_unattributed": 0,
        }
        max_ts = start_ms
        for raw in events:
            parsed = parse_event(raw)
            if not parsed:
                continue
            ids = event_join_ids(raw, parsed)
            parsed["project"] = project_for_ids(cx, ids)
            parsed["agent"] = agent_for_ids(
                cx, ids, raw=raw, parsed=parsed, run_agents=sidecar_agents
            )
            totals["unattributed" if parsed["project"] == UNATTRIBUTED else "attributed"] += 1
            if parsed.get("agent"):
                totals["agent_attributed"] += 1
            else:
                totals["agent_unattributed"] += 1
            kind = upsert_t2_entry(cx, parsed)
            totals[kind] = totals.get(kind, 0) + 1
            ev_ms = _to_ms(raw.get("timestamp"))
            if ev_ms is not None and ev_ms > max_ts:
                max_ts = ev_ms
        watermark = str(max(end_ms, max_ts))
        db.set_sync_state(cx, vendor=VENDOR, kind=STREAM_EVENTS, cursor=watermark, ok=True)
        return {
            "vendor": VENDOR,
            "ok": True,
            "has_cred": True,
            "t0": True,
            "t2": True,
            "skipped": False,
            "events": len(events),
            "inserted": totals["inserted"],
            "updated": totals["updated"],
            "skipped_rows": totals["skipped"],
            "unattributed": totals["unattributed"],
            "attributed": totals["attributed"],
            "agent_attributed": totals["agent_attributed"],
            "agent_unattributed": totals["agent_unattributed"],
            "watermark": watermark,
            "start_ms": start_ms,
            "end_ms": end_ms,
        }

    if conn is not None:
        return _run(conn)
    paths.ensure_home()
    with db.session(db_path) as cx:
        return _run(cx)


def _roles_summary(members: list[dict[str, Any]]) -> str:
    roles = sorted(
        {str(m.get("role")).strip() for m in members if m.get("role") and not m.get("isRemoved")}
    )
    return ",".join(roles) if roles else "-"


def test_vendor(
    *,
    transport: Transport | None = None,
    environ: dict[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    key = admin_api_key(environ)
    if transport is None:
        if not key:
            return _missing_cred_result(action="test", environ=environ)
        transport = make_transport(key, api_base(environ))
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    end_ms = int(stamp.timestamp() * 1000)
    start_ms = int((stamp - DEFAULT_LOOKBACK).timestamp() * 1000)
    try:
        members = fetch_members(transport)
        events = fetch_usage_events(transport, start_ms=start_ms, end_ms=end_ms)
        spend = fetch_spend(transport)
    except RuntimeError as exc:
        text = str(exc).lower()
        if "401" in text or "invalid team api key" in text or "unauthorized" in text:
            return {
                "vendor": VENDOR,
                "ok": False,
                "has_cred": True,
                "t0": True,
                "t2": True,
                "error": str(exc),
                "message": _AUTH_REJECTED,
            }
        return {
            "vendor": VENDOR,
            "ok": False,
            "has_cred": True,
            "t0": True,
            "t2": True,
            "error": str(exc),
            "message": f"cursor: error: {exc}",
        }
    spend_rows = spend.get("teamMemberSpend") if isinstance(spend, dict) else None
    role = _roles_summary(members)
    return {
        "vendor": VENDOR,
        "ok": True,
        "has_cred": True,
        "t0": True,
        "t2": True,
        "skipped": False,
        "roster": len(members),
        "role": role,
        "events_7d": len(events),
        "spend_members": len(spend_rows) if isinstance(spend_rows, list) else 0,
        "message": f"cursor: roster={len(members)} role={role} events_7d={len(events)}",
    }


def render_test(data: dict[str, Any]) -> str:
    if data.get("message"):
        return str(data["message"]).rstrip() + "\n"
    if not data.get("has_cred"):
        return f"{_MISSING_CRED}\n"
    return (
        "cursor: roster={roster} role={role} events_7d={events_7d}\n".format(
            roster=data.get("roster", 0),
            role=data.get("role") or "-",
            events_7d=data.get("events_7d", 0),
        )
    )


def render_pull(data: dict[str, Any]) -> str:
    if data.get("skipped") and data.get("reason") in {"missing_cred", "alias_not_admin"}:
        return str(data.get("message") or _MISSING_CRED).rstrip() + "\n"
    if not data.get("ok"):
        return f"cursor: error: {data.get('error') or 'pull failed'}\n"
    return (
        "cursor pull inserted={inserted} updated={updated} skipped={skipped} "
        "unattributed={unattributed} events={events}\n".format(
            inserted=data.get("inserted", 0),
            updated=data.get("updated", 0),
            skipped=data.get("skipped_rows", 0),
            unattributed=data.get("unattributed", 0),
            events=data.get("events", 0),
        )
    )


class CursorAdapter:
    name = "cursor"
    tools = ("cursor",)
    credential_spec = CredentialSpec(
        fields=(
            CredentialField(
                key="api_key",
                env="CURSOR_ADMIN_API_KEY",
                purpose="advanced Team/Enterprise Admin T2 pull",
                optional=True,
            ),
        )
    )
    capabilities = Capabilities(
        capture="yes",
        snapshot="no",
        pull="yes",
        test="yes",
    )

    def capture(self, *, root: Path | None = None) -> Iterator[Event]:
        base = root or paths.cursor_root()
        for _path, entry in iter_cursor(base):
            yield entry_to_event(entry)

    def snapshot(self, *, person: str | None = None, cycle: str | None = None) -> Snapshot:
        raise CredentialNotConfigured(self.name, "T1 snapshot")

    def pull(self, *, person: str | None = None, cycle: str | None = None) -> Iterator[Event]:
        key = admin_api_key()
        if not key:
            raise CredentialNotConfigured(self.name, "T2 pull")
            yield  # pragma: no cover
        transport = make_transport(key, api_base())
        stamp = datetime.now(timezone.utc)
        end_ms = int(stamp.timestamp() * 1000)
        start_ms = int((stamp - DEFAULT_LOOKBACK).timestamp() * 1000)
        for raw in fetch_usage_events(transport, start_ms=start_ms, end_ms=end_ms):
            parsed = parse_event(raw)
            if parsed:
                if person:
                    parsed["person"] = person
                yield entry_to_event(parsed)

    def test(self) -> VendorTestResult:
        from ardoise.vendors.creds import resolve_status

        status = resolve_status(self.credential_spec)
        resolved = any(item.present for item in status)
        data = test_vendor()
        return VendorTestResult(
            name=self.name,
            tools=self.tools,
            capabilities=self.capabilities,
            credentials=status,
            cred_resolved=resolved,
            ok=bool(data.get("ok", True)),
            detail=str(data.get("message") or ""),
        )
