"""Anthropic T2a — Claude Enterprise Analytics API pull.

T0 capture and T1 OAuth snapshots stay independent. T2a pull is gated on
``ANTHROPIC_ANALYTICS_API_KEY`` (``ANTHROPIC_ANALYTICS_KEY`` accepted as
alias). Mint a key at claude.ai → Organization settings → API
(``read:analytics``). This is **not** an Admin API key
(``sk-ant-admin01-…``) and **not** ``ANTHROPIC_API_KEY``.

When the key is missing, ``vendor test`` / ``vendor pull`` soft-skip
(Team/Enterprise only; Free stays T0) and exit success — install,
status, statement, and fresh-box stay T0/T1-only.

Events join T0 anthropic/hook rows on ``session_id`` / ``conversation_id``
when an Analytics payload exposes them (or a ``project`` slug that looks
like ``owner/repo``). Unmatched → project ``unattributed``. Emails and
keys are never written to the ledger.

Endpoints (GET, ``x-api-key`` + ``anthropic-version``):

- ``/v1/organizations/analytics/summaries`` — test probe
- ``/v1/organizations/analytics/usage_report`` — token buckets
- ``/v1/organizations/analytics/cost_report`` — billed amounts (fractional cents)
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from ardoise import db, paths, prices
from ardoise.vendors.contract import cycle_of, entry_to_event

VENDOR = "anthropic"
SOURCE = "anthropic_t2a"
STREAM = "analytics_usage"
UNATTRIBUTED = "unattributed"
ENV_KEYS = ("ANTHROPIC_ANALYTICS_API_KEY", "ANTHROPIC_ANALYTICS_KEY")
# Explicit vendor test/pull only. Do not surface this as a post-install next step.
_MISSING_CRED = "anthropic: Analytics T2a skipped (Team/Enterprise only; Free is T0)"
DEFAULT_BASE = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
PAGE_LIMIT = 31
DEFAULT_LOOKBACK = timedelta(days=7)
OVERLAP = timedelta(days=1)
MIN_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
T0_SOURCES = ("anthropic_t0", "hook", "anthropic")

Transport = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]


def _person() -> str | None:
    raw = os.environ.get("ARDOISE_PERSON")
    return raw.strip() if raw and raw.strip() else None


def analytics_api_key(environ: dict[str, str] | None = None) -> str | None:
    env = environ if environ is not None else os.environ
    for name in ENV_KEYS:
        value = str(env.get(name) or "").strip()
        if value:
            return value
    return None


def api_base(environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    raw = str(env.get("ANTHROPIC_ANALYTICS_API_BASE") or DEFAULT_BASE).strip()
    return raw.rstrip("/") or DEFAULT_BASE


def capabilities(environ: dict[str, str] | None = None) -> dict[str, Any]:
    has = bool(analytics_api_key(environ))
    return {
        "vendor": VENDOR,
        "t0": True,
        "t1": False,
        "t2": has,
        "t2a": has,
        "has_cred": has,
    }


def _iso(stamp: datetime) -> str:
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        stamp = value
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            try:
                return datetime(int(text[:4]), int(text[5:7]), int(text[8:10]), tzinfo=timezone.utc)
            except ValueError:
                return None
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _ms_or_iso_to_iso(value: Any) -> str | None:
    stamp = _parse_dt(value)
    if stamp is not None:
        return _iso(stamp)
    if isinstance(value, str) and "T" in value:
        return value if value.endswith("Z") or "+" in value[10:] else value + "Z"
    return None


def _int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def _amount_cents(value: Any) -> float | None:
    """Analytics ``amount`` is a decimal string in fractional cents."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _looks_like_slug(value: str) -> bool:
    if "/" not in value or value.startswith("claude_proj"):
        return False
    owner, _, repo = value.partition("/")
    return bool(owner and repo and " " not in value)


def session_key(row: dict[str, Any]) -> str | None:
    for key in (
        "session_id",
        "sessionId",
        "conversation_id",
        "conversationId",
    ):
        raw = row.get(key)
        if raw:
            return str(raw)
    return None


def project_key(row: dict[str, Any]) -> str | None:
    for key in ("project", "project_slug", "repo", "repository"):
        raw = row.get(key)
        if raw and _looks_like_slug(str(raw)):
            return str(raw)
    return None


