# Ardoise API (SaaS scaffold)

Hosted companion for a **later** product. Phase 1 CLI (`bin/ardoise`,
`~/.ardoise/ledger.db`) stays local and is not called from here.

Follows [`docs/saas-scaffold.md`](../../docs/saas-scaffold.md):

| Concern | Pattern |
|---|---|
| Auth | **Account first.** Supabase **email OTP** via Gotrue HTTP (`POST /v1/auth/otp` + `/verify`). API verifies `Authorization: Bearer` JWT (HS256 `SUPABASE_JWT_SECRET` when it is a raw secret, otherwise JWKS). Email/`sub` → `ops.accounts.external_key`. No card at signup. No passwords. No supabase-js. |
| Billing | Stripe **Checkout Sessions** `mode=subscription` for Team ($39/mo) / Business ($149/mo). `POST /v1/billing/checkout` + `/v1/billing/webhook`. Not Connect. Invoice-grade claims are **Business+**. Legacy `mode=payment` credits stay on `/v1/checkout/sessions`. |
| Mock | Missing Supabase URL or publishable/anon key → OTP mock (verify mints a JWT when `SUPABASE_JWT_SECRET` is a raw HMAC secret). `STRIPE_MOCK=true` **or** missing `STRIPE_SECRET_KEY` → local mock Checkout. |
| Sync | Stub only. Future `POST /v1/usage/sync` accepts already-priced JSONL (`bin/ardoise export`) after OTP. Never upload `ledger.db`. |

## Run locally with mocks

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # leave STRIPE_MOCK=true, leave Stripe/Supabase secrets empty
# optional: export SUPABASE_JWT_SECRET=dev-secret  # so you can mint a local JWT

python -m ardoise_api
# http://127.0.0.1:8787/health
```

Postgres is optional for mock smoke **and** for Auth OTP e2e. OTP request/verify
talk to Gotrue over HTTP; they do not need `DATABASE_URL` or the database
password. When `DATABASE_URL` is unset, accounts live in SQLite at
`.data/local.db`. When `DATABASE_URL` is set, the process connects to Postgres
(`ops.*`) and **refuses to start** if the URL is unreachable — there is no
silent SQLite fallback. Force SQLite with `ARDOISE_API_STORE=sqlite`.
`GET /health` reports `store` (`sqlite` or `postgres`) and
`database_url_configured`. After a Railway deploy with a valid `DATABASE_URL`,
expect `"store": "postgres"`. The app applies the `ops` tables on first
connect (same shape as `migrations/001_init.sql` + `003_subscriptions.sql`).

### Offline smoke

```bash
apps/api/scripts/smoke.sh
# prints SMOKE-OK health+mock-checkout+otp+billing
```

### Mint a local JWT (mock OTP)

```bash
python3 - <<'PY'
import time, jwt, os
secret = os.environ.get("SUPABASE_JWT_SECRET", "dev-secret")
print(jwt.encode({
    "aud": "authenticated", "role": "authenticated",
    "sub": "user-local", "email": "you@example.com",
    "iss": "https://example.supabase.co/auth/v1",
    "exp": int(time.time()) + 3600,
}, secret, algorithm="HS256"))
PY

