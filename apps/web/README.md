# Ardoise web

Marketing site for Ardoise — a local AI spend ledger.

```bash
npm install
npm run dev
npm run build
```

**Account first, card later.** `/signup` is email OTP or magic link (no card).
A Supabase redirect (`#access_token=…`, `?token_hash=`, or `?code=`) writes
the same `ardoise.session` as a typed code, then routes to `next` or `/app`.
`/pricing` Free stays signup-only. Pro/Team without a session go to
`/signup?next=/pricing`; after sign-in they return to pricing, then
`POST /v1/billing/checkout` (`lib/saas-billing.ts`). Display names are
Pro ($20) / Team ($49); checkout posts `plan=pro|team`.

Allow-list the marketing origin on Supabase Auth → URL Configuration
(Site URL + Redirect URLs, including `/signup` and `/**`). Set
`ARDOISE_WEB_ORIGIN` on the API to that origin so OTP kickoff sends
`redirect_to=/signup`.

The browser calls same-origin `/ardoise-api/*` (allow-listed proxy). The
route forwards to `NEXT_PUBLIC_ARDOISE_API_URL`, or Railway in production /
`http://127.0.0.1:8787` in `next dev`. Do not put Stripe or Supabase secrets
here.

```
NEXT_PUBLIC_ARDOISE_API_URL=https://api-production-ea055.up.railway.app
```