def event_id(row: dict[str, Any]) -> str:
    explicit = row.get("id") or row.get("eventId") or row.get("event_id")
    if explicit:
        return str(explicit)
    actor = row.get("actor") if isinstance(row.get("actor"), dict) else {}
    user = row.get("user") if isinstance(row.get("user"), dict) else {}
    seed = "|".join(
        [
            str(row.get("starting_at") or row.get("timestamp") or row.get("occurred_at") or ""),
            str(row.get("model") or ""),
            str(row.get("product") or ""),
            str(session_key(row) or ""),
            str(row.get("project_id") or ""),
            str(actor.get("user_id") or user.get("id") or row.get("user_id") or ""),
            str(row.get("uncached_input_tokens") or row.get("input_tokens") or 0),
            str(row.get("output_tokens") or 0),
            str(row.get("amount") or row.get("billed_cents") or ""),
        ]
    )
    return "ant_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _token_fields(row: dict[str, Any]) -> dict[str, int]:
    cache = row.get("cache_creation") if isinstance(row.get("cache_creation"), dict) else {}
    t5 = _int(
        cache.get("ephemeral_5m_input_tokens")
        or row.get("cache_creation_5m_tokens")
        or row.get("cacheCreation5mTokens")
    )
    t1h = _int(
        cache.get("ephemeral_1h_input_tokens")
        or row.get("cache_creation_1h_tokens")
        or row.get("cacheCreation1hTokens")
    )
    cache_write = _int(
        row.get("cache_creation_tokens")
        or row.get("cache_creation_input_tokens")
        or (t5 + t1h)
    )
    if t5 or t1h:
        cache_write = max(cache_write, t5 + t1h)
    input_tokens = _int(
        row.get("uncached_input_tokens")
        or row.get("input_tokens")
        or row.get("inputTokens")
    )
    output_tokens = _int(row.get("output_tokens") or row.get("outputTokens"))
    cache_read = _int(
        row.get("cache_read_input_tokens")
        or row.get("cache_read_tokens")
        or row.get("cacheReadTokens")
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_tokens": cache_write,
        "cache_read_tokens": cache_read,
        "cache_creation_5m_tokens": t5,
        "cache_creation_1h_tokens": t1h,
    }


def parse_event(row: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize an Analytics usage/cost row (or event-shaped fixture) to a T2a entry."""
    if not isinstance(row, dict):
        return None
    tokens = _token_fields(row)
    amount = _amount_cents(row.get("amount"))
    if amount is None:
        charged = row.get("charged_cents")
        if charged is None:
            charged = row.get("billed_cents")
        amount = _amount_cents(charged)
    if not any([*tokens.values(), amount]):
        return None
    eid = event_id(row)
    occurred = (
        _ms_or_iso_to_iso(row.get("starting_at"))
        or _ms_or_iso_to_iso(row.get("timestamp"))
        or _ms_or_iso_to_iso(row.get("occurred_at"))
        or db._now()
    )
    session = session_key(row)
    if amount is not None:
        cost = round(amount / 100.0, 8)
        billed = int(round(amount))
    else:
        cost = prices.price_usd(
            model=row.get("model"),
            input_tokens=tokens["input_tokens"],
            output_tokens=tokens["output_tokens"],
            cache_read_tokens=tokens["cache_read_tokens"],
            cache_creation_tokens=tokens["cache_creation_tokens"],
            cache_creation_5m_tokens=tokens["cache_creation_5m_tokens"],
            cache_creation_1h_tokens=tokens["cache_creation_1h_tokens"],
        )
        billed = None
    payload = {
        "vendor": VENDOR,
        "source": SOURCE,
        "tier": "T2",
        "message_id": eid,
        "request_id": eid,
        "event_id": eid,
        "conversation_id": session,
        "session_id": session,
        "model": row.get("model"),
        "occurred_at": occurred,
        "cycle": cycle_of(occurred),
        "input_tokens": tokens["input_tokens"],
        "output_tokens": tokens["output_tokens"],
        "cache_creation_tokens": tokens["cache_creation_tokens"],
        "cache_read_tokens": tokens["cache_read_tokens"],
        "cache_creation_5m_tokens": tokens["cache_creation_5m_tokens"],
        "cache_creation_1h_tokens": tokens["cache_creation_1h_tokens"],
        "cost_usd": cost,
        "billed_cents": billed,
        "person": _person() or "",
        "product": row.get("product"),
    }
    slug = project_key(row)
    if slug:
        payload["project"] = slug
    return payload


def iter_analytics_rows(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Flatten bucketed usage/cost reports and flat ``data`` / ``usageEvents`` lists."""
    if not isinstance(payload, dict):
        return []
    rows: list[dict[str, Any]] = []
    data = payload.get("data")
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            results = item.get("results")
            if isinstance(results, list):
                for result in results:
                    if not isinstance(result, dict):
                        continue
                    row = dict(result)
                    row.setdefault("starting_at", item.get("starting_at"))
                    row.setdefault("ending_at", item.get("ending_at"))
                    rows.append(row)
            else:
                rows.append(item)
        return rows
    for key in ("usageEvents", "events", "results"):
        batch = payload.get(key)
        if isinstance(batch, list):
            rows.extend(r for r in batch if isinstance(r, dict))
    return rows


def merge_cost_into_usage(
    usage_rows: list[dict[str, Any]],
    cost_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    index: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for cost in cost_rows:
        key = (cost.get("starting_at"), cost.get("model"), cost.get("product"))
        index[key] = cost
    merged: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()
    for usage in usage_rows:
        key = (usage.get("starting_at"), usage.get("model"), usage.get("product"))
        seen.add(key)
        cost = index.get(key)
        if cost is not None and usage.get("amount") is None and cost.get("amount") is not None:
            usage = {**usage, "amount": cost.get("amount")}
        merged.append(usage)
    for key, cost in index.items():
        if key not in seen:
            merged.append(cost)
    return merged


def make_transport(api_key: str, base_url: str | None = None) -> Transport:
    base = (base_url or DEFAULT_BASE).rstrip("/")

    def send(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = base + path
        payload = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method=method)
        req.add_header("x-api-key", api_key)
        req.add_header("anthropic-version", ANTHROPIC_VERSION)
        req.add_header("Accept", "application/json")
        if payload is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"anthropic analytics {method} {path.split('?', 1)[0]} failed: HTTP {exc.code}"
            ) from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"anthropic analytics API unreachable: {exc.reason}") from None
        if not raw.strip():
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise RuntimeError("anthropic analytics API returned a non-object")
        return data

    return send


