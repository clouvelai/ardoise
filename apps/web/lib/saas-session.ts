/**
 * Browser session for OTP + checkout. Access JWT only — no Stripe secrets.
 * sessionStorage so a tab refresh keeps the account; closing the tab signs out.
 */

const KEY = "ardoise.session";

export type SaasSession = {
  email: string;
  accessToken: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function saveSession(session: SaasSession): void {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.setItem(KEY, JSON.stringify(session));
}

export function getSession(): SaasSession | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) {
      return null;
    }
    const parsed: unknown = JSON.parse(raw);
    if (
      !isRecord(parsed) ||
      typeof parsed.email !== "string" ||
      typeof parsed.accessToken !== "string" ||
      !parsed.accessToken
    ) {
      return null;
    }
    return { email: parsed.email, accessToken: parsed.accessToken };
  } catch {
    return null;
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.removeItem(KEY);
}
