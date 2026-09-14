"""SQLite ledger at ~/.ardoise/ledger.db.

Schema v2 adds events (canonical), snapshots, prices, projects, sync_state,
and invoices. `entries` remains a compatibility view over `events`.
Opening the DB upgrades an existing Phase 1 file in place.
v4 adds optional agent / skill / effort attribution columns (NULL when absent).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ardoise import paths, prices
from ardoise.attribution import bind
from ardoise.vendors.contract import cycle_of, vendor_for_source

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  vendor TEXT NOT NULL DEFAULT 'unknown',
  source TEXT NOT NULL,
  person TEXT NOT NULL DEFAULT '',
  cycle TEXT NOT NULL DEFAULT '',
  message_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  project TEXT,
  model TEXT,
  occurred_at TEXT NOT NULL,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens INTEGER NOT NULL DEFAULT 0,
  cache_creation_5m_tokens INTEGER NOT NULL DEFAULT 0,
  cache_creation_1h_tokens INTEGER NOT NULL DEFAULT 0,
  billed_cents INTEGER,
  cost_usd REAL NOT NULL DEFAULT 0,
  tier TEXT NOT NULL DEFAULT 'T0',
  session_id TEXT,
  cwd TEXT,
  agent TEXT,
  skill TEXT,
  effort TEXT,
  ingested_at TEXT NOT NULL,
  UNIQUE(message_id, request_id)
);

CREATE INDEX IF NOT EXISTS idx_events_occurred ON events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_project ON events(project);
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);
CREATE INDEX IF NOT EXISTS idx_events_vendor ON events(vendor);
CREATE INDEX IF NOT EXISTS idx_events_tier ON events(tier);
CREATE INDEX IF NOT EXISTS idx_events_cycle ON events(vendor, person, cycle);

CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  vendor TEXT NOT NULL,
  person TEXT NOT NULL DEFAULT '',
  cycle TEXT NOT NULL,
  as_of TEXT NOT NULL,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens INTEGER NOT NULL DEFAULT 0,
  cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
  billed_cents INTEGER,
  cost_usd REAL,
  tier TEXT NOT NULL DEFAULT 'T1',
  ingested_at TEXT NOT NULL,
  UNIQUE(vendor, person, cycle, as_of)
);

CREATE TABLE IF NOT EXISTS prices (
  model TEXT PRIMARY KEY,
  input REAL NOT NULL,
  output REAL NOT NULL,
  cache_read REAL NOT NULL,
  cache_write_5m REAL NOT NULL,
  cache_write_1h REAL NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  unit TEXT NOT NULL DEFAULT 'per_million_tokens',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
  slug TEXT PRIMARY KEY,
  remote_url TEXT,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
  vendor TEXT NOT NULL,
  person TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL,
  cursor TEXT,
  last_success TEXT,
  last_error TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (vendor, person, kind)
);

CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  vendor TEXT NOT NULL,
  cycle TEXT NOT NULL,
  person TEXT NOT NULL DEFAULT '',
  usd_cents INTEGER NOT NULL,
  source TEXT NOT NULL DEFAULT 'paste'
    CHECK (source IN ('paste', 't1', 't2')),
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(vendor, cycle, person)
);

CREATE TABLE IF NOT EXISTS sources (
  path TEXT PRIMARY KEY,
  bytes INTEGER,
  mtime REAL,
  ingested_at TEXT NOT NULL
);
"""

SCHEMA_VERSION = "4"
INVOICE_SOURCES = frozenset({"paste", "t1", "t2"})

_ENTRY_COLS = (
    "source",
    "message_id",
    "request_id",
    "project",
    "model",
    "occurred_at",
    "input_tokens",
    "output_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
    "cache_creation_5m_tokens",
    "cache_creation_1h_tokens",
    "cost_usd",
    "session_id",
    "cwd",
    "ingested_at",
)

_LEDGER_SECRET_KEYS = frozenset(
    {
        "credential",
        "credentials",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "authorization",
        "password",
        "secret",
        "token",
        "admin_api_key",
        "cursor_api_key",
        "anthropic_admin_api_key",
        "anthropic_api_key",
    }
)


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    paths.ensure_home()
    path = db_path or paths.ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    upgrade(conn)
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    return conn


