-- Pro / Team subscriptions (account first, card later).
-- Apply after 001_init.sql + 002_rls.sql:
--   psql "$DATABASE_URL" -f apps/api/migrations/003_subscriptions.sql

ALTER TABLE ops.accounts
    ADD COLUMN IF NOT EXISTS plan text NOT NULL DEFAULT 'free';

ALTER TABLE ops.checkout_sessions
    ADD COLUMN IF NOT EXISTS mode text NOT NULL DEFAULT 'payment';

ALTER TABLE ops.checkout_sessions
    ADD COLUMN IF NOT EXISTS plan text;

ALTER TABLE ops.checkout_sessions
    ADD COLUMN IF NOT EXISTS stripe_subscription_id text;

COMMENT ON COLUMN ops.accounts.plan IS
    'free | pro | team. Invoice-grade claims are Pro+ only.';
COMMENT ON TABLE ops.checkout_sessions IS
    'Stripe Checkout Sessions. mode=payment (legacy credits) or mode=subscription (Pro/Team). Fulfill on checkout.session.completed.';
