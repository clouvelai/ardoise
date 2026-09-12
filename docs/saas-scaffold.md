# SaaS scaffold (later)

Ardoise Phase 1 is a **local** ledger. This note records how a hosted companion
would reuse the same account and payment pattern already running in
[Arbusteia](https://github.com/clouvelai/Arbusteia) — it is not an invitation
to import Arbusteia product code.

## Auth: Supabase email OTP + Postgres

Arbusteia humans sign in with **Supabase Auth email OTP**:

1. Browser calls `POST {SUPABASE_URL}/auth/v1/otp` with the public anon key.
2. User types the one-time code; Supabase returns an access JWT.
3. The API verifies `Authorization: Bearer <access_token>` (HS256
   `SUPABASE_JWT_SECRET`, or JWKS from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`).
4. Email (or `sub`) becomes the account `external_key`. Customer rows and the
   credit ledger live in **Postgres** (Supabase primary, not a replica).

A hosted Ardoise would do the same: OTP in the browser, JWT on the API,
Postgres as the system of record. No passwords stored by the app. Lab-only
dev bypass stays off in production.

## Billing: Stripe Checkout Sessions

Arbusteia PAYG uses **Stripe Checkout Sessions** (`mode=payment`), not raw
PaymentIntents:

1. `POST /v1/checkout/sessions` with a resolved Price (`lookup_key`, pin, or
   inline `price_data`).
2. Persist `ops.checkout_session` (`stripe_session_id`, amount, credits).
3. Redirect the human to the hosted Checkout URL.
4. Fulfill on `checkout.session.completed` (webhook) — idempotent credit grant.
5. When `STRIPE_MOCK=true` / no secret key, a local mock session stands in so
   the rest of the stack can be tested offline.

Do not store Stripe secrets in the Ardoise client. A future sync endpoint would
accept **already-priced usage rows** (the same JSONL `export` shape) after OTP,
never prompts or API keys.

## What stays local

Phase 1 does not open a network port, does not call Stripe or Supabase, and
does not upload the SQLite file. `~/.ardoise/ledger.db` is the product.

## Scaffold location

Implementation (not the Phase 1 CLI): [`apps/api`](../apps/api) — FastAPI,
Postgres migrations under `apps/api/migrations/`, local mock when
`STRIPE_MOCK=true` or `STRIPE_SECRET_KEY` is unset. Marketing CTAs on
`apps/web` now hit `/signup` and `/pricing`. OTP remains API-backed via
`apps/web/lib/saas-otp.ts` (`requestEmailOtp` / `verifyEmailOtp` against
`API_BASE`); the form stays a polished stub until that API is live.