def _encode_query(params: list[tuple[str, str]]) -> str:
    return urllib.parse.urlencode(params, doseq=True)


def _paged_get(transport: Transport, path: str, params: list[tuple[str, str]]) -> dict[str, Any]:
    combined: dict[str, Any] = {"data": [], "has_more": False, "next_page": None}
    page: str | None = None
    for _ in range(10_000):
        query = list(params)
        if page:
            query.append(("page", page))
        data = transport("GET", f"{path}?{_encode_query(query)}", None)
        if not isinstance(data, dict):
            break
        batch = data.get("data")
        if isinstance(batch, list):
            combined["data"].extend(batch)
        if data.get("data_refreshed_at") and not combined.get("data_refreshed_at"):
            combined["data_refreshed_at"] = data["data_refreshed_at"]
        if data.get("organization_id"):
            combined["organization_id"] = data["organization_id"]
        if data.get("summaries") and not combined.get("summaries"):
            combined["summaries"] = data["summaries"]
        has_more = bool(data.get("has_more"))
        next_page = data.get("next_page")
        if not has_more or not next_page:
            combined["has_more"] = False
            combined["next_page"] = None
            break
        page = str(next_page)
    return combined


def fetch_summaries(
    transport: Transport,
    *,
    starting_date: str,
    ending_date: str | None = None,
) -> dict[str, Any]:
    params = [("starting_date", starting_date)]
    if ending_date:
        params.append(("ending_date", ending_date))
    return transport("GET", f"/v1/organizations/analytics/summaries?{_encode_query(params)}", None)


def fetch_usage_report(
    transport: Transport,
    *,
    starting_at: str,
    ending_at: str,
) -> dict[str, Any]:
    params = [
        ("starting_at", starting_at),
        ("ending_at", ending_at),
        ("bucket_width", "1d"),
        ("limit", str(PAGE_LIMIT)),
        ("group_by[]", "model"),
        ("group_by[]", "product"),
    ]
    return _paged_get(transport, "/v1/organizations/analytics/usage_report", params)


def fetch_cost_report(
    transport: Transport,
    *,
    starting_at: str,
    ending_at: str,
) -> dict[str, Any]:
    params = [
        ("starting_at", starting_at),
        ("ending_at", ending_at),
        ("bucket_width", "1d"),
        ("limit", str(PAGE_LIMIT)),
        ("group_by[]", "model"),
        ("group_by[]", "product"),
    ]
    return _paged_get(transport, "/v1/organizations/analytics/cost_report", params)


