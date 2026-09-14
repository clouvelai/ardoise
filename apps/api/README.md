# Ardoise API (SaaS scaffold)

Hosted companion for a **later** product. Phase 1 CLI (`bin/ardoise`,
`~/.ardoise/ledger.db`) stays local and is not called from here.

Follows [`docs/saas-scaffold.md`](../../docs/saas-scaffold.md):

| Concern | Pattern |
|---|---|
| Auth | **Account first.** Supabase **email OTP or magic link** via Gotrue HTTP (`POST /v1/auth/otp` + `/verify`). Typed codes and `token_hash` / PKCE `code` land on the same verify route. API verifies `Authorization: Bearer` JWT (HS256 `SUPABASE_JWT_SECRET` when it is a raw secret, otherwise JWKS). Email/`sub` → `ops.accounts.external_key`. No card at signup. No passwords. No supabase-js. |
| Billing | Stripe **Checkout Sessions** `mode=subscription` for Pro ($20/mo) / Team ($49/mo). `POST /v1/billing/checkout` + `/v1/billing/webhook`. Not Connect. Invoice-grade claims are **Pro+**. Legacy `mode=payment` credits stay on `/v1/checkout/sessions`. |
| Mock | Missing Supabase URL or publishable/anon key → OTP mock (verify mints a JWT when `SUPABASE_JWT_SECRET` is a raw HMAC secret). `STRIPE_MOCK=true` **or** missing `STRIPE_SECRET_KEY` → local mock Checkout. |
| Sync | `POST /v1/usage/sync` upserts already-priced `bin/ardoise export` rows plus invoices/snapshots. Never upload `ledger.db`. |

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

**`DATABASE_URL` switches the store.** When it is set, accounts, credits, and
plans live in Postgres (`ops.*` — same tables as `migrations/*.sql`). The API
connects as a privileged role (service connection string); keep `ops` off
PostgREST. When `DATABASE_URL` is unset, the store is SQLite at
`.data/local.db` (local / mock smoke). OTP request/verify talk to Gotrue over
HTTP and do not need the database password. Apply migrations on the Supabase
primary before pointing Railway at that URI.

`GET /health` reports `store: "postgres"` or `"sqlite"` for the backend in
use, plus `store_ok` (a live ping) and `database_url_configured`. It does
not echo the URI. If the URL is set but the ping fails, `ok` / `store_ok`
are false and `store` stays `"postgres"` — there is no silent SQLite fallback.

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
| `GET` | `/health` | no | `store` (`sqlite` / `postgres`), `store_ok`, `database_url_configured`, `stripe_mock`, `lab_auth_bypass`, `supabase_otp_configured` (no secrets, no DSN) |
| `POST` | `/v1/auth/otp` | no | Forwards to `{SUPABASE_URL}/auth/v1/otp` with the publishable/anon (or server-only secret) key. Optional `next` (`/app`, `/pricing`, …) becomes Gotrue `redirect_to={ARDOISE_WEB_ORIGIN}/signup?next=…` so magic links return to the marketing host. Mocked if URL or key unset. |
| `POST` | `/v1/auth/otp/verify` | no | Forwards to `{SUPABASE_URL}/auth/v1/verify` (email+token or `token_hash`) or `/auth/v1/token?grant_type=pkce` (`code`). Creates a **free** account (no card). Mock: mints HS256 JWT when a raw `SUPABASE_JWT_SECRET` is set; otherwise returns “not configured”. |
| `GET` | `/v1/me` | Bearer JWT or `ard_` CLI token | Account + `plan` + `invoice_grade` (Pro+) + credit balance |
| `POST` | `/v1/cli/tokens` | Bearer JWT | Mint opaque `ard_…` token (shown once) |
| `POST` | `/v1/usage/sync` | Bearer JWT or CLI token | Upsert usage / invoices / snapshots. Rejects prompt/credential keys. |
| `GET` | `/v1/usage/status` | Bearer JWT or CLI token | Month summary. Free: estimates. Pro: billed Section A. |
| `GET` | `/v1/usage/statement` | Bearer JWT or CLI token | Markdown + CSV. Invoice-grade on Pro+. |
| `POST` | `/v1/invoices` | Bearer JWT or CLI token | Pro paste-in vendor total |
| `POST` | `/v1/billing/checkout` | Bearer JWT | Pro/Team Checkout Session (`mode=subscription`). Price IDs: `STRIPE_PRICE_PRO` / `STRIPE_PRICE_TEAM`. |
| `POST` | `/v1/billing/webhook` | Stripe signature (live) | Idempotent `checkout.session.completed` (sets plan) |
| `POST` | `/v1/checkout/sessions` | Bearer JWT | Legacy Checkout Session (`mode=payment`) |
| `GET` | `/v1/checkout/mock/{id}` | no | Local stand-in for Stripe Checkout |
| `POST` | `/v1/checkout/mock/{id}/complete` | no | Mock fulfill |
| `POST` | `/v1/stripe/webhook` | Stripe signature (live) | Same fulfill as `/v1/billing/webhook` |

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
| Database → URI | `DATABASE_URL` | When set, Postgres is the system of record (`ops.*`). Unset → SQLite. Not required for Auth OTP |

JWKS fallback: `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`. A JWT-shaped
or `sb_*` value in `SUPABASE_JWT_SECRET` is ignored as an HMAC secret so the
API does not try to HS256-verify with an API key.

## Web CTA

`apps/web` `/signup` accepts a typed code **or** a Supabase magic-link redirect
(`#access_token=…`, `?token_hash=`, `?code=`). `/pricing` Free stays signup-only;
Pro/Team call `/v1/billing/checkout` when a session exists, otherwise
`/signup?plan=`. Helpers: [`apps/web/lib/saas-otp.ts`](../web/lib/saas-otp.ts),
[`saas-callback.ts`](../web/lib/saas-callback.ts),
[`saas-billing.ts`](../web/lib/saas-billing.ts). No Stripe secrets in the client.

### Supabase Auth URLs (deploy)

Dashboard → Authentication → URL Configuration. Magic-link `ConfirmationURL`
hits Gotrue, then redirects to the marketing origin with tokens in the hash
(or `token_hash` / `code` on the query). Those URLs must be allow-listed:

| Setting | Production example |
|---|---|
| Site URL | `https://web-production-ffcebe.up.railway.app` |
| Redirect URLs | `https://web-production-ffcebe.up.railway.app/**` and `http://localhost:3000/**` |
| API `ARDOISE_WEB_ORIGIN` | same marketing origin (no trailing slash) |

The Magic Link email template should keep `{{ .ConfirmationURL }}` (not a
bare `{{ .SiteURL }}`). Include `{{ .Token }}` in the same template if you
still want a typed 6-digit code. PKCE-only templates that put
`token_hash` on the Site URL are supported; implicit `#access_token=` is
the default when `POST /v1/auth/otp` does not send a code challenge.

If you’ll charge US or EU customers, enable [Stripe Tax](https://docs.stripe.com/billing/taxes/collect-taxes)
in the Dashboard after you have an active registration. This API does not set
`automatic_tax`.
