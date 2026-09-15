/**
 * Sparse, on-brand copy for Railway / FastAPI / Gotrue errors.
 * Never surface raw JSON, supabase blobs, or stack text.
 */

export const COPY = {
  invalidEmail: "Enter a valid email.",
  invalidCode: "That code didn’t work.",
  invalidAuth: "That sign-in link didn’t work.",
  sentMagicLink: "We sent a magic link to",
  openMagicLink: "Check your email and open the link.",
  network: "Can’t reach Ardoise right now.",
  notWired: "Coming soon — API not wired.",
  signIn: "Sign in to continue.",
  rateLimit: "Try again in a moment.",
  generic: "Something went wrong.",
  signingIn: "Signing you in…",
} as const;

export class NetworkError extends Error {
  readonly code = "NETWORK" as const;

  constructor(message = COPY.network) {
    super(message);
    this.name = "NetworkError";
  }
}

export class SessionRequiredError extends Error {
  readonly code = "SESSION_REQUIRED" as const;

  constructor(message = COPY.signIn) {
    super(message);
    this.name = "SessionRequiredError";
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function isNetworkError(error: unknown): error is NetworkError {
  return error instanceof NetworkError;
}

export function isSessionRequired(
  error: unknown,
): error is SessionRequiredError {
  return error instanceof SessionRequiredError;
}

function supabaseBlob(detail: string): Record<string, unknown> | null {
  const start = detail.indexOf("{");
  const end = detail.lastIndexOf("}");
  if (start < 0 || end <= start) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(detail.slice(start, end + 1));
    return isRecord(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function detailOf(payload: unknown, fallback: string): string {
  if (!isRecord(payload)) {
    return fallback;
  }
  const detail = payload.detail;
  if (typeof detail === "string" && detail) {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (isRecord(first) && typeof first.msg === "string" && first.msg) {
      return first.msg;
    }
  }
  if (typeof payload.message === "string" && payload.message) {
    return payload.message;
  }
  return fallback;
}

function looksLikeInternal(detail: string): boolean {
  return (
    detail.includes("{") ||
    /supabase /i.test(detail) ||
    /invalid jwt/i.test(detail) ||
    detail.length > 80
  );
}

export function sparseMessage(
  error: unknown,
  fallback: string = COPY.generic,
): string {
  if (isNetworkError(error)) {
    return COPY.network;
  }
  if (isSessionRequired(error)) {
    return COPY.signIn;
  }
  if (
    isRecord(error) &&
    (error.code === "OTP_NOT_WIRED" || error.code === "BILLING_NOT_WIRED")
  ) {
    return COPY.notWired;
  }

  const raw =
    error instanceof Error && error.message ? error.message : String(error ?? "");
  const blob = supabaseBlob(raw);
  const code =
    (blob && typeof blob.error_code === "string" && blob.error_code) ||
    (blob && typeof blob.code === "string" && blob.code) ||
    "";
  const lower = `${raw} ${code}`.toLowerCase();

  if (
    code === "email_address_invalid" ||
    /valid email/.test(lower) ||
    /email_address_invalid/.test(lower)
  ) {
    return COPY.invalidEmail;
  }
  if (
    code === "otp_expired" ||
    /otp_expired|token has expired|invalid.*code|one-time code|sign-in link/.test(
      lower,
    )
  ) {
    return COPY.invalidAuth;
  }
  if (/429|rate.?limit|over_email_send_rate_limit/.test(lower)) {
    return COPY.rateLimit;
  }
  if (
    /authorization|sign in|empty bearer|invalid jwt|session/.test(lower)
  ) {
    return COPY.signIn;
  }
  if (looksLikeInternal(raw)) {
    return fallback;
  }
  return raw.trim() || fallback;
}

export function safeNextPath(value: string | null | undefined): string | null {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return null;
  }
  if (value.includes("://") || value.includes("\\")) {
    return null;
  }
  const allowed = ["/pricing", "/app", "/app/settings", "/app/statement"];
  if (allowed.includes(value)) {
    return value;
  }
  return null;
}

/** Unauthenticated app routes bounce here so magic-link login can return. */
export function signupHref(next: string | null | undefined): string {
  return `/signup?next=${safeNextPath(next) ?? "/app"}`;
}
