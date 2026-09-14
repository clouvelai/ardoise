-- Hosted ledger: CLI tokens, widened synced usage, invoices, snapshots.
-- Apply after 003_subscriptions.sql:
--   psql "$DATABASE_URL" -f apps/api/migrations/004_sync.sql

ALTER TABLE ops.synced_usage ADD COLUMN IF NOT EXISTS vendor text;
ALTER TABLE ops.synced_usage ADD COLUMN IF NOT EXISTS tier text;
ALTER TABLE ops.synced_usage ADD COLUMN IF NOT EXISTS person text;
ALTER TABLE ops.synced_usage ADD COLUMN IF NOT EXISTS cycle text;
ALTER TABLE ops.synced_usage ADD COLUMN IF NOT EXISTS billed_cents integer;
ALTER TABLE ops.synced_usage ADD COLUMN IF NOT EXISTS cache_creation_5m_tokens integer;
ALTER TABLE ops.synced_usage ADD COLUMN IF NOT EXISTS cache_creation_1h_tokens integer;
ALTER TABLE ops.synced_usage ADD COLUMN IF NOT EXISTS agent text;
ALTER TABLE ops.synced_usage ADD COLUMN IF NOT EXISTS skill text;
ALTER TABLE ops.synced_usage ADD COLUMN IF NOT EXISTS effort text;

CREATE TABLE IF NOT EXISTS ops.cli_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id uuid NOT NULL REFERENCES ops.accounts (id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    prefix text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz
);

CREATE TABLE IF NOT EXISTS ops.synced_invoices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id uuid NOT NULL REFERENCES ops.accounts (id) ON DELETE CASCADE,
    vendor text NOT NULL,
    cycle text NOT NULL,
    person text NOT NULL DEFAULT '',
    usd_cents integer NOT NULL,
    source text NOT NULL DEFAULT 'paste',
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, vendor, cycle, person)
);

CREATE TABLE IF NOT EXISTS ops.synced_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id uuid NOT NULL REFERENCES ops.accounts (id) ON DELETE CASCADE,
    vendor text NOT NULL,
    person text NOT NULL DEFAULT '',
    cycle text NOT NULL,
    as_of text NOT NULL,
    billed_cents integer,
    cost_usd numeric,
    tier text NOT NULL DEFAULT 'T1',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, vendor, person, cycle, as_of)
);

CREATE INDEX IF NOT EXISTS cli_tokens_account_idx ON ops.cli_tokens (account_id);
CREATE INDEX IF NOT EXISTS synced_invoices_account_idx ON ops.synced_invoices (account_id);
CREATE INDEX IF NOT EXISTS synced_snapshots_account_idx ON ops.synced_snapshots (account_id);

ALTER TABLE ops.cli_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.synced_invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.synced_snapshots ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE ops.cli_tokens IS 'Opaque ard_ tokens. Store hash only.';
COMMENT ON TABLE ops.synced_usage IS 'Already-priced usage rows from ardoise export. Never ledger.db.';
