# Postgres migrations

Apply against the Supabase primary (not a replica):

```bash
psql "$DATABASE_URL" -f migrations/001_init.sql
psql "$DATABASE_URL" -f migrations/002_rls.sql
psql "$DATABASE_URL" -f migrations/003_subscriptions.sql
```

Local mock smoke (`STRIPE_MOCK=true` or no `STRIPE_SECRET_KEY`) uses SQLite
and does not need Postgres. Schema is equivalent: `accounts` (incl. `plan`),
`customers`, `checkout_sessions` (incl. `mode` / subscription plan),
`credit_ledger`, `synced_usage`.

See `002_rls.sql` for RLS / Data API notes. Keep `ops` unexposed.
