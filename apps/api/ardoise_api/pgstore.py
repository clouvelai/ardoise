"""Postgres store for ops.* (DATABASE_URL). Privileged role; not PostgREST."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}


def normalize_database_url(raw: str) -> str:
    """Accept postgres:// and add sslmode=require for non-local hosts."""
    url = raw.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if "sslmode=" in url.lower():
        return url
    host = (urlparse(url).hostname or "").lower()
    if host in _LOCAL_HOSTS:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}sslmode=require"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cell(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _public_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: _cell(value) for key, value in row.items()}


class PostgresStore:
    """System of record when DATABASE_URL is set. Same ops.* tables as migrations."""

    kind = "postgres"

    def __init__(self, dsn: str) -> None:
        self._dsn = normalize_database_url(dsn)

    def __repr__(self) -> str:
        return "PostgresStore(dsn=***)"

    def connect(self) -> psycopg.Connection[dict[str, Any]]:
        # prepare_threshold=None: works with Supabase/PgBouncer transaction poolers.
        return psycopg.connect(
            self._dsn,
            row_factory=dict_row,
            connect_timeout=10,
            prepare_threshold=None,
        )

    def ping(self) -> None:
        with self.connect() as conn:
            conn.execute("SELECT 1 FROM ops.accounts LIMIT 0")

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
                "SELECT * FROM ops.accounts WHERE external_key = %s",
                (external_key,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE ops.accounts
                    SET email = COALESCE(%s, email),
                        supabase_sub = COALESCE(%s, supabase_sub),
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (email, supabase_sub, now, existing["id"]),
                )
                row = conn.execute(
                    "SELECT * FROM ops.accounts WHERE id = %s",
                    (existing["id"],),
                ).fetchone()
            else:
                account_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO ops.accounts
                        (id, external_key, email, supabase_sub, plan,
                         created_at, updated_at)
                    VALUES (%s, %s, %s, %s, 'free', %s, %s)
                    """,
                    (account_id, external_key, email, supabase_sub, now, now),
                )
                conn.execute(
                    """
                    INSERT INTO ops.customers (id, account_id, created_at)
                    VALUES (%s, %s, %s)
                    """,
                    (str(uuid.uuid4()), account_id, now),
                )
                row = conn.execute(
                    "SELECT * FROM ops.accounts WHERE id = %s",
                    (account_id,),
                ).fetchone()
        public = _public_row(row)
        assert public is not None
        return public

    def credit_balance(self, account_id: str) -> int:
        with self.connect() as conn:
            value = conn.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM ops.credit_ledger
                WHERE account_id = %s
                """,
                (account_id,),
            ).fetchone()
        if not value:
            return 0
        return int(next(iter(value.values())))

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
            row = conn.execute(
                """
                INSERT INTO ops.checkout_sessions (
                    id, account_id, stripe_session_id, amount_cents, credits,
                    currency, status, checkout_url, created_at, mode, plan,
                    stripe_subscription_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
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
            ).fetchone()
        public = _public_row(row)
        assert public is not None
        return public

    def get_checkout_by_stripe_id(
        self, stripe_session_id: str
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            return _public_row(
                conn.execute(
                    """
                    SELECT * FROM ops.checkout_sessions
                    WHERE stripe_session_id = %s
                    """,
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
                INSERT INTO ops.customers
                    (id, account_id, stripe_customer_id, created_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (account_id) DO UPDATE SET
                    stripe_customer_id = EXCLUDED.stripe_customer_id
                """,
                (str(uuid.uuid4()), account_id, stripe_customer_id, now),
            )

    def set_account_plan(self, account_id: str, plan: str) -> None:
        now = _now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE ops.accounts
                SET plan = %s, updated_at = %s
                WHERE id = %s
                """,
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
                """
                SELECT * FROM ops.checkout_sessions
                WHERE stripe_session_id = %s
                """,
                (stripe_session_id,),
            ).fetchone()
            if row is None:
                return {"ok": False, "reason": "unknown_session"}
            session_plan = plan or row.get("plan")
            session_mode = row.get("mode") or "payment"
            if row["status"] == "completed" and row["fulfilled_at"]:
                return {
                    "ok": True,
                    "already_fulfilled": True,
                    "credits": int(row["credits"]),
                    "plan": _cell(session_plan),
                    "mode": session_mode,
                    "stripe_session_id": stripe_session_id,
                }
            now = _now()
            conn.execute(
                """
                UPDATE ops.checkout_sessions
                SET status = 'completed',
                    fulfilled_at = %s,
                    plan = COALESCE(%s, plan),
                    stripe_subscription_id = COALESCE(%s, stripe_subscription_id)
                WHERE stripe_session_id = %s AND fulfilled_at IS NULL
                """,
                (now, session_plan, stripe_subscription_id, stripe_session_id),
            )
            credits = int(row["credits"])
            if credits > 0:
                existing_credit = conn.execute(
                    """
                    SELECT id FROM ops.credit_ledger
                    WHERE checkout_session_id = %s
                    """,
                    (row["id"],),
                ).fetchone()
                if existing_credit is None:
                    conn.execute(
                        """
                        INSERT INTO ops.credit_ledger
                            (id, account_id, amount, reason, checkout_session_id,
                             created_at)
                        VALUES (%s, %s, %s, 'checkout.session.completed', %s, %s)
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
                    """
                    UPDATE ops.accounts
                    SET plan = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    (session_plan, now, row["account_id"]),
                )
            if stripe_customer_id and row["account_id"]:
                conn.execute(
                    """
                    INSERT INTO ops.customers
                        (id, account_id, stripe_customer_id, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (account_id) DO UPDATE SET
                        stripe_customer_id = EXCLUDED.stripe_customer_id
                    """,
                    (
                        str(uuid.uuid4()),
                        row["account_id"],
                        stripe_customer_id,
                        now,
                    ),
                )
        return {
            "ok": True,
            "already_fulfilled": False,
            "credits": int(row["credits"]),
            "plan": _cell(session_plan),
            "mode": session_mode,
            "stripe_session_id": stripe_session_id,
        }
