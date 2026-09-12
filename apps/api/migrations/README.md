# Postgres migrations

Apply against the Supabase primary (not a replica):

```bash
psql "$DATABASE_URL" -f migrations/001_init.sql
psql "$DATABASE_URL" -f migrations/002_rls.sql
```

Local mock smoke (`STRIPE_MOCK=true` or no `STRIPE_SECRET_KEY`) uses SQLite
and does not need Postgres. Schema is equivalent: `accounts`, `customers`,
`checkout_sessions`, `credit_ledger`, `synced_usage`.

See `002_rls.sql` for RLS / Data API notes. Keep `ops` unexposed.
