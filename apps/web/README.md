# Ardoise web

Marketing site for Ardoise — a local AI spend ledger.

```bash
npm install
npm run dev
npm run build
```

From the repo root, `npm run build` runs this app via the workspace.

**Account first, card later.** `/signup` is email OTP (no card). `/pricing`
Free stays signup-only; Team/Business call `POST /v1/billing/checkout` after
a session exists (`lib/saas-billing.ts`). Helpers: [`lib/saas-otp.ts`](lib/saas-otp.ts)
(`requestEmailOtp` / `verifyEmailOtp` → `API_BASE`). If the API is down the
UI stays a polished stub. Do not put Stripe secrets here.

```
NEXT_PUBLIC_ARDOISE_API_URL=http://127.0.0.1:8787
```
