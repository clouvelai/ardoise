/**
 * Landing CTAs stay on-page (#install). Do not resurrect apps/web/src/.
 *
 * Later (do not block apps/web marketing copy):
 *   1. Browser POST {SUPABASE_URL}/auth/v1/otp with the public anon key
 *      (or POST {API}/v1/auth/otp). No passwords. Minimal fetch is enough —
 *      supabase-js is optional on the client and must not be used on the API.
 *   2. User types the one-time code; Supabase returns an access JWT.
 *   3. Send Authorization: Bearer <jwt> to apps/api (/v1/me, checkout, …).
 *   4. Stripe Checkout Sessions are created server-side. Never put
 *      STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET / SUPABASE_JWT_SECRET here.
 *
 * See apps/api/README.md and docs/saas-scaffold.md.
 */

export const EARLY_ACCESS_MAILTO =
  "mailto:hello@ardoise.ai?subject=Early%20access";

export const API_BASE =
  process.env.NEXT_PUBLIC_ARDOISE_API_URL ?? "http://127.0.0.1:8787";

export async function requestEmailOtp(_email: string): Promise<void> {
  throw new Error(
    "OTP not wired yet — landing CTA stays #install (see EARLY_ACCESS_MAILTO)",
  );
}
