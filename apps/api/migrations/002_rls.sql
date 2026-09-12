-- RLS-minded notes (Supabase Postgres).
--
-- 1. Keep `ops` off the Data API. In supabase/config.toml (hosted: Dashboard
--    → Settings → API), do not add `ops` to extra_search_path / exposed schemas.
-- 2. ENABLE ROW LEVEL SECURITY on every table even in a private schema
--    (defense in depth). Empty policy set ⇒ no access via roles that are
--    subject to RLS.
-- 3. The FastAPI app uses DATABASE_URL as a privileged role (table owner or
--    service_role) that bypasses RLS. Do not put that URL in the browser.
-- 4. Never GRANT ops to anon or authenticated. Humans talk to FastAPI with a
--    Supabase Auth JWT; the API writes Postgres. Do not authorize from
--    user_metadata (it is user-editable).
-- 5. If you later expose these tables on PostgREST, add policies that match
--    ops.accounts.supabase_sub = auth.uid() — and remember UPDATE needs SELECT.
-- 6. Views bypass RLS unless CREATE VIEW … WITH (security_invoker = true).
-- 7. Phase 1 ~/.ardoise/ledger.db stays local. This schema is not a replica.

ALTER TABLE ops.accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.checkout_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.credit_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.synced_usage ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    REVOKE ALL ON SCHEMA ops FROM PUBLIC;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON SCHEMA ops FROM anon;
        REVOKE ALL ON ALL TABLES IN SCHEMA ops FROM anon;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA ops FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON SCHEMA ops FROM authenticated;
        REVOKE ALL ON ALL TABLES IN SCHEMA ops FROM authenticated;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA ops FROM authenticated;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        GRANT USAGE ON SCHEMA ops TO service_role;
        GRANT ALL ON ALL TABLES IN SCHEMA ops TO service_role;
        GRANT ALL ON ALL SEQUENCES IN SCHEMA ops TO service_role;
    END IF;
END
$$;
