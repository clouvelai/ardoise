# Ardoise web

Marketing site for Ardoise — a local AI spend ledger.

```bash
npm install
npm run dev
npm run build
```

From the repo root, `npm run build` runs this app via the workspace.

OTP helpers live in [`lib/saas-otp.ts`](lib/saas-otp.ts)
(`requestEmailOtp` / `verifyEmailOtp` → `API_BASE`). Marketing CTAs go to
`/signup` and `/pricing`. OTP stays API-backed. Do not put Stripe secrets here.