def project_for_session(conn: Any, session_id: str | None) -> str:
    if not session_id:
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
        (session_id, *T0_SOURCES, UNATTRIBUTED),
    ).fetchone()
    if row and row["project"]:
        return str(row["project"])
    return UNATTRIBUTED


def attribute_project(conn: Any, parsed: dict[str, Any]) -> str:
    slug = parsed.get("project")
    if slug and _looks_like_slug(str(slug)):
        return str(slug)
    return project_for_session(conn, parsed.get("session_id") or parsed.get("conversation_id"))


def upsert_t2a_entry(conn: Any, row: dict[str, Any]) -> str:
    """Idempotent upsert keyed by event id. Writes the events table (entries is a view)."""
    occurred = row.get("occurred_at") or db._now()
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
        "session_id": row.get("session_id") or row.get("conversation_id"),
        "cwd": row.get("cwd"),
        "ingested_at": db._now(),
    }
    existing = conn.execute(
        """
        SELECT project, model, input_tokens, output_tokens,
               cache_creation_tokens, cache_read_tokens, cost_usd, session_id
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
              billed_cents, cost_usd, tier, session_id, cwd, ingested_at
            ) VALUES (
              :vendor, :source, :person, :cycle, :message_id, :request_id, :project, :model,
              :occurred_at, :input_tokens, :output_tokens, :cache_creation_tokens,
              :cache_read_tokens, :cache_creation_5m_tokens, :cache_creation_1h_tokens,
              :billed_cents, :cost_usd, :tier, :session_id, :cwd, :ingested_at
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
          ingested_at = :ingested_at
        WHERE message_id = :message_id AND request_id = :request_id
        """,
        payload,
    )
    return "updated"


def _clamp_start(stamp: datetime) -> datetime:
    if stamp < MIN_START:
        return MIN_START
    return stamp


def _window_iso(*, conn: Any, now: datetime, since: str | None) -> tuple[str, str]:
    end = _iso(now)
    if since:
        start_dt = _parse_dt(since) or _clamp_start(now - DEFAULT_LOOKBACK)
        return _iso(_clamp_start(start_dt)), end
    raw = db.get_sync_watermark(conn, VENDOR, STREAM)
    if raw:
        start_dt = _parse_dt(raw)
        if start_dt is not None:
            return _iso(_clamp_start(start_dt - OVERLAP)), end
    return _iso(_clamp_start(now - DEFAULT_LOOKBACK)), end


def _missing_cred_result(*, action: str) -> dict[str, Any]:
    return {
        "vendor": VENDOR,
        "ok": True,
        "has_cred": False,
        "t0": True,
        "t2": False,
        "t2a": False,
        "skipped": True,
        "reason": "missing_cred",
        "action": action,
        "message": _MISSING_CRED,
    }


def pull(
    *,
    db_path: Any = None,
    conn: Any = None,
    transport: Transport | None = None,
    environ: dict[str, str] | None = None,
    now: datetime | None = None,
    since: str | None = None,
) -> dict[str, Any]:
    """Ingest T2a Analytics rows (join + unattributed). No-op without credentials."""
    key = analytics_api_key(environ)
    if transport is None:
        if not key:
            return _missing_cred_result(action="pull")
        transport = make_transport(key, api_base(environ))
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)

    def _run(cx: Any) -> dict[str, Any]:
        start_iso, end_iso = _window_iso(conn=cx, now=stamp, since=since)
        usage_payload = fetch_usage_report(transport, starting_at=start_iso, ending_at=end_iso)
        try:
            cost_payload = fetch_cost_report(transport, starting_at=start_iso, ending_at=end_iso)
        except RuntimeError:
            cost_payload = {}
        raw_rows = merge_cost_into_usage(
            iter_analytics_rows(usage_payload),
            iter_analytics_rows(cost_payload),
        )
        totals = {"inserted": 0, "updated": 0, "skipped": 0, "unattributed": 0, "attributed": 0}
        latest = start_iso
        kept = 0
        for raw in raw_rows:
            parsed = parse_event(raw)
            if not parsed:
                continue
            kept += 1
            parsed["project"] = attribute_project(cx, parsed)
            totals["unattributed" if parsed["project"] == UNATTRIBUTED else "attributed"] += 1
            kind = upsert_t2a_entry(cx, parsed)
            totals[kind] = totals.get(kind, 0) + 1
            row_ts = raw.get("starting_at") or raw.get("timestamp") or parsed.get("occurred_at")
            if row_ts and str(row_ts) > str(latest):
                latest = str(row_ts)
        watermark = end_iso
        refreshed = None
        if isinstance(usage_payload, dict):
            refreshed = usage_payload.get("data_refreshed_at")
        if refreshed and str(refreshed) < watermark:
            watermark = str(refreshed)
        if latest and str(latest) > watermark:
            watermark = str(latest)
        db.set_sync_state(cx, vendor=VENDOR, kind=STREAM, cursor=watermark, ok=True)
        return {
            "vendor": VENDOR,
            "ok": True,
            "has_cred": True,
            "t0": True,
            "t2": True,
            "t2a": True,
            "skipped": False,
            "events": kept,
            "inserted": totals["inserted"],
            "updated": totals["updated"],
            "skipped_rows": totals["skipped"],
            "unattributed": totals["unattributed"],
            "attributed": totals["attributed"],
            "watermark": watermark,
            "starting_at": start_iso,
            "ending_at": end_iso,
        }

    if conn is not None:
        return _run(conn)
    paths.ensure_home()
    with db.session(db_path) as cx:
        return _run(cx)


