/**
 * Email OTP helpers for /signup. Fetch only — no supabase-js, no Stripe keys.
 *
 *   requestEmailOtp → POST {API_BASE}/v1/auth/otp
 *   verifyEmailOtp  → POST {API_BASE}/v1/auth/otp/verify
 *
 * If the API is down or verify is not configured, helpers throw
 * OtpNotWiredError so the UI can stay a polished “coming soon” stub.
 *
 * Stripe Checkout Sessions stay server-side (apps/api). Never put
 * STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET / SUPABASE_JWT_SECRET here.
 *
 * See apps/api/README.md and docs/saas-scaffold.md.
 */

export const EARLY_ACCESS_MAILTO =
  "mailto:hello@ardoise.ai?subject=Early%20access";

export const ENTERPRISE_MAILTO =
  "mailto:hello@ardoise.ai?subject=Ardoise%20Enterprise";

export const API_BASE =
  process.env.NEXT_PUBLIC_ARDOISE_API_URL ?? "http://127.0.0.1:8787";

export class OtpNotWiredError extends Error {
  readonly code = "OTP_NOT_WIRED" as const;

  constructor(message = "Coming soon — API not wired") {
    super(message);
    this.name = "OtpNotWiredError";
  }
}

export type OtpRequestResult = {
  email: string;
  mocked: boolean;
  detail?: string;
};

export type OtpVerifyResult = {
  email: string;
  accessToken: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function detailOf(payload: unknown, fallback: string): string {
  if (isRecord(payload) && typeof payload.detail === "string" && payload.detail) {
    return payload.detail;
  }
  return fallback;
}

async function postJson(path: string, body: unknown): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new OtpNotWiredError();
  }

  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text };
    }
  }

  if (response.status === 404 || response.status === 501) {
    throw new OtpNotWiredError();
  }

  if (!response.ok) {
    throw new Error(detailOf(payload, `OTP request failed (${response.status})`));
  }

  return payload;
}

export async function requestEmailOtp(email: string): Promise<OtpRequestResult> {
  const trimmed = email.trim().toLowerCase();
  if (!trimmed || !trimmed.includes("@")) {
    throw new Error("Enter a valid email");
  }

  const payload = await postJson("/v1/auth/otp", { email: trimmed });
  if (!isRecord(payload)) {
    throw new OtpNotWiredError();
  }

  return {
    email: typeof payload.email === "string" ? payload.email : trimmed,
    mocked: payload.mocked === true,
    detail: typeof payload.detail === "string" ? payload.detail : undefined,
  };
}

export async function verifyEmailOtp(
  email: string,
  code: string,
): Promise<OtpVerifyResult> {
  const trimmedEmail = email.trim().toLowerCase();
  const trimmedCode = code.trim();
  if (!trimmedEmail || !trimmedEmail.includes("@")) {
    throw new Error("Enter a valid email");
  }
  if (!trimmedCode) {
    throw new Error("Enter the code from your email");
  }

  const payload = await postJson("/v1/auth/otp/verify", {
    email: trimmedEmail,
    token: trimmedCode,
  });
  if (!isRecord(payload)) {
    throw new OtpNotWiredError();
  }

  const accessToken =
    (typeof payload.access_token === "string" && payload.access_token) ||
    (typeof payload.accessToken === "string" && payload.accessToken) ||
    "";
  if (!accessToken) {
    throw new OtpNotWiredError();
  }

  return { email: trimmedEmail, accessToken };
}

export function isOtpNotWired(error: unknown): error is OtpNotWiredError {
  return error instanceof OtpNotWiredError;
}
