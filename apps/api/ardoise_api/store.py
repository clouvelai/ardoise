"""Account store: SQLite locally, Postgres (ops.*) when DATABASE_URL is set."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ardoise_api.settings import Settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    external_key TEXT NOT NULL UNIQUE,
    email TEXT,
    supabase_sub TEXT,
    plan TEXT NOT NULL DEFAULT 'free',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL UNIQUE REFERENCES accounts (id),
    stripe_customer_id TEXT UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkout_sessions (
    id TEXT PRIMARY KEY,
    account_id TEXT REFERENCES accounts (id),
    stripe_session_id TEXT NOT NULL UNIQUE,
    amount_cents INTEGER NOT NULL,
    credits INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'usd',
    status TEXT NOT NULL DEFAULT 'open',
    checkout_url TEXT,
    fulfilled_at TEXT,
    mode TEXT NOT NULL DEFAULT 'payment',
    plan TEXT,
    stripe_subscription_id TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS credit_ledger (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts (id),
    amount INTEGER NOT NULL,
    reason TEXT NOT NULL,
    checkout_session_id TEXT UNIQUE REFERENCES checkout_sessions (id),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS synced_usage (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts (id),
    source TEXT,
    vendor TEXT,
    message_id TEXT,
    request_id TEXT,
    project TEXT,
    model TEXT,
    occurred_at TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_creation_tokens INTEGER,
    cache_creation_5m_tokens INTEGER,
    cache_creation_1h_tokens INTEGER,
    cost_usd REAL,
    billed_cents INTEGER,
    tier TEXT,
    person TEXT,
    cycle TEXT,
    session_id TEXT,
    agent TEXT,
    skill TEXT,
    effort TEXT,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE (account_id, message_id, request_id)
);
CREATE TABLE IF NOT EXISTS cli_tokens (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts (id),
    token_hash TEXT NOT NULL UNIQUE,
    prefix TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT
);
CREATE TABLE IF NOT EXISTS synced_invoices (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts (id),
    vendor TEXT NOT NULL,
    cycle TEXT NOT NULL,
    person TEXT NOT NULL DEFAULT '',
    usd_cents INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'paste',
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (account_id, vendor, cycle, person)
);
CREATE TABLE IF NOT EXISTS synced_snapshots (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts (id),
    vendor TEXT NOT NULL,
    person TEXT NOT NULL DEFAULT '',
    cycle TEXT NOT NULL,
    as_of TEXT NOT NULL,
    billed_cents INTEGER,
    cost_usd REAL,
    tier TEXT NOT NULL DEFAULT 'T1',
    created_at TEXT NOT NULL,
    UNIQUE (account_id, vendor, person, cycle, as_of)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(cur: sqlite3.Row | None) -> dict[str, Any] | None:
    if cur is None:
        return None
    return dict(cur)


@runtime_checkable
class AccountStore(Protocol):
    """SQLite or Postgres. Routes depend on this surface only."""

    kind: str

    def ping(self) -> None: ...

    def upsert_account(
        self,
        *,
        external_key: str,
        email: str | None,
        supabase_sub: str | None,
    ) -> dict[str, Any]: ...

    def credit_balance(self, account_id: str) -> int: ...

    def insert_checkout(
        self,
        *,
        account_id: str,
        stripe_session_id: str,
        amount_cents: int,
        credits: int,
        currency: str,
        checkout_url: str,
        status: str = "open",
        mode: str = "payment",
        plan: str | None = None,
        stripe_subscription_id: str | None = None,
    ) -> dict[str, Any]: ...

    def get_checkout_by_stripe_id(
        self, stripe_session_id: str
    ) -> dict[str, Any] | None: ...

    def set_customer_stripe_id(
        self, account_id: str, stripe_customer_id: str
    ) -> None: ...

    def set_account_plan(self, account_id: str, plan: str) -> None: ...

    def fulfill_checkout(
        self,
        stripe_session_id: str,
        *,
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
        plan: str | None = None,
    ) -> dict[str, Any]: ...

    def get_account(self, account_id: str) -> dict[str, Any] | None: ...

    def create_cli_token(self, account_id: str, *, raw_token: str, token_hash: str) -> dict[str, Any]: ...

    def account_for_cli_hash(self, token_hash: str) -> dict[str, Any] | None: ...

    def upsert_usage_rows(self, account_id: str, rows: list[dict[str, Any]]) -> int: ...

    def upsert_invoices(self, account_id: str, rows: list[dict[str, Any]]) -> int: ...

    def upsert_snapshots(self, account_id: str, rows: list[dict[str, Any]]) -> int: ...

    def list_usage(self, account_id: str, *, month: str | None = None) -> list[dict[str, Any]]: ...

    def list_invoices(self, account_id: str, *, month: str | None = None) -> list[dict[str, Any]]: ...

    def list_snapshots(self, account_id: str, *, month: str | None = None) -> list[dict[str, Any]]: ...


class UnavailableStore:
    """Configured for Postgres but the driver or DSN is not usable."""

    kind = "postgres"

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def ping(self) -> None:
        raise RuntimeError(self.reason)

    def __getattr__(self, name: str) -> Any:
        def _fail(*_args: object, **_kwargs: object) -> Any:
            raise RuntimeError(self.reason)

        return _fail


def default_sqlite_path(settings: Settings) -> str:
    if settings.sqlite_path:
        return settings.sqlite_path
    here = Path(__file__).resolve().parent.parent / ".data" / "local.db"
    return str(here)


def open_store(settings: Settings) -> AccountStore:
    """Postgres when DATABASE_URL is set; SQLite otherwise. No silent fallback."""
    url = (settings.database_url or "").strip()
    if not url:
        return Store(default_sqlite_path(settings))
    try:
        from ardoise_api.pgstore import PostgresStore
    except ImportError:
        return UnavailableStore("psycopg_missing")
    return PostgresStore(url)


class Store:
    kind = "sqlite"

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path not in {":memory:", "file:mem?mode=memory&cache=shared"}:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def ping(self) -> None:
        with self.connect() as conn:
            conn.execute("SELECT 1 FROM accounts LIMIT 0")

    def _init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._ensure_columns(conn)

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection) -> None:
        patches = (
            ("accounts", "plan", "TEXT NOT NULL DEFAULT 'free'"),
            ("checkout_sessions", "mode", "TEXT NOT NULL DEFAULT 'payment'"),
            ("checkout_sessions", "plan", "TEXT"),
            ("checkout_sessions", "stripe_subscription_id", "TEXT"),
            ("synced_usage", "vendor", "TEXT"),
            ("synced_usage", "tier", "TEXT"),
            ("synced_usage", "person", "TEXT"),
            ("synced_usage", "cycle", "TEXT"),
            ("synced_usage", "billed_cents", "INTEGER"),
            ("synced_usage", "cache_creation_5m_tokens", "INTEGER"),
            ("synced_usage", "cache_creation_1h_tokens", "INTEGER"),
            ("synced_usage", "agent", "TEXT"),
            ("synced_usage", "skill", "TEXT"),
            ("synced_usage", "effort", "TEXT"),
        )
        for table, name, ddl in patches:
            cols = {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if name not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    def upsert_account(
        self,
        *,
        external_key: str,
        email: str | None,
        supabase_sub: str | None,
    ) -> dict[str, Any]:
        now = _now()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM accounts WHERE external_key = ?", (external_key,)
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE accounts
                    SET email = COALESCE(?, email),
                        supabase_sub = COALESCE(?, supabase_sub),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (email, supabase_sub, now, existing["id"]),
                )
                row = conn.execute(
                    "SELECT * FROM accounts WHERE id = ?", (existing["id"],)
                ).fetchone()
            else:
                account_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO accounts
                        (id, external_key, email, supabase_sub, plan,
                         created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'free', ?, ?)
                    """,
                    (account_id, external_key, email, supabase_sub, now, now),
                )
                conn.execute(
                    """
                    INSERT INTO customers (id, account_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (str(uuid.uuid4()), account_id, now),
                )
                row = conn.execute(
                    "SELECT * FROM accounts WHERE id = ?", (account_id,)
                ).fetchone()
        assert row is not None
        return dict(row)

    def credit_balance(self, account_id: str) -> int:
        with self.connect() as conn:
            value = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM credit_ledger WHERE account_id = ?",
                (account_id,),
            ).fetchone()[0]
        return int(value)

    def insert_checkout(
        self,
        *,
        account_id: str,
        stripe_session_id: str,
        amount_cents: int,
        credits: int,
        currency: str,
        checkout_url: str,
        status: str = "open",
        mode: str = "payment",
        plan: str | None = None,
        stripe_subscription_id: str | None = None,
    ) -> dict[str, Any]:
        session_id = str(uuid.uuid4())
        now = _now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO checkout_sessions (
                    id, account_id, stripe_session_id, amount_cents, credits,
                    currency, status, checkout_url, created_at, mode, plan,
                    stripe_subscription_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    account_id,
                    stripe_session_id,
                    amount_cents,
                    credits,
                    currency,
                    status,
                    checkout_url,
                    now,
                    mode,
                    plan,
                    stripe_subscription_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM checkout_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        assert row is not None
        return dict(row)

    def get_checkout_by_stripe_id(self, stripe_session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return _row(
                conn.execute(
                    "SELECT * FROM checkout_sessions WHERE stripe_session_id = ?",
                    (stripe_session_id,),
                ).fetchone()
            )

    def set_customer_stripe_id(self, account_id: str, stripe_customer_id: str) -> None:
        if not stripe_customer_id:
            return
        now = _now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO customers (id, account_id, stripe_customer_id, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    stripe_customer_id = excluded.stripe_customer_id
                """,
                (str(uuid.uuid4()), account_id, stripe_customer_id, now),
            )

    def set_account_plan(self, account_id: str, plan: str) -> None:
        now = _now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE accounts SET plan = ?, updated_at = ? WHERE id = ?",
                (plan, now, account_id),
            )

    def fulfill_checkout(
        self,
        stripe_session_id: str,
        *,
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
        plan: str | None = None,
    ) -> dict[str, Any]:
        """Idempotent fulfill. Safe to replay checkout.session.completed."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM checkout_sessions WHERE stripe_session_id = ?",
                (stripe_session_id,),
            ).fetchone()
            if row is None:
                return {"ok": False, "reason": "unknown_session"}
            keys = set(row.keys())
            session_plan = plan or (row["plan"] if "plan" in keys else None)
            session_mode = row["mode"] if "mode" in keys else "payment"
            if row["status"] == "completed" and row["fulfilled_at"]:
                return {
                    "ok": True,
                    "already_fulfilled": True,
                    "credits": int(row["credits"]),
                    "plan": session_plan,
                    "mode": session_mode,
                    "stripe_session_id": stripe_session_id,
                }
            now = _now()
            conn.execute(
                """
                UPDATE checkout_sessions
                SET status = 'completed',
                    fulfilled_at = ?,
                    plan = COALESCE(?, plan),
                    stripe_subscription_id = COALESCE(?, stripe_subscription_id)
                WHERE stripe_session_id = ? AND fulfilled_at IS NULL
                """,
                (now, session_plan, stripe_subscription_id, stripe_session_id),
            )
            credits = int(row["credits"])
            if credits > 0:
                existing_credit = conn.execute(
                    "SELECT id FROM credit_ledger WHERE checkout_session_id = ?",
                    (row["id"],),
                ).fetchone()
                if existing_credit is None:
                    conn.execute(
                        """
                        INSERT INTO credit_ledger
                            (id, account_id, amount, reason, checkout_session_id, created_at)
                        VALUES (?, ?, ?, 'checkout.session.completed', ?, ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            row["account_id"],
                            credits,
                            row["id"],
                            now,
                        ),
                    )
            if session_plan in {"pro", "team"} and row["account_id"]:
                conn.execute(
                    "UPDATE accounts SET plan = ?, updated_at = ? WHERE id = ?",
                    (session_plan, now, row["account_id"]),
                )
            if stripe_customer_id and row["account_id"]:
                conn.execute(
                    """
                    INSERT INTO customers (id, account_id, stripe_customer_id, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(account_id) DO UPDATE SET
                        stripe_customer_id = excluded.stripe_customer_id
                    """,
                    (str(uuid.uuid4()), row["account_id"], stripe_customer_id, now),
                )
        return {
            "ok": True,
            "already_fulfilled": False,
            "credits": int(row["credits"]),
            "plan": session_plan,
            "mode": session_mode,
            "stripe_session_id": stripe_session_id,
        }

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return _row(
                conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
            )

    def create_cli_token(
        self, account_id: str, *, raw_token: str, token_hash: str
    ) -> dict[str, Any]:
        del raw_token
        now = _now()
        token_id = str(uuid.uuid4())
        prefix = "ard_"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO cli_tokens (id, account_id, token_hash, prefix, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token_id, account_id, token_hash, prefix, now),
            )
        return {"id": token_id, "prefix": prefix, "created_at": now}

    def account_for_cli_hash(self, token_hash: str) -> dict[str, Any] | None:
        now = _now()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT a.* FROM accounts a
                JOIN cli_tokens t ON t.account_id = a.id
                WHERE t.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE cli_tokens SET last_used_at = ? WHERE token_hash = ?",
                (now, token_hash),
            )
            return dict(row)

    def upsert_usage_rows(self, account_id: str, rows: list[dict[str, Any]]) -> int:
        now = _now()
        count = 0
        with self.connect() as conn:
            for row in rows:
                message_id = str(row.get("message_id") or "").strip()
                request_id = str(row.get("request_id") or "").strip()
                if not message_id or not request_id:
                    continue
                conn.execute(
                    """
                    INSERT INTO synced_usage (
                        id, account_id, source, vendor, message_id, request_id,
                        project, model, occurred_at, input_tokens, output_tokens,
                        cache_read_tokens, cache_creation_tokens,
                        cache_creation_5m_tokens, cache_creation_1h_tokens,
                        cost_usd, billed_cents, tier, person, cycle, session_id,
                        agent, skill, effort, payload, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?)
                    ON CONFLICT(account_id, message_id, request_id) DO UPDATE SET
                        source = excluded.source,
                        vendor = excluded.vendor,
                        project = excluded.project,
                        model = excluded.model,
                        occurred_at = excluded.occurred_at,
                        input_tokens = excluded.input_tokens,
                        output_tokens = excluded.output_tokens,
                        cache_read_tokens = excluded.cache_read_tokens,
                        cache_creation_tokens = excluded.cache_creation_tokens,
                        cache_creation_5m_tokens = excluded.cache_creation_5m_tokens,
                        cache_creation_1h_tokens = excluded.cache_creation_1h_tokens,
                        cost_usd = excluded.cost_usd,
                        billed_cents = excluded.billed_cents,
                        tier = excluded.tier,
                        person = excluded.person,
                        cycle = excluded.cycle,
                        session_id = excluded.session_id,
                        agent = excluded.agent,
                        skill = excluded.skill,
                        effort = excluded.effort
                    """,
                    (
                        str(uuid.uuid4()),
                        account_id,
                        row.get("source"),
                        row.get("vendor"),
                        message_id,
                        request_id,
                        row.get("project"),
                        row.get("model"),
                        row.get("occurred_at"),
                        row.get("input_tokens") or 0,
                        row.get("output_tokens") or 0,
                        row.get("cache_read_tokens") or 0,
                        row.get("cache_creation_tokens") or 0,
                        row.get("cache_creation_5m_tokens") or 0,
                        row.get("cache_creation_1h_tokens") or 0,
                        row.get("cost_usd") or 0,
                        row.get("billed_cents"),
                        row.get("tier"),
                        row.get("person") or "",
                        row.get("cycle") or "",
                        row.get("session_id"),
                        row.get("agent"),
                        row.get("skill"),
                        row.get("effort"),
                        now,
                    ),
                )
                count += 1
        return count

    def upsert_invoices(self, account_id: str, rows: list[dict[str, Any]]) -> int:
        now = _now()
        count = 0
        with self.connect() as conn:
            for row in rows:
                vendor = str(row.get("vendor") or "").strip()
                cycle = str(row.get("cycle") or "")[:7]
                if not vendor or len(cycle) != 7:
                    continue
                person = str(row.get("person") or "")
                cents = int(row.get("usd_cents") or row.get("billed_cents") or 0)
                conn.execute(
                    """
                    INSERT INTO synced_invoices (
                        id, account_id, vendor, cycle, person, usd_cents, source,
                        notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_id, vendor, cycle, person) DO UPDATE SET
                        usd_cents = excluded.usd_cents,
                        source = excluded.source,
                        notes = excluded.notes,
                        updated_at = excluded.updated_at
                    """,
                    (
                        str(uuid.uuid4()),
                        account_id,
                        vendor,
                        cycle,
                        person,
                        cents,
                        str(row.get("source") or "paste"),
                        row.get("notes"),
                        now,
                        now,
                    ),
                )
                count += 1
        return count

    def upsert_snapshots(self, account_id: str, rows: list[dict[str, Any]]) -> int:
        now = _now()
        count = 0
        with self.connect() as conn:
            for row in rows:
                vendor = str(row.get("vendor") or "").strip()
                cycle = str(row.get("cycle") or "")[:7]
                as_of = str(row.get("as_of") or "").strip()
                if not vendor or not cycle or not as_of:
                    continue
                conn.execute(
                    """
                    INSERT INTO synced_snapshots (
                        id, account_id, vendor, person, cycle, as_of, billed_cents,
                        cost_usd, tier, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_id, vendor, person, cycle, as_of) DO UPDATE SET
                        billed_cents = excluded.billed_cents,
                        cost_usd = excluded.cost_usd,
                        tier = excluded.tier
                    """,
                    (
                        str(uuid.uuid4()),
                        account_id,
                        vendor,
                        str(row.get("person") or ""),
                        cycle,
                        as_of,
                        row.get("billed_cents"),
                        row.get("cost_usd"),
                        str(row.get("tier") or "T1"),
                        now,
                    ),
                )
                count += 1
        return count

    def list_usage(self, account_id: str, *, month: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM synced_usage WHERE account_id = ?"
        args: list[Any] = [account_id]
        if month:
            sql += " AND (cycle = ? OR substr(COALESCE(occurred_at, ''), 1, 7) = ?)"
            args.extend([month, month])
        sql += " ORDER BY occurred_at ASC"
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def list_invoices(self, account_id: str, *, month: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM synced_invoices WHERE account_id = ?"
        args: list[Any] = [account_id]
        if month:
            sql += " AND cycle = ?"
            args.append(month)
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def list_snapshots(self, account_id: str, *, month: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM synced_snapshots WHERE account_id = ?"
        args: list[Any] = [account_id]
        if month:
            sql += " AND cycle = ?"
            args.append(month)
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

