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
