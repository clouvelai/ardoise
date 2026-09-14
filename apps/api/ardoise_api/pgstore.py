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

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return _public_row(
                conn.execute(
                    "SELECT * FROM ops.accounts WHERE id = %s",
                    (account_id,),
                ).fetchone()
            )

    def create_cli_token(
        self, account_id: str, *, raw_token: str, token_hash: str
    ) -> dict[str, Any]:
        del raw_token
        now = _now()
        token_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO ops.cli_tokens
                    (id, account_id, token_hash, prefix, created_at)
                VALUES (%s, %s, %s, 'ard_', %s)
                """,
                (token_id, account_id, token_hash, now),
            )
        return {"id": token_id, "prefix": "ard_", "created_at": now}

    def account_for_cli_hash(self, token_hash: str) -> dict[str, Any] | None:
        now = _now()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT a.* FROM ops.accounts a
                JOIN ops.cli_tokens t ON t.account_id = a.id
                WHERE t.token_hash = %s
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE ops.cli_tokens SET last_used_at = %s WHERE token_hash = %s
                """,
                (now, token_hash),
            )
            return _public_row(row)

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
                    INSERT INTO ops.synced_usage (
                        id, account_id, source, vendor, message_id, request_id,
                        project, model, occurred_at, input_tokens, output_tokens,
                        cache_read_tokens, cache_creation_tokens,
                        cache_creation_5m_tokens, cache_creation_1h_tokens,
                        cost_usd, billed_cents, tier, person, cycle, session_id,
                        agent, skill, effort, payload, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb, %s
                    )
                    ON CONFLICT (account_id, message_id, request_id) DO UPDATE SET
                        source = EXCLUDED.source,
                        vendor = EXCLUDED.vendor,
                        project = EXCLUDED.project,
                        model = EXCLUDED.model,
                        occurred_at = EXCLUDED.occurred_at,
                        input_tokens = EXCLUDED.input_tokens,
                        output_tokens = EXCLUDED.output_tokens,
                        cache_read_tokens = EXCLUDED.cache_read_tokens,
                        cache_creation_tokens = EXCLUDED.cache_creation_tokens,
                        cache_creation_5m_tokens = EXCLUDED.cache_creation_5m_tokens,
                        cache_creation_1h_tokens = EXCLUDED.cache_creation_1h_tokens,
                        cost_usd = EXCLUDED.cost_usd,
                        billed_cents = EXCLUDED.billed_cents,
                        tier = EXCLUDED.tier,
                        person = EXCLUDED.person,
                        cycle = EXCLUDED.cycle,
                        session_id = EXCLUDED.session_id,
                        agent = EXCLUDED.agent,
                        skill = EXCLUDED.skill,
                        effort = EXCLUDED.effort
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
                conn.execute(
                    """
                    INSERT INTO ops.synced_invoices (
                        id, account_id, vendor, cycle, person, usd_cents, source,
                        notes, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (account_id, vendor, cycle, person) DO UPDATE SET
                        usd_cents = EXCLUDED.usd_cents,
                        source = EXCLUDED.source,
                        notes = EXCLUDED.notes,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        str(uuid.uuid4()),
                        account_id,
                        vendor,
                        cycle,
                        str(row.get("person") or ""),
                        int(row.get("usd_cents") or row.get("billed_cents") or 0),
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
                    INSERT INTO ops.synced_snapshots (
                        id, account_id, vendor, person, cycle, as_of, billed_cents,
                        cost_usd, tier, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (account_id, vendor, person, cycle, as_of) DO UPDATE SET
                        billed_cents = EXCLUDED.billed_cents,
                        cost_usd = EXCLUDED.cost_usd,
                        tier = EXCLUDED.tier
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
        sql = "SELECT * FROM ops.synced_usage WHERE account_id = %s"
        args: list[Any] = [account_id]
        if month:
            sql += " AND (cycle = %s OR substr(COALESCE(occurred_at::text, ''), 1, 7) = %s)"
            args.extend([month, month])
        sql += " ORDER BY occurred_at ASC"
        with self.connect() as conn:
            return [_public_row(r) or {} for r in conn.execute(sql, args).fetchall()]

    def list_invoices(self, account_id: str, *, month: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM ops.synced_invoices WHERE account_id = %s"
        args: list[Any] = [account_id]
        if month:
            sql += " AND cycle = %s"
            args.append(month)
        with self.connect() as conn:
            return [_public_row(r) or {} for r in conn.execute(sql, args).fetchall()]

    def list_snapshots(self, account_id: str, *, month: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM ops.synced_snapshots WHERE account_id = %s"
        args: list[Any] = [account_id]
        if month:
            sql += " AND cycle = %s"
            args.append(month)
        with self.connect() as conn:
            return [_public_row(r) or {} for r in conn.execute(sql, args).fetchall()]

