# Ardoise web

Marketing site for Ardoise — a local AI spend ledger.

```bash
npm install
npm run dev
npm run build
```

**Account first, card later.** `/signup` is email OTP (no card). `/pricing`
Free stays signup-only. Pro/Team without a session go to
`/signup?next=/pricing`; after OTP they return to pricing, then
`POST /v1/billing/checkout` (`lib/saas-billing.ts`). Display names are
Pro ($20) / Team ($49); checkout posts `plan=pro|team`.

The browser calls same-origin `/ardoise-api/*` (allow-listed proxy). The
route forwards to `NEXT_PUBLIC_ARDOISE_API_URL`, or Railway in production /
`http://127.0.0.1:8787` in `next dev`. Do not put Stripe or Supabase secrets
here.

```
NEXT_PUBLIC_ARDOISE_API_URL=https://api-production-ea055.up.railway.app
```
