-- Ardoise hosted companion (scaffold).
-- System of record: Postgres (Supabase primary, not a replica).
-- The FastAPI process uses DATABASE_URL. Do not expose ops on PostgREST.
--
-- Apply:
--   psql "$DATABASE_URL" -f apps/api/migrations/001_init.sql
--   psql "$DATABASE_URL" -f apps/api/migrations/002_rls.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    external_key text NOT NULL UNIQUE,
    email text,
    supabase_sub text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.customers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id uuid NOT NULL UNIQUE REFERENCES ops.accounts (id) ON DELETE CASCADE,
    stripe_customer_id text UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.checkout_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id uuid REFERENCES ops.accounts (id) ON DELETE SET NULL,
    stripe_session_id text NOT NULL UNIQUE,
    amount_cents integer NOT NULL,
    credits integer NOT NULL,
    currency text NOT NULL DEFAULT 'usd',
    status text NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'completed', 'expired')),
    checkout_url text,
    fulfilled_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.credit_ledger (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id uuid NOT NULL REFERENCES ops.accounts (id) ON DELETE CASCADE,
    amount integer NOT NULL,
    reason text NOT NULL,
    checkout_session_id uuid UNIQUE REFERENCES ops.checkout_sessions (id),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Stub only. Future POST /v1/usage/sync accepts already-priced JSONL
-- (same shape as `bin/ardoise export`) after OTP. Never prompts, API keys,
-- or ~/.ardoise/ledger.db.
CREATE TABLE IF NOT EXISTS ops.synced_usage (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
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
);

CREATE INDEX IF NOT EXISTS checkout_sessions_account_idx
    ON ops.checkout_sessions (account_id);
CREATE INDEX IF NOT EXISTS credit_ledger_account_idx
    ON ops.credit_ledger (account_id);
CREATE INDEX IF NOT EXISTS synced_usage_account_idx
    ON ops.synced_usage (account_id);

COMMENT ON SCHEMA ops IS 'Ardoise API system of record. Not a PostgREST exposure.';
COMMENT ON TABLE ops.checkout_sessions IS 'Stripe Checkout Sessions (mode=payment). Fulfill on checkout.session.completed.';
COMMENT ON TABLE ops.synced_usage IS 'Scaffold stub. Do not upload ledger.db.';
