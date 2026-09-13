/**
 * Email OTP helpers for /signup. Fetch only — no supabase-js, no Stripe keys.
 *
 * Browser calls same-origin `/ardoise-api/*` (apps/web route). The route
 * forwards to the public Railway API so production marketing is not blocked
 * by the API CORS allow-list. Never put STRIPE_* / SUPABASE_JWT_SECRET here.
 *
 *   requestEmailOtp → POST {API_BASE}/v1/auth/otp
 *   verifyEmailOtp  → POST {API_BASE}/v1/auth/otp/verify
 */

import {
  COPY,
  NetworkError,
  detailOf,
  isRecord,
  sparseMessage,
} from "./saas-errors";

export const EARLY_ACCESS_MAILTO =
  "mailto:hello@ardoise.ai?subject=Early%20access";

export const ENTERPRISE_MAILTO =
  "mailto:hello@ardoise.ai?subject=Ardoise%20Enterprise";

const PRODUCTION_API_URL = "https://api-production-ea055.up.railway.app";
const LOCAL_API_URL = "http://127.0.0.1:8787";

/** Upstream the Next route proxies to. Public URL only — not a secret. */
export const API_UPSTREAM =
  process.env.NEXT_PUBLIC_ARDOISE_API_URL ??
  (process.env.NODE_ENV === "development" ? LOCAL_API_URL : PRODUCTION_API_URL);

/** Same-origin prefix used by the browser. */
export const API_BASE = "/ardoise-api";

export class OtpNotWiredError extends Error {
  readonly code = "OTP_NOT_WIRED" as const;

  constructor(message = COPY.notWired) {
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

async function postJson(path: string, body: unknown): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new NetworkError();
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
    throw new Error(COPY.invalidEmail);
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
    throw new Error(COPY.invalidEmail);
  }
  if (!trimmedCode) {
    throw new Error(COPY.invalidCode);
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

export function otpMessage(error: unknown): string {
  if (isOtpNotWired(error)) {
    return COPY.notWired;
  }
  return sparseMessage(error);
}