def upgrade(conn: sqlite3.Connection) -> None:
    """Idempotent schema upgrade for Phase 1 ledgers and partial v2 files."""
    _ensure_columns(
        conn,
        "events",
        {
            "vendor": "TEXT NOT NULL DEFAULT 'unknown'",
            "person": "TEXT NOT NULL DEFAULT ''",
            "cycle": "TEXT NOT NULL DEFAULT ''",
            "billed_cents": "INTEGER",
            "tier": "TEXT NOT NULL DEFAULT 'T0'",
            "agent": "TEXT",
            "skill": "TEXT",
            "effort": "TEXT",
        },
    )
    _rebuild_invoices(conn)
    _migrate_entries_view(conn)
    seed_prices(conn)


def _object_type(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute(
        "SELECT type FROM sqlite_master WHERE name = ?", (name,)
    ).fetchone()
    return str(row[0]) if row else None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _ensure_columns(conn: sqlite3.Connection, table: str, specs: dict[str, str]) -> None:
    if _object_type(conn, table) != "table":
        return
    have = _columns(conn, table)
    for name, decl in specs.items():
        if name not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def _rebuild_invoices(conn: sqlite3.Connection) -> None:
    """v3 invoices: (vendor, cycle, person) + usd_cents + source paste|t1|t2."""
    kind = _object_type(conn, "invoices")
    if kind != "table":
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS invoices (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              vendor TEXT NOT NULL,
              cycle TEXT NOT NULL,
              person TEXT NOT NULL DEFAULT '',
              usd_cents INTEGER NOT NULL,
              source TEXT NOT NULL DEFAULT 'paste'
                CHECK (source IN ('paste', 't1', 't2')),
              notes TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(vendor, cycle, person)
            );
            """
        )
        return
    cols = _columns(conn, "invoices")
    if "usd_cents" in cols and "invoice_id" not in cols:
        return
    conn.execute("ALTER TABLE invoices RENAME TO invoices_legacy")
    conn.executescript(
        """
        CREATE TABLE invoices (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          vendor TEXT NOT NULL,
          cycle TEXT NOT NULL,
          person TEXT NOT NULL DEFAULT '',
          usd_cents INTEGER NOT NULL,
          source TEXT NOT NULL DEFAULT 'paste'
            CHECK (source IN ('paste', 't1', 't2')),
          notes TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(vendor, cycle, person)
        );
        """
    )
    legacy = _columns(conn, "invoices_legacy")
    cents = "usd_cents" if "usd_cents" in legacy else "billed_cents"
    created = "created_at" if "created_at" in legacy else "ingested_at"
    notes = "notes" if "notes" in legacy else "NULL"
    source = "source" if "source" in legacy else "'paste'"
    conn.execute(
        f"""
        INSERT INTO invoices (vendor, cycle, person, usd_cents, source, notes, created_at, updated_at)
        SELECT
          vendor,
          cycle,
          person,
          CAST(SUM(COALESCE({cents}, 0)) AS INTEGER),
          CASE LOWER(COALESCE({source}, 'paste'))
            WHEN 't1' THEN 't1'
            WHEN 't2' THEN 't2'
            ELSE 'paste'
          END,
          MAX({notes}),
          MIN(COALESCE({created}, '')),
          MAX(COALESCE({created}, ''))
        FROM invoices_legacy
        GROUP BY vendor, cycle, person
        """
    )
    conn.execute("DROP TABLE invoices_legacy")


def _migrate_entries_view(conn: sqlite3.Connection) -> None:
    kind = _object_type(conn, "entries")
    if kind == "table":
        conn.execute(
            f"""
            INSERT OR IGNORE INTO events (
              {", ".join(_ENTRY_COLS)}, vendor, person, cycle, billed_cents, tier
            )
            SELECT
              {", ".join(_ENTRY_COLS)},
              CASE
                WHEN lower(COALESCE(source, '')) LIKE '%cursor%' THEN 'cursor'
                WHEN lower(COALESCE(source, '')) LIKE '%anthropic%'
                  OR lower(COALESCE(source, '')) LIKE '%claude%' THEN 'anthropic'
                ELSE 'unknown'
              END,
              '',
              CASE
                WHEN length(COALESCE(occurred_at, '')) >= 7 THEN substr(occurred_at, 1, 7)
                ELSE ''
              END,
              NULL,
              'T0'
            FROM entries
            """
        )
        conn.execute("DROP TABLE entries")
        kind = None
    if kind == "view":
        conn.execute("DROP VIEW entries")
        kind = None
    if kind is None:
        conn.execute(
            f"""
            CREATE VIEW entries AS
            SELECT id, {", ".join(_ENTRY_COLS)},
                   vendor, person, cycle, billed_cents, tier,
                   agent, skill, effort
            FROM events
            """
        )


@contextmanager
def session(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _reject_secrets(row: dict[str, Any]) -> None:
    for key in row:
        if str(key).strip().lower() in _LEDGER_SECRET_KEYS:
            raise ValueError("credentials are never written to the ledger")


def upsert_entry(conn: sqlite3.Connection, row: dict[str, Any]) -> str:
    """
    Insert or keep the richer duplicate (higher output_tokens, then input_tokens).
    Returns inserted | updated | skipped.
    """
    _reject_secrets(row)
    cost = row.get("cost_usd")
    billed = row.get("billed_cents")
    billed_i: int | None
    try:
        billed_i = int(billed) if billed is not None and billed != "" else None
    except (TypeError, ValueError):
        billed_i = None
    if cost is None and billed_i is not None:
        cost = billed_i / 100.0
    if cost is None:
        cost = prices.price_usd(
            model=row.get("model"),
            input_tokens=int(row.get("input_tokens") or 0),
            output_tokens=int(row.get("output_tokens") or 0),
            cache_read_tokens=int(row.get("cache_read_tokens") or 0),
            cache_creation_tokens=int(row.get("cache_creation_tokens") or 0),
            cache_creation_5m_tokens=int(row.get("cache_creation_5m_tokens") or 0),
            cache_creation_1h_tokens=int(row.get("cache_creation_1h_tokens") or 0),
        )
        row = {**row, "cost_usd": cost}

    occurred = row.get("occurred_at") or _now()
    source = row.get("source") or "unknown"
    attrs = bind(row)
    payload = {
        "vendor": row.get("vendor") or vendor_for_source(source),
        "source": source,
        "person": row.get("person") or "",
        "cycle": row.get("cycle") or cycle_of(occurred),
        "message_id": str(row["message_id"]),
        "request_id": str(row["request_id"]),
        "project": row.get("project"),
        "model": row.get("model"),
        "occurred_at": occurred,
        "input_tokens": int(row.get("input_tokens") or 0),
        "output_tokens": int(row.get("output_tokens") or 0),
        "cache_creation_tokens": int(row.get("cache_creation_tokens") or 0),
        "cache_read_tokens": int(row.get("cache_read_tokens") or 0),
        "cache_creation_5m_tokens": int(row.get("cache_creation_5m_tokens") or 0),
        "cache_creation_1h_tokens": int(row.get("cache_creation_1h_tokens") or 0),
        "billed_cents": billed_i,
        "cost_usd": float(cost),
        "tier": row.get("tier") or "T0",
        "session_id": row.get("session_id"),
        "cwd": row.get("cwd"),
        "agent": attrs.get("agent"),
        "skill": attrs.get("skill"),
        "effort": attrs.get("effort"),
        "ingested_at": _now(),
    }
    existing = conn.execute(
        "SELECT output_tokens, input_tokens FROM events WHERE message_id = ? AND request_id = ?",
        (payload["message_id"], payload["request_id"]),
    ).fetchone()
    if existing is None:
        conn.execute(
            """
            INSERT INTO events (
              vendor, source, person, cycle, message_id, request_id, project, model,
              occurred_at, input_tokens, output_tokens, cache_creation_tokens,
              cache_read_tokens, cache_creation_5m_tokens, cache_creation_1h_tokens,
              billed_cents, cost_usd, tier, session_id, cwd, agent, skill, effort, ingested_at
            ) VALUES (
              :vendor, :source, :person, :cycle, :message_id, :request_id, :project, :model,
              :occurred_at, :input_tokens, :output_tokens, :cache_creation_tokens,
              :cache_read_tokens, :cache_creation_5m_tokens, :cache_creation_1h_tokens,
              :billed_cents, :cost_usd, :tier, :session_id, :cwd, :agent, :skill, :effort, :ingested_at
            )
            """,
            payload,
        )
        upsert_project(conn, payload.get("project"))
        return "inserted"

    richer = payload["output_tokens"] > int(existing["output_tokens"]) or (
        payload["output_tokens"] == int(existing["output_tokens"])
        and payload["input_tokens"] > int(existing["input_tokens"])
    )
    if not richer:
        conn.execute(
            """
            UPDATE events SET
              vendor = CASE WHEN vendor IN ('', 'unknown') THEN :vendor ELSE vendor END,
              person = CASE WHEN person = '' THEN :person ELSE person END,
              cycle = CASE WHEN cycle = '' THEN :cycle ELSE cycle END,
              agent = COALESCE(agent, :agent),
              skill = COALESCE(skill, :skill),
              effort = COALESCE(effort, :effort)
            WHERE message_id = :message_id AND request_id = :request_id
            """,
            payload,
        )
        return "skipped"

    conn.execute(
        """
        UPDATE events SET
          vendor = :vendor,
          source = :source,
          person = COALESCE(NULLIF(:person, ''), person),
          cycle = :cycle,
          project = COALESCE(:project, project),
          model = COALESCE(:model, model),
          occurred_at = :occurred_at,
          input_tokens = :input_tokens,
          output_tokens = :output_tokens,
          cache_creation_tokens = :cache_creation_tokens,
          cache_read_tokens = :cache_read_tokens,
          cache_creation_5m_tokens = :cache_creation_5m_tokens,
          cache_creation_1h_tokens = :cache_creation_1h_tokens,
          billed_cents = COALESCE(:billed_cents, billed_cents),
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
    upsert_project(conn, payload.get("project"))
    return "updated"


def upsert_project(conn: sqlite3.Connection, slug: str | None, *, remote_url: str | None = None) -> None:
    if not slug:
        return
    now = _now()
    conn.execute(
        """
        INSERT INTO projects(slug, remote_url, first_seen, last_seen)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
          last_seen = excluded.last_seen,
          remote_url = COALESCE(excluded.remote_url, projects.remote_url)
        """,
        (slug, remote_url, now, now),
    )


def upsert_snapshot(conn: sqlite3.Connection, row: dict[str, Any]) -> str:
    _reject_secrets(row)
    payload = {
        "vendor": row["vendor"],
        "person": row.get("person") or "",
        "cycle": row["cycle"],
        "as_of": row.get("as_of") or _now(),
        "input_tokens": int(row.get("input_tokens") or 0),
        "output_tokens": int(row.get("output_tokens") or 0),
        "cache_read_tokens": int(row.get("cache_read_tokens") or 0),
        "cache_creation_tokens": int(row.get("cache_creation_tokens") or 0),
        "billed_cents": row.get("billed_cents"),
        "cost_usd": row.get("cost_usd"),
        "tier": row.get("tier") or "T1",
        "ingested_at": _now(),
    }
    conn.execute(
        """
        INSERT INTO snapshots (
          vendor, person, cycle, as_of, input_tokens, output_tokens,
          cache_read_tokens, cache_creation_tokens, billed_cents, cost_usd, tier, ingested_at
        ) VALUES (
          :vendor, :person, :cycle, :as_of, :input_tokens, :output_tokens,
          :cache_read_tokens, :cache_creation_tokens, :billed_cents, :cost_usd, :tier, :ingested_at
        )
        ON CONFLICT(vendor, person, cycle, as_of) DO UPDATE SET
          input_tokens = excluded.input_tokens,
          output_tokens = excluded.output_tokens,
          cache_read_tokens = excluded.cache_read_tokens,
          cache_creation_tokens = excluded.cache_creation_tokens,
          billed_cents = excluded.billed_cents,
          cost_usd = excluded.cost_usd,
          tier = excluded.tier,
          ingested_at = excluded.ingested_at
        """,
        payload,
    )
    return "upserted"


def _invoice_cents(row: dict[str, Any]) -> int:
    raw = row.get("usd_cents")
    if raw in (None, ""):
        raw = row.get("billed_cents")
    try:
        if raw is None or raw == "":
            raise ValueError("missing")
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError("invoice requires usd_cents (integer cents)") from None


def _invoice_source(raw: Any) -> str:
    source = str(raw or "paste").strip().lower()
    if source not in INVOICE_SOURCES:
        raise ValueError("invoice source must be paste, t1, or t2")
    return source


def _public_invoice(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    cents = item.get("usd_cents")
    if cents is None:
        cents = item.get("billed_cents") or 0
    item["usd_cents"] = int(cents)
    item["billed_cents"] = int(cents)
    item["person"] = item.get("person") or ""
    return item


def upsert_invoice(conn: sqlite3.Connection, row: dict[str, Any]) -> str:
    """Idempotent on (vendor, cycle, person). Credentials are rejected."""
    _reject_secrets(row)
    now = _now()
    payload = {
        "vendor": str(row.get("vendor") or "").strip().lower(),
        "cycle": str(row.get("cycle") or "").strip(),
        "person": str(row.get("person") or row.get("scope") or "").strip(),
        "usd_cents": _invoice_cents(row),
        "source": _invoice_source(row.get("source")),
        "notes": row.get("notes"),
        "created_at": now,
        "updated_at": now,
    }
    if not payload["vendor"]:
        raise ValueError("invoice requires vendor")
    if not payload["cycle"] or len(payload["cycle"]) < 7:
        raise ValueError("invoice requires cycle YYYY-MM")
    existing = conn.execute(
        """
        SELECT usd_cents FROM invoices
        WHERE vendor = :vendor AND cycle = :cycle AND person = :person
        """,
        payload,
    ).fetchone()
    conn.execute(
        """
        INSERT INTO invoices (
          vendor, cycle, person, usd_cents, source, notes, created_at, updated_at
        ) VALUES (
          :vendor, :cycle, :person, :usd_cents, :source, :notes, :created_at, :updated_at
        )
        ON CONFLICT(vendor, cycle, person) DO UPDATE SET
          usd_cents = excluded.usd_cents,
          source = excluded.source,
          notes = excluded.notes,
          updated_at = excluded.updated_at
        """,
        payload,
    )
    return "updated" if existing is not None else "inserted"


def list_invoices(
    conn: sqlite3.Connection,
    *,
    cycle: str | None = None,
    vendor: str | None = None,
    person: str | None = None,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM invoices WHERE 1=1"
    args: list[Any] = []
    if cycle:
        sql += " AND cycle = ?"
        args.append(cycle)
    if vendor:
        sql += " AND vendor = ?"
        args.append(vendor)
    if person is not None:
        sql += " AND person = ?"
        args.append(person)
    sql += " ORDER BY vendor, person, cycle, id"
    return [_public_invoice(r) for r in conn.execute(sql, args).fetchall()]


def latest_snapshot(
    conn: sqlite3.Connection, *, vendor: str, person: str | None, cycle: str
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM snapshots
        WHERE vendor = ? AND person = ? AND cycle = ?
        ORDER BY as_of DESC, id DESC
        LIMIT 1
        """,
        (vendor, person or "", cycle),
    ).fetchone()
    return dict(row) if row else None


def list_snapshots(
    conn: sqlite3.Connection,
    *,
    cycle: str | None = None,
    vendor: str | None = None,
    person: str | None = None,
) -> list[dict[str, Any]]:
    sql = """
        SELECT vendor, person, cycle, as_of, billed_cents, cost_usd, tier,
               input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens
        FROM snapshots
        WHERE 1=1
    """
    args: list[Any] = []
    if cycle:
        sql += " AND cycle = ?"
        args.append(cycle)
    if vendor:
        sql += " AND vendor = ?"
        args.append(vendor)
    if person is not None:
        sql += " AND person = ?"
        args.append(person)
    sql += " ORDER BY vendor, person, cycle, as_of"
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def get_sync_state(
    conn: sqlite3.Connection,
    *,
    vendor: str,
    kind: str,
    person: str | None = None,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT vendor, person, kind, cursor, last_success, last_error, updated_at
        FROM sync_state
        WHERE vendor = ? AND person = ? AND kind = ?
        """,
        (vendor, person or "", kind),
    ).fetchone()
    return dict(row) if row else None


def get_sync_watermark(
    conn: sqlite3.Connection,
    vendor: str,
    stream: str,
    person: str | None = None,
) -> str | None:
    row = get_sync_state(conn, vendor=vendor, kind=stream, person=person)
    if not row or row.get("cursor") is None:
        return None
    return str(row["cursor"])


def set_sync_state(
    conn: sqlite3.Connection,
    *,
    vendor: str,
    kind: str,
    person: str | None = None,
    cursor: str | None = None,
    last_error: str | None = None,
    ok: bool = True,
    now: str | datetime | None = None,
) -> None:
    if isinstance(now, datetime):
        stamp = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
        stamp_iso = stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        stamp_iso = now or _now()
    conn.execute(
        """
        INSERT INTO sync_state(vendor, person, kind, cursor, last_success, last_error, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(vendor, person, kind) DO UPDATE SET
          cursor = COALESCE(excluded.cursor, sync_state.cursor),
          last_success = CASE WHEN excluded.last_error IS NULL THEN excluded.last_success ELSE sync_state.last_success END,
          last_error = excluded.last_error,
          updated_at = excluded.updated_at
        """,
        (
            vendor,
            person or "",
            kind,
            cursor,
            stamp_iso if ok else None,
            None if ok else last_error,
            stamp_iso,
        ),
    )


def seed_prices(conn: sqlite3.Connection) -> None:
    user = paths.user_prices()
    bundled = paths.bundled_prices()
    book = prices.load_pricebook(
        user.stat().st_mtime if user.is_file() else None,
        bundled.stat().st_mtime if bundled.is_file() else None,
    )
    now = _now()
    currency = str(book.get("currency") or "USD")
    unit = str(book.get("unit") or "per_million_tokens")
    for model, rates in (book.get("models") or {}).items():
        if not isinstance(rates, dict):
            continue
        conn.execute(
            """
            INSERT INTO prices(
              model, input, output, cache_read, cache_write_5m, cache_write_1h,
              currency, unit, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(model) DO UPDATE SET
              input = excluded.input,
              output = excluded.output,
              cache_read = excluded.cache_read,
              cache_write_5m = excluded.cache_write_5m,
              cache_write_1h = excluded.cache_write_1h,
              currency = excluded.currency,
              unit = excluded.unit,
              updated_at = excluded.updated_at
            """,
            (
                str(model),
                float(rates.get("input") or 0),
                float(rates.get("output") or 0),
                float(rates.get("cache_read") or 0),
                float(rates.get("cache_write_5m") or 0),
                float(rates.get("cache_write_1h") or 0),
                currency,
                unit,
                now,
            ),
        )


def mark_source(conn: sqlite3.Connection, path: Path, *, bytes_: int, mtime: float) -> None:
    conn.execute(
        """
        INSERT INTO sources(path, bytes, mtime, ingested_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
          bytes = excluded.bytes,
          mtime = excluded.mtime,
          ingested_at = excluded.ingested_at
        """,
        (str(path), bytes_, mtime, _now()),
    )


def source_unchanged(conn: sqlite3.Connection, path: Path, *, bytes_: int, mtime: float) -> bool:
    row = conn.execute("SELECT bytes, mtime FROM sources WHERE path = ?", (str(path),)).fetchone()
    if row is None:
        return False
    return int(row["bytes"] or 0) == bytes_ and abs(float(row["mtime"] or 0) - mtime) < 1e-6


def count_entries(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0])


def required_tables() -> tuple[str, ...]:
    return ("events", "snapshots", "prices", "projects", "sync_state", "invoices")
