"""Account/credit store. SQLite locally; Postgres (ops.*) when DATABASE_URL is set."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PG_BOOTSTRAP = (
    "CREATE SCHEMA IF NOT EXISTS ops",
    """
    CREATE TABLE IF NOT EXISTS ops.accounts (
        id uuid PRIMARY KEY,
        external_key text NOT NULL UNIQUE,
        email text,
        supabase_sub text,
        plan text NOT NULL DEFAULT 'free',
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ops.customers (
        id uuid PRIMARY KEY,
        account_id uuid NOT NULL UNIQUE REFERENCES ops.accounts (id) ON DELETE CASCADE,
        stripe_customer_id text UNIQUE,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ops.checkout_sessions (
        id uuid PRIMARY KEY,
        account_id uuid REFERENCES ops.accounts (id) ON DELETE SET NULL,
        stripe_session_id text NOT NULL UNIQUE,
        amount_cents integer NOT NULL,
        credits integer NOT NULL,
        currency text NOT NULL DEFAULT 'usd',
        status text NOT NULL DEFAULT 'open',
        checkout_url text,
        fulfilled_at timestamptz,
        mode text NOT NULL DEFAULT 'payment',
        plan text,
        stripe_subscription_id text,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ops.credit_ledger (
        id uuid PRIMARY KEY,
        account_id uuid NOT NULL REFERENCES ops.accounts (id) ON DELETE CASCADE,
        amount integer NOT NULL,
        reason text NOT NULL,
        checkout_session_id uuid UNIQUE REFERENCES ops.checkout_sessions (id),
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ops.synced_usage (
        id uuid PRIMARY KEY,
        account_id uuid NOT NULL REFERENCES ops.accounts (id) ON DELETE CASCADE,
        source text,
        message_id text,
        request_id text,
        project text,
        model text,
        occurred_at timestamptz,
        input_tokens integer,
        output_tokens integer,
        cache_read_tokens integer,
        cache_creation_tokens integer,
        cost_usd numeric,
        session_id text,
        payload jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (account_id, message_id, request_id)
    )
    """,
    "ALTER TABLE ops.accounts ADD COLUMN IF NOT EXISTS plan text NOT NULL DEFAULT 'free'",
    "ALTER TABLE ops.checkout_sessions ADD COLUMN IF NOT EXISTS mode text NOT NULL DEFAULT 'payment'",
    "ALTER TABLE ops.checkout_sessions ADD COLUMN IF NOT EXISTS plan text",
    "ALTER TABLE ops.checkout_sessions ADD COLUMN IF NOT EXISTS stripe_subscription_id text",
    "CREATE INDEX IF NOT EXISTS checkout_sessions_account_idx ON ops.checkout_sessions (account_id)",
    "CREATE INDEX IF NOT EXISTS credit_ledger_account_idx ON ops.credit_ledger (account_id)",
    "CREATE INDEX IF NOT EXISTS synced_usage_account_idx ON ops.synced_usage (account_id)",
)

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
    message_id TEXT,
    request_id TEXT,
    project TEXT,
    model TEXT,
    occurred_at TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_creation_tokens INTEGER,
    cost_usd REAL,
    session_id TEXT,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE (account_id, message_id, request_id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    for key, value in list(data.items()):
        if isinstance(value, uuid.UUID):
            data[key] = str(value)
        elif isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


def _row(cur: Any) -> dict[str, Any] | None:
    if cur is None:
        return None
    return _as_dict(cur)


class _Conn:
    """Adapt ``?`` placeholders for Postgres; pass SQLite through."""

    def __init__(self, raw: Any, backend: str) -> None:
        self._raw = raw
        self.backend = backend

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        if self.backend == "postgres":
            sql = sql.replace("?", "%s")
        return self._raw.execute(sql, params)

    def executescript(self, sql: str) -> Any:
        return self._raw.executescript(sql)

    def __enter__(self) -> _Conn:
        self._raw.__enter__()
        return self

    def __exit__(self, *exc: Any) -> Any:
        return self._raw.__exit__(*exc)


class Store:
    def __init__(
        self,
        path: str | Path | None = None,
        *,
        database_url: str = "",
    ) -> None:
        url = (database_url or "").strip()
        if url:
            self.backend = "postgres"
            self.path = ""
            self.dsn = url
            self._init_postgres()
            return
        if path is None:
            raise ValueError("Store requires a sqlite path or database_url")
        self.backend = "sqlite"
        self.path = str(path)
        self.dsn = ""
        self._mem: sqlite3.Connection | None = None
        if self.path not in {":memory:", "file:mem?mode=memory&cache=shared"}:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> _Conn:
        if self.backend == "postgres":
            from ardoise_api.db import connect_postgres

            raw = connect_postgres(self.dsn)
            raw.execute("SET search_path TO ops, public")
            return _Conn(raw, "postgres")
        if self.path in {":memory:", "file:mem?mode=memory&cache=shared"}:
            if self._mem is None:
                uri = self.path.startswith("file:")
                self._mem = sqlite3.connect(self.path, uri=uri)
                self._mem.row_factory = sqlite3.Row
                self._mem.execute("PRAGMA foreign_keys=ON")
            return _Conn(self._mem, "sqlite")
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return _Conn(conn, "sqlite")

    def _init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._ensure_columns(conn)

    def _init_postgres(self) -> None:
        from ardoise_api.db import open_postgres

        raw, dsn = open_postgres(self.dsn)
        self.dsn = dsn
        try:
            raw.execute("SET search_path TO ops, public")
            for stmt in PG_BOOTSTRAP:
                raw.execute(stmt)
            raw.execute("SELECT 1")
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()

    @staticmethod
    def _ensure_columns(conn: Any) -> None:
        patches = (
            ("accounts", "plan", "TEXT NOT NULL DEFAULT 'free'"),
            ("checkout_sessions", "mode", "TEXT NOT NULL DEFAULT 'payment'"),
            ("checkout_sessions", "plan", "TEXT"),
            ("checkout_sessions", "stripe_subscription_id", "TEXT"),
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
        return _as_dict(row)

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
        return _as_dict(row)

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
            if session_plan in {"team", "business"} and row["account_id"]:
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
