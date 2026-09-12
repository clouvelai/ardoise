/**
 * Stripe Checkout stays on apps/api. This file only POSTs plan + Bearer JWT.
 * Never put STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET / price IDs here.
 */

import { API_BASE } from "./saas-otp";

export type PaidPlan = "team" | "business";

export class BillingNotWiredError extends Error {
  readonly code = "BILLING_NOT_WIRED" as const;

  constructor(message = "Coming soon — API not wired") {
    super(message);
    this.name = "BillingNotWiredError";
  }
}

export type CheckoutResult = {
  url: string;
  mock: boolean;
  plan: PaidPlan;
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

export async function startCheckout(
  plan: PaidPlan,
  accessToken: string,
): Promise<CheckoutResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/v1/billing/checkout`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        plan,
        success_url: `${window.location.origin}/billing/success`,
        cancel_url: `${window.location.origin}/billing/cancel`,
      }),
    });
  } catch {
    throw new BillingNotWiredError();
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
    throw new BillingNotWiredError();
  }
  if (response.status === 401) {
    throw new Error("Sign in again to continue to checkout");
  }
  if (!response.ok) {
    throw new Error(detailOf(payload, `Checkout failed (${response.status})`));
  }
  if (!isRecord(payload) || typeof payload.url !== "string" || !payload.url) {
    throw new BillingNotWiredError();
  }

  return {
    url: payload.url,
    mock: payload.mock === true,
    plan: payload.plan === "business" ? "business" : "team",
  };
}

export function isBillingNotWired(
  error: unknown,
): error is BillingNotWiredError {
  return error instanceof BillingNotWiredError;
}

export function isPaidPlan(value: string | null | undefined): value is PaidPlan {
  return value === "team" || value === "business";
}