def test_vendor(
    *,
    transport: Transport | None = None,
    environ: dict[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    key = analytics_api_key(environ)
    if transport is None:
        if not key:
            return _missing_cred_result(action="test")
        transport = make_transport(key, api_base(environ))
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    end_iso = _iso(stamp)
    start_dt = _clamp_start(stamp - DEFAULT_LOOKBACK)
    start_iso = _iso(start_dt)
    start_date = start_dt.strftime("%Y-%m-%d")
    try:
        summaries = fetch_summaries(transport, starting_date=start_date)
        usage = fetch_usage_report(transport, starting_at=start_iso, ending_at=end_iso)
    except RuntimeError as exc:
        return {
            "vendor": VENDOR,
            "ok": False,
            "has_cred": True,
            "t0": True,
            "t2": True,
            "t2a": True,
            "error": str(exc),
            "message": f"anthropic: error: {exc}",
        }
    summary_rows = summaries.get("summaries") if isinstance(summaries, dict) else None
    usage_rows = iter_analytics_rows(usage if isinstance(usage, dict) else {})
    n_sum = len(summary_rows) if isinstance(summary_rows, list) else 0
    n_usage = len(usage_rows)
    return {
        "vendor": VENDOR,
        "ok": True,
        "has_cred": True,
        "t0": True,
        "t2": True,
        "t2a": True,
        "skipped": False,
        "summaries": n_sum,
        "usage_rows": n_usage,
        "message": f"anthropic: t2a summaries={n_sum} usage_rows={n_usage}",
    }


def render_test(data: dict[str, Any]) -> str:
    if data.get("message"):
        return str(data["message"]).rstrip() + "\n"
    if not data.get("has_cred"):
        return f"{_MISSING_CRED}\n"
    return (
        "anthropic: t2a summaries={summaries} usage_rows={usage_rows}\n".format(
            summaries=data.get("summaries", 0),
            usage_rows=data.get("usage_rows", 0),
        )
    )


def render_pull(data: dict[str, Any]) -> str:
    if data.get("skipped") and data.get("reason") == "missing_cred":
        return str(data.get("message") or _MISSING_CRED).rstrip() + "\n"
    if not data.get("ok"):
        return f"anthropic: error: {data.get('error') or 'pull failed'}\n"
    return (
        "anthropic pull inserted={inserted} updated={updated} skipped={skipped} "
        "unattributed={unattributed} events={events}\n".format(
            inserted=data.get("inserted", 0),
            updated=data.get("updated", 0),
            skipped=data.get("skipped_rows", 0),
            unattributed=data.get("unattributed", 0),
            events=data.get("events", 0),
        )
    )


def iter_pull_events(
    *,
    transport: Transport,
    starting_at: str,
    ending_at: str,
    person: str | None = None,
):
    usage_payload = fetch_usage_report(transport, starting_at=starting_at, ending_at=ending_at)
    try:
        cost_payload = fetch_cost_report(transport, starting_at=starting_at, ending_at=ending_at)
    except RuntimeError:
        cost_payload = {}
    for raw in merge_cost_into_usage(
        iter_analytics_rows(usage_payload),
        iter_analytics_rows(cost_payload),
    ):
        parsed = parse_event(raw)
        if not parsed:
            continue
        if person:
            parsed["person"] = person
        if not parsed.get("project"):
            parsed["project"] = UNATTRIBUTED
        yield entry_to_event(parsed)