curl -s http://127.0.0.1:8787/health
curl -s -X POST http://127.0.0.1:8787/v1/checkout/sessions \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}'
# → { "url": "http://127.0.0.1:8787/v1/checkout/mock/cs_mock_…", "mock": true }
```

Open the mock URL and click **Pay (mock)**, or `POST /v1/stripe/webhook` with
`{"type":"checkout.session.completed","data":{"object":{"id":"cs_mock_…"}}}`
(signature skipped while mock is on).

## Routes

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/health` | no | `store` (`sqlite` / `postgres`), `database_url_configured`, `stripe_mock`, `lab_auth_bypass`, `supabase_otp_configured` (no secrets) |
| `POST` | `/v1/auth/otp` | no | Forwards to `{SUPABASE_URL}/auth/v1/otp` with the publishable/anon (or server-only secret) key. Accepts legacy `eyJ…` JWTs and `sb_publishable_…` / `sb_secret_…`. Mocked if URL or key unset. |
| `POST` | `/v1/auth/otp/verify` | no | Forwards to `{SUPABASE_URL}/auth/v1/verify`. Creates a **free** account (no card). Mock: mints HS256 JWT when a raw `SUPABASE_JWT_SECRET` is set; otherwise returns “not configured”. |
| `GET` | `/v1/me` | Bearer JWT | Account + `plan` + `invoice_grade` (Business+) + credit balance |
| `POST` | `/v1/billing/checkout` | Bearer JWT | Team/Business Checkout Session (`mode=subscription`). Price IDs: `STRIPE_PRICE_TEAM` / `STRIPE_PRICE_BUSINESS`. |
| `POST` | `/v1/billing/webhook` | Stripe signature (live) | Idempotent `checkout.session.completed` (sets plan) |
| `POST` | `/v1/checkout/sessions` | Bearer JWT | Legacy Checkout Session (`mode=payment`) |
| `GET` | `/v1/checkout/mock/{id}` | no | Local stand-in for Stripe Checkout |
| `POST` | `/v1/checkout/mock/{id}/complete` | no | Mock fulfill |
| `POST` | `/v1/stripe/webhook` | Stripe signature (live) | Same fulfill as `/v1/billing/webhook` |
| `POST` | `/v1/usage/sync` | Bearer JWT | **501 stub** |

Lab bypass (`ARDOISE_LAB_AUTH_BYPASS=true` + `X-Ardoise-Lab-User: email`) is
**off by default** and ignored when `ARDOISE_ENV=production`.

## Env

See [`.env.example`](.env.example). Stripe secrets stay on this process. The
web app may ship `NEXT_PUBLIC_SUPABASE_URL` + publishable/anon key only.

### Dashboard → env (Ardoise project only)

Live Auth project ref `yokxvbgzcoaayahouhsd` (not Arbusteia). Copy values into
the **host secret store** or local `.env` — never commit them.

| Dashboard | Env var(s) | Notes |
|---|---|---|
| Project Settings → Data API → Project URL | `SUPABASE_URL` | `https://yokxvbgzcoaayahouhsd.supabase.co` |
| API Keys → Publishable (`sb_publishable_…`) | `SUPABASE_ANON_KEY` **or** `SUPABASE_PUBLISHABLE_KEY` | Preferred for OTP (`apikey` header) |
| API Keys → Legacy anon JWT (`eyJ…`) | `SUPABASE_ANON_KEY` | Same slot as publishable |
| API Keys → Secret (`sb_secret_…`) | `SUPABASE_SERVICE_ROLE_KEY` **or** `SUPABASE_SECRET_KEY` | Server-only fallback. Never send to `apps/web` |
| API Keys → Legacy service_role JWT | `SUPABASE_SERVICE_ROLE_KEY` | Same slot as secret |
| JWT Keys → JWT Secret (HS256) | `SUPABASE_JWT_SECRET` | Optional. Skip if the Dashboard only shows a signing **key id** — verify via JWKS |
| Database → URI | `DATABASE_URL` | Optional locally. When set, `/health` `store` must be `postgres` |

JWKS fallback: `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`. A JWT-shaped
or `sb_*` value in `SUPABASE_JWT_SECRET` is ignored as an HMAC secret so the
API does not try to HS256-verify with an API key.

## Web CTA

`apps/web` `/signup` is email OTP (no card). `/pricing` Free stays signup-only;
Team/Business call `/v1/billing/checkout` when a session exists, otherwise
`/signup?plan=`. Helpers: [`apps/web/lib/saas-otp.ts`](../web/lib/saas-otp.ts),
[`saas-billing.ts`](../web/lib/saas-billing.ts). No Stripe secrets in the client.

If you’ll charge US or EU customers, enable [Stripe Tax](https://docs.stripe.com/billing/taxes/collect-taxes)
in the Dashboard after you have an active registration. This API does not set
`automatic_tax`.
