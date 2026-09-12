# Ardoise API (SaaS scaffold)

Hosted companion for a **later** product. Phase 1 CLI (`bin/ardoise`,
`~/.ardoise/ledger.db`) stays local and is not called from here.

Follows [`docs/saas-scaffold.md`](../../docs/saas-scaffold.md):

| Concern | Pattern |
|---|---|
| Auth | Supabase **email OTP** in the browser; API verifies `Authorization: Bearer` JWT (HS256 `SUPABASE_JWT_SECRET` or JWKS). Email/`sub` → `ops.accounts.external_key`. No passwords. No supabase-js on the API. |
| Billing | Stripe **Checkout Sessions** `mode=payment` (not Connect, not subscriptions, not raw PaymentIntents). Persist `ops.checkout_sessions`. Fulfill `checkout.session.completed` idempotently. |
| Mock | `STRIPE_MOCK=true` **or** missing `STRIPE_SECRET_KEY` → local mock session (offline). |
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

Postgres is optional for mock smoke. When `DATABASE_URL` is unset, the API uses
SQLite at `.data/local.db`. Apply `migrations/*.sql` on the Supabase primary
when you stand up a real project.

### Offline smoke

```bash
apps/api/scripts/smoke.sh
# prints SMOKE-OK health+mock-checkout
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
| `GET` | `/health` | no | `stripe_mock`, `lab_auth_bypass` |
| `POST` | `/v1/auth/otp` | no | Forwards to `{SUPABASE_URL}/auth/v1/otp` with the anon key. Mocked if unset. Browser may call Supabase directly instead. |
| `GET` | `/v1/me` | Bearer JWT | Account + credit balance |
| `POST` | `/v1/checkout/sessions` | Bearer JWT | Creates Checkout Session (`mode=payment`), persists row, returns hosted URL |
| `GET` | `/v1/checkout/mock/{id}` | no | Local stand-in for Stripe Checkout |
| `POST` | `/v1/checkout/mock/{id}/complete` | no | Mock fulfill |
| `POST` | `/v1/stripe/webhook` | Stripe signature (live) | Idempotent `checkout.session.completed` |
| `POST` | `/v1/usage/sync` | Bearer JWT | **501 stub** |

Lab bypass (`ARDOISE_LAB_AUTH_BYPASS=true` + `X-Ardoise-Lab-User: email`) is
**off by default** and ignored when `ARDOISE_ENV=production`.

## Env

See [`.env.example`](.env.example). Stripe secrets stay on this process. The
web app may ship `NEXT_PUBLIC_SUPABASE_URL` + anon key only.

## Web CTA

Marketing landing (`apps/web`) keeps on-page `#install` CTAs. OTP wiring
stub: [`apps/web/lib/saas-otp.ts`](../web/lib/saas-otp.ts).
