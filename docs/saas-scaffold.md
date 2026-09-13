# SaaS scaffold (later)

Ardoise Phase 1 is a **local** ledger. This note records how a hosted companion
would reuse the same account and payment pattern already running in
[Arbusteia](https://github.com/clouvelai/Arbusteia) — it is not an invitation
to import Arbusteia product code.

## Auth: Supabase email OTP + Postgres

Arbusteia humans sign in with **Supabase Auth email OTP**:

1. Browser calls `POST {SUPABASE_URL}/auth/v1/otp` with the public
   publishable/anon key (`sb_publishable_…` or legacy `eyJ…` JWT).
2. User types the one-time code; Supabase returns an access JWT.
3. The API verifies `Authorization: Bearer <access_token>` (HS256
   `SUPABASE_JWT_SECRET` when it is a raw secret; otherwise JWKS from
   `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` — use JWKS when the
   Dashboard only shows a signing key id).
4. Email (or `sub`) becomes the account `external_key`. Customer rows and the
   credit ledger live in **Postgres** (Supabase primary, not a replica) when
   `DATABASE_URL` is set. Auth OTP itself does not need the database password.

A hosted Ardoise does the same: OTP through `apps/api` (`POST /v1/auth/otp`
and `/v1/auth/otp/verify`), JWT on later calls, Postgres as the system of
record. **Account first, card later** — verify creates a free account with no
card. No passwords stored by the app. Lab-only dev bypass stays off in
production. Missing Supabase keys keep a mock/stub path so local smoke works.

## Billing: Stripe Checkout Sessions

Team ($39/mo) and Business ($149/mo) use **Stripe Checkout Sessions**
(`mode=subscription`), not Connect, not raw PaymentIntents:

1. `POST /v1/billing/checkout` with `plan=team|business` after OTP.
2. Resolve `STRIPE_PRICE_TEAM` / `STRIPE_PRICE_BUSINESS` (or inline monthly
   `price_data`). Persist `ops.checkout_sessions`.
3. Redirect the human to the hosted Checkout URL (`apps/web` success/cancel).
4. Fulfill on `checkout.session.completed` (`POST /v1/billing/webhook`) —
   sets `accounts.plan`. Invoice-grade claims stay **Business+**.
5. When `STRIPE_MOCK=true` / no secret key, a local mock session stands in.

Legacy PAYG credits remain on `POST /v1/checkout/sessions` (`mode=payment`).

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
`apps/web` hit `/signup` and `/pricing`. OTP is API-backed via
`apps/web/lib/saas-otp.ts`; paid CTAs call `lib/saas-billing.ts` only when a
session exists. If the API is down the form stays a polished stub.
