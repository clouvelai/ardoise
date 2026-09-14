/**
 * Email OTP + magic-link helpers for /signup. Fetch only — no supabase-js,
 * no Stripe keys.
 *
 * Browser calls same-origin `/ardoise-api/*` (apps/web route). The route
 * forwards to the public Railway API so production marketing is not blocked
 * by the API CORS allow-list. Never put STRIPE_* / SUPABASE_JWT_SECRET here.
 *
 *   requestEmailOtp       → POST {API_BASE}/v1/auth/otp
 *   verifyEmailOtp        → POST {API_BASE}/v1/auth/otp/verify  (typed code)
 *   verifyTokenHash       → POST {API_BASE}/v1/auth/otp/verify  (token_hash)
 *   verifyAuthCode        → POST {API_BASE}/v1/auth/otp/verify  (PKCE code)
 *   sessionFromAccessToken → GET  {API_BASE}/v1/me
 */

import type { AuthRedirect } from "./saas-callback";
import {
  COPY,
  NetworkError,
  detailOf,
  isRecord,
  sparseMessage,
} from "./saas-errors";

export const EARLY_ACCESS_MAILTO =
  "mailto:hello@ardoise.ai?subject=Early%20access";

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

export async function requestEmailOtp(
  email: string,
  options?: { next?: string | null },
): Promise<OtpRequestResult> {
  const trimmed = email.trim().toLowerCase();
  if (!trimmed || !trimmed.includes("@")) {
    throw new Error(COPY.invalidEmail);
  }

  const payload = await postJson("/v1/auth/otp", {
    email: trimmed,
    next: options?.next || undefined,
  });
  if (!isRecord(payload)) {
    throw new OtpNotWiredError();
  }

  return {
    email: typeof payload.email === "string" ? payload.email : trimmed,
    mocked: payload.mocked === true,
    detail: typeof payload.detail === "string" ? payload.detail : undefined,
  };
}

function sessionFromPayload(
  payload: unknown,
  fallbackEmail?: string,
): OtpVerifyResult {
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

  const email =
    (typeof payload.email === "string" && payload.email.trim().toLowerCase()) ||
    fallbackEmail ||
    "";
  if (!email || !email.includes("@")) {
    throw new OtpNotWiredError();
  }

  return { email, accessToken };
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
  return sessionFromPayload(payload, trimmedEmail);
}

export async function verifyTokenHash(
  tokenHash: string,
  type = "email",
): Promise<OtpVerifyResult> {
  const trimmed = tokenHash.trim();
  if (!trimmed) {
    throw new Error(COPY.invalidAuth);
  }
  const payload = await postJson("/v1/auth/otp/verify", {
    token_hash: trimmed,
    type,
  });
  return sessionFromPayload(payload);
}

export async function verifyAuthCode(code: string): Promise<OtpVerifyResult> {
  const trimmed = code.trim();
  if (!trimmed) {
    throw new Error(COPY.invalidAuth);
  }
  const payload = await postJson("/v1/auth/otp/verify", { code: trimmed });
  return sessionFromPayload(payload);
}

async function getJson(path: string, accessToken: string): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "GET",
      headers: { Authorization: `Bearer ${accessToken}` },
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

export async function sessionFromAccessToken(
  accessToken: string,
): Promise<OtpVerifyResult> {
  const trimmed = accessToken.trim();
  if (!trimmed) {
    throw new Error(COPY.invalidAuth);
  }
  const payload = await getJson("/v1/me", trimmed);
  if (!isRecord(payload) || !isRecord(payload.account)) {
    throw new OtpNotWiredError();
  }
  const email =
    typeof payload.account.email === "string"
      ? payload.account.email.trim().toLowerCase()
      : "";
  if (!email || !email.includes("@")) {
    throw new OtpNotWiredError();
  }
  return { email, accessToken: trimmed };
}

export async function sessionFromRedirect(
  parsed: AuthRedirect,
): Promise<OtpVerifyResult> {
  if (parsed.kind === "access_token") {
    return sessionFromAccessToken(parsed.accessToken);
  }
  if (parsed.kind === "token_hash") {
    return verifyTokenHash(parsed.tokenHash, parsed.type);
  }
  if (parsed.kind === "code") {
    return verifyAuthCode(parsed.code);
  }
  if (parsed.kind === "error") {
    throw new Error(parsed.message);
  }
  throw new Error(COPY.invalidAuth);
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
