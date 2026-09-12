# Ardoise web

Marketing site for Ardoise — a local AI spend ledger.

```bash
npm install
npm run dev
npm run build
```

From the repo root, `npm run build` runs this app via the workspace.

OTP (Supabase email, then JWT to [`apps/api`](../api)) is stubbed in
[`lib/saas-otp.ts`](lib/saas-otp.ts). Landing CTAs stay `#install`.
Do not put Stripe secrets here.
